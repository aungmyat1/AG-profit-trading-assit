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
"""
from __future__ import annotations

import logging

from execution.adapter import TradeProposal
from execution.executor import execute as execution_gateway_execute
from execution.models import ExecutionSource, TradeCommand

from .models import ENVIRONMENT_DEMO
from .store import generate_approval_id
from .telegram_gateway import ExecutionHandlerResult

logger = logging.getLogger("authorization.mt5_execution_handler")

REASON_NON_DEMO_ENVIRONMENT_REJECTED = "NON_DEMO_ENVIRONMENT_REJECTED"


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
    proposal: TradeProposal, *, environment: str = ENVIRONMENT_DEMO,
) -> ExecutionHandlerResult:
    """The real execution_handler injected into authorization.telegram_gateway /
    api.execution_service in production. Every test in this repository must inject a
    fake/mocked callable instead of this one, OR monkeypatch execution.executor.execute
    -- never let a test reach a real broker order-submission call."""
    if environment != ENVIRONMENT_DEMO:
        # Defense-in-depth: authorization.models deliberately defines no LIVE constant
        # and authorization.store.create() already rejects environment != DEMO, so this
        # branch should be unreachable in practice -- fail loudly rather than silently
        # proceeding if it is ever reached.
        return ExecutionHandlerResult(
            success=False, result_reference="", detail=REASON_NON_DEMO_ENVIRONMENT_REJECTED,
        )

    command_id = generate_approval_id()
    report = execution_gateway_execute(build_trade_command(proposal, command_id=command_id), user_confirmed=True)

    if report.status != "EXECUTED":
        reason = report.gate_reason_code or (report.reasons[0] if report.reasons else "EXECUTION_REJECTED")
        return ExecutionHandlerResult(success=False, result_reference=command_id, detail=reason)

    ticket = report.result.ticket if report.result else None
    return ExecutionHandlerResult(
        success=True, result_reference=str(ticket) if ticket is not None else command_id,
        detail=f"EXECUTED ticket={ticket}",
    )
