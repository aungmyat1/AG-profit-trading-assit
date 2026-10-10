"""MT5_CANDLES_READONLY_R1: read-only boundary, UTC normalization, symbol map, integrity,
gap reporting and evaluator-fixture (strategy_engine Candle) compatibility."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import re

import pytest

from host_evidence.symbol_metadata import server_time_to_utc
from mt5 import mt5_candles_readonly as adapter
from strategy_engine.session import Candle

UTC = dt.timezone.utc
MAP = {"EURUSD": "EURUSD-VIP", "GBPUSD": "GBPUSD-VIP", "USDJPY": "USDJPY-VIP", "XAUUSD": "XAUUSD-VIP"}
FORBIDDEN = re.compile(r"order_send|order_check|symbol_select|positions_|orders_|history_|account_info|\.login\(")


def _server_epoch(utc_time: dt.datetime) -> int:
    """Inverse of the adapter's conversion: UTC -> server wall clock encoded as epoch seconds."""
    for h in (2, 3):
        wall = (utc_time + dt.timedelta(hours=h)).replace(tzinfo=None)
        if server_time_to_utc(wall) == utc_time:
            return int(wall.replace(tzinfo=UTC).timestamp())
    raise AssertionError("no server offset matched")


def _rate(utc_time, o=1.1, h=1.2, l=1.0, c=1.15, tv=100, sp=5, rv=0):
    return {"time": _server_epoch(utc_time), "open": o, "high": h, "low": l, "close": c,
            "tick_volume": tv, "spread": sp, "real_volume": rv}


class FakeMT5:
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385

    def __init__(self, rates=None, known=None):
        self._rates = rates if rates is not None else []
        self._known = set(MAP.values()) if known is None else known
        self.calls = []

    def __getattribute__(self, name):
        if not name.startswith("_") and name not in ("calls", "TIMEFRAME_M15", "TIMEFRAME_H1") \
                and name not in adapter.ALLOWED_MT5_CALLS:
            raise AssertionError(f"forbidden MT5 call: {name}")
        return object.__getattribute__(self, name)

    def symbol_info(self, s):
        self.calls.append(("symbol_info", s))
        return object() if s in self._known else None

    def copy_rates_from_pos(self, s, tf, pos, count):
        self.calls.append(("copy_rates_from_pos", s, tf, pos, count))
        return self._rates[-count:] if self._rates else None

    def copy_rates_range(self, s, tf, start, end):
        self.calls.append(("copy_rates_range", s, tf, start, end))
        return self._rates

    def last_error(self):
        return (1, "fake")


def _bars(start, n, minutes):
    return [start + dt.timedelta(minutes=minutes * i) for i in range(n)]


# --- A: read-only boundary ------------------------------------------------------------------

def test_module_source_has_no_order_or_mutation_calls():
    src = open(adapter.__file__, encoding="utf-8").read()
    code = src.split('"""', 2)[2]  # skip the module docstring, which names what is forbidden
    assert not FORBIDDEN.search(code)
    for name in re.findall(r"mt5\.(\w+)\(", code):
        assert name in adapter.ALLOWED_MT5_CALLS


def test_fetch_uses_only_allowed_calls_and_closed_bars():
    rates = [_rate(t) for t in _bars(dt.datetime(2026, 10, 6, 0, tzinfo=UTC), 8, 15)]
    fake = FakeMT5(rates)
    out = adapter.fetch_closed_candles(fake, "EURUSD", "M15", 8, MAP)
    assert len(out) == 8
    assert {c[0] for c in fake.calls} <= adapter.ALLOWED_MT5_CALLS
    assert ("copy_rates_from_pos", "EURUSD-VIP", FakeMT5.TIMEFRAME_M15, 1, 8) in fake.calls


# --- B/E: canonical schema + UTC normalization ----------------------------------------------

@pytest.mark.parametrize("utc_open", [
    dt.datetime(2026, 7, 15, 21, 0, tzinfo=UTC),   # NY summer: server = UTC+3
    dt.datetime(2026, 12, 15, 22, 0, tzinfo=UTC),  # NY winter: server = UTC+2
])
def test_server_time_normalized_to_aware_utc(utc_open):
    out = adapter.fetch_closed_candles(FakeMT5([_rate(utc_open)]), "XAUUSD", "H1", 1, MAP)
    c = out[0]
    assert c.time == utc_open and c.time.utcoffset() == dt.timedelta(0)
    assert c.symbol == "XAUUSD"  # canonical, never the broker symbol
    assert tuple(f.name for f in dataclasses.fields(c)) == adapter.CANONICAL_FIELDS
    assert (c.tick_volume, c.spread, c.real_volume) == (100, 5, 0)


def test_server_midnight_is_new_york_1700():
    wall = dt.datetime(2026, 10, 7, 0, 0)  # server midnight, NY on EDT
    raw = int(wall.replace(tzinfo=UTC).timestamp())
    rate = {"time": raw, "open": 1, "high": 1, "low": 1, "close": 1, "tick_volume": 1, "spread": 0, "real_volume": 0}
    c = adapter.fetch_closed_candles(FakeMT5([rate]), "EURUSD", "H1", 1, MAP)[0]
    assert c.time == dt.datetime(2026, 10, 6, 21, 0, tzinfo=UTC)


# --- C: symbol map ---------------------------------------------------------------------------

def test_committed_symbol_map_is_explicit_for_all_four():
    assert adapter.default_symbol_map() == MAP


def test_unknown_canonical_fails_loudly():
    with pytest.raises(adapter.CandleAdapterError) as e:
        adapter.fetch_closed_candles(FakeMT5([]), "AUDUSD", "M15", 1, MAP)
    assert e.value.code == adapter.SYMBOL_MAPPING_MISSING


def test_missing_mapping_fails_loudly_without_substitution(tmp_path):
    rec = {"canonical_symbol": "EURUSD", "broker_symbol": "EURUSD-VIP"}
    (tmp_path / "EURUSD.json").write_text(json.dumps(rec), encoding="utf-8")
    (tmp_path / "GBPUSD.json").write_text(json.dumps({"canonical_symbol": "EURUSD", "broker_symbol": "X"}), encoding="utf-8")
    smap = adapter.load_symbol_map(str(tmp_path))
    assert smap == {"EURUSD": "EURUSD-VIP"}
    fake = FakeMT5([])
    for sym in ("GBPUSD", "USDJPY", "XAUUSD"):
        with pytest.raises(adapter.CandleAdapterError) as e:
            adapter.fetch_closed_candles(fake, sym, "H1", 1, smap)
        assert e.value.code == adapter.SYMBOL_MAPPING_MISSING
    assert fake.calls == []  # no lookup of any guessed symbol


def _mixed_map(tmp_path, monkeypatch, entries):
    """Point the canonical map loader at a temp map holding ``entries`` (canonical -> item)."""
    import yaml

    from mt5 import canonical_broker_map as cbm
    raw = yaml.safe_load(open(cbm.DEFAULT_MAP_PATH, encoding="utf-8"))
    raw["entries"].update(entries)
    path = tmp_path / "map.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    real = cbm.load_map
    monkeypatch.setattr(cbm, "load_map", lambda p=str(path): real(p))


@pytest.mark.parametrize("bad", [
    {"GBPUSD": {"status": "UNMAPPED", "reason": "NO_VISIBLE_FULL_CANDIDATE"}},
    {"USDJPY": "no_capture"},
    {"GBPUSD": {"status": "UNMAPPED", "reason": "NO_VISIBLE_FULL_CANDIDATE"}, "XAUUSD": "no_capture"},
])
def test_unmapped_or_data_error_blocks_only_that_symbol(tmp_path, monkeypatch, bad):
    import copy

    import yaml

    from mt5 import canonical_broker_map as cbm
    raw = yaml.safe_load(open(cbm.DEFAULT_MAP_PATH, encoding="utf-8"))
    entries = {}
    for sym, item in bad.items():
        if item == "no_capture":  # MAPPED but its host-capture citation is missing -> DATA_ERROR
            item = copy.deepcopy(raw["entries"][sym])
            item["host_capture"]["path"] = f"config/symbol_metadata/host_captured/missing/{sym}.json"
        entries[sym] = item
    _mixed_map(tmp_path, monkeypatch, entries)
    mapped, blocked = adapter.symbol_map_status()
    assert set(blocked) == set(bad)
    assert mapped == {k: v for k, v in MAP.items() if k not in bad}
    assert adapter.default_symbol_map() == mapped
    start = dt.datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    fake = FakeMT5([_rate(t) for t in _bars(start, 4, 15)])
    out = adapter.fetch_closed_candles_per_symbol(fake, adapter.SUPPORTED_SYMBOLS, "M15", 3, mapped)
    for sym in adapter.SUPPORTED_SYMBOLS:
        if sym in bad:
            assert out[sym]["status"] == adapter.DATA_ERROR
            assert out[sym]["code"] == adapter.SYMBOL_MAPPING_MISSING
        else:
            assert out[sym]["status"] == "OK" and len(out[sym]["candles"]) == 3
    # No terminal lookup for a blocked symbol, under any spelling.
    looked_up = {c[1] for c in fake.calls}
    assert looked_up == {MAP[s] for s in MAP if s not in bad}


def test_absent_broker_symbol_is_data_error_for_that_symbol_only():
    start = dt.datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    fake = FakeMT5([_rate(t) for t in _bars(start, 4, 15)], known=set(MAP.values()) - {"XAUUSD-VIP"})
    out = adapter.fetch_closed_candles_per_symbol(fake, adapter.SUPPORTED_SYMBOLS, "M15", 3, MAP)
    assert out["XAUUSD"]["status"] == adapter.DATA_ERROR
    assert out["XAUUSD"]["code"] == adapter.SYMBOL_MAPPING_MISSING
    assert all(out[s]["status"] == "OK" for s in ("EURUSD", "GBPUSD", "USDJPY"))


def test_broker_symbol_unknown_to_terminal_fails_loudly():
    fake = FakeMT5([], known=set())
    with pytest.raises(adapter.CandleAdapterError) as e:
        adapter.fetch_closed_candles(fake, "USDJPY", "M15", 1, MAP)
    assert e.value.code == adapter.SYMBOL_MAPPING_MISSING
    assert [c[0] for c in fake.calls] == ["symbol_info"]


def test_unsupported_timeframe():
    with pytest.raises(adapter.CandleAdapterError) as e:
        adapter.fetch_closed_candles(FakeMT5([]), "EURUSD", "M5", 1, MAP)
    assert e.value.code == adapter.UNSUPPORTED_TIMEFRAME


def test_no_data_is_data_missing():
    with pytest.raises(adapter.CandleAdapterError) as e:
        adapter.fetch_closed_candles(FakeMT5([]), "EURUSD", "M15", 5, MAP)
    assert e.value.code == adapter.DATA_MISSING


# --- E: integrity ----------------------------------------------------------------------------

def test_duplicate_timestamp_raises():
    t = dt.datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
    with pytest.raises(adapter.CandleAdapterError) as e:
        adapter.fetch_closed_candles(FakeMT5([_rate(t), _rate(t)]), "EURUSD", "M15", 2, MAP)
    assert e.value.code == adapter.DUPLICATE_TIMESTAMP


def test_non_monotonic_raises():
    t = dt.datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
    rates = [_rate(t + dt.timedelta(minutes=15)), _rate(t)]
    with pytest.raises(adapter.CandleAdapterError) as e:
        adapter.fetch_closed_candles(FakeMT5(rates), "EURUSD", "M15", 2, MAP)
    assert e.value.code == adapter.NON_MONOTONIC


def test_off_grid_raises():
    t = dt.datetime(2026, 10, 6, 10, 15, tzinfo=UTC)
    with pytest.raises(adapter.CandleAdapterError) as e:
        adapter.fetch_closed_candles(FakeMT5([_rate(t)]), "EURUSD", "H1", 1, MAP)
    assert e.value.code == adapter.OFF_GRID_TIMESTAMP


def test_gaps_reported_not_filled_and_classified():
    start = dt.datetime(2026, 10, 2, 18, 0, tzinfo=UTC)          # Fri 14:00 NY
    fri = _bars(start, 3, 60)                                     # 18:00..20:00 UTC (last Fri bar)
    sun = _bars(dt.datetime(2026, 10, 4, 21, 0, tzinfo=UTC), 2, 60)  # Sun 17:00 NY reopen
    mon = [dt.datetime(2026, 10, 5, 12, 0, tzinfo=UTC)] + _bars(dt.datetime(2026, 10, 5, 15, 0, tzinfo=UTC), 6, 60)
    mon_reopen = [dt.datetime(2026, 10, 5, 22, 0, tzinfo=UTC)]  # 18:00 NY, after the 17:00 NY break
    times = fri + sun + mon + mon_reopen
    out = adapter.fetch_closed_candles(FakeMT5([_rate(t) for t in times]), "XAUUSD", "H1", len(times), MAP)
    assert [c.time for c in out] == times  # nothing invented
    rep = adapter.series_report(out, "H1")
    kinds = [g["kind"] for g in rep["gaps"]]
    assert kinds == ["WEEKEND_CLOSE", "INTRADAY_GAP", "INTRADAY_GAP", "DAILY_BREAK"]
    assert rep["gaps"][-1]["missing_bars"] == 1
    assert rep["duplicates"] == rep["non_monotonic"] == 0 and rep["utc_aware"]
    assert rep["unexpected_gaps"] == 2


def test_range_fetch_filters_in_utc():
    times = _bars(dt.datetime(2026, 10, 6, 0, tzinfo=UTC), 12, 15)
    fake = FakeMT5([_rate(t) for t in times])
    out = adapter.fetch_candles_range(fake, "GBPUSD", "M15", times[2], times[5], MAP)
    assert [c.time for c in out] == times[2:6]


# --- F: evaluator fixture compatibility ------------------------------------------------------

def test_engine_candle_matches_fixture_schema():
    t = dt.datetime(2026, 10, 6, 7, 0, tzinfo=UTC)
    c = adapter.fetch_closed_candles(FakeMT5([_rate(t, tv=321)]), "EURUSD", "M15", 1, MAP)[0]
    e = c.to_engine_candle()
    assert isinstance(e, Candle)
    required = {f.name for f in dataclasses.fields(Candle)}
    assert required <= set(adapter.CANONICAL_FIELDS) | {"volume"}
    assert e == Candle(time=t, open=1.1, high=1.2, low=1.0, close=1.15, volume=321.0)
    assert all(isinstance(getattr(e, k), float) for k in ("open", "high", "low", "close", "volume"))


def test_as_rows_json_safe():
    t = dt.datetime(2026, 10, 6, 7, 0, tzinfo=UTC)
    rows = adapter.as_rows(adapter.fetch_closed_candles(FakeMT5([_rate(t)]), "USDJPY", "H1", 1, MAP))
    assert json.loads(json.dumps(rows))[0]["time"] == "2026-10-06T07:00:00+00:00"
    assert tuple(rows[0]) == adapter.CANONICAL_FIELDS


def test_adapter_does_not_import_evaluator():
    src = open(adapter.__file__, encoding="utf-8").read()
    assert "daily_evaluator" not in src and "v1_tickets" not in src
    assert os.path.basename(adapter.__file__) == "mt5_candles_readonly.py"
