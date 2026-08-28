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


def _liquidity_result(sell_side_status=None, buy_side_status=None):
    nearest_sell = None
    nearest_buy = None
    if sell_side_status is not None:
        nearest_sell = LiquidityLevel(symbol="EURUSD", timeframe="M15", side=LiquiditySide.SELL_SIDE,
                                       source="SWING_LOW", price=1.0950, origin_time=None,
                                       status=sell_side_status)
    if buy_side_status is not None:
        nearest_buy = LiquidityLevel(symbol="EURUSD", timeframe="M15", side=LiquiditySide.BUY_SIDE,
                                      source="SWING_HIGH", price=1.1050, origin_time=None,
                                      status=buy_side_status)
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


def test_displacement_qualification_is_unsigned_by_default():
    ev = evaluate_displacement(_candle(1.1000, 1.1050, 1.0990, 1.1040))
    assert ev.status == ConfirmationState.UNSIGNED_RULE
    assert ev.qualification == "UNSIGNED_RULE"
    assert ev.rule_version is None


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
    assert result.displacement.status == ConfirmationState.UNSIGNED_RULE
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


# --------------------------------------------------------------------------- execution safety

def test_entry_confirmation_package_has_no_execution_imports():
    import ast
    import pathlib

    pkg_dir = pathlib.Path(__file__).resolve().parent.parent / "entry_confirmation"
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
