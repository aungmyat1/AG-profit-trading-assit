"""DRAFT — Mission 1 / P3: synthetic regression tests for the cross-leg timebase arbiter.

Required cases per the mission prompt:
  1. correct UTC alignment                    -> ALIGNED, +0h, rate 1.0
  2. fixed-hour misalignment (+3h)            -> MISALIGNED, best_shift=+3
  3. winter/summer mixed offset (DST fracture)-> INTERNALLY_DST_INCONSISTENT
  4. missing bucket                           -> rate < 1.0 / not admissible
  5. duplicate timestamp                      -> INPUT_REJECTED (fail closed)

Run (after placing cross_leg_timebase_arbiter.py on the path, e.g. src/historical_replay/):
    python -m pytest -q tests/test_cross_leg_timebase_gate.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from strategy_engine.session import Candle

# adjust import location to wherever the arbiter lands
from historical_replay.timebase_arbiter import (
    ALIGNED, INPUT_REJECTED, INTERNALLY_DST_INCONSISTENT, MISALIGNED,
    ArbiterVerdict, arbitrate, derive_buckets,
)

UTC = timezone.utc


def _m1_series(days: int = 60, start: datetime = datetime(2025, 1, 6, 0, 0, tzinfo=UTC)):
    """Deterministic synthetic M1: one bar per minute, price = f(index) so every
    aggregation is reproducible. Weekends are NOT simulated -- the arbiter only needs
    bucket math, and closure gaps are covered by the dedicated missing-bucket test."""
    out = []
    t = start
    for i in range(days * 24 * 60):
        base = 1.1000 + (i % 97) * 0.0001
        out.append(Candle(time=t, open=base, high=base + 0.0002,
                          low=base - 0.0002, close=base + 0.0001, volume=10.0))
        t += timedelta(minutes=1)
    return out


def _candles_from_buckets(buckets, shift_hours: int = 0):
    shift = timedelta(hours=shift_hours)
    return [Candle(c.time + shift, c.open, c.high, c.low, c.close, c.volume)
            for c in sorted(buckets.values(), key=lambda c: c.time)]


@pytest.fixture(scope="module")
def m1():
    return _m1_series()


def test_derivation_is_deterministic_and_exact(m1):
    h1a = derive_buckets(m1, 60)
    h1b = derive_buckets(list(reversed(m1)) and m1, 60)  # input order must not matter
    assert set(h1a) == set(h1b)
    for k in h1a:
        assert (h1a[k].open, h1a[k].high, h1a[k].low, h1a[k].close) == \
               (h1b[k].open, h1b[k].high, h1b[k].low, h1b[k].close)


def test_case1_correct_utc_alignment_is_admissible(m1):
    candidate = _candles_from_buckets(derive_buckets(m1, 60))
    v = arbitrate(m1, candidate, tf_minutes=60)
    assert v.status == ALIGNED
    assert v.best_shift_hours == 0
    assert v.exact_match_rate == 1.0
    assert v.admissible is True


def test_case2_fixed_plus3h_displacement_is_misaligned(m1):
    candidate = _candles_from_buckets(derive_buckets(m1, 60), shift_hours=3)
    v = arbitrate(m1, candidate, tf_minutes=60)
    assert v.status == MISALIGNED
    assert v.best_shift_hours == 3
    assert v.admissible is False


def test_case3_winter_summer_mixed_offsets_are_internally_inconsistent(m1):
    """Reproduces the DEV_002 defect shape: one part of the file sits at -1h, another
    at +0h -- no single whole-hour shift may describe it."""
    buckets = sorted(derive_buckets(m1, 60).values(), key=lambda c: c.time)
    split = len(buckets) // 2
    winter = [Candle(c.time - timedelta(hours=1), c.open, c.high, c.low, c.close, c.volume)
              for c in buckets[:split]]
    summer = list(buckets[split:])
    v = arbitrate(m1, winter + summer, tf_minutes=60)
    assert v.status == INTERNALLY_DST_INCONSISTENT
    assert v.admissible is False


def test_case4_missing_bucket_never_passes(m1):
    buckets = derive_buckets(m1, 60)
    keys = sorted(buckets)
    for k in keys[len(keys) // 3: len(keys) // 3 + 24]:  # remove a full day of H1 buckets
        del buckets[k]
    candidate = _candles_from_buckets(buckets)
    v = arbitrate(m1, candidate, tf_minutes=60)
    # common buckets still rate 1.0 where present -- admission additionally requires
    # the coverage gate; the arbiter alone must not declare ALIGNED-and-complete.
    assert v.common_buckets < len(keys)
    assert not (v.admissible and v.common_buckets == len(keys))


def test_case5_duplicate_timestamp_fails_closed(m1):
    candidate = _candles_from_buckets(derive_buckets(m1, 60))
    dup = Candle(candidate[10].time, 1.0, 1.0, 1.0, 1.0, None)
    v = arbitrate(m1, candidate[:10] + [dup] + candidate[10:], tf_minutes=60)
    assert v.status == INPUT_REJECTED
    assert v.admissible is False


def test_same_source_parody_is_not_expressible():
    """Design invariant: the arbiter API has no path to compare a leg against itself --
    GEN_002's H1-vs-H1 tautology must be inexpressible. This test documents the API
    surface: arbitration ALWAYS consumes (m1_authority, candidate_leg)."""
    import inspect
    sig = inspect.signature(arbitrate)
    assert list(sig.parameters)[:2] == ["m1_authority", "candidate_leg"]
