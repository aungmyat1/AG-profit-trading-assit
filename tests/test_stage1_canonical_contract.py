"""Tests for the canonical Stage-1 contract (historical_replay.stage1): eligibility
consumer contract, persistence round-trip, and the E3M2 false-Aug19-READY regression
this phase's investigation found and fixed.
"""
from __future__ import annotations

import datetime as dt

import pytest

from historical_replay.stage1 import QualifiedEEvent, load_qualified_e_events

UTC = dt.timezone.utc


def _event(intervals):
    qual_time = intervals[0][0] if intervals else dt.datetime(2026, 1, 1, tzinfo=UTC)
    return QualifiedEEvent(
        event_id="QE-TEST", producer_version="TEST", symbol="EURUSD",
        entry_condition="E3", direction="SHORT",
        qualification_time=qual_time,
        reference_type="PDH", reference_low=None, reference_high=None, reference_level=1.1,
        reference_key="PDH|None|None|1.1", eligibility_intervals=tuple(intervals),
    )


# --------------------------------------------------------------------------- consumer contract

def test_inside_single_interval_is_eligible():
    start, end = dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC), dt.datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    event = _event([(start, end)])
    assert event.is_eligible_at(start + dt.timedelta(minutes=30))


def test_before_interval_is_not_eligible():
    start, end = dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC), dt.datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    event = _event([(start, end)])
    assert not event.is_eligible_at(start - dt.timedelta(minutes=5))


def test_after_interval_is_not_eligible():
    """The exact regression this phase found: a timestamp well after the real
    eligibility window (e.g. 7 days later) must never be considered eligible."""
    start, end = dt.datetime(2025, 8, 12, 16, 0, tzinfo=UTC), dt.datetime(2025, 8, 12, 17, 0, tzinfo=UTC)
    event = _event([(start, end)])
    false_aug19 = dt.datetime(2025, 8, 19, 7, 20, tzinfo=UTC)
    assert not event.is_eligible_at(false_aug19)


def test_interval_start_inclusive_end_exclusive():
    start, end = dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC), dt.datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    event = _event([(start, end)])
    assert event.is_eligible_at(start) is True
    assert event.is_eligible_at(end) is False


def test_between_two_intervals_is_not_eligible():
    i1 = (dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC), dt.datetime(2026, 1, 1, 11, 0, tzinfo=UTC))
    i2 = (dt.datetime(2026, 1, 3, 10, 0, tzinfo=UTC), dt.datetime(2026, 1, 3, 11, 0, tzinfo=UTC))
    event = _event([i1, i2])
    assert not event.is_eligible_at(dt.datetime(2026, 1, 2, 10, 0, tzinfo=UTC))


def test_inside_second_interval_is_eligible():
    i1 = (dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC), dt.datetime(2026, 1, 1, 11, 0, tzinfo=UTC))
    i2 = (dt.datetime(2026, 1, 3, 10, 0, tzinfo=UTC), dt.datetime(2026, 1, 3, 11, 0, tzinfo=UTC))
    event = _event([i1, i2])
    assert event.is_eligible_at(dt.datetime(2026, 1, 3, 10, 30, tzinfo=UTC))


def test_no_intervals_never_eligible():
    event = _event([])
    assert not event.is_eligible_at(dt.datetime(2026, 1, 1, tzinfo=UTC))


# --------------------------------------------------------------------------- persistence round-trip

def test_persisted_events_round_trip_exactly(tmp_path):
    events, metadata = load_qualified_e_events(
        "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json")
    assert len(events) == 18

    from collections import Counter
    counts = Counter(e.entry_condition for e in events)
    assert counts == {"E1": 3, "E2": 4, "E3": 11}

    e3_with_liquidity = [e for e in events if e.entry_condition == "E3" and e.htf_liquidity_reference is not None]
    assert len(e3_with_liquidity) == 11

    multi_interval = [e for e in events if len(e.eligibility_intervals) > 1]
    assert len(multi_interval) == 5

    assert metadata["symbol"] == "EURUSD"


def test_e3m2_regression_event_has_correct_short_interval():
    """The known regression case: E3/SHORT/PDH=1.16751's real eligibility window is
    ~1 hour on 2025-08-12, not days. Verifies the persisted canonical event carries
    the correct interval and rejects the false Aug-19 timestamp."""
    events, _ = load_qualified_e_events(
        "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json")
    event = next(e for e in events if e.entry_condition == "E3" and e.direction == "SHORT"
                and e.reference_key == "PDH|None|None|1.16751")

    assert len(event.eligibility_intervals) == 1
    start, end = event.eligibility_intervals[0]
    assert start == dt.datetime(2025, 8, 12, 16, 0, tzinfo=UTC)
    assert (end - start) <= dt.timedelta(hours=2)  # real window, not a multi-day research assumption

    false_aug19 = dt.datetime(2025, 8, 19, 7, 20, tzinfo=UTC)
    assert not event.is_eligible_at(false_aug19)
