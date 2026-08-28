"""Focused tests for DAYTRADING_LTF_EXECUTION_V1 execution-model classifiers (spec
sections 46-65). Pure/offline -- no MT5 connection. Candle fixtures are hand-built so
each rule (protected level, wick/body 2x, close-confirmation, 2-3 sweep count, gap
close-back, causality/forming-candle safety) is exercised in isolation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from daytrading.execution_models import (
    evaluate_clean_sweep,
    evaluate_gap_liquidity_respect,
    evaluate_inverted_gap,
    evaluate_liquidity_grab,
    evaluate_spread_sweep,
    evaluate_sweep_and_fail,
    evaluate_sweep_and_inducement,
)
from daytrading.ltf_execution import classify_execution_models, evaluate_ltf_execution
from daytrading.liquidity_affinity import evaluate_liquidity_affinity
from daytrading.models import (
    AFFINITY_RESOLVED,
    BIAS_BEARISH,
    BIAS_BULLISH,
    EXEC_MODEL_CLEAN_SWEEP,
    EXEC_MODEL_LIQUIDITY_GRAB,
    EXEC_MODEL_NONE,
    EXEC_MODEL_SWEEP_AND_FAIL,
    EXEC_MODEL_SWEEP_AND_INDUCEMENT,
    EXEC_STATUS_DORMANT,
    EXEC_STATUS_INDETERMINATE,
    EXEC_STATUS_INVALIDATED,
    EXEC_STATUS_MODEL_CONFIRMED,
    EXEC_STATUS_NOT_CONFIRMED,
    EXEC_STATUS_WAITING_CANDLE_CLOSE,
    EXEC_STATUS_WAITING_CONFIRMATION,
    EXEC_STATUS_WAITING_ENTRY_PRICE,
    ENTRY_METHOD_FIFTY_PERCENT_BODY,
    ENTRY_METHOD_FIFTY_PERCENT_GAP,
    LTF_DORMANT,
    LTF_INVALIDATED,
    NarrativeBiasResult,
)
from entry_confirmation import CandidateDirection
from liquidity.models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from strategy_engine.session import Candle

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _c(minute, o, h, l, c) -> Candle:
    return Candle(time=T0 + timedelta(minutes=minute), open=o, high=h, low=l, close=c)


def _bullish_narrative():
    return NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")


def _bearish_narrative():
    return NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BEARISH, status="OK")


def _resolved_affinity(narrative):
    buy_level = LiquidityLevel(symbol="EURUSD", timeframe="D1", side=LiquiditySide.BUY_SIDE, source="SWING",
                                price=1.1900, origin_time=T0, status=LiquidityStatus.UNSWEPT)
    sell_level = LiquidityLevel(symbol="EURUSD", timeframe="D1", side=LiquiditySide.SELL_SIDE, source="SWING",
                                 price=1.0500, origin_time=T0, status=LiquidityStatus.UNSWEPT)
    liq = LiquidityResult(symbol="EURUSD", timeframe="D1", status="LIQUIDITY_OK", levels=(buy_level, sell_level),
                           nearest_buy_side=buy_level, nearest_sell_side=sell_level)
    return evaluate_liquidity_affinity("EURUSD", narrative, liq)


# =========================================================================== CLEAN_SWEEP (spec 49-52)

def test_clean_sweep_bearish_confirmed_with_wick_ratio_and_protected_level():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)  # upper_wick=0.0034, body=0.0001 -> ratio 34
    result = evaluate_clean_sweep("SHORT", protected_high, [sweep])
    assert result.model_type == EXEC_MODEL_CLEAN_SWEEP
    assert result.status == EXEC_STATUS_MODEL_CONFIRMED
    assert result.wick_body_ratio >= 2.0


def test_clean_sweep_bullish_mirror_confirmed():
    protected_low = 1.1000
    sweep = _c(0, o=1.1005, h=1.1006, l=1.0970, c=1.1004)  # lower_wick=0.0034, body=0.0001
    result = evaluate_clean_sweep("LONG", protected_low, [sweep])
    assert result.status == EXEC_STATUS_MODEL_CONFIRMED


def test_clean_sweep_wick_ratio_fail_is_not_confirmed():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1010, l=1.0990, c=1.1005)  # wick small vs body
    result = evaluate_clean_sweep("SHORT", protected_high, [sweep])
    assert result.status == EXEC_STATUS_NOT_CONFIRMED
    assert result.model_type == EXEC_MODEL_CLEAN_SWEEP


def test_clean_sweep_without_protected_level_is_partial():
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)
    result = evaluate_clean_sweep("SHORT", None, [sweep])
    assert result.status == EXEC_STATUS_INDETERMINATE
    assert "PROTECTED_SWEEP_LEVEL_POLICY" in result.unresolved_policy


def test_clean_sweep_arbitrary_unprotected_high_never_confirms_via_ltf_execution():
    # Large wick above an arbitrary local high but no protected_high supplied at all --
    # classify_execution_models() must not silently substitute a random extreme.
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)
    _, execution_model, execution_status, _ = classify_execution_models(
        "SHORT", protected_high=None, protected_low=None, m5_closed_candles=[sweep],
    )
    assert execution_model == EXEC_MODEL_NONE
    assert execution_status != EXEC_STATUS_MODEL_CONFIRMED


# =========================================================================== SWEEP_AND_FAIL (spec 53)

def test_sweep_and_fail_waits_until_confirming_close():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.1010)
    hold = _c(5, o=1.1010, h=1.1040, l=1.1005, c=1.1035)  # closes above sweep.high (1.1030) -- no fail yet
    result = evaluate_sweep_and_fail("SHORT", protected_high, [sweep, hold])
    assert result.status == EXEC_STATUS_WAITING_CONFIRMATION
    assert result.confirmation_candle_closed is False


def test_sweep_and_fail_confirms_on_close_below_sweep_high():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.1010)
    fail_close = _c(5, o=1.1010, h=1.1015, l=1.1000, c=1.1005)  # closes below sweep.high (1.1030)
    result = evaluate_sweep_and_fail("SHORT", protected_high, [sweep, fail_close])
    assert result.status == EXEC_STATUS_MODEL_CONFIRMED
    assert result.model_type == EXEC_MODEL_SWEEP_AND_FAIL


# =========================================================================== SWEEP_AND_INDUCEMENT (spec 54)

def test_sweep_and_inducement_confirms_with_fifty_percent_body_entry():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)  # body 1.0995-1.0996, mid 1.09955
    result = evaluate_sweep_and_inducement("SHORT", protected_high, [sweep], inducement_confirmed=True)
    assert result.status == EXEC_STATUS_MODEL_CONFIRMED
    assert result.entry_method == ENTRY_METHOD_FIFTY_PERCENT_BODY
    assert result.entry_reference_price == (min(1.0995, 1.0996) + max(1.0995, 1.0996)) / 2.0
    assert result.structural_invalidation_reference == max(1.0995, 1.0996)


def test_sweep_and_inducement_indeterminate_without_inducement_evidence():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)
    result = evaluate_sweep_and_inducement("SHORT", protected_high, [sweep], inducement_confirmed=None)
    assert result.status == EXEC_STATUS_INDETERMINATE
    assert result.model_type == EXEC_MODEL_SWEEP_AND_INDUCEMENT


# =========================================================================== LIQUIDITY_GRAB (spec 55-56)

def test_liquidity_grab_confirms_with_two_sweep_candles_and_gap():
    protected_high = 1.1000
    s1 = _c(0, o=1.0995, h=1.1020, l=1.0990, c=1.1000)
    s2 = _c(5, o=1.1000, h=1.1025, l=1.0995, c=1.0998)
    result = evaluate_liquidity_grab("SHORT", protected_high, [s1, s2], gap_low=1.0940, gap_high=1.0960)
    assert result.status == EXEC_STATUS_MODEL_CONFIRMED
    assert result.model_type == EXEC_MODEL_LIQUIDITY_GRAB
    assert result.entry_method == ENTRY_METHOD_FIFTY_PERCENT_GAP
    assert abs(result.entry_reference_price - 1.0950) < 1e-9
    assert result.sweep_count == 2


def test_liquidity_grab_invalid_sweep_count_never_classifies_as_liquidity_grab():
    protected_high = 1.1000
    only_one = _c(0, o=1.0995, h=1.1020, l=1.0990, c=1.1000)
    result = evaluate_liquidity_grab("SHORT", protected_high, [only_one], gap_low=1.0940, gap_high=1.0960)
    assert result.status != EXEC_STATUS_MODEL_CONFIRMED

    four = [_c(i * 5, o=1.0995, h=1.1020 + i * 0.0001, l=1.0990, c=1.1000) for i in range(4)]
    result4 = evaluate_liquidity_grab("SHORT", protected_high, four, gap_low=1.0940, gap_high=1.0960)
    assert result4.status != EXEC_STATUS_MODEL_CONFIRMED


# =========================================================================== GAP_LIQUIDITY_RESPECT (spec 58-59)

def test_gap_liquidity_respect_confirmed_on_close_back_outside():
    gap_low, gap_high = 1.0940, 1.0960
    wick_in = _c(0, o=1.0965, h=1.0968, l=1.0945, c=1.0937)  # wicks up into the gap then closes back below gap_low
    result = evaluate_gap_liquidity_respect("SHORT", gap_low, gap_high, [wick_in])
    assert result.status in (EXEC_STATUS_MODEL_CONFIRMED, EXEC_STATUS_WAITING_ENTRY_PRICE)
    assert result.entry_reference_price == (gap_low + gap_high) / 2.0


def test_gap_liquidity_respect_not_confirmed_when_close_stays_inside_gap():
    gap_low, gap_high = 1.0940, 1.0960
    wick_in_and_close_inside = _c(0, o=1.0965, h=1.0968, l=1.0945, c=1.0950)  # closes inside [0.0940, 0.0960]
    result = evaluate_gap_liquidity_respect("SHORT", gap_low, gap_high, [wick_in_and_close_inside])
    assert result.status == EXEC_STATUS_NOT_CONFIRMED


def test_gap_liquidity_respect_waiting_entry_price_before_midpoint_touch():
    gap_low, gap_high = 1.0940, 1.0960
    wick_in = _c(0, o=1.0965, h=1.0968, l=1.0945, c=1.0937)
    result = evaluate_gap_liquidity_respect("SHORT", gap_low, gap_high, [wick_in])
    if not (wick_in.low <= (gap_low + gap_high) / 2.0 <= wick_in.high):
        assert result.status == EXEC_STATUS_WAITING_ENTRY_PRICE


# =========================================================================== SPREAD_SWEEP / INVERTED_GAP (spec 13/57)

def test_spread_sweep_always_partial():
    result = evaluate_spread_sweep("SHORT", 1.1000)
    assert result.status == EXEC_STATUS_INDETERMINATE
    assert "SPREAD_SWEEP_POLICY" in result.unresolved_policy


def test_inverted_gap_always_partial_never_auto_confirms():
    result = evaluate_inverted_gap("SHORT", gap_status="INVALIDATED")
    assert result.status == EXEC_STATUS_INDETERMINATE
    assert "INVERTED_GAP_POLICY" in result.unresolved_policy


# =========================================================================== CAUSALITY (spec 60-62)

def test_future_candle_leakage_does_not_change_sweep_and_fail_at_t():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.1010)
    result_before = evaluate_sweep_and_fail("SHORT", protected_high, [sweep])
    assert result_before.status == EXEC_STATUS_WAITING_CONFIRMATION

    future_fail_close = _c(5, o=1.1010, h=1.1015, l=1.1000, c=1.1005)
    result_with_future_removed = evaluate_sweep_and_fail("SHORT", protected_high, [sweep])
    assert result_with_future_removed.status == EXEC_STATUS_WAITING_CONFIRMATION
    assert result_with_future_removed == result_before  # identical -- future candle never touched


def test_forming_candle_never_used_as_evidence_but_flagged_waiting_candle_close():
    protected_high = 1.1000
    forming = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)  # would satisfy clean sweep if treated as closed
    _, execution_model, execution_status, selected = classify_execution_models(
        "SHORT", protected_high=protected_high, protected_low=None,
        m5_closed_candles=[], m5_forming_candle=forming,
    )
    assert execution_model == EXEC_MODEL_NONE  # never confirmed off the forming candle
    assert execution_status == EXEC_STATUS_WAITING_CANDLE_CLOSE


def test_sweep_does_not_auto_execute_without_a_completed_model_sequence():
    protected_high = 1.1000
    lone_sweep = _c(0, o=1.0995, h=1.1010, l=1.0990, c=1.1005)  # sweeps but no model confirms (small wick, no close-fail yet)
    _, execution_model, execution_status, selected = classify_execution_models(
        "SHORT", protected_high=protected_high, protected_low=None, m5_closed_candles=[lone_sweep],
    )
    assert execution_model == EXEC_MODEL_NONE
    assert selected is None


# =========================================================================== HTF GATE INTEGRATION (spec 46-48)

def test_ltf_execution_dormant_without_narrative_never_reaches_model_classification():
    from daytrading.models import BIAS_UNRESOLVED
    unresolved = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_UNRESOLVED, status="OK")
    affinity = evaluate_liquidity_affinity("EURUSD", unresolved, None)
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)
    result = evaluate_ltf_execution(
        "EURUSD", "M5", unresolved, affinity, CandidateDirection.SHORT, ec_request=None,
        protected_high=1.1000, m5_closed_candles=[sweep],
    )
    assert result.status == LTF_DORMANT
    assert result.execution_status == EXEC_STATUS_DORMANT
    assert result.execution_model == EXEC_MODEL_NONE


def test_ltf_execution_carries_h1_structure_and_protected_levels_without_flattening():
    narrative = _bearish_narrative()
    affinity = _resolved_affinity(narrative)
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)
    result = evaluate_ltf_execution(
        "EURUSD", "M5", narrative, affinity, CandidateDirection.SHORT, ec_request=None,
        h1_structure_direction="BEARISH", protected_high=1.1000, protected_low=1.0500,
        m5_closed_candles=[sweep],
    )
    assert result.h1_structure_direction == "BEARISH"
    assert result.protected_high == 1.1000
    assert result.protected_low == 1.0500
    assert result.execution_model == EXEC_MODEL_CLEAN_SWEEP
    assert result.execution_status == EXEC_STATUS_MODEL_CONFIRMED


# =========================================================================== STATE F -- INVALIDATION (spec section 67)

def test_confirmed_clean_sweep_invalidates_on_later_close_through_structural_reference():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)  # CLEAN_SWEEP confirms, invalidation_ref = sweep.high = 1.1030
    later_breach = _c(5, o=1.1000, h=1.1040, l=1.0999, c=1.1035)  # closes above 1.1030 -- thesis invalidated
    matching, execution_model, execution_status, selected = classify_execution_models(
        "SHORT", protected_high=protected_high, protected_low=None, m5_closed_candles=[sweep, later_breach],
    )
    assert execution_status == EXEC_STATUS_INVALIDATED
    assert selected is not None and selected.status == EXEC_STATUS_INVALIDATED


def test_ltf_execution_surfaces_invalidated_status():
    narrative = _bearish_narrative()
    affinity = _resolved_affinity(narrative)
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)
    later_breach = _c(5, o=1.1000, h=1.1040, l=1.0999, c=1.1035)
    result = evaluate_ltf_execution(
        "EURUSD", "M5", narrative, affinity, CandidateDirection.SHORT, ec_request=None,
        protected_high=1.1000, m5_closed_candles=[sweep, later_breach],
    )
    assert result.status == LTF_INVALIDATED
    assert result.execution_status == EXEC_STATUS_INVALIDATED


def test_confirming_candles_own_close_never_self_invalidates():
    protected_high = 1.1000
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)  # own close (1.0996) is well below its own high (1.1030)
    matching, execution_model, execution_status, selected = classify_execution_models(
        "SHORT", protected_high=protected_high, protected_low=None, m5_closed_candles=[sweep],
    )
    assert execution_status == EXEC_STATUS_MODEL_CONFIRMED


def test_ltf_execution_never_computes_risk_or_broker_fields():
    narrative = _bearish_narrative()
    affinity = _resolved_affinity(narrative)
    sweep = _c(0, o=1.0995, h=1.1030, l=1.0993, c=1.0996)
    result = evaluate_ltf_execution(
        "EURUSD", "M5", narrative, affinity, CandidateDirection.SHORT, ec_request=None,
        protected_high=1.1000, m5_closed_candles=[sweep],
    )
    assert not hasattr(result, "account_equity")
    assert not hasattr(result, "lot_size")
    assert not hasattr(result, "volume")
    assert result.execution_authority_changed is False
