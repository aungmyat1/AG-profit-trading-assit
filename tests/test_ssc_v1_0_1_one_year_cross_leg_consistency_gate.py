"""Mission 1 / P3 hardening (2026-09-21) -- regression tests for the cross-leg timebase
predicate logic ported INTO scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py
(no second arbiter module: this script remains the single P3 authority).

Fixes this suite locks in (the script previously had zero test coverage):
  1. ALIGNED required best_exact_rate >= threshold at WHATEVER shift was best -- fixed
     to require best_shift_hours == +0h exactly (`_classify_alignment`).
  2. The consistent-leg union merged overlapping contributors last-writer-wins
     (`merged[c.time] = c`) -- fixed to detect and drop disagreeing timestamps
     (`_merge_with_conflict_detection`).
  3. DST per-season windows (Nov1-Mar1 / May1-Sep1) never straddled either real EU DST
     transition inside the mission window and left ~4.5 months unclassified -- fixed to
     three segments split exactly at 2025-10-26 and 2026-03-29 (`SEASON_SEGMENTS`).
  4. A source confined to one season segment could be marked ALIGNED/DST_CONSISTENT
     purely because it never crossed a boundary -- fixed to NOT_EVALUABLE_SINGLE_SEASON
     (`_classify_alignment` + `_segments_with_coverage`).

Required cases (mission P3 instruction):
  1. correct UTC alignment                    -> ALIGNED, +0h
  2. fixed-hour misalignment                  -> MISALIGNED, best_shift != 0
  3. winter/summer mixed offset (DST fracture)-> DST_INCONSISTENT (bimodal census)
  4. missing bucket                            -> reduced common-bucket census, never
                                                   falsely counted as full agreement
  5. duplicate timestamp                       -> loader-level fail-closed (existing
                                                   HistoricalCandleStore/loader contract;
                                                   asserted via the general merge/duplicate
                                                   guard this gate depends on)
plus the two P3-hardening-specific cases:
  6. single-season source                      -> NOT_EVALUABLE_SINGLE_SEASON, excluded
  7. conflicting overlap on merge               -> CONFLICT detected, timestamp dropped,
                                                    never resolved by source-list order
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from strategy_engine.session import Candle

REPO = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def _load_gate_module():
    path = REPO / "scripts" / "audit_ssc_v1_0_1_one_year_cross_leg_consistency.py"
    spec = importlib.util.spec_from_file_location("ssc_cross_leg_gate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate_module()


def _m1_series(hours: int = 400, start: datetime = datetime(2025, 12, 1, 0, 0, tzinfo=UTC)):
    """Deterministic synthetic M1 inside the WINTER segment (2025-10-26..2026-03-29),
    one bar per minute, price = f(index) so aggregation is reproducible."""
    out = []
    t = start
    for i in range(hours * 60):
        base = 1.1000 + (i % 97) * 0.0001
        out.append(Candle(time=t, open=base, high=base + 0.0002,
                          low=base - 0.0002, close=base + 0.0001, volume=10.0))
        t += timedelta(minutes=1)
    return out


@pytest.fixture(scope="module")
def m1():
    return _m1_series()


def test_aggregate_derivation_is_deterministic_and_order_independent(gate, m1):
    agg_a = gate._aggregate(m1, 60)
    agg_b = gate._aggregate(list(reversed(m1)), 60)
    assert set(agg_a) == set(agg_b)
    for k in agg_a:
        assert agg_a[k] == agg_b[k]


def test_case1_correct_utc_alignment_census_explains_only_zero_shift(gate, m1):
    arbiter_agg = gate._aggregate(m1, 60)
    candidate = [Candle(t, o, h, l, c, None) for t, (o, h, l, c) in arbiter_agg.items()]
    by_time = {c.time: (c.open, c.high, c.low, c.close) for c in candidate}
    census = gate._bimodal_shift_census(by_time, arbiter_agg, min_common_buckets=10)
    assert set(census) == {0}
    best = sorted(gate._shift_scan(by_time, arbiter_agg), key=lambda r: r["exact_rate"], reverse=True)[0]
    status, dst_consistency, timezone_consistent = gate._classify_alignment(best, census, segments_evaluated=2)
    assert status == "ALIGNED"
    assert best["shift_hours"] == 0
    assert timezone_consistent is True


def test_case2_fixed_plus3h_displacement_is_misaligned(gate, m1):
    arbiter_agg = gate._aggregate(m1, 60)
    shift = timedelta(hours=3)
    candidate = [Candle(t + shift, o, h, l, c, None) for t, (o, h, l, c) in arbiter_agg.items()]
    by_time = {c.time: (c.open, c.high, c.low, c.close) for c in candidate}
    census = gate._bimodal_shift_census(by_time, arbiter_agg, min_common_buckets=10)
    best = sorted(gate._shift_scan(by_time, arbiter_agg), key=lambda r: r["exact_rate"], reverse=True)[0]
    assert best["shift_hours"] == 3
    status, _, timezone_consistent = gate._classify_alignment(best, census, segments_evaluated=2)
    # best_exact_rate == 1.0 at +3h is NOT admission -- only +0h is.
    assert status == "MISALIGNED"
    assert timezone_consistent is False


def test_case3_winter_summer_mixed_offsets_are_internally_inconsistent(gate, m1):
    """Reproduces the DEV_002 defect shape via the calendar-independent bimodal
    census: one half of the file sits at -1h, the other at +0h."""
    arbiter_agg = gate._aggregate(m1, 60)
    items = sorted(arbiter_agg.items())
    split = len(items) // 2
    shifted_half = [Candle(t - timedelta(hours=1), o, h, l, c, None) for t, (o, h, l, c) in items[:split]]
    aligned_half = [Candle(t, o, h, l, c, None) for t, (o, h, l, c) in items[split:]]
    by_time = {c.time: (c.open, c.high, c.low, c.close) for c in shifted_half + aligned_half}
    census = gate._bimodal_shift_census(by_time, arbiter_agg, min_common_buckets=10)
    assert set(census) == {-1, 0}
    best = sorted(gate._shift_scan(by_time, arbiter_agg), key=lambda r: r["exact_rate"], reverse=True)[0]
    status, dst_consistency, timezone_consistent = gate._classify_alignment(best, census, segments_evaluated=2)
    assert status == "DST_INCONSISTENT"
    assert timezone_consistent is False


def test_case4_missing_bucket_never_inflates_the_census(gate, m1):
    arbiter_agg = gate._aggregate(m1, 60)
    items = dict(arbiter_agg)
    keys = sorted(items)
    for k in keys[10:34]:  # remove a full day of H1 buckets
        del items[k]
    candidate = [Candle(t, o, h, l, c, None) for t, (o, h, l, c) in items.items()]
    by_time = {c.time: (c.open, c.high, c.low, c.close) for c in candidate}
    census = gate._bimodal_shift_census(by_time, arbiter_agg, min_common_buckets=10)
    assert census.get(0, 0) == len(items)
    assert census.get(0, 0) < len(arbiter_agg)


def test_case5_duplicate_timestamp_series_fails_closed_on_load(gate, tmp_path):
    """The gate's own candle series never tolerate a duplicate/non-increasing
    timestamp -- HistoricalCandleStore.load_series (the same fail-closed contract every
    other historical_replay consumer depends on) raises rather than silently picking
    one. This is the general guard the gate's own `_load` inherits through the shared
    loaders; asserted directly here since the gate script has no bespoke duplicate path
    of its own to bypass it."""
    from historical_replay.candle_store import HistoricalCandleStore, HistoricalDataError

    base = datetime(2025, 12, 1, tzinfo=UTC)
    candles = [Candle(base + timedelta(hours=i), 1.0, 1.0, 1.0, 1.0, None) for i in range(5)]
    dup = Candle(candles[2].time, 1.0, 1.0, 1.0, 1.0, None)
    store = HistoricalCandleStore()
    with pytest.raises(HistoricalDataError):
        store.load_series("EURUSD", "H1", candles[:3] + [dup] + candles[3:])


def test_case6_single_season_source_is_excluded_even_when_perfectly_aligned(gate):
    """A source confined to ONE season segment (e.g. summer-only, like the real
    SSC_V1_0_1_G2_DEV_001::H1 leg, 2026-06-21..2026-08-02) must never be admitted on
    the strength of its own single-segment perfection alone."""
    start = datetime(2026, 6, 21, 21, 0, tzinfo=UTC)  # inside SUMMER_POST_SPRINGFORWARD only
    m1 = _m1_series(hours=48, start=start)
    arbiter_agg = gate._aggregate(m1, 60)
    candidate = [Candle(t, o, h, l, c, None) for t, (o, h, l, c) in arbiter_agg.items()]
    by_time = {c.time: (c.open, c.high, c.low, c.close) for c in candidate}
    per_segment = gate._segments_with_coverage(by_time, arbiter_agg, min_common_buckets=10)
    assert list(per_segment) == ["SUMMER_POST_SPRINGFORWARD"]
    census = gate._bimodal_shift_census(by_time, arbiter_agg, min_common_buckets=10)
    best = sorted(gate._shift_scan(by_time, arbiter_agg), key=lambda r: r["exact_rate"], reverse=True)[0]
    assert best["shift_hours"] == 0 and best["exact_rate"] == 1.0  # perfect within its one segment
    status, dst_consistency, timezone_consistent = gate._classify_alignment(best, census, len(per_segment))
    assert status == "NOT_EVALUABLE_SINGLE_SEASON"
    assert timezone_consistent is False


def test_segments_with_coverage_spans_multiple_segments_for_a_full_year_source(gate, m1):
    """Sanity check on the other side: a source spanning the WINTER segment used by the
    other fixtures here plus a slice of SUMMER_POST_SPRINGFORWARD is evaluated in both."""
    winter_agg = gate._aggregate(m1, 60)  # 2025-12-01 start, inside WINTER
    spring = _m1_series(hours=48, start=datetime(2026, 4, 1, tzinfo=UTC))  # inside SUMMER_POST
    spring_agg = gate._aggregate(spring, 60)
    combined_arbiter = {**winter_agg, **spring_agg}
    candidate = [Candle(t, o, h, l, c, None) for t, (o, h, l, c) in combined_arbiter.items()]
    by_time = {c.time: (c.open, c.high, c.low, c.close) for c in candidate}
    per_segment = gate._segments_with_coverage(by_time, combined_arbiter, min_common_buckets=10)
    assert set(per_segment) == {"WINTER", "SUMMER_POST_SPRINGFORWARD"}


def test_case7_conflicting_overlap_is_dropped_not_silently_overwritten(gate):
    """Two sources both individually admitted as ALIGNED but disagreeing on one shared
    timestamp (data-defect scenario) must never be resolved by which source was listed
    first -- the conflicting bar is dropped from the merge and reported."""
    t0 = datetime(2026, 1, 5, tzinfo=UTC)
    source_a = [Candle(t0 + timedelta(hours=i), 1.1000, 1.1002, 1.0998, 1.1001, None) for i in range(5)]
    source_b = [Candle(t0 + timedelta(hours=i), 1.1000, 1.1002, 1.0998, 1.1001, None) for i in range(5)]
    # Introduce a genuine disagreement at hour index 2 -- same timestamp, different OHLC.
    source_b[2] = Candle(t0 + timedelta(hours=2), 1.2000, 1.2002, 1.1998, 1.2001, None)

    merged, conflicts = gate._merge_with_conflict_detection([source_a, source_b])

    assert conflicts == [(t0 + timedelta(hours=2)).isoformat()]
    merged_times = [c.time for c in merged]
    assert (t0 + timedelta(hours=2)) not in merged_times
    assert len(merged) == 4  # the 4 agreeing bars survive; the conflicting one is dropped, not guessed at


def test_no_conflict_when_all_contributors_agree(gate):
    t0 = datetime(2026, 1, 5, tzinfo=UTC)
    source_a = [Candle(t0 + timedelta(hours=i), 1.1, 1.1, 1.1, 1.1, None) for i in range(3)]
    source_b = [Candle(t0 + timedelta(hours=i), 1.1, 1.1, 1.1, 1.1, None) for i in range(1, 4)]
    merged, conflicts = gate._merge_with_conflict_detection([source_a, source_b])
    assert conflicts == []
    assert len(merged) == 4  # union of [0,1,2] and [1,2,3] -> [0,1,2,3]
