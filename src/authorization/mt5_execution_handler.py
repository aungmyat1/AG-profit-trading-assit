"""The real execution_handler adapter for authorization.telegram_gateway /
api.execution_service -- Phase D2 (AG_DEMO_EXECUTION_GATEWAY_PHASE_D2_API_AND_EXECUTION_WIRING_V1).

Bridges an authorized ExecutionApproval's TradeProposal to
execution.executor.execute() -- the SAME sole broker-submission boundary every other
path in this repository already uses (AGENTS.md "Authority order" point 3). This module
never imports the MT5 terminal library or the management-gateway module directly; it
only ever calls execution.executor's own execute() function, and only when explicitly
invoked by a caller that already holds a successful ExecutionApprovalStore.claim()
result -- i.e. only after the same approval/idempotency chain telegram_gateway.py
already enforces.

`user_confirmed=True` is passed here because reaching this function at all already
required: (1) an explicit Web or Telegram "Execute (Demo)" action from the owner this
turn, translated into an authorize-demo request, (2) a successful atomic claim on that
specific approval (never a second time), and (3) every guard in authorize_demo_execution()
(strategy demo-authority, configured+actual Demo environment, proposal integrity). That
chain IS the "explicit user instruction this turn" AGENTS.md requires -- not a default,
not inferred from READY/DEMO_ELIGIBLE alone.

AG_EXISTING_DEMO_GATEWAY_GAP_AUDIT (2026-09-08) hardening -- two confirmed gaps closed
here, both proven first by tests/test_ag_existing_demo_gateway_gap_audit.py:

  1. Call-signature: this module's own docstring above claims it serves BOTH
     api.execution_service (calls execution_handler(proposal), one positional arg) AND
     authorization.telegram_gateway (whose ExecutionHandler type is
     Callable[[TradeProposal, ExecutionApproval], ExecutionHandlerResult] -- it calls
     self._execution_handler(proposal, claimed), two positional args). Before this fix,
     mt5_execution_handler only accepted one positional argument, so wiring it into
     TelegramExecutionGateway as its own docstring describes would raise TypeError on
     the first real Execute-Demo click. `approval` is now accepted (and unused) so both
     call conventions work; it is not needed for anything the guards below already do
     via `proposal` alone.

  2. GLOBAL safety-guard bypass: execution.coordinator.ExecutionCoordinator.submit() is
     the only OTHER caller of execution.executor.execute(), and it additionally enforces
     the shared, cross-strategy OpenPositionGuard (max concurrent AG positions) and
     DailyLossGuard (-2R circuit breaker) before ever reaching execute() -- see
     execution/coordinator.py's own module docstring. This module called
     execution.executor.execute() directly, bypassing ExecutionCoordinator (and both
     guards) entirely, so an authorized, integrity-verified, Demo-eligible Telegram/Web
     click could still exceed the concurrent-position cap or fire after the daily
     circuit breaker had already tripped. Both guards are now checked here too, against
     the SAME shared, on-disk ledger (GLOBAL_LEDGER_STRATEGY_ID) ExecutionCoordinator
     already uses -- not a second, divergent copy of either rule -- and a resulting fill
     is registered into the same OpenPositionGuard via
     execution.lifecycle.register_confirmed_fill, the SAME function
     ExecutionCoordinator._submit_forex already calls, so a position opened through this
     handler counts toward the cap exactly like one opened any other way.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from execution.adapter import TradeProposal
from execution.coordinator import GLOBAL_LEDGER_STRATEGY_ID
from execution.daily_loss_guard import DailyLossGuard
from execution.executor import execute as execution_gateway_execute
from execution.lifecycle import _trading_day, register_confirmed_fill
from execution.models import ExecutionSource, TradeCommand
from execution.position_guard import OpenPositionGuard

from .models import ENVIRONMENT_DEMO, ExecutionApproval
from .store import generate_approval_id
from .telegram_gateway import ExecutionHandlerResult

logger = logging.getLogger("authorization.mt5_execution_handler")

REASON_NON_DEMO_ENVIRONMENT_REJECTED = "NON_DEMO_ENVIRONMENT_REJECTED"
REASON_BLOCKED_DAILY_LOSS = "BLOCKED_DAILY_LOSS"
REASON_BLOCKED_OPEN_POSITION = "BLOCKED_OPEN_POSITION"


def build_trade_command(proposal: TradeProposal, *, command_id: str) -> TradeCommand:
    """Maps the immutable, already-persisted TradeProposal (never Web/Telegram input)
    onto a TradeCommand. Every execution-critical field here comes from the proposal,
    not from any caller-supplied request body -- see authorization.integrity for how
    that proposal was already pinned to the approval before this function is ever
    reached."""
    return TradeCommand(
        command_id=command_id,
        action="OPEN",
        symbol=proposal.symbol,
        source=ExecutionSource.ASSISTANT_PROPOSAL,
        side=proposal.direction,
        order_type="MARKET",
        volume=proposal.volume,
        entry=proposal.entry,
        sl=proposal.stop_loss,
        tp=proposal.tp1,
        risk_percent=proposal.risk_percent,
        proposal_id=proposal.setup_id,
        position_ticket=None,
        comment=f"AG_DEMO_GATEWAY:{proposal.setup_id}"[:31],  # MT5 comment field length limit
        magic_number=None,
    )


def mt5_execution_handler(
    proposal: TradeProposal, approval: Optional[ExecutionApproval] = None, *,
    environment: str = ENVIRONMENT_DEMO,
    open_position_guard: Optional[OpenPositionGuard] = None,
    daily_loss_guard: Optional[DailyLossGuard] = None,
    now: Optional[datetime] = None,
) -> ExecutionHandlerResult:
    """The real execution_handler injected into authorization.telegram_gateway /
    api.execution_service in production. Every test in this repository must inject a
    fake/mocked callable instead of this one, OR monkeypatch execution.executor.execute
    -- never let a test reach a real broker order-submission call.

    `approval` is accepted (and otherwise unused) purely so this function is callable
    both as api.execution_service calls it (execution_handler(proposal)) and as
    authorization.telegram_gateway.TelegramExecutionGateway calls it
    (self._execution_handler(proposal, claimed)) -- see module docstring, gap 1.
    `open_position_guard`/`daily_loss_guard`/`now` are injectable purely for tests; a
    real caller never needs to pass them, exactly like ExecutionCoordinator.default()."""
    if environment != ENVIRONMENT_DEMO:
        # Defense-in-depth: authorization.models deliberately defines no LIVE constant
        # and authorization.store.create() already rejects environment != DEMO, so this
        # branch should be unreachable in practice -- fail loudly rather than silently
        # proceeding if it is ever reached.
        return ExecutionHandlerResult(
            success=False, result_reference="", detail=REASON_NON_DEMO_ENVIRONMENT_REJECTED,
        )

    # GLOBAL, cross-strategy safety guards -- see module docstring, gap 2. Checked BEFORE
    # execute() is ever called, exactly like ExecutionCoordinator.submit() already does
    # for every other execution route into execute().
    open_guard = open_position_guard or OpenPositionGuard.default()
    loss_guard = daily_loss_guard or DailyLossGuard.default(GLOBAL_LEDGER_STRATEGY_ID)
    trading_day = _trading_day(now)
    if loss_guard.is_blocked(trading_day):
        return ExecutionHandlerResult(success=False, result_reference="", detail=REASON_BLOCKED_DAILY_LOSS)
    if open_guard.is_blocked():
        return ExecutionHandlerResult(success=False, result_reference="", detail=REASON_BLOCKED_OPEN_POSITION)

    command_id = generate_approval_id()
    report = execution_gateway_execute(build_trade_command(proposal, command_id=command_id), user_confirmed=True)

    if report.status != "EXECUTED":
        reason = report.gate_reason_code or (report.reasons[0] if report.reasons else "EXECUTION_REJECTED")
        return ExecutionHandlerResult(success=False, result_reference=command_id, detail=reason)

    # Register the fill into the SAME shared guard ExecutionCoordinator._submit_forex
    # already registers into for every other execution route (execution.lifecycle's own
    # function, not a second copy of its logic) -- so this position counts toward the
    # cap for the NEXT click too, through whichever surface it arrives on.
    register_confirmed_fill(open_guard, proposal, report)

    ticket = report.result.ticket if report.result else None
    return ExecutionHandlerResult(
        success=True, result_reference=str(ticket) if ticket is not None else command_id,
        detail=f"EXECUTED ticket={ticket}",
    )
