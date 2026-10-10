"""R1 integration fixtures: no terminal, network, economic backtest or production policy."""
import ast
from collections import Counter
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from mt5 import mt5_candles_readonly as adapter
from strategy_engine.session import Candle
from v1_tickets.daily_evaluator import FX_PAIRS, evaluate_fx_pair, run_daily_evaluation
from v1_tickets.mt5_provider import MT5CandleProvider, MT5ReadOnlyCandleAdapter
from v1_tickets.policy_loader import ActionabilityPolicy, POLICY_ID, POLICY_OK

ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
SIGNED_TEST_POLICY = ActionabilityPolicy(
    status=POLICY_OK, policy_id=POLICY_ID, version=1, min_remaining_r=1.0,
    signed_by="TEST_FIXTURE_ONLY", signed_at="2026-10-07", source_path="<TEST>", reason=None)

spec = importlib.util.spec_from_file_location("live_eval_smoke", ROOT / "scripts/host/live_eval_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class FakeReader:
    def __init__(self, missing=None, short=False):
        self.requests = []
        self.missing = missing
        self.short = short

    def fetch_range(self, symbol, timeframe, start, end):
        self.requests.append((symbol, timeframe, start, end))
        rows = []
        t = start
        reference = start.hour in (0, 6)
        while t <= end:
            o = h = l = c = 1.1625
            if reference:
                if t == start:
                    o, h, l, c = 1.1620, 1.1650, 1.1600, 1.1610
                elif t == end:
                    o, h, l, c = 1.1620, 1.1625, 1.1610, 1.1620
            elif t == start:
                if self.short:
                    o, h, l, c = 1.1647, 1.1658, 1.1645, 1.1634
                else:
                    o, h, l, c = 1.1603, 1.1635, 1.1592, 1.1634
            rows.append(adapter.CanonicalCandle(symbol, t, o, h, l, c, 123, 10, 0))
            t += dt.timedelta(minutes=15)
        if self.missing == ("ref" if reference else "post"):
            rows = rows[1:]
        return rows

    def quote(self, symbol):
        return 1.16335, 1.16345, NOW


def one(tmp_path, reader=None, policy=SIGNED_TEST_POLICY):
    return evaluate_fx_pair(
        "EURUSD", "ASIAN_LONDON", now=NOW, day=NOW.date(),
        candle_provider=MT5CandleProvider(reader or FakeReader()),
        archive_root=str(tmp_path), policy=policy)


def test_provider_conversion_reaches_evaluator(stub_symbol_verified, tmp_path, monkeypatch):
    from v1_tickets import daily_evaluator
    reader = FakeReader()
    real = daily_evaluator.v1_fx.build_fx_ticket
    seen = []

    def capture(symbol, cycle, day, reference, count, post, **kwargs):
        assert count == 24 and len(reference) == 24 and len(post) == 1
        assert all(isinstance(c, Candle) and c.volume == 123 for c in reference + post)
        seen.append(post[0])
        return real(symbol, cycle, day, reference, count, post, **kwargs)

    monkeypatch.setattr(daily_evaluator.v1_fx, "build_fx_ticket", capture)
    result = one(tmp_path, reader)
    assert seen[0].time == NOW.replace(minute=0)
    assert result.decision == "WATCH_READY"
    assert {r[1] for r in reader.requests} == {"M15"}
    assert reader.requests[0][2:4] == (NOW.replace(hour=0, minute=0), NOW.replace(hour=5, minute=45))


def test_complete_matrix_and_no_silent_evaluation(tmp_path):
    reader = FakeReader()
    results = run_daily_evaluation(now=NOW, candle_provider=MT5CandleProvider(reader),
                                   archive_root=str(tmp_path), include_crypto=False,
                                   policy=SIGNED_TEST_POLICY)
    assert len(results) == 8
    assert Counter((r.instrument, r.session) for r in results) == Counter(FX_PAIRS)
    assert sum(r.decision == "OUT_OF_SESSION" for r in results) == 4
    assert all(Path(r.archive_path).exists() for r in results)


@pytest.mark.parametrize("missing", ["ref", "post"])
def test_missing_required_candles_never_no_trade(tmp_path, missing):
    result = one(tmp_path, FakeReader(missing=missing))
    assert result.decision == "INSUFFICIENT_DATA"
    assert result.canonical["prices"]["entry_reference_raw"] is None


def test_unsigned_production_style_policy(stub_symbol_verified, tmp_path):
    from v1_tickets.policy_loader import load_policy
    result = one(tmp_path, policy=load_policy(str(ROOT)))
    assert result.decision == "INFO_ONLY_POLICY_UNRESOLVED"
    assert result.canonical["actionability"]["min_remaining_r"] is None


def test_signed_test_policy_watch_ready_without_authority(stub_symbol_verified, tmp_path):
    result = one(tmp_path)
    assert result.decision == "WATCH_READY"
    assert result.canonical["execution_authorization"] is False
    assert result.canonical["demo_authorized"] is False
    assert result.canonical["live_authorized"] is False


@pytest.mark.parametrize("short", [False, True])
def test_no_invented_context(tmp_path, short):
    ticket = one(tmp_path, FakeReader(short=short)).canonical
    assert ticket["direction"] == ("SHORT" if short else "LONG")
    for key in ("h1_context", "poi"):
        assert ticket["context"][key] == "NOT_AVAILABLE"
        assert ticket["fact_provenance"][key]["status"] == "NOT_AVAILABLE"
    # Existing #55 fallback preserves the engine's M15 regime as a runtime fact;
    # it is not a D1 directional bias and the bridge does not add one.
    assert ticket["context"]["d1_context"] == "RANGE"
    assert ticket["fact_provenance"]["d1_context"] == {"status": "RUNTIME_FACT", "source": "ticket.regime"}
    assert "premium" not in json.dumps(ticket) and "discount" not in json.dumps(ticket)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_direction_alone_supplies_no_optional_facts(direction):
    from v1_tickets.canonical_ticket import build_canonical_ticket
    ticket = build_canonical_ticket({
        "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1",
        "symbol": "EURUSD", "cycle": "ASIAN_LONDON", "session_date": NOW.date().isoformat(),
        "decision": "DATA_ERROR", "direction": direction,
    }, now=NOW, policy=SIGNED_TEST_POLICY)
    for key in ("d1_context", "h1_context", "poi"):
        assert ticket["context"][key] == "NOT_AVAILABLE"
        assert ticket["fact_provenance"][key]["status"] == "NOT_AVAILABLE"


def test_deterministic_identity(tmp_path):
    first, second = one(tmp_path), one(tmp_path)
    assert first.ticket_id == second.ticket_id
    assert first.canonical == second.canonical


def test_adapter_boundary_no_suffix_guessing_or_synthetic_data(tmp_path):
    class FakeMT5:
        TIMEFRAME_M15 = 15
        def __init__(self): self.calls = []
        def symbol_info(self, symbol):
            self.calls.append(symbol)
            from host_evidence.symbol_metadata import server_utc_offset_hours
            offset = server_utc_offset_hours(NOW)
            return SimpleNamespace(bid=1.1, ask=1.1001,
                                   time=(NOW + dt.timedelta(hours=offset)).timestamp())
        def copy_rates_range(self, *args): return []

    mt5 = FakeMT5()
    mapped = MT5ReadOnlyCandleAdapter(smoke.GuardedMT5(mt5), {"EURUSD": "OWNER_EXACT_SYMBOL"})
    assert mapped.fetch_range("EURUSD", "M15", NOW - dt.timedelta(hours=1), NOW) == []
    assert mt5.calls == ["OWNER_EXACT_SYMBOL"]
    assert one(tmp_path, mapped).decision == "INSUFFICIENT_DATA"
    missing = MT5ReadOnlyCandleAdapter(smoke.GuardedMT5(mt5), {})
    with pytest.raises(adapter.CandleAdapterError, match="SYMBOL_MAPPING_MISSING"):
        missing.fetch_range("EURUSD", "M15", NOW, NOW)
    assert one(tmp_path, missing).decision == "INSUFFICIENT_DATA"


@pytest.mark.parametrize(
    ("reader", "expected_code", "expected_detail", "expected_layer"),
    [
        (FakeReader(missing="ref"), "DATA_MISSING", "M15_WINDOW_INCOMPLETE", "WINDOW_COMPLETENESS"),
        (None, "SYMBOL_MAPPING_MISSING", "no broker symbol mapped for 'EURUSD'", "SYMBOL_RESOLUTION"),
    ],
)
def test_adapter_errors_are_preserved_without_changing_ticket_authority(
        tmp_path, reader, expected_code, expected_detail, expected_layer):
    if reader is None:
        reader = MT5ReadOnlyCandleAdapter(
            type("ReadOnlyMT5", (), {"symbol_info": lambda self, name: None})(), {})
    first = one(tmp_path / "first", reader)
    second = one(tmp_path / "second", reader)
    assert first.decision == second.decision == "INSUFFICIENT_DATA"
    assert first.canonical["reason_code"] == "CandleAdapterError"
    assert first.canonical["data_error"] == {
        "code": expected_code, "detail": expected_detail, "layer": expected_layer,
    }
    assert first.ticket_id == second.ticket_id == "ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|2026-10-07"
    assert first.canonical["actionability"] == second.canonical["actionability"]
    for key in ("execution_authorization", "demo_authorized", "live_authorized"):
        assert first.canonical[key] is second.canonical[key] is False


@pytest.mark.parametrize("utc_time", [
    dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC),
    dt.datetime(2026, 12, 7, 7, 0, tzinfo=UTC),
])
def test_quote_timestamp_uses_accepted_server_time_normalization(utc_time):
    from host_evidence.symbol_metadata import server_utc_offset_hours
    server_offset = server_utc_offset_hours(utc_time)
    server_epoch = (utc_time + dt.timedelta(hours=server_offset)).timestamp()
    mt5 = type("ReadOnlyMT5", (), {
        "TIMEFRAME_M15": 15,
        "symbol_info": lambda self, name: SimpleNamespace(bid=1.1, ask=1.1001, time=server_epoch),
    })()
    reader = MT5ReadOnlyCandleAdapter(mt5, {"EURUSD": "EURUSD-VIP"})
    assert reader.quote("EURUSD")[2] == utc_time


@pytest.mark.parametrize("bad", ["stale", "future", "nan", "inverted"])
def test_invalid_quote_fails_closed(tmp_path, bad):
    reader = FakeReader()
    quotes = {
        "stale": (1.1633, 1.1634, NOW - dt.timedelta(hours=1)),
        "future": (1.1633, 1.1634, NOW + dt.timedelta(seconds=1)),
        "nan": (float("nan"), 1.1634, NOW),
        "inverted": (1.1634, 1.1633, NOW),
    }
    reader.quote = lambda symbol: quotes[bad]
    assert one(tmp_path, reader).decision == "INSUFFICIENT_DATA"


def test_closed_bars_only_and_missing_gap_not_filled(tmp_path):
    reader = FakeReader()
    bundle = MT5CandleProvider(reader)("EURUSD", "ASIAN_LONDON", NOW.date(), NOW)
    assert bundle.data_close <= NOW
    reader.quote = lambda symbol: (1.16355, 1.16365, NOW)
    quoted = MT5CandleProvider(reader)("EURUSD", "ASIAN_LONDON", NOW.date(), NOW)
    assert quoted.current_price == pytest.approx(1.1636)
    assert quoted.current_price != quoted.post_session_candles[-1].close
    assert reader.requests[-1][3] + dt.timedelta(minutes=15) <= NOW
    original = reader.fetch_range
    reader.fetch_range = lambda *args: original(*args)[::-1]
    assert one(tmp_path, reader).decision == "INSUFFICIENT_DATA"


def test_london_history_is_twenty_reference_bars():
    reader = FakeReader()
    later = NOW.replace(hour=12)
    reader.quote = lambda symbol: (1.16335, 1.16345, later)
    bundle = MT5CandleProvider(reader)("EURUSD", "LONDON_NEWYORK", later.date(), later)
    assert bundle.expected_bar_count == len(bundle.session_candles) == 20
    assert len(bundle.post_session_candles) == 1
    assert reader.requests[0][2:4] == (later.replace(hour=6, minute=0), later.replace(hour=10, minute=45))


def test_real_adapter_shaped_rates_reach_evaluator(stub_symbol_verified, tmp_path, monkeypatch):
    from host_evidence.symbol_metadata import server_time_to_utc, server_utc_offset_hours
    fixture = FakeReader()
    class FakeMT5:
        TIMEFRAME_M15 = 15
        def symbol_info(self, symbol):
            assert symbol == "OWNER_EXACT_SYMBOL"
            server_wall_epoch = (NOW + dt.timedelta(hours=server_utc_offset_hours(NOW))).timestamp()
            return SimpleNamespace(bid=1.16335, ask=1.16345, time=server_wall_epoch)
        def copy_rates_range(self, symbol, timeframe, start, end):
            assert symbol == "OWNER_EXACT_SYMBOL" and timeframe == 15
            rows = (fixture.fetch_range("EURUSD", "M15", NOW.replace(hour=0, minute=0),
                                        NOW.replace(hour=5, minute=45))
                    + fixture.fetch_range("EURUSD", "M15", NOW.replace(minute=0), NOW.replace(minute=0)))
            rates = []
            for row in rows:
                wall = next((row.time + dt.timedelta(hours=h)).replace(tzinfo=None)
                            for h in (2, 3) if server_time_to_utc((row.time + dt.timedelta(hours=h)).replace(tzinfo=None)) == row.time)
                rates.append({"time": wall.replace(tzinfo=UTC).timestamp(), "open": row.open,
                              "high": row.high, "low": row.low, "close": row.close,
                              "tick_volume": 123, "spread": 10, "real_volume": 0})
            return rates
    monkeypatch.setattr(smoke, "default_symbol_map", lambda: {"EURUSD": "OWNER_EXACT_SYMBOL"})
    guard = smoke.GuardedMT5(FakeMT5())
    provider = smoke.snapshot_provider(guard)
    result = evaluate_fx_pair("EURUSD", "ASIAN_LONDON", now=NOW, day=NOW.date(),
                              candle_provider=provider, archive_root=str(tmp_path), policy=SIGNED_TEST_POLICY)
    assert result.decision == "WATCH_READY" and not guard.refused
    report = smoke.evaluate_report(provider, now=NOW, archive_root=tmp_path, policy=SIGNED_TEST_POLICY)
    assert report["matrix_complete"] and len(report["results"]) == 8
    assert report["mission"] == "AG_OBJECTIVE_INTEGRATION_R1"
    assert report["ticket_store_source"] == "REPLAY"
    assert report["host_acceptance_status"] == "NOT_EVALUATED"
    assert sum(r["decision"] == "INSUFFICIENT_DATA" for r in report["results"]) == 3


def test_scheduled_cycle_filter_is_backward_compatible_and_complete(tmp_path):
    report = smoke.evaluate_report(MT5CandleProvider(FakeReader()), now=NOW,
                                   archive_root=tmp_path, policy=SIGNED_TEST_POLICY,
                                   cycles=("ASIAN_LONDON",))
    assert report["matrix_complete"]
    assert report["expected_evaluations"] == report["actual_evaluations"] == 4
    assert {row["session"] for row in report["results"]} == {"ASIAN_LONDON"}
    with pytest.raises(ValueError, match="unknown FX cycles"):
        smoke.evaluate_report(MT5CandleProvider(FakeReader()), now=NOW,
                              archive_root=tmp_path / "invalid", policy=SIGNED_TEST_POLICY,
                              cycles=("UNREGISTERED",))


def test_host_report_fake_provider_and_sanitized_evidence(tmp_path):
    report = smoke.evaluate_report(MT5CandleProvider(FakeReader()), now=NOW,
                                   archive_root=tmp_path / "journal", policy=SIGNED_TEST_POLICY)
    assert report["matrix_complete"] and report["actual_evaluations"] == 8
    assert sum(report["terminal_counts"].values()) == 8
    assert not report["missing_evaluations"]
    path = smoke.save_report(report, tmp_path)
    assert path.name == "2026-10-07_live_evaluator_report.json"
    text = path.read_text()
    assert "<TEST>" not in text and "TEST_FIXTURE_ONLY" not in text
    assert json.loads(text) == report


def test_host_report_detects_silent_duplicate_evaluation(tmp_path, monkeypatch):
    real = smoke.run_daily_evaluation
    def broken(**kwargs):
        results = real(**kwargs)
        return results[:-1] + [results[0]]
    monkeypatch.setattr(smoke, "run_daily_evaluation", broken)
    report = smoke.evaluate_report(MT5CandleProvider(FakeReader()), now=NOW,
                                   archive_root=tmp_path, policy=SIGNED_TEST_POLICY)
    assert not report["matrix_complete"]
    assert len(report["missing_evaluations"]) == len(report["unexpected_evaluations"]) == 1


def test_guard_refuses_order_api_before_access():
    guard = smoke.GuardedMT5(object())
    for name in ("order_send", "order_check", "positions_get", "orders_get", "symbol_select"):
        with pytest.raises(PermissionError): getattr(guard, name)
    assert len(guard.refused) == 5


def test_imports_without_mt5_or_initialization():
    code = """
import sys
class NoMT5:
    def find_spec(self, fullname, *args):
        if fullname == 'MetaTrader5': raise AssertionError('terminal import attempted')
sys.meta_path.insert(0, NoMT5())
import v1_tickets.daily_evaluator, v1_tickets.mt5_provider, v1_tickets.canonical_ticket
assert 'MetaTrader5' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "src",
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_execution_firewall_transitive_imports():
    forbidden_modules = ("execution", "trade_management", "assistant.commands", "mt5.management_gateway")
    forbidden_calls = {"order_send", "order_check", "execute_command", "positions_get", "orders_get",
                       "order_modify", "order_cancel", "position_close", "position_modify"}
    todo = [ROOT / "src/v1_tickets/mt5_provider.py", ROOT / "scripts/host/live_eval_smoke.py"]
    seen = set()
    while todo:
        path = todo.pop()
        if path in seen: continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        package = ".".join(path.relative_to(ROOT / "src").parts[:-1]) if path.is_relative_to(ROOT / "src") else ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                assert name not in forbidden_calls, (path, name)
            names = []
            if isinstance(node, ast.Import): names = [a.name for a in node.names]
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    parts = package.split(".")
                    module = ".".join(parts[:len(parts) - node.level + 1] + ([module] if module else []))
                names = [module] + [module + "." + a.name for a in node.names]
            for name in names:
                assert not any(name == bad or name.startswith(bad + ".") for bad in forbidden_modules), (path, name)
                for base in (ROOT / "src", ROOT / "scripts/host"):
                    stem = base.joinpath(*name.split("."))
                    for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
                        if candidate.is_file(): todo.append(candidate)
    assert ROOT / "src/v1_tickets/daily_evaluator.py" in seen
    assert ROOT / "src/mt5/mt5_candles_readonly.py" in seen
