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
    t = build_fx_ticket(symbol, cycle, DAY, session, 2, post, data_source="FIXTURE", evaluated_at=dt.datetime(2026, 1, 5, 16, tzinfo=UTC))
    assert t["decision"] == "READY" and t["direction"] == "SHORT" and t["strategy_version"] == "1.1.1"
    assert t["targets"][0]["type"] == "OPPOSITE_SESSION_BOUNDARY" and t["targets"][1]["type"] == "FIXED_R_MULTIPLE_5"
    assert t["targets"][0]["price"] < t["entry"] < t["stop_loss"]          # SHORT geometry
    assert t["data_source"] == "FIXTURE" and t["label"].endswith("NOT A BROKER ORDER")
    assert t["metadata_status"] == ("REPO_EVIDENCED" if symbol in ("EURUSD", "GBPUSD") else "FIXTURE_ONLY")
    assert t["position_size"] == "NOT_SPECIFIED" and t["spread_check"] == "NOT_EVALUATED"


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
    assert ACTIVE_CONFIG.replace("\\", "/") == "config/v1_tickets/crypto_ticket_v2.yaml"


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
    assert err["decision"] == "DATA_ERROR" and err["reason_codes"] == ["MT5_FEED_ERROR"]
    assert "HOST_METADATA_MISSING BTCUSD" in err["detail"] and "entry" not in err


def test_crypto_v2_missing_swap_fields_is_data_error(tmp_path, monkeypatch):
    """HIGH-1 regression: Mt5CryptoFeed refuses to run if swap/rollover fields are absent."""
    from v1_tickets.crypto import Mt5CryptoFeed
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "ev"))
    _write_host_record(str(tmp_path / "ev"), "BTCUSD", include_swap=False)
    cfg, calls = _cfg(2), []
    feed = Mt5CryptoFeed(_mt5_fetch(calls), cfg["venue"]["symbols"], cfg["venue"]["source_id"])
    t = build_crypto_ticket("BTCUSDT", V2_IN.date() - dt.timedelta(days=1), V2_IN, feed=feed,
                            state_dir=str(tmp_path / "s"), config=cfg)
    assert t["decision"] == "DATA_ERROR" and t["reason_codes"] == ["MT5_FEED_ERROR"]
    assert "HOST_SWAP_METADATA_MISSING" in t["detail"]
