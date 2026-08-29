"""Tests for historical_replay.resampler.resample_broker_aligned (historical-validation
continuation: a real bug found this session). MT5's own D1/H4 candles are anchored to
the BROKER's calendar day/4h window, not UTC midnight -- plain UTC-boundary `resample`
mismatched EVERY SINGLE bar of a real native MT5 D1 export for the same symbol/range,
because the broker's seasonal +2/+3 UTC offset does not divide evenly into 24h. These
tests lock in the fix with a synthetic broker-offset fixture, plus (where the real
dataset is present) the actual cross-validation against the native MT5 D1 export.
"""
from __future__ import annotations

import datetime as dt
import os

import pytest

from historical_replay.candle_store import HistoricalDataError
from historical_replay.resampler import resample, resample_broker_aligned
from strategy_engine.session import Candle

UTC = dt.timezone.utc
REAL_M5 = r"D:\EURUSD_M5_202504211715_202607310000.csv"
REAL_DAILY = r"D:\EURUSD_Daily_202501020000_202607310000.csv"


def _m5_broker_aligned(broker_start: dt.datetime, n: int, base_price: float = 1.10):
    """Builds n M5 candles at BROKER-time spacing starting at broker_start, and their
    UTC equivalents assuming a fixed +3h broker offset (summer)."""
    candles, broker_times = [], []
    for i in range(n):
        bt = broker_start + dt.timedelta(minutes=5 * i)
        utc_t = (bt - dt.timedelta(hours=3)).replace(tzinfo=UTC)
        candles.append(Candle(time=utc_t, open=base_price + i * 0.001, high=base_price + i * 0.001 + 0.0005,
                               low=base_price + i * 0.001 - 0.0005, close=base_price + i * 0.001 + 0.0002))
        broker_times.append(bt)
    return candles, broker_times


def test_broker_aligned_d1_bucket_boundary_is_broker_midnight_not_utc_midnight():
    """The exact bug: a full broker day (00:00-24:00 broker time, offset +3) spans UTC
    21:00 the previous day to UTC 21:00 -- NOT UTC 00:00 to 00:00."""
    broker_midnight = dt.datetime(2026, 1, 5, 0, 0)  # a broker-time midnight
    candles, broker_times = _m5_broker_aligned(broker_midnight, 288)  # one full broker day

    d1 = resample_broker_aligned(candles, broker_times, "M5", "D1")
    assert len(d1) == 1
    # UTC label = the first member's UTC time = broker midnight - 3h = 21:00 the previous day
    assert d1[0].time == dt.datetime(2026, 1, 4, 21, 0, tzinfo=UTC)


def test_plain_utc_resample_mismatches_broker_aligned_for_the_same_data():
    """Demonstrates the bug directly: the same input, bucketed by UTC midnight instead
    of broker midnight, produces a DIFFERENT (wrong) bar."""
    broker_midnight = dt.datetime(2026, 1, 5, 0, 0)
    candles, broker_times = _m5_broker_aligned(broker_midnight, 288)

    d1_broker = resample_broker_aligned(candles, broker_times, "M5", "D1")
    d1_utc = resample(candles, "M5", "D1")

    assert len(d1_broker) == 1
    # UTC bucketing splits this single broker day across two UTC-calendar-day buckets,
    # each incomplete (missing bars), so plain resample() drops both -- proving the
    # naive approach silently loses data a broker-aligned bucket correctly keeps.
    assert d1_utc == []


def test_broker_aligned_ohlc_aggregation_math():
    broker_midnight = dt.datetime(2026, 1, 5, 0, 0)
    candles, broker_times = _m5_broker_aligned(broker_midnight, 288)
    d1 = resample_broker_aligned(candles, broker_times, "M5", "D1")
    bar = d1[0]
    assert bar.open == candles[0].open
    assert bar.close == candles[-1].close
    assert bar.high == max(c.high for c in candles)
    assert bar.low == min(c.low for c in candles)


def test_internal_gap_drops_bucket_not_fabricates():
    broker_midnight = dt.datetime(2026, 1, 5, 0, 0)
    candles, broker_times = _m5_broker_aligned(broker_midnight, 288)
    # remove one bar from the middle -- an internal gap
    del candles[100]
    del broker_times[100]
    d1 = resample_broker_aligned(candles, broker_times, "M5", "D1")
    assert d1 == []


def test_short_partial_day_is_kept_not_dropped():
    """Unlike plain resample()'s fixed-bar-count completeness rule, a broker-aligned
    bucket only requires internal contiguity -- a naturally shorter day (e.g. a holiday
    early close, or this dataset's own first/last partial day) is a valid, shorter bar,
    not an incomplete one to discard."""
    broker_midnight = dt.datetime(2026, 1, 5, 0, 0)
    candles, broker_times = _m5_broker_aligned(broker_midnight, 50)  # far short of a full 288-bar day
    d1 = resample_broker_aligned(candles, broker_times, "M5", "D1")
    assert len(d1) == 1
    assert d1[0].close == candles[-1].close


def test_rejects_unsupported_target_timeframe():
    candles, broker_times = _m5_broker_aligned(dt.datetime(2026, 1, 5, 0, 0), 10)
    with pytest.raises(HistoricalDataError):
        resample_broker_aligned(candles, broker_times, "M5", "H1")


def test_rejects_mismatched_lengths():
    candles, broker_times = _m5_broker_aligned(dt.datetime(2026, 1, 5, 0, 0), 10)
    with pytest.raises(HistoricalDataError):
        resample_broker_aligned(candles, broker_times[:-1], "M5", "D1")


# --------------------------------------------------------------------------- real-data cross-validation

pytestmark_real = pytest.mark.skipif(
    not (os.path.exists(REAL_M5) and os.path.exists(REAL_DAILY)),
    reason="real historical M5/Daily datasets not present on this machine",
)


@pytestmark_real
def test_broker_aligned_d1_matches_native_mt5_daily_export():
    """The actual cross-validation this session ran: broker-aligned D1 derived from
    the M5 base feed must match MT5's own natively-exported Daily candles (excluding
    the dataset's own first/last partial-day edges, which are a data-coverage boundary
    effect, not a bucketing defect)."""
    import csv

    from historical_replay.mt5_export_loader import load_mt5_export_csv

    m5_candles, report = load_mt5_export_csv(REAL_M5, "EURUSD", "M5")
    derived_d1 = resample_broker_aligned(m5_candles, report.broker_times, "M5", "D1")

    native_by_date = {}
    with open(REAL_DAILY, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for r in reader:
            date = dt.datetime.strptime(r[0], "%Y.%m.%d").date()
            native_by_date[date] = (float(r[1]), float(r[2]), float(r[3]), float(r[4]))

    compared = mismatches = 0
    for c in derived_d1[1:-1]:  # drop the dataset's own first/last partial-day edges
        guess_date = (c.time + dt.timedelta(hours=3)).date()
        native = native_by_date.get(guess_date)
        if native is None:
            continue
        compared += 1
        if (abs(c.open - native[0]) > 1e-6 or abs(c.high - native[1]) > 1e-6
                or abs(c.low - native[2]) > 1e-6 or abs(c.close - native[3]) > 1e-6):
            mismatches += 1

    assert compared > 300  # sanity: most of the ~320 buckets should have a native match
    assert mismatches == 0
