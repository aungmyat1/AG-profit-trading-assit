"""AG_EXISTING_DEMO_GATEWAY_GAP_AUDIT (2026-09-08): reconciliation/gap-audit tests for
the already-implemented, already-Demo-verified Telegram/Web -> authorization ->
execution.executor.execute() Demo gateway.

This is NOT a rebuild of the gateway (see src/authorization/telegram_gateway.py,
src/authorization/mt5_execution_handler.py, src/execution/coordinator.py) -- it is a
narrow reconciliation test proving two confirmed gaps found while auditing the existing
implementation against current acceptance criteria, then proving the smallest hardening
patch closes them without touching any broker boundary. No real MT5/Bybit call anywhere
in this file: execution.executor.execute is always monkeypatched.

Gap 1 (interface incompatibility): authorization.mt5_execution_handler.mt5_execution_handler
is documented as "the real execution_handler adapter for authorization.telegram_gateway /
api.execution_service" (its own module docstring) -- i.e. it is meant to serve BOTH call
sites. api.execution_service.authorize_demo_execution calls it as execution_handler(proposal)
(one positional arg). authorization.telegram_gateway.TelegramExecutionGateway._handle_execute
calls it as self._execution_handler(proposal, claimed) (two positional args) -- see
authorization/telegram_gateway.py's own ExecutionHandler type alias:
Callable[[TradeProposal, ExecutionApproval], ExecutionHandlerResult]. Before this fix,
mt5_execution_handler's signature only accepted one positional argument, so wiring it as
TelegramExecutionGateway's execution_handler (exactly as its own docstring claims it is fit
for) would raise TypeError the first time a real Execute-Demo click reached it.

Gap 2 (safety-guard bypass): execution.coordinator.ExecutionCoordinator.submit() is the
only caller of execution.executor.execute() that also enforces the GLOBAL, cross-strategy
OpenPositionGuard (max concurrent AG strategy positions) and DailyLossGuard (-2R circuit
breaker) -- see execution/coordinator.py's own module docstring. mt5_execution_handler
calls execution.executor.execute() directly, bypassing ExecutionCoordinator entirely, so
neither guard was ever consulted on the Telegram/Web execution path: an authorized,
integrity-verified, Demo-eligible click could still open a position past the concurrent-
position cap or after the daily circuit breaker had already tripped.
"""
from __future__ import annotations

from datetime import datetime, timezone

import authorization.mt5_execution_handler as handler_module
from authorization.mt5_execution_handler import mt5_execution_handler
from authorization.models import ExecutionApproval, ENVIRONMENT_DEMO, STATE_CLAIMED, VENUE_MT5
from authorization.telegram_gateway import TelegramExecutionGateway
from authorization.store import ExecutionApprovalStore
from execution.adapter import TradeProposal
from execution.daily_loss_guard import DailyLossGuard
from execution.lifecycle import _trading_day
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


def _approval(proposal: TradeProposal) -> ExecutionApproval:
    now = datetime.now(timezone.utc)
    return ExecutionApproval(
        approval_id="approval1", setup_id=proposal.setup_id, proposal_hash="irrelevant",
        venue=VENUE_MT5, environment=ENVIRONMENT_DEMO, state=STATE_CLAIMED,
        created_at=now, expires_at=now,
    )


def _fake_execute_success(command, *, user_confirmed, proposal_store=None):
    assert user_confirmed is True
    return ExecutionReport(
        command_id=command.command_id, source=ExecutionSource.ASSISTANT_PROPOSAL,
        status="EXECUTED",
        result=OrderSendResult(status="FILLED", reason_code="OK", symbol=command.symbol,
                               broker_retcode=10009, ticket=555111),
    )


# --------------------------------------------------------------- Gap 1: call-signature

def test_mt5_execution_handler_is_callable_the_way_telegram_gateway_calls_it(monkeypatch):
    """authorization.telegram_gateway.ExecutionHandler = Callable[[TradeProposal,
    ExecutionApproval], ExecutionHandlerResult] -- TelegramExecutionGateway._handle_execute
    calls self._execution_handler(proposal, claimed), two positional args. This must not
    raise TypeError when mt5_execution_handler (this repo's own real handler, per its
    module docstring) is injected as that gateway's execution_handler."""
    monkeypatch.setattr(handler_module, "execution_gateway_execute", _fake_execute_success)
    monkeypatch.setattr(handler_module, "OpenPositionGuard", _NeverBlockedPositionGuard)
    monkeypatch.setattr(handler_module, "DailyLossGuard", _NeverBlockedLossGuard)

    proposal = _proposal()
    approval = _approval(proposal)

    result = mt5_execution_handler(proposal, approval)  # two positional args, as telegram_gateway calls it
    assert result.success is True


def test_mt5_execution_handler_still_supports_single_arg_api_call(monkeypatch):
    """api.execution_service.authorize_demo_execution calls execution_handler(proposal)
    -- one positional arg. The Gap 1 fix must not break this existing, already-tested
    call convention."""
    monkeypatch.setattr(handler_module, "execution_gateway_execute", _fake_execute_success)
    monkeypatch.setattr(handler_module, "OpenPositionGuard", _NeverBlockedPositionGuard)
    monkeypatch.setattr(handler_module, "DailyLossGuard", _NeverBlockedLossGuard)

    result = mt5_execution_handler(_proposal())
    assert result.success is True


# ------------------------------------------------------------ Gap 2: global guard bypass

class _NeverBlockedPositionGuard:
    @classmethod
    def default(cls):
        return cls()

    def is_blocked(self):
        return False

    def register_open(self, *a, **k):
        pass


class _NeverBlockedLossGuard:
    @classmethod
    def default(cls, strategy_id):
        return cls()

    def is_blocked(self, trading_day):
        return False

    def record_trade_result(self, trading_day, r_multiple):
        return 0.0


def test_mt5_execution_handler_fails_closed_when_open_position_guard_blocked(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(handler_module, "execution_gateway_execute",
                         lambda *a, **k: calls.append(1) or _fake_execute_success(*a, **k))

    open_guard = OpenPositionGuard.default(str(tmp_path / "open_positions.json"))
    open_guard.register_open("999999", "SOME_OTHER_STRATEGY", "EURUSD")  # slot already occupied
    loss_guard = DailyLossGuard.default("AG_EXECUTION_COORDINATOR_GLOBAL", str(tmp_path / "daily_r.json"))

    result = mt5_execution_handler(
        _proposal(), open_position_guard=open_guard, daily_loss_guard=loss_guard,
    )

    assert result.success is False
    assert "OPEN_POSITION" in result.detail
    assert calls == [], "execute() must never be called once the GLOBAL open-position guard is blocked"


def test_mt5_execution_handler_fails_closed_when_daily_loss_guard_blocked(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(handler_module, "execution_gateway_execute",
                         lambda *a, **k: calls.append(1) or _fake_execute_success(*a, **k))

    open_guard = OpenPositionGuard.default(str(tmp_path / "open_positions.json"))
    loss_guard = DailyLossGuard.default("AG_EXECUTION_COORDINATOR_GLOBAL", str(tmp_path / "daily_r.json"))
    loss_guard.record_trade_result(_trading_day(None), -2.5)  # already past the -2R circuit breaker

    result = mt5_execution_handler(
        _proposal(), open_position_guard=open_guard, daily_loss_guard=loss_guard,
    )

    assert result.success is False
    assert "DAILY_LOSS" in result.detail
    assert calls == [], "execute() must never be called once the GLOBAL daily-loss guard is blocked"


def test_mt5_execution_handler_allows_execution_when_guards_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(handler_module, "execution_gateway_execute", _fake_execute_success)

    open_guard = OpenPositionGuard.default(str(tmp_path / "open_positions.json"))
    loss_guard = DailyLossGuard.default("AG_EXECUTION_COORDINATOR_GLOBAL", str(tmp_path / "daily_r.json"))

    result = mt5_execution_handler(
        _proposal(), open_position_guard=open_guard, daily_loss_guard=loss_guard,
    )

    assert result.success is True
    assert "555111" in result.result_reference
    # the newly-filled position must now itself count toward the shared cap
    assert open_guard.open_count() == 1
