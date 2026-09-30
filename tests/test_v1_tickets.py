"""AG V1 T6/T7/T8: informational tickets (Goal 1). Synthetic fixtures only; no network, no
broker. Covers FX/gold on both frozen session pairs, crypto BTCUSDT/ETHUSDT in the frozen
daily window with the data source printed, fallback, market-data failure, and idempotent
ARCHIVE_ONLY journaling."""
from __future__ import annotations

import datetime as dt
import glob
import math

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
