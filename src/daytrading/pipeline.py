"""DayTrading pipeline: NarrativeBias -> LiquidityAffinity -> LTFExecution ->
RiskManagement -> TRADE_STATE (spec section 8/20/21).

`derive_trade_state()` is pure composition over already-computed stage results -- no
detection logic. `evaluate_daytrading()` is the live/gated orchestrator: each stage only
runs once the previous one clears its gate (section 21's "simple gating function",
deliberately not an event-processing subsystem) -- e.g. M5 entry-confirmation data is
never fetched if narrative_bias or liquidity_affinity is unresolved.
"""
from __future__ import annotations

from typing import Optional

from entry_confirmation import CandidateDirection, SweepShiftArrayRequest, evaluate_entry_confirmation

from .liquidity_affinity import evaluate_liquidity_affinity
from .ltf_execution import evaluate_ltf_execution
from .models import (
    AFFINITY_PARTIAL,
    AFFINITY_RESOLVED,
    BIAS_BEARISH,
    BIAS_BULLISH,
    DayTradingLiquidityAffinityResult,
    DayTradingResult,
    LTF_CONFIRMED,
    LTF_INVALIDATED,
    LTF_NOT_CONFIRMED,
    LTFExecutionResult,
    NarrativeBiasResult,
    RISK_PASS,
    RiskManagementResult,
    STATE_INVALIDATED,
    STATE_NO_TRADE,
    STATE_TRADE_READY_LONG,
    STATE_TRADE_READY_SHORT,
    STATE_WAIT_AFFINITY,
    STATE_WAIT_LTF_EXECUTION,
    STATE_WAIT_RISK,
    TIMEFRAME_COMPASS,
    TIMEFRAME_INTEREST,
    TIMEFRAME_TRADE,
)
from .narrative_bias import evaluate_narrative_bias
from .risk_management import evaluate_risk_management

_TRADE_READY_STATE = {"LONG": STATE_TRADE_READY_LONG, "SHORT": STATE_TRADE_READY_SHORT}
_EXPECTED_SWEEP_SIDE = {"LONG": "SELL_SIDE", "SHORT": "BUY_SIDE"}


def _select_swept_level(levels, candidate_direction: CandidateDirection):
    """Most-recently-swept H1 liquidity level opposite `candidate_direction` (a LONG
    setup needs SELL_SIDE liquidity swept below price before reversing up, and vice
    versa) -- reused verbatim from `liquidity_h1.levels`, never a new sweep detector.
    None if no such level has a `sweep_time` yet (fail closed)."""
    wanted_side = _EXPECTED_SWEEP_SIDE.get(candidate_direction.value)
    if wanted_side is None:
        return None
    candidates = [lv for lv in levels if lv.side.value == wanted_side and lv.sweep_time is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda lv: lv.sweep_time)


def _build_sweep_shift_request(
    symbol: str, trade_timeframe: str, candidate_direction: CandidateDirection,
    evaluation_time, current_price, liquidity_h1, h1_tiers, protected_high, protected_low,
    ec_result, latest_gap, affinity,
) -> Optional[SweepShiftArrayRequest]:
    """Assembles entry_confirmation.SweepShiftArrayRequest (SMC_SWEEP_SHIFT_ARRAY_V1,
    spec section 16/68) purely from evidence evaluate_daytrading() already computed --
    no new detection, no new MT5 fetch. `latest_gap` is the same supply_demand ZoneResult
    already selected for gap_low/gap_high. None (never guessed) if the required sweep
    evidence isn't available."""
    if liquidity_h1 is None or liquidity_h1.status != "LIQUIDITY_OK":
        return None
    swept_level = _select_swept_level(liquidity_h1.levels, candidate_direction)
    if swept_level is None:
        return None

    from entry_confirmation import evaluate_gap_context

    pivot_price = protected_low if candidate_direction == CandidateDirection.LONG else protected_high
    pivot_type = "SWING_LOW" if candidate_direction == CandidateDirection.LONG else "SWING_HIGH"
    external_tier = h1_tiers.external if h1_tiers.status == "VALID" else None
    internal_tier = h1_tiers.internal if h1_tiers.status == "VALID" else None
    gap_context = evaluate_gap_context(latest_gap) if latest_gap is not None else None

    return SweepShiftArrayRequest(
        symbol=symbol, timeframe=trade_timeframe, candidate_direction=candidate_direction,
        evaluation_time=evaluation_time,
        sweep_level=swept_level, poi_reference="H1_EXTERNAL_TIER",
        pivot_price=pivot_price, pivot_time=swept_level.origin_time, pivot_type=pivot_type,
        external_tier=external_tier, internal_tier=internal_tier,
        structure_shift=ec_result.structure_shift if ec_result is not None else None,
        structure_break_candle_time=ec_result.structure_shift.event_time
        if ec_result is not None and ec_result.structure_shift is not None else None,
        displacement=ec_result.displacement if ec_result is not None else None,
        displacement_leg_start=swept_level.sweep_time, displacement_leg_end=evaluation_time,
        gap_context=gap_context, gap_origin_time=latest_gap.origin_time if latest_gap is not None else None,
        premium_discount_zone=affinity.premium_discount_context if affinity is not None else None,
        current_price=current_price, target_liquidity_reference=affinity.primary_target_price if affinity is not None else None,
    )


def derive_trade_state(
    narrative_bias: NarrativeBiasResult,
    liquidity_affinity: Optional[DayTradingLiquidityAffinityResult],
    ltf_execution: Optional[LTFExecutionResult],
    risk_management: Optional[RiskManagementResult],
) -> DayTradingResult:
    if narrative_bias.bias not in (BIAS_BULLISH, BIAS_BEARISH):
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 trade_state=STATE_NO_TRADE,
                                 reasons=(f"narrative_bias={narrative_bias.bias} -- no directional context.",))

    if liquidity_affinity is None:
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 trade_state=STATE_WAIT_AFFINITY, reasons=("liquidity_affinity not yet evaluated.",))
    if liquidity_affinity.status not in (AFFINITY_RESOLVED, AFFINITY_PARTIAL):
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 liquidity_affinity=liquidity_affinity, trade_state=STATE_NO_TRADE,
                                 reasons=(f"liquidity_affinity={liquidity_affinity.status} -- "
                                          f"no resolved liquidity objective to hand off to LTF execution.",))

    if ltf_execution is None:
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 liquidity_affinity=liquidity_affinity, trade_state=STATE_WAIT_LTF_EXECUTION,
                                 reasons=("ltf_execution not yet evaluated.",))
    if ltf_execution.status == LTF_INVALIDATED:
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 liquidity_affinity=liquidity_affinity, ltf_execution=ltf_execution,
                                 trade_state=STATE_INVALIDATED, reasons=("ltf_execution INVALIDATED.",))
    if ltf_execution.status == LTF_NOT_CONFIRMED:
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 liquidity_affinity=liquidity_affinity, ltf_execution=ltf_execution,
                                 trade_state=STATE_NO_TRADE, reasons=("ltf_execution NOT_CONFIRMED.",))
    if ltf_execution.status != LTF_CONFIRMED:
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 liquidity_affinity=liquidity_affinity, ltf_execution=ltf_execution,
                                 trade_state=STATE_WAIT_LTF_EXECUTION,
                                 reasons=(f"ltf_execution={ltf_execution.status} -- not yet confirmed.",))

    if risk_management is None:
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 liquidity_affinity=liquidity_affinity, ltf_execution=ltf_execution,
                                 direction=ltf_execution.direction, trade_state=STATE_WAIT_RISK,
                                 reasons=("risk_management not yet evaluated.",))
    if risk_management.status != RISK_PASS:
        return DayTradingResult(symbol=narrative_bias.symbol, narrative_bias=narrative_bias,
                                 liquidity_affinity=liquidity_affinity, ltf_execution=ltf_execution,
                                 risk_management=risk_management, direction=ltf_execution.direction,
                                 trade_state=STATE_NO_TRADE,
                                 reasons=(f"risk_management={risk_management.status}.",))

    return DayTradingResult(
        symbol=narrative_bias.symbol, narrative_bias=narrative_bias, liquidity_affinity=liquidity_affinity,
        ltf_execution=ltf_execution, risk_management=risk_management, direction=ltf_execution.direction,
        trade_state=_TRADE_READY_STATE[ltf_execution.direction],
    )


def evaluate_daytrading(
    symbol: str,
    candidate_direction: CandidateDirection = CandidateDirection.NONE,
    compass_timeframe: str = TIMEFRAME_COMPASS,
    interest_timeframe: str = TIMEFRAME_INTEREST,
    trade_timeframe: str = TIMEFRAME_TRADE,
    tm_request_builder=None,
) -> DayTradingResult:
    """Live/gated orchestrator. `tm_request_builder(direction) -> Optional[TradeManagementRequest]`
    is only invoked once ltf_execution reaches CONFIRMED -- risk sizing is never computed
    for a setup that never confirmed. Deferred imports (see e.g. liquidity/affinity.py's
    module docstring for why): this module sits in daytrading, imported independently of
    the assistant package's own circular-import-sensitive chain."""
    from datetime import datetime, timezone

    from market_structure import analyze_structure
    from liquidity import liquidity_result as _liquidity_result
    from supply_demand import fair_value_gaps_for, premium_discount_from_previous_day

    from .true_day import true_day_window

    structure_d1 = analyze_structure(symbol, compass_timeframe)
    liquidity_d1 = _liquidity_result(symbol, compass_timeframe)
    dealing_range = None
    try:
        dealing_range = premium_discount_from_previous_day(symbol)
    except Exception:
        dealing_range = None

    evaluation_time = datetime.now(timezone.utc)
    day_context = true_day_window(evaluation_time)
    structure_h1 = analyze_structure(symbol, interest_timeframe)
    inefficiency = None
    try:
        inefficiency = fair_value_gaps_for(symbol, interest_timeframe)
    except Exception:
        inefficiency = None
    h1_candles = ()
    try:
        from mt5.market_data import get_candles as _get_candles
        h1_candles = _get_candles(symbol, interest_timeframe, day_context.day_start_utc, evaluation_time)
    except Exception:
        h1_candles = ()

    narrative = evaluate_narrative_bias(
        symbol, compass_timeframe, structure_d1, liquidity_d1, dealing_range,
        evaluation_time=evaluation_time, h1_structure=structure_h1, h1_candles=h1_candles,
        inefficiency=inefficiency,
    )

    if narrative.bias not in (BIAS_BULLISH, BIAS_BEARISH):
        return derive_trade_state(narrative, None, None, None)

    from market_structure.tiers import analyze_structure_tiers
    from liquidity.hierarchy import external_swing_liquidity, scope_liquidity_levels
    from supply_demand import dealing_range_zones
    from mt5.market_data import MarketDataError as _MarketDataError, get_latest_candles as _get_latest_candles, get_tick

    liquidity_h1 = _liquidity_result(symbol, interest_timeframe)
    h1_tiers = analyze_structure_tiers(symbol, interest_timeframe)
    current_price = None
    try:
        current_price = get_tick(symbol).bid
    except _MarketDataError:
        pass

    h1_scoped = ()
    h1_dealing_range = None
    if h1_tiers.status == "VALID" and h1_tiers.external is not None:
        try:
            h1_candles_full = _get_latest_candles(symbol, interest_timeframe, 300)
        except _MarketDataError:
            h1_candles_full = []
        external_levels = external_swing_liquidity(symbol, interest_timeframe, h1_tiers.external, h1_candles_full) \
            if h1_candles_full else ()
        h1_scoped = scope_liquidity_levels(external_levels, liquidity_h1.levels if liquidity_h1.status == "LIQUIDITY_OK" else ())
        sh, sl = h1_tiers.external.latest_swing_high, h1_tiers.external.latest_swing_low
        if sh is not None and sl is not None and sl.price < sh.price:
            h1_dealing_range = dealing_range_zones(symbol, sl.price, sh.price, source="h1_external_tier_swing_range",
                                                    current_price=current_price)

    affinity = evaluate_liquidity_affinity(
        symbol, narrative, liquidity_h1, tiers=h1_tiers, scoped_levels=h1_scoped, imbalances=inefficiency.zones
        if inefficiency is not None and inefficiency.status == "OK" else (),
        dealing_range=h1_dealing_range, h1_structure=structure_h1, current_price=current_price,
        evaluation_time=evaluation_time,
    )

    if affinity.status not in (AFFINITY_RESOLVED, AFFINITY_PARTIAL):
        return derive_trade_state(narrative, affinity, None, None)

    from mt5.market_data import MarketDataError, get_latest_candles
    from entry_confirmation import DISPLACEMENT, ALL_CONFIRMATIONS, EntryConfirmationRequest
    from entry_confirmation.displacement import MEDIAN_LOOKBACK
    from market_structure import analyze_structure as _analyze_structure

    structure_m5 = _analyze_structure(symbol, trade_timeframe)
    liquidity_m5 = _liquidity_result(symbol, trade_timeframe)
    candle_history = ()
    candidate_candle = None
    if DISPLACEMENT in ALL_CONFIRMATIONS:
        try:
            fetched = get_latest_candles(symbol, trade_timeframe, MEDIAN_LOOKBACK + 1)
            candidate_candle = fetched[-1]
            candle_history = tuple(fetched[:-1])
        except MarketDataError:
            candidate_candle, candle_history = None, ()

    ec_request = EntryConfirmationRequest(
        symbol=symbol, timeframe=trade_timeframe, candidate_direction=candidate_direction,
        requested_confirmations=ALL_CONFIRMATIONS, candidate_candle=candidate_candle,
        candle_history=candle_history, structure_result=structure_m5, liquidity_result=liquidity_m5,
    )

    # --- LTF execution-model context (spec DAYTRADING_LTF_EXECUTION_RUNTIME_V1 sections
    # 6-8): canonical protected level = H1 EXTERNAL tier swing (already computed above as
    # h1_tiers -- never re-derived from M5). Canonical M5 closed candles = the same
    # get_latest_candles() call already used for displacement (position 1+, forming bar
    # deliberately excluded by market_data.py). Canonical gap = supply_demand's own FVG
    # detector, never a second gap definition. Fail closed (None) wherever evidence isn't
    # available -- never a synthesized/nearest-arbitrary substitute. ---
    h1_structure_direction = h1_tiers.external.direction if (h1_tiers.status == "VALID" and h1_tiers.external is not None) else None
    protected_high = protected_low = None
    if h1_tiers.status == "VALID" and h1_tiers.external is not None:
        if h1_tiers.external.latest_swing_high is not None:
            protected_high = h1_tiers.external.latest_swing_high.price
        if h1_tiers.external.latest_swing_low is not None:
            protected_low = h1_tiers.external.latest_swing_low.price

    m5_closed_candles = candle_history + ((candidate_candle,) if candidate_candle is not None else ())

    gap_low = gap_high = None
    latest_gap = None
    try:
        from supply_demand import fair_value_gaps_for as _fair_value_gaps_for
        m5_gaps = _fair_value_gaps_for(symbol, trade_timeframe)
        if m5_gaps.status == "OK":
            wanted_direction = "BULLISH" if candidate_direction == CandidateDirection.LONG else "BEARISH"
            relevant = [z for z in m5_gaps.zones if z.direction.value == wanted_direction
                        and z.status.value in ("FRESH", "TOUCHED") and z.low is not None and z.high is not None]
            if relevant:
                latest_gap = max(relevant, key=lambda z: z.origin_time or narrative.evaluation_time)
                gap_low, gap_high = latest_gap.low, latest_gap.high
    except Exception:
        gap_low = gap_high = None
        latest_gap = None

    # Spec section 16: SMCSweepShiftArrayResult (engine_v2_1) evaluated as corroborating
    # evidence over the same H1 pivot/M5 structure-shift facts -- entry_confirmation's own
    # evaluate_entry_confirmation() is pure computation over already-fetched candles/
    # results (no additional MT5 fetch), so calling it once here to build the request is
    # never a duplicate broker call, only a duplicate (cheap) pure computation.
    sweep_shift_request = None
    if candidate_direction != CandidateDirection.NONE:
        try:
            ec_result_for_sweep_shift = evaluate_entry_confirmation(ec_request)
            sweep_shift_request = _build_sweep_shift_request(
                symbol, trade_timeframe, candidate_direction, evaluation_time, current_price,
                liquidity_h1, h1_tiers, protected_high, protected_low,
                ec_result_for_sweep_shift, latest_gap, affinity,
            )
        except Exception:
            sweep_shift_request = None

    ltf = evaluate_ltf_execution(
        symbol, trade_timeframe, narrative, affinity, candidate_direction, ec_request,
        h1_structure_direction=h1_structure_direction, protected_high=protected_high, protected_low=protected_low,
        m5_closed_candles=m5_closed_candles, gap_low=gap_low, gap_high=gap_high,
        sweep_shift_request=sweep_shift_request,
    )

    if ltf.status != LTF_CONFIRMED or tm_request_builder is None:
        return derive_trade_state(narrative, affinity, ltf, None)

    tm_request = tm_request_builder(ltf.direction)
    risk = evaluate_risk_management(symbol, tm_request)
    return derive_trade_state(narrative, affinity, ltf, risk)
