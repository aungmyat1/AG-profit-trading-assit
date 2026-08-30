"""Tests for the Market Data Assistant layer (assistant/market_data.py): market
snapshot, historical UTC-range query, session completeness, data-health failure, and
multi-timeframe snapshot. Deterministic checks first; live-guarded checks against a
real MT5 terminal follow the same skipif pattern as tests/test_market_data.py.
"""
from __future__ import annotations

import datetime as dt

import pytest

from assistant.market_data import _detect_unexpected_gaps, _spans_weekend_closure
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _candle(hour, minute, day=5):
    t = dt.datetime(2026, 1, day, hour, minute, tzinfo=UTC)
    return Candle(time=t, open=1.1, high=1.1005, low=1.0995, close=1.1, volume=1.0)


# --------------------------------------------------------------------------- pure gap logic

def test_spans_weekend_closure_true_across_saturday():
    friday_evening = dt.datetime(2026, 1, 2, 21, 0, tzinfo=UTC)  # Friday
    sunday_evening = dt.datetime(2026, 1, 4, 22, 0, tzinfo=UTC)  # Sunday
    assert _spans_weekend_closure(friday_evening, sunday_evening) is True


def test_spans_weekend_closure_false_on_a_weekday_gap():
    monday = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    monday_later = dt.datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
    assert _spans_weekend_closure(monday, monday_later) is False


def test_detect_unexpected_gaps_flags_weekday_gap_not_weekend():
    # Two M15 candles 2 hours apart on a Monday -- an unexpected gap.
    candles = [_candle(10, 0), _candle(12, 0)]
    gaps = _detect_unexpected_gaps(candles, "M15")
    assert len(gaps) == 1


def test_detect_unexpected_gaps_ignores_normal_spacing():
    candles = [_candle(10, 0), _candle(10, 15), _candle(10, 30)]
    assert _detect_unexpected_gaps(candles, "M15") == []


# --------------------------------------------------------------------------- live verification

def _mt5_available():
    import MetaTrader5 as mt5
    return mt5.initialize()


def _fx_session_open_today():
    return dt.datetime.now(UTC).weekday() < 5


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_market_snapshot_live():
    from assistant.market_data import market_snapshot
    from mt5.connection import connect

    connect()
    snap = market_snapshot("EURUSD")
    assert snap.status == "OK"
    assert snap.bid > 0
    assert snap.ask >= snap.bid
    assert snap.latest_closed_candle is not None
    assert snap.recent_high >= snap.recent_low


@pytest.mark.skipif(
    not _mt5_available() or not _fx_session_open_today(),
    reason="requires a running MT5 terminal and an open FX trading day",
)
def test_historical_candles_utc_range_live():
    from assistant.market_data import historical_candles
    from mt5.connection import connect

    connect()
    now = dt.datetime.now(dt.timezone.utc)
    result = historical_candles("EURUSD", "M15", start_utc=now - dt.timedelta(hours=2), end_utc=now)
    assert result.status == "OK"
    assert result.candle_count > 0
    assert result.end_utc <= now


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_historical_candles_rejects_ambiguous_query():
    from assistant.market_data import historical_candles

    result = historical_candles("EURUSD", "M15", start_utc=dt.datetime.now(dt.timezone.utc), count=5)
    assert result.status == "AMBIGUOUS_QUERY"


@pytest.mark.skipif(
    not _mt5_available() or not _fx_session_open_today(),
    reason="requires a running MT5 terminal and an open FX trading day",
)
def test_session_snapshot_completeness_live():
    from assistant.market_data import session_snapshot
    from mt5.connection import connect
    import session_clock as sc

    connect()
    now = dt.datetime.now(dt.timezone.utc)
    session_date = now.date()
    _, end = sc.get_session_bounds(session_date, "asian")
    result = session_snapshot("EURUSD", "asian", session_date)

    if now < end:
        assert result.complete is False
        assert result.status == "SESSION_INCOMPLETE"
    else:
        assert result.complete is True
        assert result.status == "OK"
        assert result.bar_count == result.expected_bar_count == 24
        assert result.high >= result.low
        assert result.midpoint == pytest.approx((result.high + result.low) / 2.0)


@pytest.mark.skipif(
    not _mt5_available() or not _fx_session_open_today(),
    reason="requires a running MT5 terminal and an open FX trading day",
)
def test_data_health_ok_and_failure_live():
    from assistant.market_data import data_health
    from mt5.connection import connect

    connect()
    ok = data_health("EURUSD")
    assert ok.status == "OK"
    assert ok.mt5_connected is True

    failing = data_health("NOT_A_REAL_SYMBOL")
    assert failing.status == "SYMBOL_NOT_FOUND"
    assert failing.checks["symbol_available"] == "SYMBOL_NOT_FOUND"


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_multi_timeframe_snapshot_live():
    from assistant.market_data import multi_timeframe_snapshot
    from mt5.connection import connect

    connect()
    result = multi_timeframe_snapshot("EURUSD", ["M15", "H1"])
    assert result.status == "OK"
    assert len(result.by_timeframe) == 2
    for tf in result.by_timeframe:
        assert tf.status == "OK"
        assert tf.structure is not None
        assert tf.structure.state in ("BULLISH", "BEARISH", "STRUCTURE_STATE_UNDEFINED")
