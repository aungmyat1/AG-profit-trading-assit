"""Tests for entry_confirmation/ (ENTRY_CONFIRMATION_V1). Deterministic-fact tests only
-- no outcome/profitability testing, per the mission's 'unit test philosophy'."""
from __future__ import annotations

import datetime as dt

import pytest

from entry_confirmation import (
    DISPLACEMENT,
    LIQUIDITY_RECLAIM,
    REJECTION,
    STRUCTURE_SHIFT,
    CandidateDirection,
    ConfirmationState,
    EntryConfirmationRequest,
    OverallState,
    evaluate_entry_confirmation,
)
from entry_confirmation.displacement import evaluate_displacement, measure_candle as measure_displacement
from entry_confirmation.liquidity_alignment import evaluate_liquidity_alignment
from entry_confirmation.rejection import evaluate_rejection, measure_candle as measure_rejection
from entry_confirmation.structure_alignment import evaluate_structure_alignment
from liquidity import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from market_structure import STATE_BULLISH, StructurePoint, StructurePointKind, StructureResult
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _candle(o, h, l, c, hour=10):
    return Candle(time=dt.datetime(2026, 1, 5, hour, 0, tzinfo=UTC), open=o, high=h, low=l, close=c, volume=1.0)


def _structure_result(choch_kind=None, choch_time=None, choch_price=1.1, status="VALID"):
    latest_choch = None
    if choch_kind is not None:
        latest_choch = StructurePoint(time_utc=choch_time or dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
                                       price=choch_price, kind=choch_kind)
    return StructureResult(symbol="EURUSD", timeframe="M15", status=status, reason_codes=(),
                            state=STATE_BULLISH, latest_choch=latest_choch)


def _liquidity_result(sell_side_status=None, buy_side_status=None, reclaim_time=None):
    nearest_sell = None
    nearest_buy = None
    if sell_side_status is not None:
        nearest_sell = LiquidityLevel(symbol="EURUSD", timeframe="M15", side=LiquiditySide.SELL_SIDE,
                                       source="SWING_LOW", price=1.0950, origin_time=None,
                                       status=sell_side_status, reclaim_time=reclaim_time)
    if buy_side_status is not None:
        nearest_buy = LiquidityLevel(symbol="EURUSD", timeframe="M15", side=LiquiditySide.BUY_SIDE,
                                      source="SWING_HIGH", price=1.1050, origin_time=None,
                                      status=buy_side_status, reclaim_time=reclaim_time)
    return LiquidityResult(symbol="EURUSD", timeframe="M15", status="LIQUIDITY_OK",
                            nearest_buy_side=nearest_buy, nearest_sell_side=nearest_sell)


# --------------------------------------------------------------------------- displacement

def test_displacement_bullish_candle_measurements():
    m = measure_displacement(_candle(1.1000, 1.1050, 1.0990, 1.1040))
    assert m["direction"] == "BULLISH"
    assert m["body_size"] == pytest.approx(0.0040)
    assert m["range_size"] == pytest.approx(0.0060)
    assert m["body_ratio"] == pytest.approx(0.0040 / 0.0060)


def test_displacement_bearish_candle_measurements():
    m = measure_displacement(_candle(1.1040, 1.1050, 1.0990, 1.1000))
    assert m["direction"] == "BEARISH"
    assert m["body_ratio"] == pytest.approx(0.0040 / 0.0060)


def test_displacement_doji_zero_body():
    m = measure_displacement(_candle(1.1000, 1.1050, 1.0990, 1.1000))
    assert m["direction"] == "NEUTRAL"
    assert m["body_size"] == 0.0


def test_displacement_zero_range_no_division_error():
    m = measure_displacement(_candle(1.1000, 1.1000, 1.1000, 1.1000))
    assert m["range_size"] == 0.0
    assert m["body_ratio"] == 1.0
    assert m["close_location"] == 0.5


def test_displacement_missing_candle_is_unavailable():
    ev = evaluate_displacement(None)
    assert ev.status == ConfirmationState.UNAVAILABLE


def test_displacement_qualification_insufficient_without_direction():
    # AG_ENTRY_DISPLACEMENT_V1 (see displacement.py) needs candidate_direction to check
    # direction alignment -- omitting it fails closed rather than guessing a direction.
    ev = evaluate_displacement(_candle(1.1000, 1.1050, 1.0990, 1.1040))
    assert ev.status == ConfirmationState.INSUFFICIENT_DATA
    assert ev.rule_version == "AG_ENTRY_DISPLACEMENT_V1"


def _bodies(*bodies):
    """Prior candles (oldest first), each with the given |close-open|, all dated on
    2026-01-04 -- strictly before every displacement candle under test (2026-01-05)."""
    out = []
    for i, body in enumerate(bodies):
        o = 1.1000
        c = o + body
        out.append(Candle(time=dt.datetime(2026, 1, 4, i % 24, 0, tzinfo=UTC),
                           open=o, high=max(o, c) + 0.0005, low=min(o, c) - 0.0005, close=c, volume=1.0))
    return out


def test_displacement_bullish_qualified_pass():
    history = _bodies(*([0.0010] * 20))  # median_body_20 = 0.0010
    candle = _candle(1.1000, 1.1042, 1.0998, 1.1040)  # range 0.0044, body 0.0040
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.body_ratio == pytest.approx(0.0040 / 0.0044)
    assert ev.body_ratio >= 0.60
    assert ev.relative_body == pytest.approx(4.0)
    assert ev.status == ConfirmationState.PASS
    assert ev.rule_version == "AG_ENTRY_DISPLACEMENT_V1"


def test_displacement_bearish_qualified_pass():
    history = _bodies(*([0.0010] * 20))
    candle = _candle(1.1040, 1.1042, 1.0998, 1.1000)  # bearish, same magnitude
    ev = evaluate_displacement(candle, CandidateDirection.SHORT, history)
    assert ev.status == ConfirmationState.PASS


def test_displacement_wrong_direction_fails():
    history = _bodies(*([0.0010] * 20))
    candle = _candle(1.1000, 1.1042, 1.0998, 1.1040)  # bullish candle
    ev = evaluate_displacement(candle, CandidateDirection.SHORT, history)  # SELL requested
    assert ev.status == ConfirmationState.FAIL
    assert "direction" in ev.reason


def test_displacement_body_ratio_exact_boundary_passes():
    history = _bodies(*([0.0001] * 20))  # tiny median so relative_body condition trivially passes
    # open 1.1000, close 1.1060 -> body 0.0060; high 1.1090, low 1.0990 -> range 0.0100
    candle = _candle(1.1000, 1.1090, 1.0990, 1.1060)
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.body_ratio == pytest.approx(0.60)
    assert ev.status == ConfirmationState.PASS


def test_displacement_body_ratio_just_below_boundary_fails():
    history = _bodies(*([0.0001] * 20))
    # body 0.00599, range 0.0100 -> body_ratio just under 0.60
    candle = _candle(1.1000, 1.1090, 1.0990, 1.10599)
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.body_ratio < 0.60
    assert ev.status == ConfirmationState.FAIL


def test_displacement_relative_body_exact_boundary_passes():
    history = _bodies(*([0.0010] * 20))  # median 0.0010, 1.30x = 0.0013
    candle = _candle(1.1000, 1.1015, 1.0999, 1.1013)  # body 0.0013, range 0.0016
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.median_body == pytest.approx(0.0010)
    assert ev.body_size == pytest.approx(0.0013)
    assert ev.status == ConfirmationState.PASS


def test_displacement_relative_body_just_below_boundary_fails():
    history = _bodies(*([0.0010] * 20))  # 1.30x = 0.0013
    candle = _candle(1.1000, 1.1015, 1.0999, 1.10129)  # body 0.00129 < 0.0013
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.body_size < 1.30 * ev.median_body
    assert ev.status == ConfirmationState.FAIL


def test_displacement_zero_range_candle_is_insufficient_data():
    history = _bodies(*([0.0010] * 20))
    candle = _candle(1.1000, 1.1000, 1.1000, 1.1000)
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.status == ConfirmationState.INSUFFICIENT_DATA


def test_displacement_insufficient_history_is_insufficient_data():
    history = _bodies(*([0.0010] * 19))  # one short of 20
    candle = _candle(1.1000, 1.1042, 1.0998, 1.1040)
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.status == ConfirmationState.INSUFFICIENT_DATA
    assert "20" in ev.reason


def test_displacement_history_after_candidate_is_excluded():
    # A caller bug supplying a "future" candle in history must not silently inflate the
    # reference sample -- median_body_20 still requires 20 genuinely-prior candles.
    history = _bodies(*([0.0010] * 20))
    future_candle = Candle(time=dt.datetime(2026, 1, 6, 0, 0, tzinfo=UTC),
                            open=1.1000, high=1.1002, low=1.0998, close=1.1001, volume=1.0)
    candle = _candle(1.1000, 1.1042, 1.0998, 1.1040)  # 2026-01-05, after history, before future_candle
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history + [future_candle])
    assert ev.status == ConfirmationState.PASS
    assert ev.median_body == pytest.approx(0.0010)  # future candle excluded, not counted


def test_displacement_median_reference_excludes_candidate_itself():
    # Median must be computed from history only, never influenced by the evaluated
    # candle's own (large) body.
    history = _bodies(*([0.0010] * 20))
    candle = _candle(1.1000, 1.1042, 1.0998, 1.1040)  # large body, same timestamp as history end+1
    ev = evaluate_displacement(candle, CandidateDirection.LONG, history)
    assert ev.median_body == pytest.approx(0.0010)  # not pulled up by the 0.0040 candidate body


# --------------------------------------------------------------------------- rejection

def test_rejection_measurements_upper_lower_wicks():
    m = measure_rejection(_candle(1.1000, 1.1050, 1.0980, 1.1010))
    assert m["upper_wick"] == pytest.approx(1.1050 - 1.1010)
    assert m["lower_wick"] == pytest.approx(1.1000 - 1.0980)
    assert m["range_size"] == pytest.approx(1.1050 - 1.0980)


def test_rejection_zero_range_no_division_error():
    m = measure_rejection(_candle(1.1000, 1.1000, 1.1000, 1.1000))
    assert m["upper_wick_ratio"] == 0.0
    assert m["lower_wick_ratio"] == 0.0
    assert m["close_location"] == 0.5


def test_rejection_missing_candle_is_unavailable():
    assert evaluate_rejection(None).status == ConfirmationState.UNAVAILABLE


def test_rejection_qualification_is_unsigned_by_default():
    ev = evaluate_rejection(_candle(1.1000, 1.1050, 1.0980, 1.1010))
    assert ev.status == ConfirmationState.UNSIGNED_RULE
    assert ev.qualification == "UNSIGNED_RULE"


# --------------------------------------------------------------------------- structure alignment

def test_structure_alignment_long_bullish_choch_passes():
    sr = _structure_result(choch_kind=StructurePointKind.BULLISH_CHOCH)
    r = evaluate_structure_alignment(sr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.PASS


def test_structure_alignment_long_bearish_choch_fails():
    sr = _structure_result(choch_kind=StructurePointKind.BEARISH_CHOCH)
    r = evaluate_structure_alignment(sr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.FAIL


def test_structure_alignment_short_bearish_choch_passes():
    sr = _structure_result(choch_kind=StructurePointKind.BEARISH_CHOCH)
    r = evaluate_structure_alignment(sr, CandidateDirection.SHORT)
    assert r.status == ConfirmationState.PASS


def test_structure_alignment_short_bullish_choch_fails():
    sr = _structure_result(choch_kind=StructurePointKind.BULLISH_CHOCH)
    r = evaluate_structure_alignment(sr, CandidateDirection.SHORT)
    assert r.status == ConfirmationState.FAIL


def test_structure_alignment_no_event_is_unavailable():
    sr = _structure_result(choch_kind=None)
    r = evaluate_structure_alignment(sr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.UNAVAILABLE


def test_structure_alignment_invalid_result_is_insufficient_data():
    sr = _structure_result(choch_kind=StructurePointKind.BULLISH_CHOCH, status="MARKET_DATA_ERROR")
    r = evaluate_structure_alignment(sr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.INSUFFICIENT_DATA


def test_structure_alignment_missing_result_is_unavailable():
    r = evaluate_structure_alignment(None, CandidateDirection.LONG)
    assert r.status == ConfirmationState.UNAVAILABLE


def test_structure_alignment_stale_event_fails():
    sr = _structure_result(choch_kind=StructurePointKind.BULLISH_CHOCH,
                            choch_time=dt.datetime(2026, 1, 1, tzinfo=UTC))
    r = evaluate_structure_alignment(sr, CandidateDirection.LONG,
                                      reference_time=dt.datetime(2026, 1, 5, tzinfo=UTC))
    assert r.status == ConfirmationState.FAIL


# --------------------------------------------------------------------------- liquidity alignment

def test_liquidity_alignment_long_sell_side_reclaimed_passes():
    lr = _liquidity_result(sell_side_status=LiquidityStatus.RECLAIMED)
    r = evaluate_liquidity_alignment(lr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.PASS


def test_liquidity_alignment_long_buy_side_reclaimed_not_aligned():
    lr = _liquidity_result(buy_side_status=LiquidityStatus.RECLAIMED)  # no sell-side level at all
    r = evaluate_liquidity_alignment(lr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.FAIL


def test_liquidity_alignment_short_buy_side_reclaimed_passes():
    lr = _liquidity_result(buy_side_status=LiquidityStatus.RECLAIMED)
    r = evaluate_liquidity_alignment(lr, CandidateDirection.SHORT)
    assert r.status == ConfirmationState.PASS


def test_liquidity_alignment_short_sell_side_reclaimed_not_aligned():
    lr = _liquidity_result(sell_side_status=LiquidityStatus.RECLAIMED)
    r = evaluate_liquidity_alignment(lr, CandidateDirection.SHORT)
    assert r.status == ConfirmationState.FAIL


def test_liquidity_alignment_unswept_fails():
    lr = _liquidity_result(sell_side_status=LiquidityStatus.UNSWEPT)
    r = evaluate_liquidity_alignment(lr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.FAIL


def test_liquidity_alignment_no_data_is_unavailable():
    r = evaluate_liquidity_alignment(None, CandidateDirection.LONG)
    assert r.status == ConfirmationState.UNAVAILABLE


def test_liquidity_alignment_swept_not_yet_confirmed_is_insufficient_data():
    lr = _liquidity_result(sell_side_status=LiquidityStatus.SWEPT)
    r = evaluate_liquidity_alignment(lr, CandidateDirection.LONG)
    assert r.status == ConfirmationState.INSUFFICIENT_DATA


# --------------------------------------------------------------------------- request/engine

def test_unrequested_primitive_is_not_requested():
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15",
                                    candidate_direction=CandidateDirection.LONG,
                                    requested_confirmations=(DISPLACEMENT,),
                                    candidate_candle=_candle(1.1000, 1.1050, 1.0990, 1.1040))
    result = evaluate_entry_confirmation(req)
    # No candidate_direction/history supplied on this request -> INSUFFICIENT_DATA,
    # not UNSIGNED_RULE (AG_ENTRY_DISPLACEMENT_V1 is signed; it just lacks inputs here).
    assert result.displacement.status == ConfirmationState.INSUFFICIENT_DATA
    assert result.structure_shift.status == ConfirmationState.NOT_REQUESTED
    assert result.liquidity_reclaim.status == ConfirmationState.NOT_REQUESTED
    assert result.rejection.status == ConfirmationState.NOT_REQUESTED


def test_engine_rejects_unknown_confirmation_key():
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15",
                                    requested_confirmations=("not_a_real_primitive",))
    with pytest.raises(ValueError):
        evaluate_entry_confirmation(req)


# --------------------------------------------------------------------------- aggregation

def test_aggregation_all_pass_is_confirmed():
    sr = _structure_result(choch_kind=StructurePointKind.BULLISH_CHOCH)
    lr = _liquidity_result(sell_side_status=LiquidityStatus.RECLAIMED)
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15",
                                    candidate_direction=CandidateDirection.LONG,
                                    requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM),
                                    structure_result=sr, liquidity_result=lr)
    result = evaluate_entry_confirmation(req)
    assert result.overall_state == OverallState.CONFIRMED


def test_aggregation_mixed_is_partial():
    sr = _structure_result(choch_kind=StructurePointKind.BULLISH_CHOCH)
    lr = _liquidity_result(sell_side_status=LiquidityStatus.UNSWEPT)
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15",
                                    candidate_direction=CandidateDirection.LONG,
                                    requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM),
                                    structure_result=sr, liquidity_result=lr)
    result = evaluate_entry_confirmation(req)
    assert result.overall_state == OverallState.PARTIAL


def test_aggregation_all_fail_is_not_confirmed():
    sr = _structure_result(choch_kind=StructurePointKind.BEARISH_CHOCH)
    lr = _liquidity_result(sell_side_status=LiquidityStatus.UNSWEPT)
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15",
                                    candidate_direction=CandidateDirection.LONG,
                                    requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM),
                                    structure_result=sr, liquidity_result=lr)
    result = evaluate_entry_confirmation(req)
    assert result.overall_state == OverallState.NOT_CONFIRMED


def test_aggregation_unsigned_rule_makes_overall_indeterminate():
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15",
                                    candidate_direction=CandidateDirection.LONG,
                                    requested_confirmations=(DISPLACEMENT,),
                                    candidate_candle=_candle(1.1000, 1.1050, 1.0990, 1.1040))
    result = evaluate_entry_confirmation(req)
    assert result.overall_state == OverallState.INDETERMINATE


def test_aggregation_no_requested_confirmations_is_indeterminate():
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15")
    result = evaluate_entry_confirmation(req)
    assert result.overall_state == OverallState.INDETERMINATE


def test_missing_requirements_lists_unavailable_and_insufficient():
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15",
                                    candidate_direction=CandidateDirection.LONG,
                                    requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM))
    result = evaluate_entry_confirmation(req)
    assert set(result.missing_requirements) == {STRUCTURE_SHIFT, LIQUIDITY_RECLAIM}


# --------------------------------------------------------------------------- event sequencing

def _sequenced_request(liquidity_time, structure_time, displacement_time, direction=CandidateDirection.SHORT):
    choch_kind = StructurePointKind.BEARISH_CHOCH if direction == CandidateDirection.SHORT else StructurePointKind.BULLISH_CHOCH
    sell_status = LiquidityStatus.RECLAIMED if direction == CandidateDirection.LONG else None
    buy_status = LiquidityStatus.RECLAIMED if direction == CandidateDirection.SHORT else None
    sr = _structure_result(choch_kind=choch_kind, choch_time=structure_time)
    lr = _liquidity_result(sell_side_status=sell_status, buy_side_status=buy_status, reclaim_time=liquidity_time)
    history = _bodies(*([0.0010] * 20))
    body = 0.0040 if direction == CandidateDirection.SHORT else -0.0040
    candle = Candle(time=displacement_time, open=1.1040, high=1.1050 if direction == CandidateDirection.LONG else 1.1042,
                     low=1.0998 if direction == CandidateDirection.SHORT else 1.0990,
                     close=1.1040 + body, volume=1.0)
    return EntryConfirmationRequest(
        symbol="EURUSD", timeframe="M15", candidate_direction=direction,
        requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM, DISPLACEMENT),
        structure_result=sr, liquidity_result=lr, candidate_candle=candle, candle_history=history,
    )


def test_event_sequence_valid_sell_passes():
    liquidity_time = dt.datetime(2026, 1, 5, 10, 10, tzinfo=UTC)
    structure_time = dt.datetime(2026, 1, 5, 10, 15, tzinfo=UTC)
    displacement_time = dt.datetime(2026, 1, 5, 10, 20, tzinfo=UTC)
    req = _sequenced_request(liquidity_time, structure_time, displacement_time, CandidateDirection.SHORT)
    result = evaluate_entry_confirmation(req)
    assert result.event_sequence.status == ConfirmationState.PASS


def test_event_sequence_valid_buy_passes():
    liquidity_time = dt.datetime(2026, 1, 5, 13, 5, tzinfo=UTC)
    structure_time = dt.datetime(2026, 1, 5, 13, 10, tzinfo=UTC)
    displacement_time = dt.datetime(2026, 1, 5, 13, 15, tzinfo=UTC)
    req = _sequenced_request(liquidity_time, structure_time, displacement_time, CandidateDirection.LONG)
    result = evaluate_entry_confirmation(req)
    assert result.event_sequence.status == ConfirmationState.PASS


def test_event_sequence_stale_structure_before_liquidity_fails():
    # CHoCH happened BEFORE the liquidity sweep it's supposed to confirm -- not valid.
    structure_time = dt.datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
    liquidity_time = dt.datetime(2026, 1, 5, 10, 10, tzinfo=UTC)
    displacement_time = dt.datetime(2026, 1, 5, 10, 20, tzinfo=UTC)
    req = _sequenced_request(liquidity_time, structure_time, displacement_time, CandidateDirection.SHORT)
    result = evaluate_entry_confirmation(req)
    assert result.event_sequence.status == ConfirmationState.FAIL
    assert result.overall_state != OverallState.CONFIRMED


def test_event_sequence_premature_displacement_fails():
    # Displacement happened before the liquidity event it's supposed to confirm.
    displacement_time = dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    liquidity_time = dt.datetime(2026, 1, 5, 10, 10, tzinfo=UTC)
    structure_time = dt.datetime(2026, 1, 5, 10, 15, tzinfo=UTC)
    req = _sequenced_request(liquidity_time, structure_time, displacement_time, CandidateDirection.SHORT)
    result = evaluate_entry_confirmation(req)
    assert result.event_sequence.status == ConfirmationState.FAIL


def test_event_sequence_same_candle_structure_and_displacement_passes():
    liquidity_time = dt.datetime(2026, 1, 5, 10, 10, tzinfo=UTC)
    same_time = dt.datetime(2026, 1, 5, 10, 15, tzinfo=UTC)
    req = _sequenced_request(liquidity_time, same_time, same_time, CandidateDirection.SHORT)
    result = evaluate_entry_confirmation(req)
    assert result.event_sequence.status == ConfirmationState.PASS


def test_event_sequence_missing_timestamp_is_insufficient_data():
    sr = _structure_result(choch_kind=StructurePointKind.BEARISH_CHOCH)
    lr = _liquidity_result(buy_side_status=LiquidityStatus.RECLAIMED, reclaim_time=None)  # no reclaim_time
    history = _bodies(*([0.0010] * 20))
    candle = _candle(1.1040, 1.1042, 1.0998, 1.1000)
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15", candidate_direction=CandidateDirection.SHORT,
                                    requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM, DISPLACEMENT),
                                    structure_result=sr, liquidity_result=lr, candidate_candle=candle,
                                    candle_history=history)
    result = evaluate_entry_confirmation(req)
    assert result.event_sequence.status == ConfirmationState.INSUFFICIENT_DATA
    assert result.overall_state == OverallState.INDETERMINATE


def test_event_sequence_not_requested_unless_all_three_inputs_requested():
    req = EntryConfirmationRequest(symbol="EURUSD", timeframe="M15", candidate_direction=CandidateDirection.LONG,
                                    requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM))
    result = evaluate_entry_confirmation(req)
    assert result.event_sequence.status == ConfirmationState.NOT_REQUESTED


def test_event_sequence_no_lookahead_evaluation_timestamp():
    # The confirmation as a whole must never depend on data later than the displacement
    # candle -- confirm the request contract has no "evaluate as of" field that could be
    # satisfied by a future candle: candle_history is caller-supplied and prior-filtered
    # by evaluate_displacement itself (see test_displacement_history_after_candidate_is_excluded).
    liquidity_time = dt.datetime(2026, 1, 5, 10, 10, tzinfo=UTC)
    structure_time = dt.datetime(2026, 1, 5, 10, 15, tzinfo=UTC)
    displacement_time = dt.datetime(2026, 1, 5, 10, 20, tzinfo=UTC)
    req = _sequenced_request(liquidity_time, structure_time, displacement_time, CandidateDirection.SHORT)
    result = evaluate_entry_confirmation(req)
    assert result.displacement.candle_timestamp == displacement_time
    assert all(c.time < displacement_time for c in req.candle_history)


# --------------------------------------------------------------------------- execution safety

def test_entry_confirmation_package_has_no_execution_imports():
    import ast
    import pathlib

    pkg_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "entry_confirmation"
    forbidden = {"execution", "mt5"}
    for path in pkg_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = {node.module.split(".")[0]}
            else:
                continue
            assert not (names & forbidden), f"{path} imports forbidden module(s): {names & forbidden}"
