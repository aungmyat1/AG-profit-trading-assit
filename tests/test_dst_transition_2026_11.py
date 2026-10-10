"""CS-DST-FIX-01: VT server clock (New York + 7h) across the 2026-11-01 US DST end.

Covers the CS-DST-AUDIT-01 anomalies A1 (per-bar rule conversion, no process-cached offset),
A2 (repeated/skipped server hour is explicit, never folded) and A3 (25h/23h server D1).
The fake MT5 below stamps bars exactly as the VT server does: server wall clock = NY wall + 7h,
encoded as epoch seconds. It is built from zoneinfo only, independent of the code under test.
"""
from __future__ import annotations

import calendar
import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")
M15 = dt.timedelta(minutes=15)


def _server_raw(t_utc: dt.datetime) -> int:
    wall = t_utc.astimezone(NY).replace(tzinfo=None) + dt.timedelta(hours=7)
    return calendar.timegm(wall.timetuple())


def _server_text(t_utc: dt.datetime) -> str:
    return (t_utc.astimezone(NY).replace(tzinfo=None) + dt.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")


def _fx_open(t_utc: dt.datetime) -> bool:
    """FX trades Sun 17:00 NY -> Fri 17:00 NY."""
    ny = t_utc.astimezone(NY)
    wd = ny.weekday()
    return not (wd == 5 or (wd == 4 and ny.hour >= 17) or (wd == 6 and ny.hour < 17))


def _bars(start: dt.datetime, end: dt.datetime, fx: bool):
    """Bar-open UTC instants in [start, end), M15."""
    out, t = [], start
    while t < end:
        if not fx or _fx_open(t):
            out.append(t)
        t += M15
    return out


def _row(t_utc: dt.datetime) -> dict:
    return {"time": _server_raw(t_utc), "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.1,
            "tick_volume": 10, "spread": 1, "real_volume": 0}


class FakeMt5:
    """copy_rates_from_pos over a series that grows with `now` (a long-lived process)."""
    TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_M30 = 1, 5, 15, 30
    TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1, TIMEFRAME_W1 = 16385, 16388, 16408, 32769

    def __init__(self, fx: bool = True):
        self.fx = fx
        self.now = None

    def set_now(self, now: dt.datetime):
        self.now = now

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def symbol_info(self, symbol):
        return SimpleNamespace(visible=True, spread=1)

    def symbol_select(self, symbol, enable):
        return True

    def last_error(self):
        return (0, "")

    def copy_rates_from_pos(self, symbol, timeframe, pos, count):
        assert timeframe == self.TIMEFRAME_M15
        times = _bars(dt.datetime(2026, 10, 5, tzinfo=UTC), self.now + M15, self.fx)  # last = forming bar at `now`
        rows = [_row(t) for t in times]
        end = len(rows) - pos
        return rows[max(0, end - count):end]


@pytest.fixture
def md(monkeypatch):
    from mt5 import broker_time, market_data
    fake = FakeMt5()
    monkeypatch.setattr(market_data, "mt5", fake)
    monkeypatch.setattr(broker_time, "mt5", fake)
    market_data.clear_raw_candle_cache()
    cached = getattr(market_data, "_broker_offset_hours", None)  # pre-fix process cache, if any
    if cached is not None and hasattr(cached, "cache_clear"):
        cached.cache_clear()
    yield market_data, fake
    market_data.clear_raw_candle_cache()
    if cached is not None and hasattr(cached, "cache_clear"):
        cached.cache_clear()


# ------------------------------------------------------------------ broker_time / reopen

def test_us_eastern_offset_flips_on_2026_11_01():
    from mt5.broker_time import us_eastern_utc_offset_hours
    assert us_eastern_utc_offset_hours(dt.date(2026, 10, 31)) == 4
    assert us_eastern_utc_offset_hours(dt.date(2026, 11, 1)) == 5


def test_offset_from_reopen_basic_and_2026_11_01_transition():
    from mt5.broker_time import BrokerTimeError, offset_from_reopen
    # Basic: summer reopen Sun 2026-09-27 17:00 EDT = 21:00Z, read as Mon 00:00 server.
    assert offset_from_reopen(dt.datetime(2026, 9, 28, 0, 0)) == 3
    # Last reopen before the change (10-25, EDT) and the first one after it (11-01, EST).
    assert offset_from_reopen(dt.datetime(2026, 10, 26, 0, 0)) == 3
    assert offset_from_reopen(dt.datetime(2026, 11, 2, 0, 0)) == 2
    with pytest.raises(BrokerTimeError):
        offset_from_reopen(dt.datetime(2026, 11, 2, 0, 30))


# ------------------------------------------------------------------ A2: repeated / skipped hour

@pytest.mark.parametrize("wall,code", [
    (dt.datetime(2026, 11, 1, 8, 0), "AMBIGUOUS_DST_HOUR"),
    (dt.datetime(2026, 11, 1, 8, 45), "AMBIGUOUS_DST_HOUR"),
    (dt.datetime(2026, 3, 8, 9, 0), "NONEXISTENT_DST_HOUR"),
    (dt.datetime(2026, 3, 8, 9, 45), "NONEXISTENT_DST_HOUR"),
])
def test_server_time_to_utc_rejects_dst_hour(wall, code):
    from host_evidence import symbol_metadata as sm
    with pytest.raises(ValueError) as exc:
        sm.server_time_to_utc(wall)
    assert getattr(exc.value, "reason_code", None) == code


def test_server_time_to_utc_edges_of_dst_hour():
    from host_evidence.symbol_metadata import server_time_to_utc
    assert server_time_to_utc(dt.datetime(2026, 11, 1, 7, 45)) == dt.datetime(2026, 11, 1, 4, 45, tzinfo=UTC)
    assert server_time_to_utc(dt.datetime(2026, 11, 1, 9, 0)) == dt.datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    assert server_time_to_utc(dt.datetime(2026, 3, 8, 8, 45)) == dt.datetime(2026, 3, 8, 6, 45, tzinfo=UTC)
    assert server_time_to_utc(dt.datetime(2026, 3, 8, 10, 0)) == dt.datetime(2026, 3, 8, 7, 0, tzinfo=UTC)


def test_candle_adapter_drops_repeated_hour_bars(caplog):
    from mt5 import mt5_candles_readonly as ro
    fake = FakeMt5(fx=False)
    fake.set_now(dt.datetime(2026, 11, 1, 8, 0, tzinfo=UTC))
    rates = fake.copy_rates_from_pos("BTCUSD", fake.TIMEFRAME_M15, 1, 24)  # 02:00Z..07:45Z
    with caplog.at_level("WARNING"):
        candles = ro._to_canonical("BTCUSD", rates)
    times = [c.time for c in candles]
    assert len(times) == len(set(times))
    assert not [t for t in times if dt.datetime(2026, 11, 1, 5, tzinfo=UTC) <= t < dt.datetime(2026, 11, 1, 7, tzinfo=UTC)]
    assert times[-1] == dt.datetime(2026, 11, 1, 7, 45, tzinfo=UTC)
    assert "AMBIGUOUS_DST_HOUR" in caplog.text


# ------------------------------------------------------------------ A1: market_data (FX)

def _expected_closed(now: dt.datetime, count: int):
    return _bars(dt.datetime(2026, 10, 5, tzinfo=UTC), now, True)[-count:]


def test_long_lived_process_across_2026_11_01(md):
    market_data, fake = md
    fake.set_now(dt.datetime(2026, 10, 30, 12, 0, tzinfo=UTC))
    before = market_data.get_latest_candles("EURUSD", "M15", 8)
    assert [c.time for c in before] == _expected_closed(fake.now, 8)
    market_data.clear_raw_candle_cache()  # bar cache only; the process (and any offset state) lives on
    fake.set_now(dt.datetime(2026, 11, 2, 12, 0, tzinfo=UTC))
    after = market_data.get_latest_candles("EURUSD", "M15", 8)
    assert [c.time for c in after] == _expected_closed(fake.now, 8)
    assert after[-1].time == dt.datetime(2026, 11, 2, 11, 45, tzinfo=UTC)


def test_fx_lookback_spanning_10_30_to_11_02(md):
    market_data, fake = md
    fake.set_now(dt.datetime(2026, 11, 2, 12, 0, tzinfo=UTC))
    expected = _expected_closed(fake.now, 200)
    candles = market_data.get_latest_candles("EURUSD", "M15", 200)
    times = [c.time for c in candles]
    assert times == expected
    assert dt.datetime(2026, 10, 30, 20, 45, tzinfo=UTC) in times     # last Fri bar, 16:45 EDT
    assert dt.datetime(2026, 10, 30, 21, 45, tzinfo=UTC) not in times  # +2 mis-conversion of it
    assert dt.datetime(2026, 11, 1, 22, 0, tzinfo=UTC) in times        # Sun reopen, 17:00 EST


# ------------------------------------------------------------------ A1: session_scanner (crypto)

def test_crypto_scanner_lookback_spanning_10_30_to_11_02():
    from session_scanner.quality import normalize_bars
    from session_scanner.timebase import derive_time_authority
    ta = derive_time_authority({"utc_time": "2026-11-02T12:00:00Z",
                                "trade_server_last_known_time": "2026-11-02T14:00:00"})
    assert ta.gate == "PASS"
    utc_times = _bars(dt.datetime(2026, 10, 30, 12, tzinfo=UTC), dt.datetime(2026, 11, 2, 12, tzinfo=UTC), False)
    raw = [{"time": _server_text(t), "open": 1, "high": 2, "low": 0.5, "close": 1} for t in utc_times]
    got = [b.time_utc for b in normalize_bars(raw, ta)]
    dst_hour = [t for t in utc_times if dt.datetime(2026, 11, 1, 5, tzinfo=UTC) <= t < dt.datetime(2026, 11, 1, 7, tzinfo=UTC)]
    assert got == [t for t in utc_times if t not in dst_hour]


def test_scanner_gate_fails_when_live_offset_disagrees_with_rule():
    from session_scanner.timebase import derive_time_authority
    ta = derive_time_authority({"utc_time": "2026-11-02T12:00:00Z",
                                "trade_server_last_known_time": "2026-11-02T15:00:00"})  # +3 after DST end
    assert ta.gate == "FAIL" and ta.reason == "BROKER_OFFSET_RULE_MISMATCH"


# ------------------------------------------------------------------ A3: 25h / 23h server D1

def _d1(t):
    from strategy_engine.session import Candle
    return Candle(time=t, open=1, high=2, low=0.5, close=1, volume=1)


def test_25h_d1_not_closed_at_open_plus_24h():
    from v1_tickets.crypto_cfd import _closed
    d1_open = dt.datetime(2026, 10, 31, 21, tzinfo=UTC)          # server 2026-11-01 00:00
    rows = [_d1(d1_open - dt.timedelta(days=1)), _d1(d1_open)]
    assert [c.time for c in _closed(rows, dt.datetime(2026, 11, 1, 21, 30, tzinfo=UTC), dt.timedelta(days=1))] \
        == [d1_open - dt.timedelta(days=1)]
    assert [c.time for c in _closed(rows, dt.datetime(2026, 11, 1, 22, 0, tzinfo=UTC), dt.timedelta(days=1))] \
        == [d1_open - dt.timedelta(days=1), d1_open]


def test_d1_closed_when_next_open_observed_and_23h_spring_day():
    from v1_tickets.crypto_cfd import _closed
    spring = dt.datetime(2026, 3, 7, 22, tzinfo=UTC)              # server 2026-03-08 00:00, 23h long
    assert [c.time for c in _closed([_d1(spring)], dt.datetime(2026, 3, 8, 21, 0, tzinfo=UTC),
                                    dt.timedelta(days=1))] == [spring]
    nxt = dt.datetime(2026, 3, 8, 21, tzinfo=UTC)
    assert [c.time for c in _closed([_d1(spring), _d1(nxt)], dt.datetime(2026, 3, 8, 21, 0, tzinfo=UTC),
                                    dt.timedelta(days=1))] == [spring]


# ------------------------------------------------------------------ trading_date on 11-01

def test_large_smc_trading_date_on_2026_11_01():
    from large_smc_watch.watch import next_day_boundary, trading_date
    assert trading_date(dt.datetime(2026, 10, 31, 21, 0, tzinfo=UTC)) == dt.date(2026, 11, 1)   # 17:00 EDT
    assert trading_date(dt.datetime(2026, 11, 1, 21, 59, tzinfo=UTC)) == dt.date(2026, 11, 1)   # 16:59 EST
    assert trading_date(dt.datetime(2026, 11, 1, 22, 0, tzinfo=UTC)) == dt.date(2026, 11, 2)    # 17:00 EST
    assert next_day_boundary(dt.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)) == dt.datetime(2026, 11, 1, 22, 0, tzinfo=UTC)
