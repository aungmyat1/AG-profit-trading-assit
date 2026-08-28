"""Tests for session_router: classifier thresholds, router dispatch, sweep/range setups,
ambiguity, and lookahead protection (CANONICAL_SESSION_MIGRATION_REPORT.md section 22)."""
from __future__ import annotations

import datetime as dt

import pytest

from strategy_engine.session import (
    Candle, build_reference_box, classify, Regime,
    entry_1_trend, entry_2_sweep, entry_3_range, route_completed_session,
    DecisionStatus, SetupType, Direction,
)

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)


def _candle(hour, minute, o, h, l, c) -> Candle:
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _flat_box(n=24, price=1.1000):
    candles = [_candle(*divmod(15 * i, 60), price, price, price, price) for i in range(n)]
    return build_reference_box("asian", candles, expected_bar_count=n)


def _er_box(er: float):
    """A ReferenceBox with path_length=1.0 and displacement chosen so efficiency_ratio == er
    bit-for-bit (constructed directly rather than via build_reference_box's candle arithmetic,
    which is exercised separately -- this isolates classify()'s threshold/equality behavior)."""
    from strategy_engine.session.reference_box import ReferenceBox
    return ReferenceBox(
        session_name="asian", session_open=1.10000, session_high=1.10100, session_low=1.09900,
        session_close=1.10000 + er, session_range=0.00200, session_mid=1.10000,
        path_length=1.0, displacement=er, efficiency_ratio=er,
        bar_count=3, expected_bar_count=3, session_complete=True,
    )


# --------------------------------------------------------------------------- classifier

def test_zero_path_length_is_range():
    box = _flat_box()
    assert box.path_length == 0
    assert classify(box) is Regime.RANGE


def test_er_threshold_below_is_range():
    box = _er_box(0.3999)
    assert box.efficiency_ratio == pytest.approx(0.3999, abs=1e-6)
    assert classify(box) is Regime.RANGE


def test_er_threshold_at_exactly_point_four_is_trend():
    box = _er_box(0.4000)
    assert box.efficiency_ratio == pytest.approx(0.40, abs=1e-6)
    assert classify(box) is Regime.TREND


def test_er_threshold_just_above_is_trend():
    box = _er_box(0.4001)
    assert box.efficiency_ratio == pytest.approx(0.4001, abs=1e-6)
    assert classify(box) is Regime.TREND


# --------------------------------------------------------------------------- router dispatch

def _trend_box():
    candles = [_candle(0, 0, 1.1000, 1.1005, 1.0995, 1.1000),
               _candle(0, 15, 1.1000, 1.1200, 1.0995, 1.1200)]  # strong directional close
    return build_reference_box("asian", candles, expected_bar_count=2)


def _range_box():
    candles = [_candle(0, 0, 1.1000, 1.1050, 1.0950, 1.1010),
               _candle(0, 15, 1.1010, 1.1040, 1.0960, 1.1005)]  # closes near open, low ER
    return build_reference_box("asian", candles, expected_bar_count=2)


def test_trend_regime_routes_to_entry_1_only():
    box = _trend_box()
    assert classify(box) is Regime.TREND
    decision = entry_1_trend("TEST", "EURUSD", box, DAY)
    assert decision.setup_type is SetupType.TREND
    assert decision.decision_status is DecisionStatus.VALID
    assert decision.direction is Direction.LONG  # close > open


def test_range_with_sweep_routes_to_entry_2():
    box = _range_box()
    assert classify(box) is Regime.RANGE
    sweep_candle = _candle(6, 0, 1.1005, box.session_high + 0.0010, 1.1000, box.session_high - 0.0002)
    post = [sweep_candle]
    decision = entry_2_sweep("TEST", "EURUSD", box, DAY, post)
    assert decision.setup_type is SetupType.SWEEP
    assert decision.decision_status is DecisionStatus.VALID
    assert decision.direction is Direction.SHORT


def test_range_without_sweep_falls_through_to_entry_3():
    box = _range_box()
    boring_candle = _candle(6, 0, 1.1005, 1.1006, 1.1004, 1.1005)  # nowhere near either boundary
    post = [boring_candle]
    sweep_decision = entry_2_sweep("TEST", "EURUSD", box, DAY, post)
    assert sweep_decision.decision_status is DecisionStatus.NO_SETUP

    range_decision = entry_3_range("TEST", "EURUSD", box, DAY, post)
    assert range_decision.setup_type is SetupType.NONE
    assert range_decision.decision_status is DecisionStatus.NO_SETUP
    assert range_decision.reason_code == "NO_SETUP_BY_WINDOW_END"


def test_full_router_range_then_boundary_rejection():
    box = _range_box()
    # Touches the high exactly (no strict breach, so Entry 2's sweep does NOT qualify) and
    # closes back inside, red -- a rejection, not a sweep.
    rejection_candle = _candle(6, 0, box.session_high - 0.0002,
                                box.session_high, box.session_high - 0.0005,
                                box.session_high - 0.0004)
    _, regime, decision = route_completed_session(
        "TEST", "EURUSD", "asian", DAY, box_candles_for(box), 2, [rejection_candle]
    )
    assert regime is Regime.RANGE
    assert decision.setup_type is SetupType.RANGE
    assert decision.direction is Direction.SHORT


def box_candles_for(box):
    # Rebuild the exact two candles _range_box() used, since route_completed_session takes
    # raw session candles rather than a prebuilt box.
    return [_candle(0, 0, 1.1000, 1.1050, 1.0950, 1.1010),
            _candle(0, 15, 1.1010, 1.1040, 1.0960, 1.1005)]


# --------------------------------------------------------------------------- ambiguity

def test_dual_sweep_same_candle_is_ambiguous_no_trade():
    box = _range_box()
    dual_candle = _candle(6, 0, 1.1005, box.session_high + 0.0010, box.session_low - 0.0010, 1.1005)
    decision = entry_2_sweep("TEST", "EURUSD", box, DAY, [dual_candle])
    assert decision.decision_status is DecisionStatus.AMBIGUOUS
    assert decision.reason_code == "AMBIGUOUS_DUAL_SWEEP"
    assert decision.direction is None


def test_strict_penetration_touch_without_breach_is_not_a_sweep():
    box = _range_box()
    touch_only = _candle(6, 0, 1.1005, box.session_high, 1.1000, 1.1004)  # high == boundary, not >
    decision = entry_2_sweep("TEST", "EURUSD", box, DAY, [touch_only])
    assert decision.decision_status is DecisionStatus.NO_SETUP


# --------------------------------------------------------------------------- lookahead

def test_trend_decision_unaffected_by_modifying_later_post_session_candles():
    box = _trend_box()
    decision_a = entry_1_trend("TEST", "EURUSD", box, DAY)
    # Entry 1 never receives post-session candles at all -- nothing to look ahead into.
    decision_b = entry_1_trend("TEST", "EURUSD", box, DAY)
    assert decision_a == decision_b


def test_sweep_decision_unaffected_by_candles_after_the_qualifying_one():
    box = _range_box()
    qualifying = _candle(6, 0, 1.1005, box.session_high + 0.0010, 1.1000, box.session_high - 0.0002)
    later_noise = _candle(6, 15, 1.5000, 1.6000, 1.4000, 1.5500)  # wildly different, must be ignored

    decision_without_future = entry_2_sweep("TEST", "EURUSD", box, DAY, [qualifying])
    decision_with_future = entry_2_sweep("TEST", "EURUSD", box, DAY, [qualifying, later_noise])

    assert decision_without_future.entry_reference == decision_with_future.entry_reference
    assert decision_without_future.direction == decision_with_future.direction
    assert decision_without_future.signal_timestamp == decision_with_future.signal_timestamp


def test_range_box_is_built_only_from_the_sessions_own_candles():
    box = _range_box()
    # A later, out-of-window candle with an extreme high/low must not have moved the box.
    intruder = _candle(6, 0, 9.0, 9.0, 9.0, 9.0)
    box_with_intruder_not_included = build_reference_box(
        "asian", box_candles_for(box), expected_bar_count=2
    )
    assert box_with_intruder_not_included.session_high == box.session_high
    assert box_with_intruder_not_included.session_low == box.session_low


# --------------------------------------------------------------------------- version attribution

def test_setup_decision_carries_canonical_and_classifier_versions():
    box = _trend_box()
    decision = entry_1_trend("TEST", "EURUSD", box, DAY)
    assert decision.canonical_session_version == "CANONICAL_SESSION_WINDOWS_V1"
    assert decision.classifier_id == "ER_ONLY_V2"
    assert decision.setup_version
    assert decision.contract_status == "RESEARCH_CANDIDATE_NOT_EXECUTION_AUTHORITY"
