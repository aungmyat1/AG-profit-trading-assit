"""Tests for strategy_manager.manager: registry lookup, unknown strategy, unsigned
cycle (the mandatory LONDON_NEWYORK block), and a successful dispatch with the adapter
mocked. No live MT5/subprocess needed."""
from __future__ import annotations

from datetime import date, datetime, timezone

from assistant.models import (
    CONTEXT_READY,
    MODE_ANALYZE_ONLY,
    MODE_LIVE,
    STATUS_BLOCKED,
    STATUS_TRADE_READY,
    MarketContext,
)
from strategy_manager import manager
from strategy_manager.session_trade_adapter import AdapterRunResult

_READY_CONTEXT = MarketContext(
    symbol="EURUSD", broker_resolved_symbol="EURUSD", timestamp_utc=datetime.now(timezone.utc),
    session_date=date(2026, 8, 27), account_login=1, account_server="Test-Demo", account_is_demo=True,
    current_bid=1.1700, current_ask=1.1702, tick_time_utc=datetime.now(timezone.utc), status=CONTEXT_READY,
)


def test_unknown_strategy_is_blocked(monkeypatch):
    monkeypatch.setattr(manager, "build_context", lambda symbol: _READY_CONTEXT)
    result = manager.evaluate("NOT_A_REAL_STRATEGY", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)
    assert result.strategy_result.status == STATUS_BLOCKED
    assert manager.REASON_STRATEGY_NOT_REGISTERED in result.strategy_result.reason_codes


def test_unregistered_or_inactive_strategy_blocked(monkeypatch):
    monkeypatch.setattr(manager, "build_context", lambda symbol: _READY_CONTEXT)
    monkeypatch.setattr(manager, "_load_registry", lambda: {"SESSION_TRADE_V1": {"registered": True, "active": False}})
    result = manager.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)
    assert result.strategy_result.status == STATUS_BLOCKED
    assert manager.REASON_STRATEGY_NOT_ACTIVE in result.strategy_result.reason_codes


def test_london_newyork_cycle_is_blocked_and_adapter_never_called(monkeypatch):
    monkeypatch.setattr(manager, "build_context", lambda symbol: _READY_CONTEXT)
    calls = []
    monkeypatch.setattr(manager, "run_session_trade_v1", lambda *a, **k: calls.append((a, k)))

    result = manager.evaluate("SESSION_TRADE_V1", "EURUSD", "LONDON_NEWYORK", MODE_ANALYZE_ONLY)

    assert result.strategy_result.status == STATUS_BLOCKED
    assert manager.REASON_UNSIGNED_CYCLE in result.strategy_result.reason_codes
    assert calls == []  # the adapter (and therefore the subprocess) was never invoked


def test_live_mode_is_blocked_and_adapter_never_called(monkeypatch):
    monkeypatch.setattr(manager, "build_context", lambda symbol: _READY_CONTEXT)
    calls = []
    monkeypatch.setattr(manager, "run_session_trade_v1", lambda *a, **k: calls.append((a, k)))

    result = manager.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_LIVE)

    assert result.strategy_result.status == STATUS_BLOCKED
    assert manager.REASON_LIVE_HARD_BLOCKED in result.strategy_result.reason_codes
    assert calls == []


def test_successful_dispatch_for_asian_london(monkeypatch):
    monkeypatch.setattr(manager, "build_context", lambda symbol: _READY_CONTEXT)
    fake_adapter_result = AdapterRunResult(
        execution_outcome="DRY_RUN", payload={"execution": "DRY_RUN", "signal_id": "sig1"}, exit_code=0,
        analysis=dict(strategy_id="ASIAN_SESSION_V1", contract_version="1.4", trading_date="2026-08-27",
                      accepted=True, setup="SWEEP", direction="SHORT", entry=1.1650, stop_loss=1.1670,
                      tp2_5r=1.1550, risk_fraction=0.005, reason_codes=[]),
    )
    monkeypatch.setattr(manager, "run_session_trade_v1", lambda symbol, cycle, mode: fake_adapter_result)

    result = manager.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)

    assert result.strategy_result.status == STATUS_TRADE_READY
    assert result.strategy_result.setup == "SWEEP"
    assert result.adapter_result is fake_adapter_result


def test_context_failure_short_circuits_before_registry(monkeypatch):
    from assistant.models import CONTEXT_FAILED, STATUS_INVALID_CONTEXT
    failed_context = MarketContext(
        symbol="EURUSD", broker_resolved_symbol="EURUSD", timestamp_utc=datetime.now(timezone.utc),
        session_date=date(2026, 8, 27), account_login=0, account_server="", account_is_demo=False,
        current_bid=float("nan"), current_ask=float("nan"), tick_time_utc=datetime.now(timezone.utc),
        status=CONTEXT_FAILED, reason_codes=("STALE_DATA",),
    )
    monkeypatch.setattr(manager, "build_context", lambda symbol: failed_context)
    calls = []
    monkeypatch.setattr(manager, "_load_registry", lambda: calls.append("registry") or {})

    result = manager.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)

    assert result.strategy_result.status == STATUS_INVALID_CONTEXT
    assert calls == []  # registry never consulted once context has already failed
