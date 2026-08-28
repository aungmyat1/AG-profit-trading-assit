"""DAYTRADING_LTF_EXECUTION_V1 execution-model classifiers (spec sections 9-28).

Pure, causal, offline functions over a CLOSED M5 candle window: no MT5/broker calls, no
risk sizing (spec sections 38/64/65). Each classifier answers "given the already-valid
DayTrading thesis, do these events form THIS execution model?" -- never "is there a
trade" from a bare sweep/CHoCH alone (spec section 4).

Reuse boundary: protected levels come from market_structure.tiers' EXTERNAL swing
high/low (passed in, never re-derived here); gaps come from
supply_demand.fair_value_gaps_for()'s ZoneResult (passed in, never re-detected here);
inducement evidence comes from liquidity.hierarchy.InducementCandidate (passed in, never
re-detected here). This module only sequences those existing facts into the seven
presenter execution-model shapes.

Causality: callers must supply only candles with time <= evaluation_time. Every
classifier here is a pure function of its input sequence -- append/modify candles after
evaluation_time and results are unaffected, because they are never seen.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from strategy_engine.session import Candle

from .models import (
    AGGRESSIVE_MOVE_POLICY_PARTIAL,
    ENTRY_METHOD_FIFTY_PERCENT_BODY,
    ENTRY_METHOD_FIFTY_PERCENT_GAP,
    ENTRY_METHOD_NONE,
    EXEC_MODEL_CLEAN_SWEEP,
    EXEC_MODEL_GAP_LIQUIDITY_RESPECT,
    EXEC_MODEL_INVERTED_GAP,
    EXEC_MODEL_LIQUIDITY_GRAB,
    EXEC_MODEL_SPREAD_SWEEP,
    EXEC_MODEL_SWEEP_AND_FAIL,
    EXEC_MODEL_SWEEP_AND_INDUCEMENT,
    EXEC_MODEL_UNRESOLVED,
    EXEC_STATUS_INDETERMINATE,
    EXEC_STATUS_MODEL_CONFIRMED,
    EXEC_STATUS_NOT_CONFIRMED,
    EXEC_STATUS_WAITING_CONFIRMATION,
    EXEC_STATUS_WAITING_ENTRY_PRICE,
    EXEC_STATUS_WAITING_SWEEP,
    INVERTED_GAP_POLICY_PARTIAL,
    OPEN_LEVEL_TOLERANCE_POLICY_UNRESOLVED,
    PROTECTED_SWEEP_LEVEL_POLICY_PARTIAL,
    SPREAD_SWEEP_POLICY_PARTIAL,
    STOP_BREADTH_POLICY_UNRESOLVED,
    ExecutionModelAssessment,
)

WICK_BODY_RATIO_MIN = 2.0  # "wick should be at least double the size of body" -- spec section 11/15
LIQUIDITY_GRAB_SWEEP_COUNTS = (2, 3)  # "there can be two or three sweep" -- spec section 18


def _body_bounds(c: Candle) -> Tuple[float, float]:
    return (min(c.open, c.close), max(c.open, c.close))


def _body_size(c: Candle) -> float:
    lo, hi = _body_bounds(c)
    return hi - lo


def _body_mid(c: Candle) -> float:
    lo, hi = _body_bounds(c)
    return (lo + hi) / 2.0


def _upper_wick(c: Candle) -> float:
    _, hi = _body_bounds(c)
    return c.high - hi


def _lower_wick(c: Candle) -> float:
    lo, _ = _body_bounds(c)
    return lo - c.low


def _is_sweep_candle(direction: str, protected_level: float, c: Candle) -> bool:
    return c.high > protected_level if direction == "SHORT" else c.low < protected_level


def _wick_body_ratio(direction: str, c: Candle) -> Optional[float]:
    body = _body_size(c)
    if body <= 0:
        return None
    wick = _upper_wick(c) if direction == "SHORT" else _lower_wick(c)
    return wick / body


def _protected_missing(direction: str) -> ExecutionModelAssessment:
    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_UNRESOLVED, direction=direction, status=EXEC_STATUS_INDETERMINATE,
        unresolved_policy=PROTECTED_SWEEP_LEVEL_POLICY_PARTIAL,
        reason="No protected_high/protected_low supplied -- protected-level gate cannot be evaluated.",
    )


def evaluate_clean_sweep(
    direction: str, protected_level: Optional[float], candles: Sequence[Candle],
) -> ExecutionModelAssessment:
    """Spec sections 11-12. Protected sweep + wick/body >= 2.0. OPEN_LEVEL_ALIGNMENT is
    left structurally UNRESOLVED (no numeric open/gap tolerance is frozen); it never
    gates confirmation of the wick-ratio rule that IS explicit."""
    if protected_level is None:
        return _protected_missing(direction)

    sweep_idx = next((i for i, c in enumerate(candles) if _is_sweep_candle(direction, protected_level, c)), None)
    if sweep_idx is None:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_CLEAN_SWEEP, direction=direction, protected_level=protected_level,
            status=EXEC_STATUS_WAITING_SWEEP, reason="No sweep candle above/below protected level yet.",
        )

    sweep_candle = candles[sweep_idx]
    ratio = _wick_body_ratio(direction, sweep_candle)
    wick_pass = ratio is not None and ratio >= WICK_BODY_RATIO_MIN

    if not wick_pass:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_CLEAN_SWEEP, direction=direction, protected_level=protected_level,
            sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=1,
            wick_body_ratio=ratio, status=EXEC_STATUS_NOT_CONFIRMED,
            evidence=("protected_sweep_gate=PASS", f"wick_body_ratio={ratio}"),
            reason=f"wick_body_ratio {ratio} < {WICK_BODY_RATIO_MIN} -- CLEAN_SWEEP requires the >=2x wick rule.",
        )

    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_CLEAN_SWEEP, direction=direction, protected_level=protected_level,
        sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=1,
        wick_body_ratio=ratio, structural_invalidation_reference=sweep_candle.high if direction == "SHORT" else sweep_candle.low,
        confirmation_candle_time=sweep_candle.time, confirmation_candle_close=sweep_candle.close,
        status=EXEC_STATUS_MODEL_CONFIRMED,
        evidence=("protected_sweep_gate=PASS", f"wick_body_ratio={ratio}"),
        unresolved_policy=OPEN_LEVEL_TOLERANCE_POLICY_UNRESOLVED,
        reason="OPEN_LEVEL_ALIGNMENT=UNRESOLVED -- see unresolved_policy.",
    )


def evaluate_spread_sweep(direction: str, protected_level: Optional[float]) -> ExecutionModelAssessment:
    """Spec section 13: always PARTIAL -- no deterministic numeric rule distinguishes
    Spread Sweep from Clean Sweep in the supplied reference material."""
    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_SPREAD_SWEEP, direction=direction, protected_level=protected_level,
        status=EXEC_STATUS_INDETERMINATE, unresolved_policy=SPREAD_SWEEP_POLICY_PARTIAL,
        reason=SPREAD_SWEEP_POLICY_PARTIAL,
    )


def evaluate_sweep_and_fail(
    direction: str, protected_level: Optional[float], candles: Sequence[Candle],
) -> ExecutionModelAssessment:
    """Spec section 14: close-confirmed, causal. "Wait till close below the highest
    candle" (bearish) / above the lowest candle (bullish mirror)."""
    if protected_level is None:
        return _protected_missing(direction)

    sweep_idx = next((i for i, c in enumerate(candles) if _is_sweep_candle(direction, protected_level, c)), None)
    if sweep_idx is None:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_SWEEP_AND_FAIL, direction=direction, protected_level=protected_level,
            status=EXEC_STATUS_WAITING_SWEEP, reason="No sweep candle above/below protected level yet.",
        )

    sweep_candle = candles[sweep_idx]
    reference = sweep_candle.high if direction == "SHORT" else sweep_candle.low

    for c in candles[sweep_idx + 1:]:
        failed = (c.close < reference) if direction == "SHORT" else (c.close > reference)
        if failed:
            return ExecutionModelAssessment(
                model_type=EXEC_MODEL_SWEEP_AND_FAIL, direction=direction, protected_level=protected_level,
                sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=1,
                structural_invalidation_reference=reference, confirmation_candle_closed=True,
                confirmation_candle_time=c.time, confirmation_candle_close=c.close,
                status=EXEC_STATUS_MODEL_CONFIRMED,
                evidence=("protected_sweep_gate=PASS", f"confirming_close={c.close}"),
                reason=None,
            )

    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_SWEEP_AND_FAIL, direction=direction, protected_level=protected_level,
        sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=1,
        structural_invalidation_reference=reference, confirmation_candle_closed=False,
        status=EXEC_STATUS_WAITING_CONFIRMATION,
        reason=f"Waiting for a closed candle to close {'below' if direction == 'SHORT' else 'above'} {reference}.",
    )


def evaluate_sweep_and_inducement(
    direction: str, protected_level: Optional[float], candles: Sequence[Candle], inducement_confirmed: Optional[bool],
) -> ExecutionModelAssessment:
    """Spec section 15-16: reuses liquidity.hierarchy inducement evidence (passed in as
    `inducement_confirmed`) -- never a second inducement definition. Entry geometry
    (50% body) and structural stop reference only; no position sizing (spec section 38)."""
    if protected_level is None:
        return _protected_missing(direction)

    sweep_idx = next((i for i, c in enumerate(candles) if _is_sweep_candle(direction, protected_level, c)), None)
    if sweep_idx is None:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_SWEEP_AND_INDUCEMENT, direction=direction, protected_level=protected_level,
            status=EXEC_STATUS_WAITING_SWEEP, reason="No sweep candle above/below protected level yet.",
        )

    sweep_candle = candles[sweep_idx]
    ratio = _wick_body_ratio(direction, sweep_candle)
    wick_pass = ratio is not None and ratio >= WICK_BODY_RATIO_MIN

    if inducement_confirmed is None:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_SWEEP_AND_INDUCEMENT, direction=direction, protected_level=protected_level,
            sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=1, wick_body_ratio=ratio,
            status=EXEC_STATUS_INDETERMINATE,
            reason="No inducement evidence supplied -- SWEEP_AND_INDUCEMENT cannot be evaluated (spec section 37).",
        )
    if not wick_pass or not inducement_confirmed:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_SWEEP_AND_INDUCEMENT, direction=direction, protected_level=protected_level,
            sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=1, wick_body_ratio=ratio,
            status=EXEC_STATUS_NOT_CONFIRMED,
            reason=f"wick_pass={wick_pass}, inducement_confirmed={inducement_confirmed}.",
        )

    body_lo, body_hi = _body_bounds(sweep_candle)
    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_SWEEP_AND_INDUCEMENT, direction=direction, protected_level=protected_level,
        sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=1, wick_body_ratio=ratio,
        entry_method=ENTRY_METHOD_FIFTY_PERCENT_BODY, entry_reference_price=_body_mid(sweep_candle),
        structural_invalidation_reference=body_hi if direction == "SHORT" else body_lo,
        confirmation_candle_time=sweep_candle.time, confirmation_candle_close=sweep_candle.close,
        status=EXEC_STATUS_MODEL_CONFIRMED,
        evidence=("protected_sweep_gate=PASS", f"wick_body_ratio={ratio}", "inducement=CONFIRMED"),
        reason=None,
    )


def evaluate_liquidity_grab(
    direction: str, protected_level: Optional[float], candles: Sequence[Candle],
    gap_low: Optional[float] = None, gap_high: Optional[float] = None,
) -> ExecutionModelAssessment:
    """Spec sections 17-19: 2-3 contiguous sweep candles, then a gap; entry at 50% gap.
    The 2-3 count is scoped to THIS model only (spec section 18), never a global rule."""
    if protected_level is None:
        return _protected_missing(direction)

    sweep_idxs = [i for i, c in enumerate(candles) if _is_sweep_candle(direction, protected_level, c)]
    contiguous = []
    for i in sweep_idxs:
        if contiguous and i == contiguous[-1] + 1:
            contiguous.append(i)
        else:
            contiguous = [i]
    count = len(contiguous)

    if count == 0:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_LIQUIDITY_GRAB, direction=direction, protected_level=protected_level,
            status=EXEC_STATUS_WAITING_SWEEP, reason="No sweep candle above/below protected level yet.",
        )
    if count not in LIQUIDITY_GRAB_SWEEP_COUNTS:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_LIQUIDITY_GRAB, direction=direction, protected_level=protected_level,
            sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=count,
            status=EXEC_STATUS_NOT_CONFIRMED,
            reason=f"sweep_count={count} not in {LIQUIDITY_GRAB_SWEEP_COUNTS} -- LIQUIDITY_GRAB requires 2 or 3 sweep candles.",
        )
    if gap_low is None or gap_high is None:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_LIQUIDITY_GRAB, direction=direction, protected_level=protected_level,
            sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=count,
            status=EXEC_STATUS_WAITING_CONFIRMATION, unresolved_policy=AGGRESSIVE_MOVE_POLICY_PARTIAL,
            reason="Valid sweep count but no gap evidence supplied yet.",
        )

    last_sweep = candles[contiguous[-1]]
    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_LIQUIDITY_GRAB, direction=direction, protected_level=protected_level,
        sweep_side="BUY_SIDE" if direction == "SHORT" else "SELL_SIDE", sweep_count=count,
        gap_low=gap_low, gap_high=gap_high,
        entry_method=ENTRY_METHOD_FIFTY_PERCENT_GAP, entry_reference_price=(gap_low + gap_high) / 2.0,
        structural_invalidation_reference=last_sweep.high if direction == "SHORT" else last_sweep.low,
        confirmation_candle_time=last_sweep.time, confirmation_candle_close=last_sweep.close,
        status=EXEC_STATUS_MODEL_CONFIRMED,
        evidence=("protected_sweep_gate=PASS", f"sweep_count={count}", "gap=DETECTED"),
        unresolved_policy=STOP_BREADTH_POLICY_UNRESOLVED,
        reason=None,
    )


def evaluate_gap_liquidity_respect(
    direction: str, gap_low: Optional[float], gap_high: Optional[float], candles: Sequence[Candle],
) -> ExecutionModelAssessment:
    """Spec sections 25-28: wick may penetrate the gap, but the candle must CLOSE back
    outside it. Bearish respect = price wicks up into a bearish gap then closes back
    below gap_low; bullish mirror closes back above gap_high."""
    if gap_low is None or gap_high is None:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_GAP_LIQUIDITY_RESPECT, direction=direction,
            status=EXEC_STATUS_INDETERMINATE, reason="No gap evidence supplied.",
        )

    touch_idx = next((i for i, c in enumerate(candles) if c.low < gap_high and c.high > gap_low), None)
    if touch_idx is None:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_GAP_LIQUIDITY_RESPECT, direction=direction, gap_low=gap_low, gap_high=gap_high,
            status=EXEC_STATUS_WAITING_SWEEP, reason="Price has not yet traded into the gap.",
        )

    touch = candles[touch_idx]
    closed_outside = (touch.close < gap_low) if direction == "SHORT" else (touch.close > gap_high)
    if not closed_outside:
        return ExecutionModelAssessment(
            model_type=EXEC_MODEL_GAP_LIQUIDITY_RESPECT, direction=direction, gap_low=gap_low, gap_high=gap_high,
            confirmation_candle_closed=True, status=EXEC_STATUS_NOT_CONFIRMED,
            reason=f"close={touch.close} did not close back outside the gap ({gap_low}-{gap_high}).",
        )

    entry = (gap_low + gap_high) / 2.0
    price_reached_entry = any(c.low <= entry <= c.high for c in candles[touch_idx:])
    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_GAP_LIQUIDITY_RESPECT, direction=direction, gap_low=gap_low, gap_high=gap_high,
        entry_method=ENTRY_METHOD_FIFTY_PERCENT_GAP, entry_reference_price=entry,
        structural_invalidation_reference=touch.high if direction == "SHORT" else touch.low,
        confirmation_candle_closed=True, confirmation_candle_time=touch.time, confirmation_candle_close=touch.close,
        status=EXEC_STATUS_MODEL_CONFIRMED if price_reached_entry else EXEC_STATUS_WAITING_ENTRY_PRICE,
        evidence=("wick_penetration=DETECTED", "close_back_outside_gap=DETECTED"),
        unresolved_policy=STOP_BREADTH_POLICY_UNRESOLVED,
        reason=None,
    )


def evaluate_inverted_gap(direction: str, gap_status: Optional[str]) -> ExecutionModelAssessment:
    """Spec sections 22-24/57: reuses supply_demand ZoneStatus (MITIGATED/INVALIDATED)
    as the only available evidence; no deterministic inversion-direction rule is frozen,
    so this never auto-confirms (spec section 78's ban on inventing hidden rules)."""
    return ExecutionModelAssessment(
        model_type=EXEC_MODEL_INVERTED_GAP, direction=direction, gap_status=gap_status,
        status=EXEC_STATUS_INDETERMINATE, unresolved_policy=INVERTED_GAP_POLICY_PARTIAL,
        reason=INVERTED_GAP_POLICY_PARTIAL,
    )
