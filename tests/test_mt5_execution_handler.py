"""Tests for authorization.mt5_execution_handler -- the real execution_handler adapter
that bridges an authorized proposal to execution.executor.execute(). Every test here
monkeypatches execution.executor.execute; none may reach a real MetaTrader5.order_send
call (see test_no_real_order_send_import below for a static guarantee of that too).
"""
from __future__ import annotations

import authorization.mt5_execution_handler as handler_module
from authorization.mt5_execution_handler import REASON_NON_DEMO_ENVIRONMENT_REJECTED, mt5_execution_handler
from execution.adapter import TradeProposal
from execution.daily_loss_guard import DailyLossGuard
from execution.models import ExecutionReport, ExecutionSource, OrderSendResult
from execution.position_guard import OpenPositionGuard


def _proposal(**overrides) -> TradeProposal:
    base = dict(
        setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-08",
        strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol="GBPUSD", profile_id="FOREX",
        direction="SHORT", entry=1.34942, stop_loss=1.35026, tp1=1.34798, tp2=1.34522,
        volume=0.05, risk_amount=4.2, risk_percent=0.5,
    )
    base.update(overrides)
    return TradeProposal(**base)


def _guards(tmp_path):
    """AG_EXISTING_DEMO_GATEWAY_GAP_AUDIT (2026-09-08): mt5_execution_handler now checks
    the GLOBAL OpenPositionGuard/DailyLossGuard before calling execute() (see that
    module's own docstring, gap 2). Every test here injects tmp_path-backed guards so a
    test run never reads or writes this repository's real journal/ag_open_strategy_
    positions.json / journal/ag_strategy_daily_realized_r.json state -- the same
    isolation convention execution/coordinator.py's own tests already use."""
    return (
        OpenPositionGuard.default(str(tmp_path / "open_positions.json")),
        DailyLossGuard.default("AG_EXECUTION_COORDINATOR_GLOBAL", str(tmp_path / "daily_r.json")),
    )


def test_successful_mocked_execution_maps_ticket(tmp_path, monkeypatch):
    def fake_execute(command, *, user_confirmed, proposal_store=None):
        assert user_confirmed is True
        assert command.symbol == "GBPUSD"
        assert command.action == "OPEN"
        return ExecutionReport(
            command_id=command.command_id, source=ExecutionSource.ASSISTANT_PROPOSAL,
            status="EXECUTED",
            result=OrderSendResult(status="FILLED", reason_code="OK", symbol="GBPUSD", broker_retcode=10009, ticket=123456),
        )

    monkeypatch.setattr(handler_module, "execution_gateway_execute", fake_execute)
    open_guard, loss_guard = _guards(tmp_path)

    result = mt5_execution_handler(_proposal(), open_position_guard=open_guard, daily_loss_guard=loss_guard)
    assert result.success is True
    assert "123456" in result.result_reference


def test_rejected_execution_maps_failure_with_reason(tmp_path, monkeypatch):
    def fake_execute(command, *, user_confirmed, proposal_store=None):
        return ExecutionReport(
            command_id=command.command_id, source=ExecutionSource.ASSISTANT_PROPOSAL,
            status="REJECTED", gate_reason_code="RISK_CHECK_FAILED",
        )

    monkeypatch.setattr(handler_module, "execution_gateway_execute", fake_execute)
    open_guard, loss_guard = _guards(tmp_path)

    result = mt5_execution_handler(_proposal(), open_position_guard=open_guard, daily_loss_guard=loss_guard)
    assert result.success is False
    assert result.detail == "RISK_CHECK_FAILED"


def test_non_demo_environment_rejected_without_calling_gateway(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(handler_module, "execution_gateway_execute", lambda *a, **k: calls.append(1))
    open_guard, loss_guard = _guards(tmp_path)

    result = mt5_execution_handler(_proposal(), environment="LIVE",
                                    open_position_guard=open_guard, daily_loss_guard=loss_guard)
    assert result.success is False
    assert result.detail == REASON_NON_DEMO_ENVIRONMENT_REJECTED
    assert calls == []  # gateway never called at all


def test_no_real_order_send_import_anywhere_in_module():
    """Static guarantee: the adapter module's own source never mentions order_send,
    MetaTrader5, or mt5.mt5_gateway -- its only broker-reaching path is
    execution.executor.execute(), the repository's single sanctioned boundary."""
    import inspect

    source = inspect.getsource(handler_module)
    for forbidden in ("order_send", "MetaTrader5", "mt5_gateway", "mt5.management_gateway"):
        assert forbidden not in source, f"unexpected direct broker reference: {forbidden!r}"
