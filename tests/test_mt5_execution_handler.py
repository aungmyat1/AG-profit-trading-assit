"""Tests for authorization.mt5_execution_handler -- the real execution_handler adapter
that bridges an authorized proposal to execution.executor.execute(). Every test here
monkeypatches execution.executor.execute; none may reach a real MetaTrader5.order_send
call (see test_no_real_order_send_import below for a static guarantee of that too).
"""
from __future__ import annotations

import authorization.mt5_execution_handler as handler_module
from authorization.mt5_execution_handler import REASON_NON_DEMO_ENVIRONMENT_REJECTED, mt5_execution_handler
from execution.adapter import TradeProposal
from execution.models import ExecutionReport, ExecutionSource, OrderSendResult


def _proposal(**overrides) -> TradeProposal:
    base = dict(
        setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-08",
        strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol="GBPUSD", profile_id="FOREX",
        direction="SHORT", entry=1.34942, stop_loss=1.35026, tp1=1.34798, tp2=1.34522,
        volume=0.05, risk_amount=4.2, risk_percent=0.5,
    )
    base.update(overrides)
    return TradeProposal(**base)


def test_successful_mocked_execution_maps_ticket(monkeypatch):
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

    result = mt5_execution_handler(_proposal())
    assert result.success is True
    assert "123456" in result.result_reference


def test_rejected_execution_maps_failure_with_reason(monkeypatch):
    def fake_execute(command, *, user_confirmed, proposal_store=None):
        return ExecutionReport(
            command_id=command.command_id, source=ExecutionSource.ASSISTANT_PROPOSAL,
            status="REJECTED", gate_reason_code="RISK_CHECK_FAILED",
        )

    monkeypatch.setattr(handler_module, "execution_gateway_execute", fake_execute)

    result = mt5_execution_handler(_proposal())
    assert result.success is False
    assert result.detail == "RISK_CHECK_FAILED"


def test_non_demo_environment_rejected_without_calling_gateway(monkeypatch):
    calls = []
    monkeypatch.setattr(handler_module, "execution_gateway_execute", lambda *a, **k: calls.append(1))

    result = mt5_execution_handler(_proposal(), environment="LIVE")
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
