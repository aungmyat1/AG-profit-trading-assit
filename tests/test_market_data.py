"""Regression test for the naive-datetime/system-timezone bug in mt5.market_data.

get_candles() used to pass naive "broker wall clock" datetimes straight to
mt5.copy_rates_range(). The MetaTrader5 python module silently reinterprets a naive
datetime using this machine's OWN system timezone (not UTC, not broker time), which on
a non-UTC system shifted every query by that machine's UTC offset. Fixed by passing
epoch integers instead (see market_data.py's _to_broker_epoch). This test can only run
against a live connected terminal -- skipped otherwise.
"""
from __future__ import annotations

import datetime as dt

import pytest

pytest.importorskip("MetaTrader5")


def _mt5_available():
    import MetaTrader5 as mt5
    return mt5.initialize()


def _fx_session_open_today():
    return dt.datetime.now(dt.timezone.utc).weekday() < 5


@pytest.mark.skipif(
    not _mt5_available() or not _fx_session_open_today(),
    reason="requires a running MT5 terminal and an open FX trading day",
)
def test_get_candles_last_bar_matches_true_utc_now():
    from mt5.connection import connect
    from mt5.market_data import get_candles

    connect()
    now = dt.datetime.now(dt.timezone.utc)
    candles = get_candles("EURUSD", "M15", now - dt.timedelta(hours=1), now)

    assert candles, "expected at least one candle in the last hour"
    last = candles[-1]
    # The last bar's open time must be within the requested hour and not shifted by a
    # multi-hour system-timezone offset (the bug this test guards against).
    assert now - dt.timedelta(hours=1) <= last.time < now
    assert (now - last.time) < dt.timedelta(minutes=30)


def test_check_freshness_pure_function():
    from mt5.market_data import check_freshness

    now = dt.datetime(2026, 1, 5, 12, 0, tzinfo=dt.timezone.utc)
    assert check_freshness(now - dt.timedelta(seconds=30), now, max_age_seconds=120) is None
    assert check_freshness(now - dt.timedelta(seconds=200), now, max_age_seconds=120) == "STALE_DATA"


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_get_tick_returns_positive_bid_ask():
    from mt5.connection import connect
    from mt5.market_data import get_tick

    connect()
    tick = get_tick("EURUSD")
    assert tick.bid > 0
    assert tick.ask >= tick.bid
    assert tick.time_utc.tzinfo is not None


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_get_candles_unknown_symbol_fails_closed():
    from mt5.connection import connect
    from mt5.market_data import MarketDataError, get_candles

    connect()
    now = dt.datetime.now(dt.timezone.utc)
    with pytest.raises(MarketDataError) as exc_info:
        get_candles("NOT_A_REAL_SYMBOL", "M15", now - dt.timedelta(hours=1), now)
    assert exc_info.value.reason_code == "SYMBOL_NOT_FOUND"


@pytest.mark.skipif(
    not _mt5_available() or not _fx_session_open_today(),
    reason="requires a running MT5 terminal and an open FX trading day",
)
def test_get_candles_session_window_is_half_open_and_exact():
    import session_clock as sc
    from mt5.connection import connect
    from mt5.market_data import get_candles

    connect()
    now = dt.datetime.now(dt.timezone.utc)
    session_date = now.date()
    start, end = sc.get_session_bounds(session_date, "asian")
    if now < end:
        pytest.skip("today's Asian session has not completed yet")

    candles = get_candles("EURUSD", "M15", start, end)
    expected = sc.expected_bar_count("asian", "M15")

    assert len(candles) == expected  # exactly 24 -- the 06:00 bar must be excluded (half-open)
    assert candles[0].time == start
    assert candles[-1].time == end - dt.timedelta(minutes=15)
