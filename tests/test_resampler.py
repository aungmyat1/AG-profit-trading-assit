"""Tests for historical_replay.resampler (historical-validation continuation spec
sections 6, 11, 52-53): OHLC aggregation math, UTC-boundary alignment, and dropping
(never fabricating) incomplete windows.
"""
from __future__ import annotations

import datetime as dt

import pytest

from historical_replay.candle_store import HistoricalCandleStore, HistoricalDataError
from historical_replay.resampler import resample
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _m5(start: dt.datetime, n: int, base_price: float = 1.10) -> list[Candle]:
    out = []
    for i in range(n):
        t = start + dt.timedelta(minutes=5 * i)
        # deterministic, distinguishable OHLC per bar so aggregation math is checkable
        out.append(Candle(time=t, open=base_price + i * 0.0010, high=base_price + i * 0.0010 + 0.0005,
                           low=base_price + i * 0.0010 - 0.0005, close=base_price + i * 0.0010 + 0.0002,
                           volume=10))
    return out


def test_m5_to_h1_aggregation_math():
    # Exactly one H1 bucket: 12 M5 bars from 10:00 to 10:55.
    base = _m5(dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC), 12)
    h1 = resample(base, "M5", "H1")
    assert len(h1) == 1
    bar = h1[0]
    assert bar.time == dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    assert bar.open == base[0].open
    assert bar.close == base[-1].close
    assert bar.high == max(c.high for c in base)
    assert bar.low == min(c.low for c in base)
    assert bar.volume == sum(c.volume for c in base)


def test_incomplete_bucket_is_dropped_not_fabricated():
    # Only 11 of the 12 required M5 bars for the 10:00-11:00 H1 bucket -- missing 10:55.
    base = _m5(dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC), 11)
    h1 = resample(base, "M5", "H1")
    assert h1 == []


def test_partial_leading_bucket_before_first_full_hour_is_dropped():
    # Starts at 10:35 -- the 10:00-11:00 bucket is missing its first 7 bars.
    base = _m5(dt.datetime(2026, 1, 5, 10, 35, tzinfo=UTC), 5) + _m5(dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC), 12)
    h1 = resample(base, "M5", "H1")
    assert len(h1) == 1
    assert h1[0].time == dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)


def test_h4_boundary_alignment():
    base = _m5(dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC), 96)  # 08:00-15:55 -> two complete H4 buckets
    h4 = resample(base, "M5", "H4")
    assert [b.time for b in h4] == [dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC), dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC)]


def test_d1_boundary_alignment():
    base = _m5(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 288)  # full UTC day, 288 M5 bars
    d1 = resample(base, "M5", "D1")
    assert len(d1) == 1
    assert d1[0].time == dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    assert d1[0].open == base[0].open
    assert d1[0].close == base[-1].close
    assert d1[0].high == max(c.high for c in base)
    assert d1[0].low == min(c.low for c in base)


def test_same_timeframe_passthrough():
    base = _m5(dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC), 5)
    assert resample(base, "M5", "M5") == base


# --------------------------------------------------------------------------- closure, derived timeframes

def test_derived_h4_bar_not_visible_before_its_close():
    """Spec section 53: preserve H1 closure (already covered elsewhere) and extend to
    H4/D1 -- a derived HTF bar must not be queryable before its own close."""
    base = _m5(dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC), 96)  # two H4 buckets: 08:00-12:00, 12:00-16:00
    h4 = resample(base, "M5", "H4")
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "H4", h4)

    just_before_second_close = dt.datetime(2026, 1, 5, 15, 59, tzinfo=UTC)
    latest = store.closed_candles("EURUSD", "H4", just_before_second_close, 1)
    assert latest[0].time == dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC)  # 08:00-12:00, NOT 12:00-16:00


def test_derived_d1_bar_visible_only_after_close():
    base = _m5(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 288) + _m5(dt.datetime(2026, 1, 6, 0, 0, tzinfo=UTC), 288)
    d1 = resample(base, "M5", "D1")
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "D1", d1)

    mid_jan5 = dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
    with pytest.raises(HistoricalDataError):  # Jan 5's D1 bar hasn't closed yet -- nothing closed to return
        store.closed_candles("EURUSD", "D1", mid_jan5, 1)

    after_close = dt.datetime(2026, 1, 6, 0, 0, tzinfo=UTC)
    latest = store.closed_candles("EURUSD", "D1", after_close, 1)
    assert latest[0].time == dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
