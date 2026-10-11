"""OwnerDecision / ExecutionDecision -- the typed bridge between an explicit owner
action on the CanonicalProposal-based Owner Analysis Panel and the existing
assistant.commands.execute_command() gate (AGENTS.md Authority order point 3).

This module defines data only -- no execution, no I/O. See owner_decision.bridge for
the evaluation function that fills an ExecutionDecision from an OwnerDecision +
CanonicalProposal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

from execution.models import TradeCommand

OWNER_ACTION_APPROVE_DEMO = "APPROVE_DEMO"
OWNER_ACTION_REJECT = "REJECT"
OWNER_ACTIONS = frozenset({OWNER_ACTION_APPROVE_DEMO, OWNER_ACTION_REJECT})

ENVIRONMENT_DEMO = "DEMO"
ENVIRONMENT_LIVE = "LIVE"

EXECUTION_DECISION_AUTHORIZED = "AUTHORIZED"
EXECUTION_DECISION_REJECTED = "REJECTED"


@dataclass(frozen=True)
class OwnerDecision:
    """A single explicit owner action on one CanonicalProposal. Constructing this
    object is itself never approval or execution -- only owner_decision.bridge.
    evaluate_owner_decision() interprets it, and only APPROVE_DEMO can ever produce an
    AUTHORIZED ExecutionDecision.

    decision_id is the caller-supplied idempotency key (e.g. a UUID minted by the
    Owner Analysis Panel at the moment the owner clicks Approve/Reject); replaying the
    same decision_id never creates a second, independent authorization (P8)."""

    decision_id: str
    proposal_envelope_id: str
    action: str  # OWNER_ACTION_APPROVE_DEMO / OWNER_ACTION_REJECT
    symbol: str
    environment: str = ENVIRONMENT_DEMO
    decided_at: Optional[datetime] = None  # caller/UI timestamp, audit only -- staleness
    # is judged by the evaluator's own `now` against the proposal's own plan_expires_at,
    # never by trusting this field alone.
    actor: Optional[str] = None  # audit metadata only, never influences authorization


@dataclass(frozen=True)
class ExecutionDecision:
    """Always-returned outcome of evaluate_owner_decision(). AUTHORIZED means
    `trade_command` is a PREPARED, UNCONFIRMED execution.models.TradeCommand template
    (source=ASSISTANT_PROPOSAL) -- constructing/returning it performs no order_check/
    order_send (execution.models.TradeCommand's own contract: "Never executed by
    constructing one"). Reaching an actual broker order still requires a SEPARATE,
    later call this module never makes:
    assistant.commands.execute_command(trade_command, user_confirmed=True), where
    user_confirmed must be derived from an explicit user instruction that same turn
    (AGENTS.md Authority order point 3)."""

    decision_id: str
    proposal_envelope_id: str
    status: str  # EXECUTION_DECISION_AUTHORIZED / EXECUTION_DECISION_REJECTED
    reason_code: str
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    trade_command: Optional[TradeCommand] = None
