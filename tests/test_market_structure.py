"""Tests for market_structure: the smc_adapter mapping (deterministic synthetic
fixtures, no MT5 needed) plus a live-guarded end-to-end analyze_structure() check.

Fixtures use swing_length=_SWING_LENGTH so a handful of candles is enough to produce confirmed
swings/BOS/CHOCH -- this is about verifying OUR mapping and state rule, not tuning
smartmoneyconcepts' own algorithm.
"""
from __future__ import annotations

import datetime as dt

import pytest

from market_structure.analyzer import _structure_state
from market_structure.models import StructurePointKind
from market_structure.smc_adapter import candles_to_dataframe, latest_swings_and_breaks
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _candles(prices, start=dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), step_minutes=15):
    out = []
    t = start
    for p in prices:
        out.append(Candle(time=t, open=p, high=p + 0.0005, low=p - 0.0005, close=p, volume=1.0))
        t += dt.timedelta(minutes=step_minutes)
    return out


_SWING_LENGTH = 1  # small on purpose: these fixtures test OUR mapping, not smc's own tuning


def _ascending_zigzag(cycles=25, trend_step=0.0100, amplitude=0.0300):
    """Higher highs + higher lows: each pullback (low_i+1) stays above the prior low but
    well below the prior high, so both the uptrend AND the local reversals are genuine."""
    prices = []
    for i in range(cycles):
        low = 1.1000 + i * trend_step
        high = low + amplitude
        prices.append(low)
        prices.append(high)
    return prices


def _descending_zigzag(cycles=25, trend_step=0.0100, amplitude=0.0300):
    """Mirror of _ascending_zigzag: lower highs + lower lows."""
    prices = []
    for i in range(cycles):
        high = 1.2000 - i * trend_step
        low = high - amplitude
        prices.append(high)
        prices.append(low)
    return prices


def _range_oscillation(cycles=25):
    """Same two price levels repeated every cycle: real alternating swings, but no
    persistent directional level progression, so BOS/CHOCH should never confirm."""
    prices = []
    for _ in range(cycles):
        prices.append(1.1000)
        prices.append(1.1300)
    return prices


# --------------------------------------------------------------------------- adapter shape

def test_candles_to_dataframe_has_expected_columns_and_datetime_index():
    df = candles_to_dataframe(_candles([1.1, 1.2, 1.1]))
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "time_utc"
    assert str(df.index.dtype).startswith("datetime64")


# --------------------------------------------------------------------------- behavior fixtures

def test_ascending_zigzag_is_bullish():
    candles = _candles(_ascending_zigzag())
    df = candles_to_dataframe(candles)
    latest = latest_swings_and_breaks(df, swing_length=_SWING_LENGTH, close_break=True)

    assert latest["latest_swing_high"] is not None
    assert latest["latest_swing_low"] is not None
    state = _structure_state(latest["latest_bos"], latest["latest_choch"])
    assert state == "BULLISH"
    if latest["latest_bos"] is not None:
        assert latest["latest_bos"].kind == StructurePointKind.BULLISH_BOS


def test_descending_zigzag_is_bearish():
    candles = _candles(_descending_zigzag())
    df = candles_to_dataframe(candles)
    latest = latest_swings_and_breaks(df, swing_length=_SWING_LENGTH, close_break=True)

    assert latest["latest_swing_high"] is not None
    assert latest["latest_swing_low"] is not None
    state = _structure_state(latest["latest_bos"], latest["latest_choch"])
    assert state == "BEARISH"
    if latest["latest_bos"] is not None:
        assert latest["latest_bos"].kind == StructurePointKind.BEARISH_BOS


def test_range_oscillation_has_swings_but_no_confirmed_break():
    candles = _candles(_range_oscillation())
    df = candles_to_dataframe(candles)
    latest = latest_swings_and_breaks(df, swing_length=_SWING_LENGTH, close_break=True)

    assert latest["latest_swing_high"] is not None
    assert latest["latest_swing_low"] is not None
    assert latest["latest_bos"] is None
    assert latest["latest_choch"] is None
    assert _structure_state(latest["latest_bos"], latest["latest_choch"]) == "STRUCTURE_STATE_UNDEFINED"


# --------------------------------------------------------------------------- live verification

def _mt5_available():
    try:
        import MetaTrader5 as mt5
        return bool(mt5.initialize())
    except Exception:
        return False


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
@pytest.mark.parametrize("timeframe", ["H1", "M15"])
def test_analyze_structure_live_eurusd(timeframe):
    from mt5.connection import connect
    from market_structure import analyze_structure

    connect()
    result = analyze_structure("EURUSD", timeframe)

    assert result.status == "VALID"
    assert result.state in ("BULLISH", "BEARISH", "STRUCTURE_STATE_UNDEFINED")
    assert result.data_start_utc < result.data_end_utc
    assert result.closed_candle_count > 0
    assert result.smc_version is not None
