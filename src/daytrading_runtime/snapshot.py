"""Live evidence wiring for E1/E2/E3 (spec sections 14-19, 30, 41). Builds
SMCConditionResult objects from live MT5 data using ONLY existing capabilities:
supply_demand.fair_value_gaps_for (D1 gaps), supply_demand.order_blocks_for (H1 POI
inventory), liquidity.liquidity_result (M15 sweep levels), and
entry_confirmation.gap.evaluate_gap_context's own already-signed touch/reaction
semantics. This module does not add a new gap/POI/reaction rule -- the only "new" logic
is the mechanical loop that finds which already-fetched candle intersects an
already-computed gap (gap.py's own `_intersects` test, applied across a series instead
of a single caller-supplied candle), so gap.py can be called the way it already expects.

E2 runs the deterministic E2_H1_POI_REACTION_V1 model
(entry_confirmation.e2_h1_poi_reaction.evaluate_e2_h1_poi_reaction) instead of always
asserting poi_reacted=None -- that model itself fails closed (WAITING_POI/
WAITING_REACTION/INVALIDATED) whenever the causal chain (H1 POI touch -> qualifying M5
reaction candle) isn't fully evidenced; it never fabricates a reaction. Location +
reaction only (SMC_ENTRY_MODELS_V1's E2 half) -- see build_e2_result's own docstring for
what the deeper M2 confirmation still needs before it can be wired here too.

Fails closed on any MarketDataError (spec section 30): a fetch failure yields an
INDETERMINATE condition, never a fabricated trigger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from entry_confirmation.e2_h1_poi_reaction import E2PoiReactionRequest, evaluate_e2_h1_poi_reaction
from entry_confirmation.gap import evaluate_gap_context, gap_midpoint
from entry_confirmation.models import CandidateDirection
from liquidity.analyzer import liquidity_result
from mt5.market_data import MarketDataError, get_latest_candles
from smc_watcher.conditions import evaluate_e1_condition, evaluate_e2_condition, evaluate_e3_condition
from smc_watcher.models import CONDITION_TYPE_DAILY_GAP_REACTION, SMCConditionResult, STATE_INDETERMINATE
from supply_demand.analyzer import fair_value_gaps_for, order_blocks_for
from supply_demand.models import ZoneStatus

D1_GAP_LOOKBACK_CANDLES = 60
D1_REACTION_HISTORY_CANDLES = 25
H1_POI_LOOKBACK_CANDLES = 50
M5_LOOKBACK_CANDLES = 200


def _indeterminate(condition_id: str, condition_type: str, reason_code: str) -> SMCConditionResult:
    return SMCConditionResult(
        condition_id=condition_id, condition_type=condition_type, state=STATE_INDETERMINATE,
        reason_codes=(reason_code,),
    )


def _latest_active_zone(zones):
    active = [z for z in zones if z.status != ZoneStatus.INVALIDATED]
    if not active:
        return None
    return max(active, key=lambda z: z.origin_time or datetime.min)


def build_e1_result(symbol: str) -> SMCConditionResult:
    from smc_watcher.models import CONDITION_E1

    try:
        gap_query = fair_value_gaps_for(symbol, "D1", count=D1_GAP_LOOKBACK_CANDLES)
        if gap_query.status != "OK":
            return _indeterminate(CONDITION_E1, CONDITION_TYPE_DAILY_GAP_REACTION, gap_query.status)
        d1_candles = get_latest_candles(symbol, "D1", D1_GAP_LOOKBACK_CANDLES)
    except MarketDataError as exc:
        return _indeterminate(CONDITION_E1, CONDITION_TYPE_DAILY_GAP_REACTION, exc.reason_code)

    zone = _latest_active_zone(gap_query.zones)
    if zone is None or zone.low is None or zone.high is None:
        return evaluate_e1_condition(None)

    after_origin = [c for c in d1_candles if zone.origin_time is None or c.time > zone.origin_time]
    touch_candle = next((c for c in after_origin if c.low <= zone.high and c.high >= zone.low), None)
    reaction_candle = None
    reaction_history: Tuple = ()
    if touch_candle is not None:
        idx = after_origin.index(touch_candle)
        following = after_origin[idx + 1:]
        reaction_candle = following[0] if following else None
        reaction_history = tuple(d1_candles[:D1_REACTION_HISTORY_CANDLES])

    direction = CandidateDirection.LONG if gap_midpoint(zone.low, zone.high) is not None and (
        touch_candle is not None and touch_candle.close < gap_midpoint(zone.low, zone.high)
    ) else CandidateDirection.SHORT

    gap_context = evaluate_gap_context(zone, touch_candle, reaction_candle, reaction_history, direction)
    return evaluate_e1_condition(gap_context)


def build_e2_result(symbol: str) -> SMCConditionResult:
    """Runs the real E2_H1_POI_REACTION_V1 model (entry_confirmation.
    e2_h1_poi_reaction) against live H1 POI inventory + M5 reaction evidence, then feeds
    its verdict into evaluate_e2_condition's existing fail-closed contract (unchanged).

    Location + reaction only (SMC_ENTRY_MODELS_V1's E2 half) -- the deeper M2
    (SUPPLY_DEMAND_SHIFT) confirmation this used to delegate to (via the sweep-shift
    pipeline, now correctly re-homed to M3) is NOT wired into the live runtime by this
    pass; it needs an M5 opposing-zone feed this snapshot module does not yet fetch. See
    entry_confirmation.m2_supply_demand_shift for the standalone, tested engine."""
    from smc_watcher.models import CONDITION_E2, CONDITION_TYPE_H1_POI_REACTION
    from entry_confirmation.poi import evaluate_poi_context

    try:
        ob_query = order_blocks_for(symbol, "H1")
        h1_candles = get_latest_candles(symbol, "H1", H1_POI_LOOKBACK_CANDLES)
    except MarketDataError as exc:
        return _indeterminate(CONDITION_E2, CONDITION_TYPE_H1_POI_REACTION, exc.reason_code)
    if ob_query.status != "OK":
        return _indeterminate(CONDITION_E2, CONDITION_TYPE_H1_POI_REACTION, ob_query.status)

    zone = _latest_active_zone(ob_query.zones)
    if zone is None:
        return evaluate_e2_condition(None)

    poi_context = evaluate_poi_context(zone)

    try:
        m5_candles = get_latest_candles(symbol, "M5", M5_LOOKBACK_CANDLES)
    except MarketDataError as exc:
        return _indeterminate(CONDITION_E2, CONDITION_TYPE_H1_POI_REACTION, exc.reason_code)

    now = m5_candles[-1].time if m5_candles else None
    reaction = evaluate_e2_h1_poi_reaction(E2PoiReactionRequest(
        symbol=symbol, h1_poi_zone=zone, h1_candles=h1_candles,
        m5_candles=m5_candles, m5_displacement_history=m5_candles, evaluation_time=now,
    ))

    poi_reacted = reaction.eligible_for_confirmation
    poi_reaction_time = reaction.reaction_time if poi_reacted else None
    return evaluate_e2_condition(poi_context, poi_reaction_time=poi_reaction_time, poi_reacted=poi_reacted)


def build_e3_results(symbol: str, timeframe: str = "M15") -> Tuple[SMCConditionResult, SMCConditionResult]:
    from smc_watcher.models import CONDITION_E3, CONDITION_TYPE_LIQUIDITY_SWEEP

    try:
        result = liquidity_result(symbol, timeframe)
    except MarketDataError as exc:
        indeterminate = _indeterminate(CONDITION_E3, CONDITION_TYPE_LIQUIDITY_SWEEP, exc.reason_code)
        return indeterminate, indeterminate
    if result.status != "LIQUIDITY_OK":
        indeterminate = _indeterminate(CONDITION_E3, CONDITION_TYPE_LIQUIDITY_SWEEP, result.status)
        return indeterminate, indeterminate

    return evaluate_e3_condition(result.nearest_buy_side), evaluate_e3_condition(result.nearest_sell_side)


@dataclass(frozen=True)
class SymbolSMCSnapshot:
    symbol: str
    e1: SMCConditionResult
    e2: SMCConditionResult
    e3_buy_side: SMCConditionResult
    e3_sell_side: SMCConditionResult


def build_symbol_snapshot(symbol: str) -> SymbolSMCSnapshot:
    e3_buy, e3_sell = build_e3_results(symbol)
    return SymbolSMCSnapshot(
        symbol=symbol, e1=build_e1_result(symbol), e2=build_e2_result(symbol),
        e3_buy_side=e3_buy, e3_sell_side=e3_sell,
    )
