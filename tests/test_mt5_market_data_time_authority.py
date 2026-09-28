"""P6-R1: mt5.market_data.get_candles consumes the shared server-time authority.

The MT5 SDK boundary (account_info / terminal_info / symbol_info / copy_rates_range) is
replaced by an in-memory broker-clock server; no terminal is touched. Candle bars are
the same synthetic shapes as test_broker_time_authority (USDJPY lacks 2026-09-14 00:00).
"""
from __future__ import annotations

import calendar
import datetime as dt
from types import SimpleNamespace

import pytest

import mt5.market_data as md
from test_broker_time_authority import EURUSD, GBPUSD, USDJPY, weeks

UTC = dt.timezone.utc


def _rates(times):
    return [{"time": calendar.timegm(t.timetuple()), "open": 1.0, "high": 1.0, "low": 1.0,
             "close": 1.0, "tick_volume": 1} for t in times]


@pytest.fixture
def server(monkeypatch):
    series = {"EURUSD": EURUSD, "GBPUSD": GBPUSD, "USDJPY": USDJPY}
    calls = []

    def copy_rates_range(symbol, _tf, frm, to):
        calls.append(symbol)
        return _rates([t for t in series[symbol] if frm <= calendar.timegm(t.timetuple()) <= to])

    md.clear_time_authority_cache()
    for name, fn in {
        "account_info": lambda: SimpleNamespace(server="VTMarkets-Demo", company="VT Markets"),
        "terminal_info": lambda: SimpleNamespace(connected=True),
        "symbol_info": lambda s: SimpleNamespace(visible=True) if s in series else None,
        "copy_rates_range": copy_rates_range,
        "last_error": lambda: (1, "Success"),
    }.items():
        monkeypatch.setattr(md.mt5, name, fn, raising=False)
    yield SimpleNamespace(series=series, calls=calls)
    md.clear_time_authority_cache()


def test_usdjpy_current_week_candles_are_true_utc(server):
    bars = md.get_candles("USDJPY", "M15", dt.datetime(2026, 9, 28, 0, tzinfo=UTC), dt.datetime(2026, 9, 28, 6, tzinfo=UTC))
    assert len(bars) == 24
    assert (bars[0].time, bars[-1].time) == (dt.datetime(2026, 9, 28, 0, tzinfo=UTC), dt.datetime(2026, 9, 28, 5, 45, tzinfo=UTC))


def test_usdjpy_incomplete_week_uses_same_server_authority(server):
    bars = md.get_candles("USDJPY", "M15", dt.datetime(2026, 9, 15, 0, tzinfo=UTC), dt.datetime(2026, 9, 15, 6, tzinfo=UTC))
    assert bars[0].time == dt.datetime(2026, 9, 15, 0, tzinfo=UTC) and len(bars) == 24
    prov = md.server_time_provenance("USDJPY", dt.datetime(2026, 9, 15, tzinfo=UTC), dt.datetime(2026, 9, 15, 6, tzinfo=UTC))
    assert prov == [{
        "broker": "VT Markets", "server": "VTMarkets-Demo",
        "effective_from_utc": "2026-09-13T21:00:00+00:00", "effective_until_utc": "2026-09-20T20:00:00+00:00",
        "effective_until_basis": "WEEK_BOUND",
        "utc_offset_hours": 3, "source": "SERVER_CONSENSUS", "evidence_symbols": ["EURUSD", "GBPUSD"],
        "scope": "SERVER_SHARED",
    }]


def test_validated_authority_is_reused_without_new_evidence(server):
    span = (dt.datetime(2026, 9, 28, tzinfo=UTC), dt.datetime(2026, 9, 28, 6, tzinfo=UTC))
    md.get_candles("EURUSD", "M15", *span)
    evidence_calls = len(server.calls)
    md.get_candles("GBPUSD", "M15", *span)
    assert len(server.calls) == evidence_calls + 1  # only the data request itself


def test_dst_transition_maps_each_bar_through_its_own_period(server):
    server.series["EURUSD"] = weeks([dt.datetime(2026, 10, 19), dt.datetime(2026, 10, 26), dt.datetime(2026, 11, 2)],
                                    last_until=dt.datetime(2026, 11, 6))
    server.series["GBPUSD"] = server.series["EURUSD"]
    bars = md.get_candles("EURUSD", "M15", dt.datetime(2026, 10, 30, 20, tzinfo=UTC), dt.datetime(2026, 11, 1, 23, tzinfo=UTC))
    times = [b.time for b in bars]
    assert times[:4] == [dt.datetime(2026, 10, 30, 20, 0, tzinfo=UTC) + i * dt.timedelta(minutes=15) for i in range(4)]
    assert times[3] == dt.datetime(2026, 10, 30, 20, 45, tzinfo=UTC)          # Fri 23:45 broker at +3
    assert times[4:] == [dt.datetime(2026, 11, 1, 22, 0, tzinfo=UTC),         # Mon 00:00 broker at +2
                         dt.datetime(2026, 11, 1, 22, 15, tzinfo=UTC),
                         dt.datetime(2026, 11, 1, 22, 30, tzinfo=UTC),
                         dt.datetime(2026, 11, 1, 22, 45, tzinfo=UTC)]


def test_same_server_disagreement_fails_closed(server):
    server.series["GBPUSD"] = weeks([dt.datetime(2026, 9, 21), dt.datetime(2026, 9, 28)],
                                    drop={dt.datetime(2026, 9, 28, 0, m) for m in (0, 15, 30, 45)})
    with pytest.raises(md.MarketDataError) as exc:
        md.get_candles("USDJPY", "M15", dt.datetime(2026, 9, 28, tzinfo=UTC), dt.datetime(2026, 9, 28, 6, tzinfo=UTC))
    assert exc.value.reason_code == "TIME_AUTHORITY_CONFLICT"


def test_no_server_identity_fails_closed(server, monkeypatch):
    monkeypatch.setattr(md.mt5, "account_info", lambda: None, raising=False)
    with pytest.raises(md.MarketDataError) as exc:
        md.get_candles("USDJPY", "M15", dt.datetime(2026, 9, 28, tzinfo=UTC), dt.datetime(2026, 9, 28, 6, tzinfo=UTC))
    assert exc.value.reason_code == "TIME_AUTHORITY_UNAVAILABLE"


def test_no_evidence_for_period_fails_closed(server):
    with pytest.raises(md.MarketDataError) as exc:
        md.get_candles("USDJPY", "M15", dt.datetime(2026, 7, 1, tzinfo=UTC), dt.datetime(2026, 7, 1, 6, tzinfo=UTC))
    assert exc.value.reason_code == "TIME_AUTHORITY_UNAVAILABLE"
