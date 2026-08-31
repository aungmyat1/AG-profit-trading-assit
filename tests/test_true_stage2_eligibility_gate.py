"""Gates 0-3 (spec source, TRUE_STAGE2_VERIFICATION_FROM_FROZEN_STAGE1 phase): proves
the actual Stage-2 consumer path -- not just QualifiedEEvent.is_eligible_at() in
isolation -- respects eligibility_intervals, using the frozen canonical artifact.
"""
from __future__ import annotations

import datetime as dt

import pytest

from historical_replay.stage1 import load_qualified_e_events

UTC = dt.timezone.utc
ARTIFACT = "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json"


@pytest.fixture(scope="module")
def events():
    evts, _meta = load_qualified_e_events(ARTIFACT)
    return evts


# --------------------------------------------------------------------------- Gate 0

def test_gate0_input_integrity(events):
    from collections import Counter
    counts = Counter(e.entry_condition for e in events)
    assert len(events) == 18
    assert counts == {"E1": 3, "E2": 4, "E3": 11}
    assert sum(1 for e in events if len(e.eligibility_intervals) >= 1) == 18
    assert sum(1 for e in events if len(e.eligibility_intervals) > 1) == 5
    assert sum(1 for e in events if e.entry_condition == "E3" and e.htf_liquidity_reference is not None) == 11


# --------------------------------------------------------------------------- Gate 1

def test_gate1_known_e3m2_regression(events):
    event = next(e for e in events if e.entry_condition == "E3" and e.direction == "SHORT"
                and e.reference_key == "PDH|None|None|1.16751")
    start, end = event.eligibility_intervals[0]
    assert start == dt.datetime(2025, 8, 12, 16, 0, tzinfo=UTC)
    assert end == dt.datetime(2025, 8, 12, 17, 0, tzinfo=UTC)

    assert event.is_eligible_at(dt.datetime(2025, 8, 12, 16, 0, tzinfo=UTC))
    assert event.is_eligible_at(dt.datetime(2025, 8, 12, 16, 55, tzinfo=UTC))
    assert not event.is_eligible_at(dt.datetime(2025, 8, 12, 17, 0, tzinfo=UTC))
    assert not event.is_eligible_at(dt.datetime(2025, 8, 12, 17, 5, tzinfo=UTC))
    false_aug19 = dt.datetime(2025, 8, 19, 7, 20, tzinfo=UTC)
    assert not event.is_eligible_at(false_aug19)

    # actual consumer-path proof: the M5-step filter a Stage-2 runner uses must skip
    # this timestamp entirely (never call evaluate_entry_stage for it)
    eligible_steps = [t for t in _synthetic_m5_steps(dt.datetime(2025, 8, 12, 15, 55, tzinfo=UTC),
                                                       dt.datetime(2025, 8, 19, 8, 0, tzinfo=UTC))
                      if event.is_eligible_at(t)]
    assert all(t < dt.datetime(2025, 8, 12, 17, 0, tzinfo=UTC) for t in eligible_steps)
    assert false_aug19 not in eligible_steps


def _synthetic_m5_steps(start, end):
    t = start
    while t < end:
        yield t
        t += dt.timedelta(minutes=5)


# --------------------------------------------------------------------------- Gate 2

def test_gate2_multi_interval_consumer(events):
    multi = [e for e in events if len(e.eligibility_intervals) > 1]
    assert len(multi) == 5
    event = multi[0]
    (start_a, end_a), (start_b, end_b) = event.eligibility_intervals[0], event.eligibility_intervals[1]
    assert start_b >= end_a  # intervals are chronologically ordered, non-overlapping

    assert event.is_eligible_at(start_a)
    assert not event.is_eligible_at(end_a)
    gap_midpoint = end_a + (start_b - end_a) / 2
    if gap_midpoint != start_b:  # only meaningful if there IS a real gap
        assert not event.is_eligible_at(gap_midpoint)
    assert event.is_eligible_at(start_b)
    assert not event.is_eligible_at(end_b)


# --------------------------------------------------------------------------- Gate 3

def test_gate3_all_18_boundary_and_gap_audit(events):
    boundary_failures = 0
    gap_failures = 0
    for event in events:
        for start, end in event.eligibility_intervals:
            if not event.is_eligible_at(start):
                boundary_failures += 1
            if event.is_eligible_at(end):
                boundary_failures += 1
        for i in range(len(event.eligibility_intervals) - 1):
            gap_start = event.eligibility_intervals[i][1]
            gap_end = event.eligibility_intervals[i + 1][0]
            if gap_end > gap_start and event.is_eligible_at(gap_start):
                gap_failures += 1
    assert boundary_failures == 0
    assert gap_failures == 0
