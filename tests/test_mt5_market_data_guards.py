"""Focused unit tests for the fail-closed data guards in src/mt5/market_data.py (WP3,
AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1). These test the pure validators directly against
hand-built Candle lists -- no live MT5 terminal/connection needed (matches the
crypto-feed guard tests at tests/test_binance_usdtm_feed.py /
tests/test_bybit_linear_perp_feed.py, which this repo already has for the other feeds but
was missing for the MT5/FX path -- see WP0 finding).
"""
from __future__ import annotations

import datetime as dt

import pytest

from strategy_engine.session import Candle
from mt5.market_data import MarketDataError, _validate_monotonic, _validate_ohlc

UTC = dt.timezone.utc


def _candle(time, o=1.0, h=1.1, l=0.9, c=1.05, v=10.0) -> Candle:
    return Candle(time=time, open=o, high=h, low=l, close=c, volume=v)


def test_monotonic_accepts_strictly_increasing_timestamps():
    candles = [_candle(dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC)),
               _candle(dt.datetime(2026, 9, 1, 6, 15, tzinfo=UTC))]
    _validate_monotonic(candles, "EURUSD")  # must not raise


def test_monotonic_rejects_duplicate_timestamps():
    t = dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC)
    candles = [_candle(t), _candle(t)]
    with pytest.raises(MarketDataError) as exc_info:
        _validate_monotonic(candles, "EURUSD")
    assert exc_info.value.reason_code == "DUPLICATE_TIMESTAMPS"


def test_monotonic_rejects_out_of_order_timestamps():
    candles = [_candle(dt.datetime(2026, 9, 1, 6, 15, tzinfo=UTC)),
               _candle(dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC))]
    with pytest.raises(MarketDataError) as exc_info:
        _validate_monotonic(candles, "EURUSD")
    assert exc_info.value.reason_code == "NON_MONOTONIC_TIMESTAMPS"


def test_ohlc_accepts_internally_consistent_bar():
    candles = [_candle(dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC), o=1.0850, h=1.0860, l=1.0840, c=1.0855)]
    _validate_ohlc(candles, "EURUSD")  # must not raise


def test_ohlc_rejects_high_below_open():
    candles = [_candle(dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC), o=1.09, h=1.05, l=0.9, c=1.0)]
    with pytest.raises(MarketDataError) as exc_info:
        _validate_ohlc(candles, "EURUSD")
    assert exc_info.value.reason_code == "INVALID_OHLC"


def test_ohlc_rejects_low_above_close():
    candles = [_candle(dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC), o=1.0, h=1.1, l=1.09, c=1.0)]
    with pytest.raises(MarketDataError) as exc_info:
        _validate_ohlc(candles, "EURUSD")
    assert exc_info.value.reason_code == "INVALID_OHLC"


def test_ohlc_rejects_nonfinite_price():
    candles = [_candle(dt.datetime(2026, 9, 1, 6, 0, tzinfo=UTC), o=float("nan"))]
    with pytest.raises(MarketDataError) as exc_info:
        _validate_ohlc(candles, "EURUSD")
    assert exc_info.value.reason_code == "NONFINITE_PRICE"
