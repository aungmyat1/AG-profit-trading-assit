"""authorize_demo_execution(): the ONE orchestration function both the HTTP API and
Telegram must call (AG_DEMO_EXECUTION_GATEWAY_PHASE_D2_API_AND_EXECUTION_WIRING_V1,
final invariant: "BOTH USE ONE AUTHORIZATION SERVICE"). authorization.telegram_gateway
already implements almost this exact sequence for the Telegram transport; this module
is the transport-agnostic core so api.app can reuse it without duplicating the chain.

Sequence (spec section 11), each step fails closed to a normalized reason code:
  1. load approval           4. verify proposal integrity
  2. atomic claim             5. verify strategy Demo authority
  3. load proposal            6. dispatch execution_handler, journal, return

Risk revalidation, broker/symbol-metadata validation, and reconciliation-via-
positions/orders-query are NOT implemented in this function yet -- they belong inside
the injected `execution_handler` (mt5_execution_handler ultimately delegates to
execution.executor.execute(), which already performs its own risk/geometry/symbol-
metadata gates -- see execution/executor.py's `_validate_geometry_and_sizing` /
`_resolve_equity_and_symbol_meta`). Duplicating those checks here would be a second,
divergent copy of the same rules; this module intentionally defers to the existing
gateway for them rather than re-implementing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from authorization.integrity import compute_proposal_hash
from authorization.models import (
    ENVIRONMENT_DEMO,
    REASON_APPROVAL_ALREADY_PROCESSED,
    REASON_APPROVAL_EXPIRED,
    REASON_APPROVAL_NOT_FOUND,
    REASON_PROPOSAL_INTEGRITY_MISMATCH,
    REASON_PROPOSAL_NOT_FOUND,
)
from authorization.store import ExecutionApprovalStore
from authorization.strategy_authority import check_strategy_demo_authorized
from authorization.telegram_gateway import ExecutionHandlerResult
from execution.adapter import TradeProposal
from execution.journal import record_event

logger = logging.getLogger("api.execution_service")

SOURCE_WEB = "WEB"
SOURCE_TELEGRAM = "TELEGRAM"


class ProposalRegistry(Protocol):
    """Minimal lookup contract. InMemoryProposalRegistry below is the only
    implementation this phase ships; a real persistent-store-backed implementation
    (reading post_asian_pilot's proposal journal, the BTC research ledger, etc.) is
    deferred -- see AG_DEMO_EXECUTION_GATEWAY_PHASE_D2_STATUS 'remaining_operational_debt'."""

    def get_by_hash(self, proposal_hash: str) -> Optional[TradeProposal]: ...


class InMemoryProposalRegistry:
    """Process-local registry, same scope/limitation as execution.executor.ProposalStore
    (in-memory cache, not a persistence layer). Populated at ticket-creation time by
    whatever created the approval (an API route, a test, a future real ingestion path)."""

    def __init__(self) -> None:
        self._by_hash: dict[str, TradeProposal] = {}

    def register(self, proposal: TradeProposal) -> str:
        proposal_hash = compute_proposal_hash(proposal)
        self._by_hash[proposal_hash] = proposal
        return proposal_hash

    def get_by_hash(self, proposal_hash: str) -> Optional[TradeProposal]:
        return self._by_hash.get(proposal_hash)

    def all(self) -> dict[str, TradeProposal]:
        """Read-only snapshot for GET /api/proposals -- a copy, so a caller iterating
        the result can never mutate this registry's internal state."""
        return dict(self._by_hash)


@dataclass(frozen=True)
class AuthorizationExecutionResult:
    """Normalized outer shape for authorize_demo_execution() -- always returned, never
    an exception for an expected/blocked outcome (same convention as ClaimResult /
    ExecutionReport elsewhere in this repository)."""

    approval_id: str
    success: bool
    state: str
    reason_code: Optional[str] = None
    result_reference: Optional[str] = None


def authorize_demo_execution(
    approval_id: str,
    *,
    store: ExecutionApprovalStore,
    proposal_registry: ProposalRegistry,
    execution_handler: Callable[[TradeProposal], ExecutionHandlerResult],
    source: str = SOURCE_WEB,
    actor_id: Optional[str] = None,
    registry_path: Optional[str] = None,
) -> AuthorizationExecutionResult:
    """`actor_id` is audit metadata only (e.g. requester IP for a web call, Telegram
    numeric user ID for a Telegram callback) -- it is journaled alongside the outcome
    but never influences the authorization decision itself, which remains keyed
    entirely on `approval_id`'s own atomic claim state."""
    approval = store.get(approval_id)
    if approval is None:
        return AuthorizationExecutionResult(approval_id, False, "NOT_FOUND", REASON_APPROVAL_NOT_FOUND)

    claim = store.claim(approval_id)
    if not claim.success:
        state = claim.approval.state if claim.approval else "UNKNOWN"
        return AuthorizationExecutionResult(approval_id, False, state, claim.reason_code)
    approval = claim.approval

    proposal = proposal_registry.get_by_hash(approval.proposal_hash)
    if proposal is None:
        store.mark_failed(approval_id, failure_reason=REASON_PROPOSAL_NOT_FOUND)
        return AuthorizationExecutionResult(approval_id, False, "FAILED", REASON_PROPOSAL_NOT_FOUND)

    if not store.verify_integrity(approval, proposal):
        store.mark_failed(approval_id, failure_reason=REASON_PROPOSAL_INTEGRITY_MISMATCH)
        return AuthorizationExecutionResult(approval_id, False, "FAILED", REASON_PROPOSAL_INTEGRITY_MISMATCH)

    demo_check = (
        check_strategy_demo_authorized(proposal.strategy_id, registry_path)
        if registry_path else check_strategy_demo_authorized(proposal.strategy_id)
    )
    if not demo_check.authorized:
        store.mark_failed(approval_id, failure_reason=demo_check.reason_code)
        _journal(approval, proposal, source, actor_id, success=False, reason_code=demo_check.reason_code)
        return AuthorizationExecutionResult(approval_id, False, "FAILED", demo_check.reason_code)

    if approval.environment != ENVIRONMENT_DEMO:
        store.mark_failed(approval_id, failure_reason="NON_DEMO_ENVIRONMENT_REJECTED")
        return AuthorizationExecutionResult(approval_id, False, "FAILED", "NON_DEMO_ENVIRONMENT_REJECTED")

    store.mark_executing(approval_id)
    handler_result = execution_handler(proposal)

    if handler_result.success:
        store.mark_executed(
            approval_id, approved_by_user_id=0, result_reference=handler_result.result_reference,
        )
        _journal(approval, proposal, source, actor_id, success=True, result_reference=handler_result.result_reference)
        return AuthorizationExecutionResult(
            approval_id, True, "EXECUTED", result_reference=handler_result.result_reference,
        )

    store.mark_failed(approval_id, failure_reason=handler_result.detail)
    _journal(approval, proposal, source, actor_id, success=False, reason_code=handler_result.detail)
    return AuthorizationExecutionResult(approval_id, False, "FAILED", handler_result.detail)


def _journal(
    approval, proposal: TradeProposal, source: str, actor_id: Optional[str], *,
    success: bool, reason_code: Optional[str] = None, result_reference: Optional[str] = None,
) -> None:
    """Additive event record via the existing execution.journal (append-only,
    command_id-keyed) -- never overwrites a prior entry. Never includes any secret."""
    try:
        record_event(
            approval.approval_id, "demo_execution_authorized" if success else "demo_execution_blocked",
            approval_id=approval.approval_id, proposal_hash=approval.proposal_hash,
            strategy_id=proposal.strategy_id, symbol=proposal.symbol,
            environment=approval.environment, source=source, actor_id=actor_id, success=success,
            reason_code=reason_code, result_reference=result_reference,
        )
    except OSError:  # noqa: BLE001 -- journaling must never crash the authorization path
        logger.exception("journal write failed for approval_id=%s", approval.approval_id)
