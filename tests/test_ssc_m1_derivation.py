"""Unit tests for the deterministic M1 -> M15/H1 derivation used by the SSC one-year
authority remediation (mission SSC ONE-YEAR H1/M15 AUTHORITY REMEDIATION V1).

These lock the derivation CONTRACT, not any market result: bucket boundaries, OHLC
aggregation, the NATIVE_FAITHFUL_INCLUSIVE completeness policy, and the fail-closed
guards. No strategy, replay or optimization code is exercised here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from historical_replay.m1_derivation import (
    BUCKET_POLICY,
    DERIVED_TIMEFRAMES,
    DerivationError,
    aggregate_m1,
    bucket_census,
    bucket_start,
    verify_against_reference,
    verify_derived_series,
)
from strategy_engine.session.candles import Candle


def _m1(start: datetime, minutes: int, price: float = 1.10000, volume: float = 1.0):
    """A contiguous run of `minutes` synthetic M1 bars ascending from `start`."""
    out = []
    for i in range(minutes):
        t = start + timedelta(minutes=i)
        base = price + i * 0.00001
        out.append(Candle(time=t, open=base, high=base + 0.00005,
                          low=base - 0.00005, close=base + 0.00002, volume=volume))
    return out


UTC = timezone.utc


# --- bucket boundaries ---------------------------------------------------------------

def test_bucket_start_floors_to_exact_utc_boundary():
    t = datetime(2026, 3, 4, 7, 38, 41, 123456, tzinfo=UTC)
    assert bucket_start(t, "M15") == datetime(2026, 3, 4, 7, 30, tzinfo=UTC)
    assert bucket_start(t, "H1") == datetime(2026, 3, 4, 7, 0, tzinfo=UTC)


def test_bucket_start_is_utc_anchored_not_broker_wallclock():
    """A broker at UTC+3 wall clock would bucket 04:00Z into an '07:00' broker hour. The
    contract forbids that: 04:00Z must floor to 04:00Z."""
    t = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
    assert bucket_start(t, "H1") == datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
    assert bucket_start(t, "M15") == datetime(2026, 7, 1, 4, 0, tzinfo=UTC)


def test_bucket_start_rejects_naive_timestamp():
    with pytest.raises(DerivationError, match="NAIVE_TIMESTAMP_REJECTED"):
        bucket_start(datetime(2026, 1, 1, 0, 0), "H1")


def test_bucket_start_rejects_unsupported_timeframe():
    with pytest.raises(DerivationError, match="UNSUPPORTED_TIMEFRAME"):
        bucket_start(datetime(2026, 1, 1, tzinfo=UTC), "H4")


# --- aggregation ---------------------------------------------------------------------

def test_aggregate_h1_ohlc_is_first_max_min_last():
    bars = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60)
    out = aggregate_m1(bars, "H1")
    assert len(out) == 1
    bar = out[0]
    assert bar.time == datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
    assert bar.open == bars[0].open
    assert bar.close == bars[-1].close
    assert bar.high == max(b.high for b in bars)
    assert bar.low == min(b.low for b in bars)
    assert bar.volume == pytest.approx(60.0)


def test_aggregate_m15_splits_one_hour_into_four_buckets():
    bars = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60)
    out = aggregate_m1(bars, "M15")
    assert [b.time.minute for b in out] == [0, 15, 30, 45]
    assert all(b.time.hour == 0 for b in out)


def test_aggregate_is_deterministic_across_repeated_calls():
    bars = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 120)
    first = aggregate_m1(bars, "H1")
    second = aggregate_m1(bars, "H1")
    assert [(c.time, c.open, c.high, c.low, c.close) for c in first] == \
           [(c.time, c.open, c.high, c.low, c.close) for c in second]


def test_aggregate_volume_is_none_when_no_member_carries_volume():
    bars = [Candle(time=b.time, open=b.open, high=b.high, low=b.low, close=b.close, volume=None)
            for b in _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60)]
    assert aggregate_m1(bars, "H1")[0].volume is None


def test_aggregate_rejects_unsupported_target_timeframe():
    bars = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 5)
    with pytest.raises(DerivationError, match="UNSUPPORTED_TIMEFRAME"):
        aggregate_m1(bars, "M5")


# --- NATIVE_FAITHFUL_INCLUSIVE policy ------------------------------------------------

def test_policy_constant_is_declared():
    assert BUCKET_POLICY == "NATIVE_FAITHFUL_INCLUSIVE"
    assert set(DERIVED_TIMEFRAMES) == {"M15", "H1"}


def test_short_bucket_is_included_and_aggregated_from_present_bars():
    """The core policy departure: a partial bucket is emitted, not dropped -- matching
    MT5's own native candle at a weekly open / rollover break."""
    bars = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 20)  # 00:00..00:19 only
    out = aggregate_m1(bars, "H1")
    assert len(out) == 1
    assert out[0].time == datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
    assert out[0].open == bars[0].open
    assert out[0].close == bars[-1].close
    assert out[0].high == max(b.high for b in bars)
    assert out[0].low == min(b.low for b in bars)


def test_absent_market_produces_no_bucket_never_a_fabricated_one():
    """A genuine closure has no M1 bars, so no bar may be invented for it."""
    a = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60)
    b = _m1(datetime(2026, 5, 6, 0, 0, tzinfo=UTC), 60)  # 2-day weekend closure
    out = aggregate_m1(a + b, "H1")
    assert len(out) == 2
    assert [c.time for c in out] == [datetime(2026, 5, 4, 0, 0, tzinfo=UTC),
                                     datetime(2026, 5, 6, 0, 0, tzinfo=UTC)]


def test_prices_are_never_altered_by_aggregation():
    bars = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60)
    out = aggregate_m1(bars, "H1")
    # every aggregated value must be an actual member value, never interpolated
    member_opens = {b.open for b in bars}
    member_closes = {b.close for b in bars}
    member_highs = {b.high for b in bars}
    member_lows = {b.low for b in bars}
    assert out[0].open in member_opens
    assert out[0].close in member_closes
    assert out[0].high in member_highs
    assert out[0].low in member_lows


def test_census_counts_short_buckets_and_the_bars_a_strict_rule_would_drop():
    bars = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60) + \
        _m1(datetime(2026, 5, 4, 1, 0, tzinfo=UTC), 30)  # second hour is short
    c = bucket_census(bars, "H1")
    assert c["expected_m1_bars_per_bucket"] == 60
    assert c["total_buckets_with_any_m1"] == 2
    assert c["complete_buckets"] == 1
    assert c["short_buckets_included_by_policy"] == 1
    assert c["bars_dropped_by_strict_rule"] == 1
    assert c["over_full_buckets"] == 0


def test_census_never_reports_over_full_buckets_for_unique_m1():
    c = bucket_census(_m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 180), "H1")
    assert c["over_full_buckets"] == 0
    assert c["complete_buckets"] == 3


# --- quality verification ------------------------------------------------------------

def test_verify_derived_series_passes_a_clean_series():
    out = aggregate_m1(_m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 240), "H1")
    q = verify_derived_series(out, "H1")
    assert q["quality_status"] == "PASS"
    assert q["duplicates"] == 0
    assert q["non_monotonic_rows"] == 0
    assert q["invalid_ohlc"] == 0
    assert q["off_utc_boundary_rows"] == 0


def test_verify_derived_series_rejects_empty_series():
    with pytest.raises(DerivationError, match="EMPTY_DERIVED_SERIES"):
        verify_derived_series([], "H1")


def test_verify_derived_series_detects_invalid_ohlc():
    bad = [Candle(time=datetime(2026, 5, 4, 0, 0, tzinfo=UTC), open=1.1, high=1.0,
                  low=1.2, close=1.1, volume=1.0)]
    q = verify_derived_series(bad, "H1")
    assert q["invalid_ohlc"] == 1
    assert q["quality_status"] == "FAIL"


def test_verify_derived_series_detects_off_boundary_rows():
    off = [Candle(time=datetime(2026, 5, 4, 0, 7, tzinfo=UTC), open=1.1, high=1.2,
                  low=1.0, close=1.1, volume=1.0)]
    q = verify_derived_series(off, "H1")
    assert q["off_utc_boundary_rows"] == 1
    assert q["quality_status"] == "FAIL"


def test_verify_derived_series_counts_weekend_steps_as_non_native_not_errors():
    a = _m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60)
    b = _m1(datetime(2026, 5, 6, 0, 0, tzinfo=UTC), 60)
    q = verify_derived_series(aggregate_m1(a + b, "H1"), "H1")
    assert q["non_native_steps"] == 1
    assert q["quality_status"] == "PASS"  # a closure is not a defect


# --- reference parity ----------------------------------------------------------------

def test_reference_parity_reports_exact_on_identical_series():
    out = aggregate_m1(_m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 120), "H1")
    r = verify_against_reference(out, out, "self")
    assert r["exact_match_rate"] == 1.0
    assert r["ohlc_mismatches"] == 0
    assert r["reference_only_buckets"] == 0


def test_reference_parity_detects_a_single_price_difference():
    out = aggregate_m1(_m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 120), "H1")
    perturbed = [Candle(time=out[0].time, open=out[0].open + 0.00001, high=out[0].high,
                        low=out[0].low, close=out[0].close, volume=out[0].volume), out[1]]
    r = verify_against_reference(out, perturbed, "perturbed")
    assert r["ohlc_mismatches"] == 1
    assert r["exact_match_rate"] == 0.5


def test_reference_parity_restrict_to_excludes_wider_reference_history():
    out = aggregate_m1(_m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60), "H1")
    wider = aggregate_m1(_m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 240), "H1")
    span = (out[0].time, out[-1].time + timedelta(hours=1))
    r = verify_against_reference(out, wider, "wider", restrict_to=span)
    assert r["reference_rows_in_span"] == 1
    assert r["reference_only_buckets"] == 0


def test_reference_parity_reports_none_rate_when_no_common_bucket():
    out = aggregate_m1(_m1(datetime(2026, 5, 4, 0, 0, tzinfo=UTC), 60), "H1")
    other = aggregate_m1(_m1(datetime(2027, 5, 4, 0, 0, tzinfo=UTC), 60), "H1")
    r = verify_against_reference(out, other, "disjoint")
    assert r["common_buckets"] == 0
    assert r["exact_match_rate"] is None


# --- module isolation ----------------------------------------------------------------

def test_derivation_module_imports_no_strategy_or_optimization_code():
    """A3: dataset construction must be independent of strategy outcomes. The module may
    not import SSC setup/bias/outcome/economic/optimization modules."""
    import historical_replay.m1_derivation as mod

    source = open(mod.__file__, encoding="utf-8").read()
    forbidden = (
        "session_sweep_continuation", "bias_gate", "outcome_resolution",
        "performance_attribution", "optimization", "replay import",
    )
    for token in forbidden:
        assert f"import {token}" not in source, f"forbidden import: {token}"
