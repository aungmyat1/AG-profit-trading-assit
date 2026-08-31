"""True Stage-2 entry-only replay (historical-validation continuation, two-stage
architecture phase). Consumes already-qualified `Stage1Event`s and calls ONLY
M1/M2/M3 + the composer (`compose_conditional_entry_analysis`, already the pure
Stage-2 boundary function in daytrading_runtime.conditional_entry_snapshot -- not
rewritten here) -- never E1/E2/E3 evaluators, never D1/H1 discovery
(fair_value_gaps_for(D1), order_blocks_for(H1), liquidity_result(H1)).

COUPLING FINDING (this phase's audit): M3's `liquidity_level` parameter and E3's own
eligibility check are literally the SAME liquidity_result(symbol,"H1") call and the
SAME LiquidityLevel object (conditional_entry_snapshot.py:356-359 feeds both its own
E3 evaluation at :214-215 and M3's parameter at :254). A true Stage-2 boundary for
E3-paired combinations therefore requires the qualifying LiquidityLevel to travel WITH
the Stage-1 event, not be re-derived from H1 discovery in Stage 2.

M3_LIQUIDITY_FIELDS_USED (audited from evaluate_m3_sweep_drop_pump and everything it
calls -- engine_v2_1.evaluate_reversal_sweep_shift, route.py): side, price, source,
sweep_time, reclaim_time. `Stage1LiquidityReference` persists exactly these plus the
minimal structural fields (symbol, timeframe, origin_time, status) LiquidityLevel's
dataclass constructor requires but M3's own evaluation path never reads.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Dict, Optional, Sequence, Tuple

from daytrading_runtime.conditional_entry_snapshot import M5_LOOKBACK_CANDLES
from entry_confirmation import (
    EConditionResult,
    SMCConditionalEntryAnalysis,
    evaluate_m1_character_change_with_inducement,
    evaluate_m2_supply_demand_shift,
    evaluate_m3_sweep_drop_pump,
)
from entry_confirmation.composer import compose
from liquidity.hierarchy import (
    InducementCandidate,
    external_swing_liquidity,
    find_inducement_candidates,
    scope_liquidity_levels,
)
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure.tiers import analyze_structure_tiers
from mt5.market_data import MarketDataError, get_latest_candles, get_tick
from supply_demand import ValidatedOrderBlock, ZoneResult
from supply_demand.analyzer import fair_value_gaps_for, validated_order_blocks_for
from supply_demand.ob_contract import OBValidationStatus
from supply_demand.models import ZoneRole, ZoneStatus

from .candle_store import HistoricalCandleStore, HistoricalDataError
from .data_source_patch import historical_data_context
from .orchestrator import Stage1Event

_INDUCEMENT_SIDE_FOR_DIRECTION = {"SHORT": LiquiditySide.BUY_SIDE, "LONG": LiquiditySide.SELL_SIDE}
_OPPOSING_ROLE_FOR_DIRECTION = {"SHORT": ZoneRole.DEMAND, "LONG": ZoneRole.SUPPLY}
_OB_STATUS_TO_ZONE_STATUS = {
    OBValidationStatus.VALID: ZoneStatus.FRESH, OBValidationStatus.MITIGATED: ZoneStatus.MITIGATED,
    OBValidationStatus.INVALIDATED: ZoneStatus.INVALIDATED,
}


@dataclass(frozen=True)
class Stage1LiquidityReference:
    """Serializable stand-in for a `liquidity.models.LiquidityLevel` -- carries only
    what M3's own evaluation path reads (side/price/source/sweep_time/reclaim_time)
    plus the minimal fields the LiquidityLevel dataclass constructor requires
    (symbol/timeframe/origin_time/status), which M3 never reads. See module docstring."""
    symbol: str
    timeframe: str
    side: str  # LiquiditySide.value
    source: str
    price: float
    origin_time: Optional[datetime]
    status: str  # LiquidityStatus.value
    sweep_time: Optional[datetime]
    reclaim_time: Optional[datetime]

    @classmethod
    def from_liquidity_level(cls, level: LiquidityLevel) -> "Stage1LiquidityReference":
        return cls(symbol=level.symbol, timeframe=level.timeframe, side=level.side.value,
                    source=level.source, price=level.price, origin_time=level.origin_time,
                    status=level.status.value, sweep_time=level.sweep_time, reclaim_time=level.reclaim_time)

    def to_liquidity_level(self) -> LiquidityLevel:
        return LiquidityLevel(symbol=self.symbol, timeframe=self.timeframe, side=LiquiditySide(self.side),
                               source=self.source, price=self.price, origin_time=self.origin_time,
                               status=LiquidityStatus(self.status), sweep_time=self.sweep_time,
                               reclaim_time=self.reclaim_time)


def enrich_e3_events_with_liquidity(store: HistoricalCandleStore, symbol: str,
                                    events: Sequence[Stage1Event]) -> Tuple[Stage1Event, ...]:
    """One-time Stage-1 enrichment pass (spec source phase 7): for each E3 event, fetch
    the real LiquidityLevel that was active at its qualification_time (a single
    liquidity_result(H1) call per event -- NOT a full replay), matching the event's own
    recorded direction, and attach it as a Stage1LiquidityReference. Non-E3 events pass
    through unchanged."""
    from liquidity.analyzer import liquidity_result

    out = []
    for e in events:
        if e.entry_condition != "E3":
            out.append(e)
            continue
        with historical_data_context(store, e.qualification_time):
            result = liquidity_result(symbol, "H1")
        # SHORT <- buy-side swept (per conditional_entry_snapshot.py:254); LONG <- sell-side.
        level = result.nearest_buy_side if e.direction == "SHORT" else result.nearest_sell_side
        ref = Stage1LiquidityReference.from_liquidity_level(level) if level is not None else None
        out.append(replace(e, liquidity_reference=ref))
    return tuple(out)


def _parse_reference_key(reference_key: Optional[str]):
    """Inverse of proposals.identity.reference_key_for: recovers
    (reference_type, reference_low, reference_high, reference_level) from the exact
    "TYPE|low|high|level" string it produces, so setup_id identity (spec section 4-5
    of the identity-repair phase) can be reconstructed without re-running E discovery.
    Returns (None, None, None, None) if reference_key is None (matches
    reference_key_for's own "nothing to disambiguate on" case)."""
    if reference_key is None:
        return None, None, None, None
    raw_type, raw_low, raw_high, raw_level = reference_key.split("|", 3)
    reference_type = None if raw_type == "NONE" else raw_type

    def _num(raw: str) -> Optional[float]:
        return None if raw == "None" else float(raw)

    return reference_type, _num(raw_low), _num(raw_high), _num(raw_level)


def _m5_side_primitives(symbol: str, current_price: Optional[float]):
    """M5-only primitives M1/M2/M3 consume -- fetched fresh at each replay step, same
    functions the live entrypoint uses for its M5-side inputs (conditional_entry_
    snapshot.py:365-412), never D1/H1. Mirrors that logic exactly; not a reimplementation."""
    m5_candles = tuple(get_latest_candles(symbol, "M5", M5_LOOKBACK_CANDLES))

    m5_fvg_zones: Tuple[ZoneResult, ...] = ()
    try:
        q = fair_value_gaps_for(symbol, "M5")
        if q.status == "OK":
            m5_fvg_zones = q.zones
    except MarketDataError:
        pass

    m5_validated_order_blocks: Tuple[ValidatedOrderBlock, ...] = tuple(validated_order_blocks_for(symbol, "M5"))
    m5_candidate_zones = tuple(
        replace(v.candidate, status=_OB_STATUS_TO_ZONE_STATUS[v.status])
        for v in m5_validated_order_blocks if v.status in _OB_STATUS_TO_ZONE_STATUS and v.candidate is not None
    )

    inducement_candidates: Tuple[InducementCandidate, ...] = ()
    try:
        from liquidity.analyzer import liquidity_result as _m5_liquidity_result  # M5, not H1 -- M-side only
        tiers = analyze_structure_tiers(symbol, "M5")
        m5_liq = _m5_liquidity_result(symbol, "M5")
        if tiers.status == "VALID" and tiers.external is not None and m5_liq.status == "LIQUIDITY_OK":
            externals = external_swing_liquidity(symbol, "M5", tiers.external, m5_candles) if m5_candles else ()
            scoped = scope_liquidity_levels(externals, m5_liq.levels)
            inducement_candidates = tuple(find_inducement_candidates(scoped, current_price)) if current_price is not None else ()
    except MarketDataError:
        pass

    return m5_candles, m5_fvg_zones, m5_validated_order_blocks, m5_candidate_zones, inducement_candidates


def evaluate_entry_stage(symbol: str, event: Stage1Event, evaluation_time: datetime) -> SMCConditionalEntryAnalysis:
    """The true Stage-2 entry point: Stage1Event -> M1/M2/M3 -> composer.compose(),
    calling ZERO D1/H1 discovery and ZERO E1/E2/E3 evaluators (unlike
    compose_conditional_entry_analysis, which always evaluates all three E's --
    reusing it here would call evaluate_e1_daily_gap_reaction/evaluate_e2_h1_poi_
    reaction even for an E3 event, just with None inputs; this function instead calls
    composer.compose() -- the pure per-(E,M)-pair primitive composer.py itself uses --
    directly, once per maneuver, so evaluate_eN never runs at all). Must run inside
    historical_data_context. Returns the same SMCConditionalEntryAnalysis shape
    build_symbol_conditional_entry_analysis produces, for ledger/funnel reuse."""
    current_price = None
    try:
        current_price = get_tick(symbol).bid
    except MarketDataError:
        pass

    m5_candles, m5_fvg, m5_obs, m2_zones, inducement_candidates = _m5_side_primitives(symbol, current_price)

    opposing_role = _OPPOSING_ROLE_FOR_DIRECTION[event.direction]
    opposing_zone = max((z for z in m2_zones if z.role == opposing_role),
                        key=lambda z: z.origin_time or datetime.min, default=None)

    inducement_side = _INDUCEMENT_SIDE_FOR_DIRECTION[event.direction]
    candidate = next((c for c in inducement_candidates if c.side == inducement_side), None)

    liquidity_level = event.liquidity_reference.to_liquidity_level() if event.liquidity_reference is not None else None

    ref_type, ref_low, ref_high, ref_level = _parse_reference_key(event.reference_key)
    pseudo_e = EConditionResult(symbol=symbol, entry_condition=event.entry_condition,
                                direction=event.direction, eligible_for_confirmation=True,
                                reference_type=ref_type, reference_low=ref_low,
                                reference_high=ref_high, reference_level=ref_level)

    m1 = evaluate_m1_character_change_with_inducement(
        symbol, pseudo_e, candidate, None, m5_candles, m5_candles, m5_fvg, m5_obs, current_price, evaluation_time)
    m2 = evaluate_m2_supply_demand_shift(
        symbol, pseudo_e, opposing_zone, m5_candles, m5_candles, m2_zones, m5_fvg, m5_obs, current_price, evaluation_time)
    m3 = evaluate_m3_sweep_drop_pump(
        symbol, pseudo_e, liquidity_level, m5_candles, m5_candles, m5_fvg, m5_obs, current_price, evaluation_time)

    combinations = tuple(c for c in (compose(pseudo_e, m1), compose(pseudo_e, m2), compose(pseudo_e, m3)) if c is not None)

    return SMCConditionalEntryAnalysis(
        symbol=symbol, snapshot_time=evaluation_time,
        e_conditions={"E1": pseudo_e if event.entry_condition == "E1" else EConditionResult(entry_condition="E1", symbol=symbol),
                      "E2": pseudo_e if event.entry_condition == "E2" else EConditionResult(entry_condition="E2", symbol=symbol),
                      "E3": pseudo_e if event.entry_condition == "E3" else EConditionResult(entry_condition="E3", symbol=symbol)},
        m_maneuvers={"M1": (m1,), "M2": (m2,), "M3": (m3,)},
        combinations=combinations, selected_combination=None,
        data_quality="OK" if m5_candles else "UNAVAILABLE",
    )
