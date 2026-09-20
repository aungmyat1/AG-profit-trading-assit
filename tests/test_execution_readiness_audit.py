from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from execution.readiness import EXECUTION_INFRASTRUCTURE_READY, run_execution_readiness_audit


def _proposal(**overrides):
    base = dict(
        setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-08",
        strategy_id="ST_ASIAN_SWEEP_5R_V1",
        symbol="GBPUSD",
        profile_id="FOREX",
        direction="SHORT",
        entry=1.34942,
        stop_loss=1.35026,
        tp1=1.34798,
        tp2=1.34522,
        volume=0.05,
        risk_amount=4.2,
        risk_percent=0.5,
    )
    base.update(overrides)
    return type("P", (), base)()


def test_execution_readiness_blocks_live_account(monkeypatch):
    monkeypatch.setattr("execution.readiness.get_account", lambda: SimpleNamespace(
        is_demo=False, trade_allowed=True, equity=1000.0, login=123, server="Live-Server"
    ))
    monkeypatch.setattr("execution.readiness.verify_configured_account", lambda: None)
    monkeypatch.setattr("execution.readiness.get_symbol_meta", lambda symbol: SimpleNamespace(
        symbol=symbol, tick_size=1e-5, tick_value=1.0, contract_size=100000.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=1e-5,
        trade_stops_level=0, trade_freeze_level=0,
    ))
    monkeypatch.setattr("execution.readiness.get_tick", lambda symbol: SimpleNamespace(
        bid=1.34942, ask=1.34952, spread_points=10
    ))

    result = run_execution_readiness_audit(_proposal())

    assert result.passed is False
    assert result.reason_code == "LIVE_ACCOUNT_HARD_BLOCK"


def test_execution_readiness_passes_when_all_gate_checks_clear(monkeypatch):
    monkeypatch.setattr("execution.readiness.get_account", lambda: SimpleNamespace(
        is_demo=True, trade_allowed=True, equity=1000.0, login=123, server="VantageMarkets-Demo"
    ))
    monkeypatch.setattr("execution.readiness.verify_configured_account", lambda: None)
    monkeypatch.setattr("execution.readiness.get_symbol_meta", lambda symbol: SimpleNamespace(
        symbol=symbol, tick_size=1e-5, tick_value=1.0, contract_size=100000.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=1e-5,
        trade_stops_level=0, trade_freeze_level=0,
    ))
    monkeypatch.setattr("execution.readiness.get_tick", lambda symbol: SimpleNamespace(
        bid=1.34942, ask=1.34952, spread_points=10
    ))
    monkeypatch.setattr("execution.readiness.evaluate_sizing", lambda *args, **kwargs: SimpleNamespace(status="READY"))
    monkeypatch.setattr("execution.readiness.journal_has_executed", lambda *args, **kwargs: False)

    result = run_execution_readiness_audit(_proposal())

    assert result.passed is True
    assert result.status == EXECUTION_INFRASTRUCTURE_READY
    assert result.reason_code is None
