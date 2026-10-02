"""Scanner V1 source-isolation and fallback regressions.

These tests are offline. They exercise source selection and the source-aware quality
contract without opening a network connection or invoking any broker mutation tool.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from session_scanner import checklist
from session_scanner import scanner as scanner_module
from session_scanner.quality import Bar, INVALID, STALE, VALID, assess_series, fetch_with_sync
from session_scanner.registry import load_specs, resolve_spec, verify_live
from session_scanner.scanner import load_scanner_config, run_scan
from session_scanner.strategy_adapter import AsianSweepAdapter, resolve_proposal_scope
from session_scanner.terminal_client import Mt5ReadOnlyClient, TerminalMcpClient
from session_scanner.timebase import derive_time_authority

UTC = timezone.utc


class _FakeSource:
    def __init__(self, name: str):
        self.source_name = name


def _quality_item(symbol: str, *, status: str = "PASS", broker_symbol: str | None = None,
                  latest: str = "2026-10-02T13:15:00+00:00", bid: float = 1.1,
                  ask: float = 1.1001, timestamp: str = "2026-10-02T13:31:00+00:00") -> dict:
    return {
        "canonical_symbol": symbol,
        "broker_symbol": broker_symbol or f"{symbol}-VIP",
        "source": "TERMINAL_MCP",
        "data_quality_gate": status,
        "instrument": {"broker_symbol": broker_symbol or f"{symbol}-VIP"},
        "quote": {"bid": bid, "ask": ask, "timestamp_utc": timestamp},
        "data_quality": {"M15": {"timeframe": "M15", "last_closed_bar_utc": latest}},
    }


def _candidate(source: str, item: dict, gate: str = "PASS") -> dict:
    return {
        "scanner_version": "SESSION_SCANNER_V1", "source": source,
        "data_authority": source.lower(), "data_quality_gate": gate,
        "source_timestamp": "2026-10-02T13:31:32Z", "instruments": [item],
        "ready_setups": [], "no_trade": [], "blocked": [],
        "execution_authorized": False,
    }


def test_secondary_client_is_explicit_and_read_only():
    primary = TerminalMcpClient("http://127.0.0.1:9/never", "NO_TOKEN")
    secondary = Mt5ReadOnlyClient("http://127.0.0.1:9/never", "NO_TOKEN")
    assert primary.source_name == "TERMINAL_MCP"
    assert secondary.source_name == "MT5_READONLY"
    assert secondary.source_name == "MT5_READONLY"


def test_primary_pass_is_selected_atomically(monkeypatch):
    cfg = {"version": "SESSION_SCANNER_V1", "instruments": {"EURUSD": {}}}
    primary_item = _quality_item("EURUSD")
    secondary_item = _quality_item("EURUSD", broker_symbol="EURUSD-SECONDARY", bid=1.2, ask=1.2001)

    def fake_scan(source, cfg, local_utc_now, source_label):
        return _candidate(source_label, primary_item if source_label == "TERMINAL_MCP" else secondary_item)

    monkeypatch.setattr(scanner_module, "_run_source_scan", fake_scan)
    out = run_scan(_FakeSource("TERMINAL_MCP"), cfg, secondary_source=_FakeSource("MT5_READONLY"))
    assert out["actual_source"] == "TERMINAL_MCP"
    assert out["data_source_degraded"] is False
    assert out["instruments"][0]["quote"]["bid"] == 1.1
    assert out["fallback_reason"] == "PRIMARY_QUALITY_GATE_PASS"


def test_quality_failed_primary_falls_back_without_mixing(monkeypatch):
    cfg = {"version": "SESSION_SCANNER_V1", "instruments": {"EURUSD": {}}}
    primary_item = _quality_item("EURUSD", status="FAIL", bid=1.1)
    secondary_item = _quality_item("EURUSD", broker_symbol="EURUSD-SECONDARY", bid=1.2, ask=1.2001)

    def fake_scan(source, cfg, local_utc_now, source_label):
        if source_label == "TERMINAL_MCP":
            return _candidate(source_label, primary_item, gate="FAIL")
        return _candidate(source_label, secondary_item, gate="PASS")

    monkeypatch.setattr(scanner_module, "_run_source_scan", fake_scan)
    out = run_scan(_FakeSource("TERMINAL_MCP"), cfg, secondary_source=_FakeSource("MT5_READONLY"))
    assert out["primary_source"] == "TERMINAL_MCP"
    assert out["actual_source"] == "MT5_READONLY"
    assert out["data_source_degraded"] is True
    assert out["fallback_reason"] == "PRIMARY_QUALITY_GATE_FAIL"
    assert out["instruments"][0]["source"] == "TERMINAL_MCP"  # candidate data is not rewritten or mixed
    assert out["instruments"][0]["quote"]["bid"] == 1.2


def test_both_failed_sources_fail_closed(monkeypatch):
    cfg = {"version": "SESSION_SCANNER_V1", "instruments": {"EURUSD": {}}}
    failed = _candidate("TERMINAL_MCP", _quality_item("EURUSD", status="FAIL"), gate="FAIL")

    monkeypatch.setattr(scanner_module, "_run_source_scan", lambda *args, **kwargs: failed)
    out = run_scan(_FakeSource("TERMINAL_MCP"), cfg, secondary_source=_FakeSource("MT5_READONLY"))
    assert out["actual_source"] == "TERMINAL_MCP"
    assert out["data_quality_gate"] == "FAIL"
    assert out["data_source_degraded"] is False
    assert out["fallback_reason"] == "PRIMARY_AND_SECONDARY_QUALITY_GATE_FAIL"


def test_reconciliation_exposes_all_required_classifications():
    cfg = {"version": "SESSION_SCANNER_V1"}
    cases = {
        "MATCH": (_quality_item("MATCH"), _quality_item("MATCH"), "SOURCE_MATCH"),
        "MINOR": (_quality_item("MINOR"), _quality_item("MINOR", latest="2026-10-02T13:15:30+00:00"),
                  "MINOR_TIMESTAMP_DIFFERENCE"),
        "ALIAS": (_quality_item("ALIAS"), _quality_item("ALIAS", broker_symbol="ALIAS-ALT"),
                  "SYMBOL_ALIAS_DIFFERENCE"),
        "STALE": (_quality_item("STALE"), _quality_item("STALE", status="FAIL"), "SOURCE_STALE"),
        "MISMATCH": (_quality_item("MISMATCH"), _quality_item("MISMATCH", bid=1.3), "SOURCE_MISMATCH"),
    }
    primary = {"instruments": [_quality_item(k) for k in cases]}
    secondary = {"instruments": []}
    for key, (p, s, expected) in cases.items():
        primary["instruments"] = [p]
        secondary["instruments"] = [s]
        row = scanner_module._reconcile_sources(primary, secondary, cfg)[0]
        assert row["status"] == expected, key


def test_retry_exception_is_a_failed_quality_gate():
    now = datetime(2026, 10, 2, 13, 31, tzinfo=UTC)
    ta = derive_time_authority({"utc_time": "2026-10-02T13:31:32Z", "trade_server_last_known_time": "2026-10-02T16:31:15"})
    stale = [Bar(datetime(2026, 10, 2, 12, 15, tzinfo=UTC), 1.1, 1.101, 1.099, 1.100)]
    assess = lambda bars: assess_series(bars, "M15", now, ta, None, 1)
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) == 1:
            return stale
        raise RuntimeError("source unavailable")

    result = fetch_with_sync(fetch, assess)
    assert result.retry_performed is True
    assert result.quality.status == INVALID
    assert result.as_dict()["data_quality_gate"] == "FAIL"
    assert result.retry_error == "RuntimeError"
    assert len(calls) == 2


def test_trend_signal_has_no_entry_timing():
    signal = SimpleNamespace(status="SIGNAL", regime="TREND", signal_timestamp=None)
    assert checklist.signal_entry_status(signal, None) == (False, "ENTRY_TIMING_NOT_DEFINED_FOR_SETUP")


def test_risk_policy_stays_scoped_to_eurusd_and_gbpusd():
    cfg = load_scanner_config()
    adapter_cfg = cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]
    adapter = AsianSweepAdapter(adapter_cfg["contract"], adapter_cfg["proposal_scope"])
    for symbol in ("EURUSD", "GBPUSD"):
        scope = resolve_proposal_scope(adapter.strategy, "ASIAN_LONDON", symbol, adapter.pilots)
        assert scope.authorized is True
        assert scope.risk_per_trade_pct == 0.5
    for symbol in ("USDJPY", "XAUUSD"):
        scope = resolve_proposal_scope(adapter.strategy, "ASIAN_LONDON", symbol, adapter.pilots)
        assert scope.authorized is False
        assert scope.reason.startswith("RISK_POLICY_AMBIGUOUS")


def test_secondary_uses_the_same_symbol_mapping_contract():
    cfg = load_scanner_config()
    specs = load_specs(cfg)
    eur = resolve_spec(specs, "EURUSD")
    record = verify_live(eur, {"symbol": eur.broker_symbol, "digits": 5, "point": 0.00001,
                               "trade_mode_name": "full"}, price_source="MT5_READONLY")
    assert record.broker_symbol == "EURUSD-VIP"
    assert record.price_source == "MT5_READONLY"
