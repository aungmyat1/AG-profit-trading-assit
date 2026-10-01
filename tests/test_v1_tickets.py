"""AG V1 T6/T7/T8: informational tickets (Goal 1). Synthetic fixtures only; no network, no
broker. Covers FX/gold on both frozen session pairs, crypto BTCUSDT/ETHUSDT in the frozen
daily window with the data source printed, fallback, market-data failure, and idempotent
ARCHIVE_ONLY journaling."""
from __future__ import annotations

import datetime as dt
import glob
import math
import os

import pytest

from execution_runtime.public_crypto_feed import CandleBundle, PublicCryptoFeedUnavailable
from strategy_engine.session import Candle
from v1_tickets.crypto import archive_crypto_ticket, build_crypto_ticket
from v1_tickets.fx import HOST_METADATA_FIELDS, V1_CYCLES, V1_FX_SYMBOLS, archive_fx_ticket, build_fx_ticket

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)
SCALE = {"EURUSD": 1.0, "GBPUSD": 1.2, "USDJPY": 140.0, "XAUUSD": 2400.0}
REF_HOUR = {"ASIAN_LONDON": (0, 7), "LONDON_NEWYORK": (6, 12)}


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    """Host captures on the machine running the tests must never leak in (evidence resolves from repo root)."""
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def _c(h, m, o, hi, lo, cl, k):
    return Candle(dt.datetime(2026, 1, 5, h, m, tzinfo=UTC), o * k, hi * k, lo * k, cl * k)


def _fx(symbol, cycle):
    k = SCALE[symbol]
    ref, post = REF_HOUR[cycle]
    session = [_c(ref, 0, 1.1000, 1.1050, 1.0950, 1.1010, k), _c(ref, 15, 1.1010, 1.1040, 1.0960, 1.1005, k)]
    post_c = [_c(post, 0, 1.1005, 1.1006, 1.1004, 1.1005, k), _c(post, 15, 1.1005, 1.1060, 1.1000, 1.1048, k)]
    return session, post_c


@pytest.mark.parametrize("symbol", V1_FX_SYMBOLS)
@pytest.mark.parametrize("cycle", V1_CYCLES)
def test_fx_ticket_ready_with_frozen_contract_targets(symbol, cycle):
    session, post = _fx(symbol, cycle)
    at = dt.datetime(2026, 1, 5, REF_HOUR[cycle][1], 35, tzinfo=UTC)      # signal bar (h:15) closed 5 min ago
    t = build_fx_ticket(symbol, cycle, DAY, session, 2, post, data_source="FIXTURE", evaluated_at=at,
                        data_close=at, spread=0.0001 * SCALE[symbol])
    assert t["decision"] == "READY" and t["direction"] == "SHORT" and t["strategy_version"] == "1.1.1"
    assert t["targets"][0]["type"] == "OPPOSITE_SESSION_BOUNDARY" and t["targets"][1]["type"] == "FIXED_R_MULTIPLE_5"
    assert t["targets"][0]["price"] < t["entry"] < t["stop_loss"]          # SHORT geometry
    assert t["data_source"] == "FIXTURE" and t["label"].endswith("NOT A BROKER ORDER")
    assert t["metadata_status"] == "FIXTURE_ONLY"                        # no host capture in the test root
    assert t["position_size"] == "NOT_SPECIFIED" and t["spread_check"] == "PASS"
    assert t["spread_risk_fraction"] <= 0.15


def test_fx_ready_is_withheld_when_stale_or_spread_fails():
    session, post = _fx("EURUSD", "ASIAN_LONDON")
    at = dt.datetime(2026, 1, 5, 7, 35, tzinfo=UTC)
    build = lambda **kw: build_fx_ticket("EURUSD", "ASIAN_LONDON", DAY, session, 2, post,  # noqa: E731
                                         data_source="FIXTURE", **kw)
    old = build(evaluated_at=at + dt.timedelta(minutes=11), data_close=at, spread=0.0001)       # signal closed 16 min ago
    assert (old["decision"], old["reason_code"], old["suppressed_decision"]) == ("STALE", "STALE_SIGNAL", "READY")
    stale_data = build(evaluated_at=at, data_close=at - dt.timedelta(minutes=16), spread=0.0001)
    assert (stale_data["decision"], stale_data["reason_code"]) == ("STALE", "STALE_DATA")
    risk = build(evaluated_at=at, data_close=at, spread=0.0)["risk_distance"]
    wide = build(evaluated_at=at, data_close=at, spread=0.16 * risk)
    assert (wide["decision"], wide["spread_check"], wide["reason_code"]) == ("SPREAD_TOO_WIDE",) * 3
    edge = build(evaluated_at=at, data_close=at, spread=0.15 * risk)
    assert edge["decision"] == "READY" and edge["spread_check"] == "PASS"
    no_quote = build(evaluated_at=at, data_close=at)
    assert (no_quote["decision"], no_quote["reason_code"]) == ("NO_TRADE", "SPREAD_NOT_EVALUATED")
    assert old["engine_reason_code"] == edge["reason_code"]             # engine result preserved for audit
    assert not any(t["decision"] == "READY" for t in (old, stale_data, wide, no_quote))


def test_stale_is_measured_from_signal_bar_close_not_open():
    """signal_timestamp is the M15 bar OPEN; STALE only when now - (open + 15m) > 15 min."""
    session, _ = _fx("EURUSD", "ASIAN_LONDON")
    post = [_c(7, 0, 1.1005, 1.1060, 1.1000, 1.1048, 1.0)]               # signal bar opens 07:00, closes 07:15
    build = lambda at: build_fx_ticket("EURUSD", "ASIAN_LONDON", DAY, session, 2, post,  # noqa: E731
                                       data_source="FIXTURE", evaluated_at=at, data_close=at, spread=0.0001)
    fresh, late = build(dt.datetime(2026, 1, 5, 7, 16, tzinfo=UTC)), build(dt.datetime(2026, 1, 5, 7, 31, tzinfo=UTC))
    assert fresh["signal_timestamp"] == "2026-01-05T07:00:00+00:00"
    assert fresh["signal_close_utc"] == "2026-01-05T07:15:00+00:00"
    assert fresh["decision"] == "READY"
    assert (late["decision"], late["reason_code"], late["suppressed_decision"]) == ("STALE", "STALE_SIGNAL", "READY")


def test_crypto_stale_gate_uses_mss_bar_close():
    """Crypto passes mss_time (M5 bar open) + M5 as signal_close; same 15-min rule from that close."""
    from v1_tickets.guards import gate_ready
    mss_close = dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC) + dt.timedelta(minutes=5)
    ready = {"decision": "READY", "reason_codes": []}
    gate = lambda at: gate_ready(ready, now=at, data_close=at, signal_close=mss_close,  # noqa: E731
                                 spread=0.1, risk=10.0, reason_key="reason_codes")
    assert gate(dt.datetime(2026, 1, 5, 7, 20, tzinfo=UTC))["decision"] == "READY"
    late = gate(dt.datetime(2026, 1, 5, 7, 20, 1, tzinfo=UTC))
    assert (late["decision"], late["reason_codes"][0]) == ("STALE", "STALE_SIGNAL")


def test_fx_ticket_no_trade_and_data_error_never_invent_a_setup():
    session, post = _fx("EURUSD", "ASIAN_LONDON")
    no_trade = build_fx_ticket("EURUSD", "ASIAN_LONDON", DAY, session, 2, post[:1], data_source="FIXTURE",
                               evaluated_at=dt.datetime(2026, 1, 5, 9, tzinfo=UTC))
    assert no_trade["decision"] == "NO_TRADE" and "entry" not in no_trade
    broken = build_fx_ticket("EURUSD", "ASIAN_LONDON", DAY, [], 2, [], data_source="FIXTURE",
                             evaluated_at=dt.datetime(2026, 1, 5, 9, tzinfo=UTC))
    assert broken["decision"] in ("DATA_ERROR", "NO_TRADE") and "entry" not in broken
    with pytest.raises(ValueError):
        build_fx_ticket("AUDUSD", "ASIAN_LONDON", DAY, session, 2, post, data_source="X", evaluated_at=dt.datetime.now(UTC))


def test_fx_archive_is_idempotent_archive_only(tmp_path):
    session, post = _fx("XAUUSD", "LONDON_NEWYORK")
    t = build_fx_ticket("XAUUSD", "LONDON_NEWYORK", DAY, session, 2, post, data_source="FIXTURE",
                        evaluated_at=dt.datetime(2026, 1, 5, 16, tzinfo=UTC))
    p1 = archive_fx_ticket(t, str(tmp_path))
    p2 = archive_fx_ticket(t, str(tmp_path))            # duplicate poll / restart
    assert p1 == p2 and len(glob.glob(str(tmp_path / "**" / "*.json"), recursive=True)) == 1


def test_host_metadata_field_list_is_explicit():
    for f in ("digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size", "trade_stops_level"):
        assert f in HOST_METADATA_FIELDS


# ------------------------------------------------------------------ crypto

OBS = dt.date(2025, 9, 1)
IN_WINDOW = dt.datetime(2025, 9, 2, 6, 35, tzinfo=UTC)


def _series(minutes, count, end, base):
    step = dt.timedelta(minutes=minutes)
    start = end - step * count
    out = []
    for i in range(count):
        mid = base * (1 + 0.002 * math.sin(i / 7.0))
        out.append(Candle(start + step * i, mid, mid * 1.001, mid * 0.999, mid * 1.0003))
    return out


class _FakeFeed:
    def __init__(self, source="BYBIT_LINEAR_PERP", fail=False, reason=None):
        self.source, self.fail, self.reason, self.calls = source, fail, reason, 0

    def fetch_bundle(self, symbol, requests_):
        self.calls += 1
        if self.fail:
            raise PublicCryptoFeedUnavailable("KLINES_REQUEST_FAILED", "KLINES_REQUEST_FAILED")
        end = IN_WINDOW.replace(minute=30)
        base = 60000.0 if symbol == "BTCUSDT" else 3000.0
        candles = {"H1": _series(60, 200, end.replace(minute=0), base), "M5": _series(5, 600, end, base)}
        return CandleBundle(symbol, self.source, candles, self.reason)


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
@pytest.mark.parametrize("source,reason", [("BYBIT_LINEAR_PERP", None), ("BINANCE_USDT_M_PERP", "KLINES_REQUEST_FAILED")])
def test_crypto_ticket_prints_data_source_and_runs_frozen_engine(tmp_path, symbol, source, reason):
    t = build_crypto_ticket(symbol, OBS, IN_WINDOW, feed=_FakeFeed(source, reason=reason), state_dir=str(tmp_path / "s"))
    assert t["data_source"] == source and t["primary_failure_reason"] == reason
    assert t["strategy_version"] == "2.0.0" and t["window_status"] == "IN_WINDOW"
    assert t["decision"] in ("READY", "WATCH", "NO_TRADE")   # the frozen engine actually evaluated
    assert t["symbol_status"] == ("SHADOW" if symbol == "ETHUSDT" else "ACTIVE_INCUBATION")
    archive_crypto_ticket(t, str(tmp_path / "a"))


def test_crypto_ticket_outside_frozen_window_is_blocked_without_fetch(tmp_path):
    feed = _FakeFeed()
    t = build_crypto_ticket("BTCUSDT", OBS, dt.datetime(2025, 9, 2, 12, 0, tzinfo=UTC), feed=feed, state_dir=str(tmp_path))
    assert t["decision"] == "BLOCKED" and feed.calls == 0


def test_crypto_ticket_both_feeds_down_is_data_error_with_reasons(tmp_path):
    t = build_crypto_ticket("ETHUSDT", OBS, IN_WINDOW, feed=_FakeFeed(fail=True), state_dir=str(tmp_path))
    assert t["decision"] == "DATA_ERROR" and t["data_source"] == "NONE"
    assert t["primary_failure_reason"] == t["fallback_failure_reason"] == "KLINES_REQUEST_FAILED"


def test_v1_ticket_modules_have_no_execution_or_transport_imports():
    import ast
    from pathlib import Path
    for path in Path(__file__).resolve().parent.parent.joinpath("src", "v1_tickets").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else [])
            for m in mods:
                assert m.split(".")[0] not in {"execution", "trade_management", "notifications", "telegram", "api"}, m
                assert m not in {"mt5.management_gateway", "MetaTrader5"}, m


# ------------------------------------------------------------------ crypto ticket config versions

def _cfg(version):
    from v1_tickets.crypto import load_ticket_config
    return load_ticket_config(f"config/v1_tickets/crypto_ticket_v{version}.yaml",
                              os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


V2_IN = dt.datetime(2025, 9, 2, 13, 35, tzinfo=UTC)          # Tue 09:35 America/New_York (EDT)


def test_crypto_config_v1_preserved_and_v2_active():
    v1, v2 = _cfg(1), _cfg(2)
    assert (v1["version"], v1["status"], v1["venue"]["kind"]) == (1, "PRESERVED", "PUBLIC_PERP")
    assert (v1["window"]["start"], v1["window"]["end"], v1["window"]["timezone"]) == ("06:30", "06:45", "UTC")
    assert (v2["version"], v2["status"], v2["supersedes"]) == (2, "SHADOW_NEW_VENUE", 1)
    assert v2["venue"] == {"kind": "MT5", "source_id": "MT5_VT_MARKETS_DEMO",
                           "symbols": {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"},
                           "server_time_rule": "SERVER_MIDNIGHT_EQUALS_NEW_YORK_1700"}
    from v1_tickets.crypto import ACTIVE_CONFIG
    assert ACTIVE_CONFIG.replace("\\", "/") == "config/v1_tickets/crypto_ticket_v3.yaml"


def test_crypto_config_v3_is_v2_plus_weekend_shadow():
    v2, v3 = _cfg(2), _cfg(3)
    assert (v3["version"], v3["status"], v3["supersedes"]) == (3, "SHADOW", 2)
    assert v3["venue"] == v2["venue"]                                  # same VT venue, metadata and costs
    weekday, weekend = v3["window"]["windows"]
    assert weekday["name"] == "WEEKDAY" and {k: v for k, v in weekday.items() if k != "name"} == v2["window"]
    assert (weekend["name"], weekend["start"], weekend["end"], weekend["timezone"], weekend["weekdays"]) == \
        ("WEEKEND", "21:00", "23:00", "UTC", [6, 7])
    assert weekend["label"] == "WEEKEND — ~2x cost vs range"


@pytest.mark.parametrize("now,expected,window", [
    (V2_IN, "IN_WINDOW", "WEEKDAY"),
    (dt.datetime(2025, 9, 6, 21, 0, tzinfo=UTC), "IN_WINDOW", "WEEKEND"),       # Sat 21:00 UTC (start inclusive)
    (dt.datetime(2025, 9, 7, 22, 59, tzinfo=UTC), "IN_WINDOW", "WEEKEND"),      # Sun 22:59 UTC
    (dt.datetime(2025, 9, 7, 23, 0, tzinfo=UTC), "AFTER_WINDOW", None),         # Sun 23:00 UTC (end exclusive)
    (dt.datetime(2025, 9, 6, 20, 59, tzinfo=UTC), "BEFORE_WINDOW", None),       # Sat 20:59 UTC
    (dt.datetime(2025, 9, 5, 21, 30, tzinfo=UTC), "AFTER_WINDOW", None),        # Fri 21:30 UTC: no weekend window
    (dt.datetime(2025, 9, 6, 14, 0, tzinfo=UTC), "BEFORE_WINDOW", None),        # Sat 10:00 EDT: weekday window closed
])
def test_crypto_v3_windows_weekday_ny_plus_weekend_utc(now, expected, window):
    from v1_tickets.crypto import active_window, window_status
    assert window_status(_cfg(3), (now - dt.timedelta(days=1)).date(), now) == expected
    assert (active_window(_cfg(3), now) or {}).get("name") == window


@pytest.mark.parametrize("now,window,label", [
    (V2_IN, "WEEKDAY", None),
    (dt.datetime(2025, 9, 6, 21, 30, tzinfo=UTC), "WEEKEND", "WEEKEND — ~2x cost vs range"),
])
def test_crypto_v3_ticket_records_window_and_shadow_status(tmp_path, monkeypatch, now, window, label):
    from host_delivery import telegram_message as tg
    from v1_tickets.crypto import Mt5CryptoFeed, archive_crypto_ticket
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "ev"))
    _write_host_record(str(tmp_path / "ev"), "BTCUSD")
    cfg, calls = _cfg(3), []
    feed = Mt5CryptoFeed(_mt5_fetch(calls), cfg["venue"]["symbols"], cfg["venue"]["source_id"])
    t = build_crypto_ticket("BTCUSDT", now.date() - dt.timedelta(days=1), now, feed=feed,
                            state_dir=str(tmp_path / "s"), config=cfg)
    assert t["ticket_config"] == "AG_V1_CRYPTO_TICKET@v3" and t["window_status"] == "IN_WINDOW"
    assert (t["window"], t["ticket_status"], t.get("window_label")) == (window, "SHADOW", label)
    assert t["decision"] != "BLOCKED" and calls
    path = archive_crypto_ticket(t, str(tmp_path / "archive"))          # shadow outcome keeps the window
    with open(path, encoding="utf-8") as f:
        assert f'"window": "{window}"' in f.read()
    msg = tg.format_ticket(t)
    assert f"window: {window}  status: SHADOW" in msg and (label is None or label in msg)


def test_crypto_v2_tickets_unchanged_by_v3_fields(tmp_path, monkeypatch):
    from v1_tickets.crypto import Mt5CryptoFeed
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "ev"))
    _write_host_record(str(tmp_path / "ev"), "BTCUSD")
    cfg = _cfg(2)
    t = build_crypto_ticket("BTCUSDT", OBS, V2_IN, feed=Mt5CryptoFeed(_mt5_fetch([]), cfg["venue"]["symbols"]),
                            state_dir=str(tmp_path / "s"), config=cfg)
    assert not {"window", "ticket_status", "window_label"} & set(t)


@pytest.mark.parametrize("now,expected", [
    (V2_IN, "IN_WINDOW"),
    (dt.datetime(2025, 9, 2, 12, 59, tzinfo=UTC), "BEFORE_WINDOW"),       # 08:59 EDT
    (dt.datetime(2025, 9, 2, 16, 0, tzinfo=UTC), "AFTER_WINDOW"),         # 12:00 EDT (end exclusive)
    (dt.datetime(2025, 9, 6, 14, 0, tzinfo=UTC), "OUTSIDE_WEEKDAYS"),     # Saturday
    (dt.datetime(2025, 9, 7, 14, 0, tzinfo=UTC), "OUTSIDE_WEEKDAYS"),     # Sunday
    (dt.datetime(2025, 12, 2, 14, 30, tzinfo=UTC), "IN_WINDOW"),          # 09:30 EST (winter)
    (dt.datetime(2025, 12, 2, 13, 30, tzinfo=UTC), "BEFORE_WINDOW"),      # 08:30 EST
])
def test_crypto_v2_window_is_weekday_new_york_0900_1200(now, expected):
    from v1_tickets.crypto import window_status
    assert window_status(_cfg(2), (now - dt.timedelta(days=1)).date(), now) == expected


def test_crypto_v1_window_matches_frozen_daily_report():
    from v1_tickets.crypto import window_status
    assert window_status(_cfg(1), OBS, IN_WINDOW) == window_status(None, OBS, IN_WINDOW) == "IN_WINDOW"
    assert window_status(_cfg(1), OBS, V2_IN) == "AFTER_WINDOW"


def _write_host_record(root, broker, include_swap=True):
    from host_evidence.symbol_metadata import build_record, write_record
    fields = {"digits": 2, "point": 0.01, "trade_tick_size": 0.01, "trade_tick_value": 0.01,
              "trade_contract_size": 1.0, "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0,
              "trade_stops_level": 0, "trade_freeze_level": 0, "spread": 1694, "currency_profit": "USD"}
    if include_swap:
        fields.update({"swap_long": -25.0, "swap_short": 5.0, "swap_rollover3days": 3})
    write_record(build_record(broker, broker, fields, "VTMarkets-Demo", 3, "t", trade_mode="FULL"), root)


def _mt5_fetch(calls):
    def fetch(broker, tf, count):
        calls.append((broker, tf))
        end = V2_IN.replace(minute=30)
        base = 60000.0 if broker == "BTCUSD" else 3000.0
        minutes = {"H1": 60, "M5": 5}[tf]
        return _series(minutes, count, end.replace(minute=0) if tf == "H1" else end, base)
    return fetch


@pytest.mark.parametrize("symbol,broker", [("BTCUSDT", "BTCUSD"), ("ETHUSDT", "ETHUSD")])
def test_crypto_v2_runs_frozen_engine_on_vt_mt5(tmp_path, monkeypatch, symbol, broker):
    from v1_tickets.crypto import Mt5CryptoFeed
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "ev"))
    _write_host_record(str(tmp_path / "ev"), broker)
    cfg, calls = _cfg(2), []
    feed = Mt5CryptoFeed(_mt5_fetch(calls), cfg["venue"]["symbols"], cfg["venue"]["source_id"])
    t = build_crypto_ticket(symbol, V2_IN.date() - dt.timedelta(days=1), V2_IN, feed=feed,
                            state_dir=str(tmp_path / "s"), config=cfg)
    assert t["ticket_config"] == "AG_V1_CRYPTO_TICKET@v2" and t["data_source"] == "MT5_VT_MARKETS_DEMO"
    assert t["strategy_version"] == "2.0.0" and t["decision"] in ("READY", "WATCH", "NO_TRADE")
    assert {b for b, _ in calls} == {broker}


def test_crypto_v2_outside_window_and_missing_metadata_fail_closed(tmp_path, monkeypatch):
    from v1_tickets.crypto import Mt5CryptoFeed
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "empty"))
    cfg, calls = _cfg(2), []
    feed = Mt5CryptoFeed(_mt5_fetch(calls), cfg["venue"]["symbols"])
    sat = dt.datetime(2025, 9, 6, 14, 0, tzinfo=UTC)
    blocked = build_crypto_ticket("BTCUSDT", sat.date(), sat, feed=feed, state_dir=str(tmp_path), config=cfg)
    assert blocked["decision"] == "BLOCKED" and blocked["reason_codes"] == ["OUTSIDE_CONFIG_WINDOW"] and not calls
    err = build_crypto_ticket("BTCUSDT", OBS, V2_IN, feed=feed, state_dir=str(tmp_path), config=cfg)
    assert err["decision"] == "DATA_ERROR" and err["reason_codes"] == ["METADATA_MISSING"]
    assert "METADATA_MISSING BTCUSD" in err["detail"] and "entry" not in err


def test_crypto_v2_missing_swap_fields_is_data_error(tmp_path, monkeypatch):
    """HIGH-1 regression: Mt5CryptoFeed refuses to run if swap/rollover fields are absent."""
    from v1_tickets.crypto import Mt5CryptoFeed
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "ev"))
    _write_host_record(str(tmp_path / "ev"), "BTCUSD", include_swap=False)
    cfg, calls = _cfg(2), []
    feed = Mt5CryptoFeed(_mt5_fetch(calls), cfg["venue"]["symbols"], cfg["venue"]["source_id"])
    t = build_crypto_ticket("BTCUSDT", V2_IN.date() - dt.timedelta(days=1), V2_IN, feed=feed,
                            state_dir=str(tmp_path / "s"), config=cfg)
    assert t["decision"] == "DATA_ERROR" and t["reason_codes"] == ["SWAP_FIELDS_MISSING"]
    assert "SWAP_FIELDS_MISSING BTCUSD" in t["detail"]


def _raise(exc):
    def fetch(broker, tf, count):
        raise exc
    return fetch


@pytest.mark.parametrize("make_fetch,code", [
    (lambda calls: (lambda b, tf, n: _mt5_fetch(calls)(b, tf, n)[1:]), "INCOMPLETE_CANDLES"),
    (lambda calls: _raise(__import__("host_evidence.symbol_metadata", fromlist=["x"]).HostDataError(
        "SYMBOL_NOT_FOUND", "'BTCUSD'")), "SYMBOL_NOT_FOUND"),
    (lambda calls: _raise(ValueError("bad float")), "CONVERSION_ERROR"),
])
def test_crypto_v2_specific_reason_codes(tmp_path, monkeypatch, make_fetch, code):
    from v1_tickets.crypto import Mt5CryptoFeed
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "ev"))
    _write_host_record(str(tmp_path / "ev"), "BTCUSD")
    cfg = _cfg(2)
    feed = Mt5CryptoFeed(make_fetch([]), cfg["venue"]["symbols"], cfg["venue"]["source_id"])
    t = build_crypto_ticket("BTCUSDT", OBS, V2_IN, feed=feed, state_dir=str(tmp_path / "s"), config=cfg)
    assert t["decision"] == "DATA_ERROR" and t["reason_codes"] == [code] and "entry" not in t


def test_crypto_v2_evidence_never_resolves_from_cwd(tmp_path, monkeypatch):
    from host_evidence import symbol_metadata as sm
    from v1_tickets.crypto import Mt5CryptoFeed
    _write_host_record(str(tmp_path), "BTCUSD")
    monkeypatch.chdir(tmp_path)                                         # a CWD that holds a valid capture
    monkeypatch.setenv("AG_EVIDENCE_ROOT", ".")
    cfg = _cfg(2)
    feed = Mt5CryptoFeed(_mt5_fetch([]), cfg["venue"]["symbols"], cfg["venue"]["source_id"])
    t = build_crypto_ticket("BTCUSDT", OBS, V2_IN, feed=feed, state_dir=str(tmp_path / "s"), config=cfg)
    assert t["decision"] == "DATA_ERROR" and t["reason_codes"] == ["CWD_LOOKUP"]
    monkeypatch.delenv("AG_EVIDENCE_ROOT")
    assert sm.evidence_root() == sm.REPO_ROOT and os.path.isabs(sm.REPO_ROOT)
    assert sm.evidence_path("BTCUSD").startswith(sm.REPO_ROOT)


def test_crypto_v2_stale_data_is_never_ready(tmp_path, monkeypatch):
    from v1_tickets.crypto import Mt5CryptoFeed
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "ev"))
    _write_host_record(str(tmp_path / "ev"), "BTCUSD")
    cfg = _cfg(2)
    feed = Mt5CryptoFeed(_mt5_fetch([]), cfg["venue"]["symbols"], cfg["venue"]["source_id"], quote=lambda b: (1.0, 1.0))
    late = V2_IN + dt.timedelta(minutes=40)                             # last M5 bar closed > 15 min ago
    t = build_crypto_ticket("BTCUSDT", OBS, late, feed=feed, state_dir=str(tmp_path / "s"), config=cfg)
    assert t["decision"] == "STALE" and t["reason_codes"][0] == "STALE_DATA"
    assert t["suppressed_decision"] in ("READY", "WATCH", "NO_TRADE")
    from v1_tickets.crypto import archive_crypto_ticket
    assert archive_crypto_ticket(t, str(tmp_path / "arch"))
