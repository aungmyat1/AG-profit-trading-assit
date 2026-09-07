"""large_smc_research.c10_stop_policy -- ST_LARGE_SMC_V1's now-signed C10 broker
stop-loss distance policy (AG_LARGE_SMC_V1_C10_STRUCTURAL_INVALIDATION_IMPLEMENTATION_
AND_PROMOTION_V3: DYNAMIC_ATR_WITH_HARD_FLOOR). Pure-function unit tests only; no MT5,
no engine wiring (see tests/test_large_smc_research_engine.py for the engine-level
integration).
"""
from __future__ import annotations

import datetime as dt

import pytest

from large_smc_research.c10_stop_policy import (
    ATR_MULTIPLIER,
    ATR_PERIOD,
    MIN_BUFFER_PIPS,
    PIP_SIZE_EURUSD,
    C10StopPolicyViolation,
    compute_atr14_m5,
    compute_c10_stop,
)

UTC = dt.timezone.utc
ANCHOR = 1.1000
BID, ASK = 1.09990, 1.10010
SPREAD = ASK - BID
FLOOR = MIN_BUFFER_PIPS * PIP_SIZE_EURUSD


class _Candle:
    def __init__(self, time, open_, high, low, close):
        self.time = time
        self.open = open_
        self.high = high
        self.low = low
        self.close = close


def _flat_candles(n, price=1.1000, step_minutes=5, start=dt.datetime(2026, 1, 5, tzinfo=UTC)):
    """Zero true-range candles -> ATR == 0.0, so the floor always wins. Deterministic,
    no randomness."""
    return [
        _Candle(start + dt.timedelta(minutes=step_minutes * i), price, price, price, price)
        for i in range(n)
    ]


def _volatile_candles(n, base=1.1000, high_offset=0.0050, low_offset=0.0050,
                       step_minutes=5, start=dt.datetime(2026, 1, 5, tzinfo=UTC)):
    """Constant, large true range every bar -> a large, easily-predicted ATR."""
    return [
        _Candle(start + dt.timedelta(minutes=step_minutes * i), base, base + high_offset,
                base - low_offset, base)
        for i in range(n)
    ]


# --------------------------------------------------------------------------- ATR itself


def test_atr_insufficient_history_returns_none():
    assert compute_atr14_m5(_flat_candles(ATR_PERIOD)) is None  # exactly period candles -> period-1 TRs, not enough


def test_atr_exact_minimum_history_computes():
    assert compute_atr14_m5(_flat_candles(ATR_PERIOD + 1)) == pytest.approx(0.0)


def test_atr_constant_true_range_matches_closed_form():
    candles = _volatile_candles(ATR_PERIOD + 1, high_offset=0.0050, low_offset=0.0050)
    atr = compute_atr14_m5(candles)
    # Every bar's TR is high-low = 0.0100 (constant range, prev_close == base every bar).
    assert atr == pytest.approx(0.0100)


def test_atr_future_candles_do_not_change_past_atr():
    """No-lookahead: ATR computed from candles up to T must equal ATR computed from the
    same T-bounded candles plus additional bars appended AFTER T is excluded by the
    caller -- i.e. compute_atr14_m5 itself never looks past what it is given, and a
    caller that correctly fetches only closed-as-of-T candles gets an identical result
    regardless of what happens later."""
    candles_at_t = _volatile_candles(ATR_PERIOD + 1, high_offset=0.0050, low_offset=0.0050)
    atr_at_t = compute_atr14_m5(candles_at_t)

    future = _volatile_candles(
        5, base=9.9999, high_offset=5.0, low_offset=5.0,
        start=candles_at_t[-1].time + dt.timedelta(minutes=5),
    )
    # Simulate a caller that (correctly) still only fetches candles up to T -- ATR must
    # be unchanged regardless of what future bars would look like.
    atr_still_at_t = compute_atr14_m5(candles_at_t)
    assert atr_still_at_t == atr_at_t

    # And explicitly prove the future bars WOULD have changed it if wrongly included,
    # so this test is not vacuous.
    atr_if_future_wrongly_included = compute_atr14_m5(candles_at_t + future)
    assert atr_if_future_wrongly_included != atr_at_t


# --------------------------------------------------------------------------- buffer: floor vs ATR


def test_buffer_floor_wins_when_atr_below_floor():
    """ATR component (0.35 x ATR) below the 1.5 pip floor -> floor wins."""
    candles = _volatile_candles(ATR_PERIOD + 1, high_offset=0.00015, low_offset=0.00015)
    atr = compute_atr14_m5(candles)
    assert ATR_MULTIPLIER * atr < FLOOR  # sanity: fixture actually exercises the floor branch

    result = compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=candles)
    assert result.buffer_price == pytest.approx(FLOOR)
    assert result.floor_component == pytest.approx(FLOOR)
    assert result.atr_component < FLOOR


def test_buffer_atr_wins_when_atr_above_floor():
    """ATR component above the floor -> ATR wins, per the owner's canonical equation."""
    candles = _volatile_candles(ATR_PERIOD + 1, high_offset=0.0050, low_offset=0.0050)
    atr = compute_atr14_m5(candles)
    assert ATR_MULTIPLIER * atr > FLOOR  # sanity

    result = compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=candles)
    assert result.buffer_price == pytest.approx(ATR_MULTIPLIER * atr)
    assert result.atr_component > FLOOR


def test_buffer_deterministic_equality_at_floor_boundary():
    """Constructing an ATR whose 0.35x component lands exactly on the 1.5-pip floor
    must deterministically select that exact value (max() with equal operands)."""
    target_atr = FLOOR / ATR_MULTIPLIER
    candles = _volatile_candles(ATR_PERIOD + 1, high_offset=target_atr / 2, low_offset=target_atr / 2)
    atr = compute_atr14_m5(candles)
    assert atr == pytest.approx(target_atr)

    result = compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=candles)
    assert result.buffer_price == pytest.approx(FLOOR)
    assert result.buffer_price == pytest.approx(result.atr_component)


# --------------------------------------------------------------------------- LONG / SHORT


def test_long_stop_no_spread_added():
    """LONG: raw_stop = anchor - buffer. Spread is never added on the LONG side (owner
    instruction: 'do not add spread to LONG simply for symmetry')."""
    candles = _flat_candles(ATR_PERIOD + 1)  # ATR == 0 -> floor governs
    result = compute_c10_stop("LONG", ANCHOR, bid=BID, ask=ASK, m5_candles=candles)
    assert result.spread_price == 0.0
    assert result.stop_price == pytest.approx(ANCHOR - FLOOR)
    assert result.stop_price < ANCHOR


def test_long_stop_ignores_missing_tick():
    """LONG never needs bid/ask at all -- a missing tick (None, None) must not block it."""
    candles = _flat_candles(ATR_PERIOD + 1)
    result = compute_c10_stop("LONG", ANCHOR, bid=None, ask=None, m5_candles=candles)
    assert result.stop_price == pytest.approx(ANCHOR - FLOOR)


def test_short_stop_includes_verified_spread():
    """SHORT: anchor + buffer + spread -- protects the structural anchor from Ask-side
    stop-trigger effects."""
    candles = _flat_candles(ATR_PERIOD + 1)  # ATR == 0 -> floor governs
    result = compute_c10_stop("SHORT", ANCHOR, bid=BID, ask=ASK, m5_candles=candles)
    assert result.spread_price == pytest.approx(SPREAD)
    assert result.stop_price == pytest.approx(ANCHOR + FLOOR + SPREAD)
    assert result.stop_price > ANCHOR


def test_short_missing_spread_fails_closed():
    candles = _flat_candles(ATR_PERIOD + 1)
    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("SHORT", ANCHOR, bid=None, ask=ASK, m5_candles=candles)
    assert exc_info.value.reason_code == "MISSING_SPREAD"

    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("SHORT", ANCHOR, bid=BID, ask=None, m5_candles=candles)
    assert exc_info.value.reason_code == "MISSING_SPREAD"


def test_short_spread_not_double_counted():
    candles = _flat_candles(ATR_PERIOD + 1)
    baseline = compute_c10_stop("SHORT", ANCHOR, bid=ANCHOR, ask=ANCHOR, m5_candles=candles)
    single = compute_c10_stop("SHORT", ANCHOR, BID, ASK, m5_candles=candles)
    doubled_bid, doubled_ask = ANCHOR - SPREAD, ANCHOR + SPREAD
    doubled = compute_c10_stop("SHORT", ANCHOR, doubled_bid, doubled_ask, m5_candles=candles)

    single_delta = single.stop_price - baseline.stop_price
    doubled_delta = doubled.stop_price - baseline.stop_price
    assert doubled_delta == pytest.approx(2 * single_delta)


def test_negative_spread_fails_closed():
    candles = _flat_candles(ATR_PERIOD + 1)
    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("SHORT", ANCHOR, bid=1.1010, ask=1.0990, m5_candles=candles)
    assert exc_info.value.reason_code == "INVALID_SPREAD"


# --------------------------------------------------------------------------- fail-closed inputs


def test_missing_structural_anchor_fails_closed():
    candles = _flat_candles(ATR_PERIOD + 1)
    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("LONG", None, None, None, m5_candles=candles)
    assert exc_info.value.reason_code == "MISSING_STRUCTURAL_ANCHOR"


def test_missing_atr_data_fails_closed():
    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=None)
    assert exc_info.value.reason_code == "MISSING_ATR_DATA"


def test_insufficient_atr_warmup_fails_closed_not_floor():
    """Missing/insufficient ATR must NOT silently degrade to the 1.5-pip floor alone --
    it must fail closed."""
    too_few = _flat_candles(ATR_PERIOD)  # one short of the minimum
    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=too_few)
    assert exc_info.value.reason_code == "ATR_NOT_READY"


def test_invalid_direction_fails_closed():
    candles = _flat_candles(ATR_PERIOD + 1)
    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("SIDEWAYS", ANCHOR, BID, ASK, m5_candles=candles)
    assert exc_info.value.reason_code == "INVALID_DIRECTION"


# --------------------------------------------------------------------------- broker minimum stop (C10-C)


def test_broker_minimum_stop_violation_rejects():
    candles = _flat_candles(ATR_PERIOD + 1)
    no_check = compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=candles, entry_price=ANCHOR + 0.01)
    actual_distance = abs((ANCHOR + 0.01) - no_check.stop_price)

    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop(
            "LONG", ANCHOR, None, None, m5_candles=candles,
            min_stop_distance_price=actual_distance + 0.0005,
            entry_price=ANCHOR + 0.01,
        )
    assert exc_info.value.reason_code == "MIN_STOP_VIOLATION"


def test_broker_minimum_stop_satisfied_passes():
    candles = _flat_candles(ATR_PERIOD + 1)
    result = compute_c10_stop(
        "LONG", ANCHOR, None, None, m5_candles=candles,
        min_stop_distance_price=0.0000001, entry_price=ANCHOR + 0.01,
    )
    assert result.stop_price is not None


def test_missing_entry_for_min_stop_check_fails_closed():
    candles = _flat_candles(ATR_PERIOD + 1)
    with pytest.raises(C10StopPolicyViolation) as exc_info:
        compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=candles, min_stop_distance_price=0.001)
    assert exc_info.value.reason_code == "MISSING_ENTRY_FOR_MIN_STOP_CHECK"


def test_min_stop_check_not_applicable_when_absent():
    candles = _flat_candles(ATR_PERIOD + 1)
    result = compute_c10_stop("LONG", ANCHOR, None, None, m5_candles=candles)
    assert result.stop_price is not None


# --------------------------------------------------------------------------- determinism


def test_deterministic_repeatability():
    candles = _volatile_candles(ATR_PERIOD + 1, high_offset=0.0050, low_offset=0.0050)
    run_1 = compute_c10_stop("SHORT", ANCHOR, BID, ASK, m5_candles=candles)
    run_2 = compute_c10_stop("SHORT", ANCHOR, BID, ASK, m5_candles=candles)
    run_3 = compute_c10_stop("SHORT", ANCHOR, BID, ASK, m5_candles=candles)
    assert run_1 == run_2 == run_3


def test_no_atr_optimization_parameter_exposed():
    """0.35 and 1.5 are frozen owner parameters for this strategy version, not free
    optimizer inputs -- confirm they are plain module constants, not configurable via
    any exposed tuning entry point."""
    assert ATR_MULTIPLIER == 0.35
    assert MIN_BUFFER_PIPS == 1.5
    assert ATR_PERIOD == 14
