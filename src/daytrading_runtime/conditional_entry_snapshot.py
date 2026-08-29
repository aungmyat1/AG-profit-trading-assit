"""Live/analysis-only runtime wiring for SMC_CONDITIONAL_ENTRY_V2 (spec sections 6-19).
Builds one `SMCConditionalEntryAnalysis` per symbol: E1/E2/E3 (location+reaction) ->
M1/M2/M3 (M5 confirmation, evaluated independently per qualified direction, NOT tied to
whichever E happened to qualify it) -> the 3x3 composer. No new detector, no new
threshold -- every piece below is a caller-supplied adapter over already-signed
`entry_confirmation`/`market_structure`/`supply_demand`/`liquidity` primitives.

Split into two layers (same discipline `daytrading/pipeline.py` already uses):

- `compose_conditional_entry_analysis` -- PURE. Takes every already-fetched primitive as
  a parameter, calls nothing MT5-shaped, fully unit-testable without mocking (see
  tests/test_conditional_entry_snapshot.py).
- `build_symbol_conditional_entry_analysis` -- the thin MT5-fetching wrapper. Fails
  closed on every MarketDataError (never crashes the whole analysis; missing pieces are
  recorded in `warnings`/`data_quality`, matching `daytrading_runtime/snapshot.py`'s own
  fail-closed convention).

Single-snapshot data reuse (spec section 14): D1/H1/M5 candles, M5 FVG/OB inventory, and
current price are each fetched exactly once and shared across every E/M evaluation --
never per-model.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Dict, Optional, Sequence, Tuple

from entry_confirmation import (
    CHECK_TIMEFRAME,
    CONFIRMATION_TIMEFRAME,
    EXECUTION_TIMEFRAME,
    REFERENCE_TIMEFRAME_E1,
    REFERENCE_TIMEFRAME_E2,
    CandidateDirection,
    E2PoiReactionRequest,
    EConditionResult,
    SMCConditionalEntryAnalysis,
    e1_to_econdition,
    e2_to_econdition,
    e3_to_econdition,
    evaluate_e1_daily_gap_reaction,
    evaluate_e2_h1_poi_reaction,
    evaluate_e3_htf_liquidity_sweep,
    evaluate_entry_combinations,
    evaluate_m1_character_change_with_inducement,
    evaluate_m2_supply_demand_shift,
    evaluate_m3_sweep_drop_pump,
    gap_midpoint,
)
from entry_confirmation.m1_character_change_inducement import M1Result
from entry_confirmation.m2_supply_demand_shift import M2Result
from entry_confirmation.m3_sweep_drop_pump import M3Result
from liquidity.analyzer import liquidity_result
from liquidity.hierarchy import (
    InducementCandidate,
    ScopedLiquidityLevel,
    external_swing_liquidity,
    find_inducement_candidates,
    scope_liquidity_levels,
)
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure import MarketStructureConfig, load_market_structure_config
from market_structure.tiers import analyze_structure_tiers
from mt5.market_data import MarketDataError, get_latest_candles, get_tick
from strategy_engine.session import Candle
from supply_demand import ValidatedOrderBlock, ZoneResult
from supply_demand.analyzer import fair_value_gaps_for, order_blocks_for, validated_order_blocks_for
from supply_demand.models import ZoneRole, ZoneStatus
from supply_demand.ob_contract import OBValidationStatus

D1_GAP_LOOKBACK_CANDLES = 60
D1_REACTION_HISTORY_CANDLES = 25
H1_POI_LOOKBACK_CANDLES = 50
M5_LOOKBACK_CANDLES = 200

_TAKEN_STATUSES = (LiquidityStatus.SWEPT, LiquidityStatus.RECLAIMED, LiquidityStatus.CONSUMED)

# Adapts AG_ORDER_BLOCK_V1's OBValidationStatus (which DOES track true closed-beyond
# INVALIDATED, unlike the raw smc.ob() ZoneStatus, which can only ever report
# FRESH/MITIGATED -- see supply_demand/smc_adapter.py's own module docstring) onto
# supply_demand's ZoneStatus vocabulary. Not a new lifecycle rule -- a status-vocabulary
# adapter between two already-signed contracts, needed because M2's zone-failure gate
# requires a real ZoneResult with a real ZoneStatus.INVALIDATED.
_OB_STATUS_TO_ZONE_STATUS = {
    OBValidationStatus.VALID: ZoneStatus.FRESH,
    OBValidationStatus.MITIGATED: ZoneStatus.MITIGATED,
    OBValidationStatus.INVALIDATED: ZoneStatus.INVALIDATED,
}

_INDUCEMENT_SIDE_FOR_DIRECTION = {
    CandidateDirection.SHORT.value: LiquiditySide.BUY_SIDE,
    CandidateDirection.LONG.value: LiquiditySide.SELL_SIDE,
}
_OPPOSING_ROLE_FOR_DIRECTION = {
    CandidateDirection.SHORT.value: ZoneRole.DEMAND,
    CandidateDirection.LONG.value: ZoneRole.SUPPLY,
}


def _latest_active_zone(zones: Sequence[ZoneResult]) -> Optional[ZoneResult]:
    active = [z for z in zones if z.status != ZoneStatus.INVALIDATED]
    if not active:
        return None
    return max(active, key=lambda z: z.origin_time or datetime.min)


def _validated_ob_to_zone(vob: ValidatedOrderBlock) -> Optional[ZoneResult]:
    mapped = _OB_STATUS_TO_ZONE_STATUS.get(vob.status)
    if mapped is None or vob.candidate is None:
        return None
    return replace(vob.candidate, status=mapped)


def _select_inducement(
    candidates: Sequence[InducementCandidate], side: LiquiditySide, current_price: Optional[float],
) -> Optional[InducementCandidate]:
    matching = [c for c in candidates if c.side == side]
    if not matching:
        return None
    if current_price is None:
        return matching[0]
    # Nearest-by-distance tie-break -- a deterministic ordering, not a signed priority
    # rule (mirrors entry_confirmation's own "earliest selected" documented tie-breaks
    # for ambiguous multi-candidate cases, e.g. e2_h1_poi_reaction.py's FVG selection).
    return min(matching, key=lambda c: abs(c.candidate.price - current_price))


def _select_taken_level(levels: Sequence[LiquidityLevel], side: LiquiditySide, price: float) -> Optional[LiquidityLevel]:
    return next(
        (lvl for lvl in levels if lvl.side == side and lvl.price == price
         and lvl.status in _TAKEN_STATUSES and lvl.sweep_time is not None),
        None,
    )


def _recently_taken_inducement(
    scoped: Sequence[ScopedLiquidityLevel], side: LiquiditySide, current_price: Optional[float],
) -> Tuple[Optional[InducementCandidate], Optional[LiquidityLevel]]:
    """Best-effort single-snapshot detection of an inducement candidate that has
    ALREADY been taken. `liquidity.hierarchy.find_inducement_candidates` only ever
    returns still-UNSWEPT candidates by its own signed contract, so an already-taken
    inducement is, by construction, invisible to it. This reapplies the SAME relational
    test (an internal level positioned between price and an external target on the same
    side) to a now-taken internal level instead.

    KNOWN LIMITATION (documented, not hidden): this does not replay history, so it
    cannot confirm the level was ALREADY between price and the target at the moment it
    was taken -- only that a plausible external target still exists now. A future pass
    with historical candle replay could tighten this."""
    if current_price is None:
        return None, None
    externals_unswept = [
        s for s in scoped if s.scope == "EXTERNAL" and s.level.side == side
        and s.level.status == LiquidityStatus.UNSWEPT
    ]
    taken_internal = [
        s for s in scoped if s.scope == "INTERNAL" and s.level.side == side
        and s.level.status in _TAKEN_STATUSES and s.level.sweep_time is not None
    ]
    for internal in taken_internal:
        for target in externals_unswept:
            is_between = (
                current_price < internal.level.price < target.level.price if side == LiquiditySide.BUY_SIDE
                else current_price > internal.level.price > target.level.price
            )
            if is_between:
                return InducementCandidate(
                    candidate_id=internal.level_id, candidate=internal.level,
                    target_id=target.level_id, target=target.level, side=side,
                ), internal.level
    return None, None


def compose_conditional_entry_analysis(
    symbol: str,
    evaluation_time: Optional[datetime],
    current_price: Optional[float],
    d1_gap_zone: Optional[ZoneResult],
    d1_touch_candle: Optional[Candle],
    d1_reaction_candle: Optional[Candle],
    d1_reaction_history: Sequence[Candle],
    d1_direction: CandidateDirection,
    h1_poi_zone: Optional[ZoneResult],
    h1_candles: Sequence[Candle],
    htf_liquidity_buy: Optional[LiquidityLevel],
    htf_liquidity_sell: Optional[LiquidityLevel],
    m5_candles: Sequence[Candle],
    m5_displacement_history: Sequence[Candle],
    m5_fvg_zones: Sequence[ZoneResult],
    m5_validated_order_blocks: Sequence[ValidatedOrderBlock],
    inducement_candidates: Sequence[InducementCandidate] = (),
    inducement_taken_levels: Sequence[LiquidityLevel] = (),
    m2_candidate_zones: Sequence[ZoneResult] = (),
    structure_config: Optional[MarketStructureConfig] = None,
    warnings: Sequence[str] = (),
) -> SMCConditionalEntryAnalysis:
    structure_config = structure_config or load_market_structure_config()

    e1_result = evaluate_e1_daily_gap_reaction(
        symbol, d1_gap_zone, d1_direction, d1_touch_candle, d1_reaction_candle, d1_reaction_history,
    )
    e1 = e1_to_econdition(e1_result)

    e2_result = evaluate_e2_h1_poi_reaction(E2PoiReactionRequest(
        symbol=symbol, h1_poi_zone=h1_poi_zone, h1_candles=h1_candles,
        m5_candles=m5_candles, m5_displacement_history=m5_displacement_history, evaluation_time=evaluation_time,
    ))
    e2 = e2_to_econdition(e2_result)

    # E3: evaluate both sides independently (buy-side sweep -> candidate SHORT,
    # sell-side -> candidate LONG); prefer whichever is eligible for explainability,
    # falling back to the buy-side evaluation so a symbol with no liquidity data at all
    # still reports E3 = NOT_APPLICABLE rather than being silently omitted.
    e3_buy_result = evaluate_e3_htf_liquidity_sweep(symbol, htf_liquidity_buy) if htf_liquidity_buy is not None else None
    e3_sell_result = evaluate_e3_htf_liquidity_sweep(symbol, htf_liquidity_sell) if htf_liquidity_sell is not None else None
    e3_result = next(
        (r for r in (e3_buy_result, e3_sell_result) if r is not None and r.eligible_for_confirmation),
        e3_buy_result or e3_sell_result,
    )
    e3 = e3_to_econdition(e3_result) if e3_result is not None else EConditionResult(entry_condition="E3", symbol=symbol)

    e_conditions: Dict[str, EConditionResult] = {"E1": e1, "E2": e2, "E3": e3}

    directions = sorted({
        e.direction for e in e_conditions.values() if e.eligible_for_confirmation and e.direction
    })

    m1_by_direction: Dict[str, M1Result] = {}
    m2_by_direction: Dict[str, M2Result] = {}
    m3_by_direction: Dict[str, M3Result] = {}

    for direction in directions:
        pseudo_e = EConditionResult(symbol=symbol, direction=direction, eligible_for_confirmation=True)

        inducement_side = _INDUCEMENT_SIDE_FOR_DIRECTION[direction]
        candidate = _select_inducement(inducement_candidates, inducement_side, current_price)
        taken_level = _select_taken_level(inducement_taken_levels, inducement_side, candidate.candidate.price) \
            if candidate is not None else None
        m1_by_direction[direction] = evaluate_m1_character_change_with_inducement(
            symbol, pseudo_e, candidate, taken_level, m5_candles, m5_displacement_history,
            m5_fvg_zones, m5_validated_order_blocks, current_price, evaluation_time, structure_config,
        )

        opposing_role = _OPPOSING_ROLE_FOR_DIRECTION[direction]
        opposing_zone = max(
            (z for z in m2_candidate_zones if z.role == opposing_role),
            key=lambda z: z.origin_time or datetime.min, default=None,
        )
        m2_by_direction[direction] = evaluate_m2_supply_demand_shift(
            symbol, pseudo_e, opposing_zone, m5_candles, m5_displacement_history,
            m2_candidate_zones, m5_fvg_zones, m5_validated_order_blocks, current_price, evaluation_time, structure_config,
        )

        liquidity_level = htf_liquidity_buy if direction == CandidateDirection.SHORT.value else htf_liquidity_sell
        m3_by_direction[direction] = evaluate_m3_sweep_drop_pump(
            symbol, pseudo_e, liquidity_level, m5_candles, m5_displacement_history,
            m5_fvg_zones, m5_validated_order_blocks, current_price, evaluation_time, structure_config,
        )

    if not directions:
        # No qualified E-condition at all -- report NOT_APPLICABLE explicitly for every
        # maneuver rather than omitting them (spec section 19: never fabricate a setup,
        # never hide a component either).
        m1_by_direction["NONE"] = evaluate_m1_character_change_with_inducement(
            symbol, None, None, None, m5_candles, m5_displacement_history, (), (), current_price, evaluation_time,
        )
        m2_by_direction["NONE"] = evaluate_m2_supply_demand_shift(
            symbol, None, None, m5_candles, m5_displacement_history, (), (), (), current_price, evaluation_time,
        )
        m3_by_direction["NONE"] = evaluate_m3_sweep_drop_pump(
            symbol, None, None, m5_candles, m5_displacement_history, (), (), current_price, evaluation_time,
        )

    m_maneuvers = {
        "M1": tuple(m1_by_direction.values()),
        "M2": tuple(m2_by_direction.values()),
        "M3": tuple(m3_by_direction.values()),
    }
    all_m_results = m_maneuvers["M1"] + m_maneuvers["M2"] + m_maneuvers["M3"]

    combinations = evaluate_entry_combinations(tuple(e_conditions.values()), all_m_results)

    warnings = tuple(warnings)
    if not m5_candles:
        data_quality = "UNAVAILABLE"
    elif warnings:
        data_quality = "PARTIAL"
    else:
        data_quality = "OK"

    return SMCConditionalEntryAnalysis(
        symbol=symbol, snapshot_time=evaluation_time,
        reference_timeframes={
            "E1": REFERENCE_TIMEFRAME_E1, "E2": REFERENCE_TIMEFRAME_E2,
            "E3": e3.reference_timeframe,
        },
        check_timeframe=CHECK_TIMEFRAME, confirmation_timeframe=CONFIRMATION_TIMEFRAME,
        execution_timeframe=EXECUTION_TIMEFRAME,
        e_conditions=e_conditions, m_maneuvers=m_maneuvers,
        combinations=combinations, selected_combination=None,
        data_quality=data_quality, missing_data=warnings, warnings=warnings,
    )


def build_symbol_conditional_entry_analysis(symbol: str) -> SMCConditionalEntryAnalysis:
    """Thin MT5-fetching wrapper -- fetches every primitive exactly once, then delegates
    to `compose_conditional_entry_analysis` (pure). Fails closed on every
    MarketDataError: a fetch failure is recorded in `warnings` and the affected
    component degrades to its own NOT_APPLICABLE/INSUFFICIENT_DATA state, it never
    raises out of this function and never fabricates a trigger."""
    warnings = []

    d1_gap_zone = None
    d1_touch_candle: Optional[Candle] = None
    d1_reaction_candle: Optional[Candle] = None
    d1_reaction_history: Tuple[Candle, ...] = ()
    d1_direction = CandidateDirection.NONE
    try:
        gap_query = fair_value_gaps_for(symbol, "D1", count=D1_GAP_LOOKBACK_CANDLES)
        d1_candles = get_latest_candles(symbol, "D1", D1_GAP_LOOKBACK_CANDLES)
        if gap_query.status == "OK":
            zone = _latest_active_zone(gap_query.zones)
            if zone is not None and zone.low is not None and zone.high is not None:
                d1_gap_zone = zone
                after_origin = [c for c in d1_candles if zone.origin_time is None or c.time > zone.origin_time]
                d1_touch_candle = next((c for c in after_origin if c.low <= zone.high and c.high >= zone.low), None)
                if d1_touch_candle is not None:
                    idx = after_origin.index(d1_touch_candle)
                    following = after_origin[idx + 1:]
                    d1_reaction_candle = following[0] if following else None
                    d1_reaction_history = tuple(d1_candles[:D1_REACTION_HISTORY_CANDLES])
                mid = gap_midpoint(zone.low, zone.high)
                d1_direction = CandidateDirection.LONG if (
                    mid is not None and d1_touch_candle is not None and d1_touch_candle.close < mid
                ) else CandidateDirection.SHORT
        else:
            warnings.append(f"E1_D1_GAP_QUERY_FAILED:{gap_query.status}")
    except MarketDataError as exc:
        warnings.append(f"E1_D1_FETCH_FAILED:{exc.reason_code}")

    h1_poi_zone = None
    h1_candles: Tuple[Candle, ...] = ()
    try:
        ob_query = order_blocks_for(symbol, "H1")
        h1_candles = tuple(get_latest_candles(symbol, "H1", H1_POI_LOOKBACK_CANDLES))
        if ob_query.status == "OK":
            h1_poi_zone = _latest_active_zone(ob_query.zones)
        else:
            warnings.append(f"E2_H1_POI_QUERY_FAILED:{ob_query.status}")
    except MarketDataError as exc:
        warnings.append(f"E2_H1_FETCH_FAILED:{exc.reason_code}")

    htf_liquidity_buy: Optional[LiquidityLevel] = None
    htf_liquidity_sell: Optional[LiquidityLevel] = None
    try:
        h1_liquidity = liquidity_result(symbol, "H1")
        if h1_liquidity.status == "LIQUIDITY_OK":
            htf_liquidity_buy = h1_liquidity.nearest_buy_side
            htf_liquidity_sell = h1_liquidity.nearest_sell_side
        else:
            warnings.append(f"E3_H1_LIQUIDITY_FAILED:{h1_liquidity.status}")
    except MarketDataError as exc:
        warnings.append(f"E3_H1_FETCH_FAILED:{exc.reason_code}")

    m5_candles: Tuple[Candle, ...] = ()
    try:
        m5_candles = tuple(get_latest_candles(symbol, "M5", M5_LOOKBACK_CANDLES))
    except MarketDataError as exc:
        warnings.append(f"M5_CANDLES_FETCH_FAILED:{exc.reason_code}")

    m5_fvg_zones: Tuple[ZoneResult, ...] = ()
    try:
        m5_fvg_query = fair_value_gaps_for(symbol, "M5")
        if m5_fvg_query.status == "OK":
            m5_fvg_zones = m5_fvg_query.zones
        else:
            warnings.append(f"M5_FVG_QUERY_FAILED:{m5_fvg_query.status}")
    except MarketDataError as exc:
        warnings.append(f"M5_FVG_FETCH_FAILED:{exc.reason_code}")

    m5_validated_order_blocks: Tuple[ValidatedOrderBlock, ...] = tuple(validated_order_blocks_for(symbol, "M5"))
    m5_candidate_zones: Tuple[ZoneResult, ...] = tuple(
        z for z in (_validated_ob_to_zone(v) for v in m5_validated_order_blocks) if z is not None
    )

    current_price: Optional[float] = None
    try:
        current_price = get_tick(symbol).bid
    except MarketDataError:
        warnings.append("CURRENT_PRICE_UNAVAILABLE")

    evaluation_time = m5_candles[-1].time if m5_candles else datetime.now(timezone.utc)

    inducement_candidates: Tuple[InducementCandidate, ...] = ()
    inducement_taken_levels: Tuple[LiquidityLevel, ...] = ()
    try:
        m5_tiers = analyze_structure_tiers(symbol, "M5")
        m5_liquidity = liquidity_result(symbol, "M5")
        if m5_tiers.status == "VALID" and m5_tiers.external is not None and m5_liquidity.status == "LIQUIDITY_OK":
            external_levels = external_swing_liquidity(symbol, "M5", m5_tiers.external, m5_candles) if m5_candles else ()
            scoped = scope_liquidity_levels(external_levels, m5_liquidity.levels)
            live_candidates = find_inducement_candidates(scoped, current_price) if current_price is not None else ()
            taken_buy = _recently_taken_inducement(scoped, LiquiditySide.BUY_SIDE, current_price)
            taken_sell = _recently_taken_inducement(scoped, LiquiditySide.SELL_SIDE, current_price)
            inducement_candidates = tuple(live_candidates) + tuple(
                c for c in (taken_buy[0], taken_sell[0]) if c is not None
            )
            inducement_taken_levels = tuple(l for l in (taken_buy[1], taken_sell[1]) if l is not None)
        else:
            warnings.append("M1_INDUCEMENT_CONTEXT_UNAVAILABLE")
    except MarketDataError as exc:
        warnings.append(f"M1_INDUCEMENT_FETCH_FAILED:{exc.reason_code}")

    return compose_conditional_entry_analysis(
        symbol=symbol, evaluation_time=evaluation_time, current_price=current_price,
        d1_gap_zone=d1_gap_zone, d1_touch_candle=d1_touch_candle, d1_reaction_candle=d1_reaction_candle,
        d1_reaction_history=d1_reaction_history, d1_direction=d1_direction,
        h1_poi_zone=h1_poi_zone, h1_candles=h1_candles,
        htf_liquidity_buy=htf_liquidity_buy, htf_liquidity_sell=htf_liquidity_sell,
        m5_candles=m5_candles, m5_displacement_history=m5_candles,
        m5_fvg_zones=m5_fvg_zones, m5_validated_order_blocks=m5_validated_order_blocks,
        inducement_candidates=inducement_candidates, inducement_taken_levels=inducement_taken_levels,
        m2_candidate_zones=m5_candidate_zones,
        warnings=tuple(warnings),
    )
