"""Telegram callback integration for AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1 -- Phase C.

Wires notifications.telegram_client + notifications.trade_ticket_formatter to the
Phase B authorization core (authorization.store.ExecutionApprovalStore). This module
is the ONLY place a Telegram callback is translated into an authorization-core call --
callback data is parsed by notifications.telegram_client.parse_callback_query (which
already trusts nothing but callback_query_id/from.id/message.chat.id/data), and this
gateway then does its own user/chat authorization check before touching any approval.

Execution boundary (Phase C, deliberate): `execution_handler` is caller-injected. This
milestone always injects a fake/test handler -- no MT5 order API, no Bybit order API,
and no `execution.coordinator`/`execution.executor` import exists anywhere in this
module. The real ExecutionCoordinator.submit(proposal, user_confirmed=True) wiring is
Phase D/F work, not this one.

`proposal_lookup` is also caller-injected: the gateway NEVER reconstructs a
TradeProposal from Telegram data, only resolves the already-persisted, immutable one
by `approval.setup_id` (spec section 13). Which store that lookup reads from (FX pilot
proposal store, BTC research ledger, etc.) is intentionally out of this module's
knowledge -- that wiring is also deferred.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from execution.adapter import TradeProposal

from .models import (
    REASON_APPROVAL_ALREADY_PROCESSED,
    REASON_APPROVAL_EXPIRED,
    REASON_APPROVAL_NOT_FOUND,
    REASON_PHASE_D1_BROKER_EXECUTION_DISABLED,
    REASON_PROPOSAL_INTEGRITY_MISMATCH,
    REASON_PROPOSAL_NOT_FOUND,
    REASON_UNAUTHORIZED_TELEGRAM_CHAT,
    REASON_UNAUTHORIZED_TELEGRAM_USER,
    STATE_EXECUTED,
    STATE_EXPIRED,
    STATE_REJECTED,
    AuthorizationCheckResult,
    ExecutionApproval,
)
from .store import ExecutionApprovalStore, check_chat_authorized, check_user_authorized
from .strategy_authority import check_strategy_demo_authorized

logger = logging.getLogger("authorization.telegram_gateway")


@dataclass(frozen=True)
class ExecutionHandlerResult:
    """Deterministic outer shape the injected execution handler must return -- never
    an exception for an expected broker outcome, same convention as every other
    result-object type in this repository."""

    success: bool
    result_reference: str
    detail: str


ExecutionHandler = Callable[[TradeProposal, ExecutionApproval], ExecutionHandlerResult]
ProposalLookup = Callable[[str], Optional[TradeProposal]]
StrategyAuthorizationCheck = Callable[[str], AuthorizationCheckResult]


def fake_execution_handler(proposal: TradeProposal, approval: ExecutionApproval) -> ExecutionHandlerResult:
    """Phase C's transport-validation handler -- always "succeeds". Kept only for the
    Phase C test suite; Phase D1 wires phase_d1_broker_disabled_handler instead (see
    below) precisely because this one must never run once a real strategy-sourced
    proposal can reach _handle_execute."""
    return ExecutionHandlerResult(success=True, result_reference=f"FAKE-{approval.approval_id}",
                                  detail="fake execution handler (Phase C -- no broker call)")


def phase_d1_broker_disabled_handler(proposal: TradeProposal, approval: ExecutionApproval) -> ExecutionHandlerResult:
    """Phase D1's execution handler: deterministically fails closed no matter what.

    In the expected D1 path this function is never even called -- the strategy demo
    authorization recheck in _handle_execute already blocks BEFORE any execution
    handler runs, for the current demo_authorized=false contract (strategies/
    registry.yaml). This handler exists as defense-in-depth ONLY: if that registry
    value were ever flipped to true during this milestone (not authorized to happen in
    D1 -- see AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_REAL_PROPOSAL_INTEGRATION
    section 15/27), broker reachability must still be zero, so this handler refuses
    unconditionally rather than assuming the registry recheck is the only gate.
    """
    return ExecutionHandlerResult(success=False, result_reference="",
                                  detail=REASON_PHASE_D1_BROKER_EXECUTION_DISABLED)


class TelegramExecutionGateway:
    def __init__(
        self, *, client, store: ExecutionApprovalStore, proposal_lookup: ProposalLookup,
        execution_handler: ExecutionHandler, allowed_user_ids: List[int], allowed_chat_id: int,
        strategy_authorization_check: StrategyAuthorizationCheck = check_strategy_demo_authorized,
    ):
        self._client = client
        self._store = store
        self._proposal_lookup = proposal_lookup
        self._execution_handler = execution_handler
        self._allowed_user_ids = list(allowed_user_ids)
        self._allowed_chat_id = allowed_chat_id
        # Injectable purely so tests never depend on the real strategies/registry.yaml
        # file; the CLI always wires the real check_strategy_demo_authorized (Phase D1
        # section 13: "The authoritative source must be existing strategy
        # configuration/registry... Do not copy demo_authorized into an independent
        # Telegram config").
        self._strategy_authorization_check = strategy_authorization_check

    # ---------------------------------------------------------------- ticket sending

    def send_ticket(self, proposal: TradeProposal, approval: ExecutionApproval) -> Optional[ExecutionApproval]:
        from notifications.trade_ticket_formatter import build_ticket_keyboard, format_ticket

        text = format_ticket(proposal, approval)
        keyboard = build_ticket_keyboard(approval.approval_id)
        result = self._client.send_message(self._allowed_chat_id, text, reply_markup=keyboard)
        if not result.ok:
            logger.warning("ticket send failed approval_id=%s reason=%s", approval.approval_id, result.description)
            return None
        message_id = result.result.get("message_id") if isinstance(result.result, dict) else None
        updated = self._store.mark_sent_to_telegram(approval.approval_id, chat_id=self._allowed_chat_id,
                                                     message_id=message_id)
        logger.info("ticket sent approval_id=%s setup_id=%s chat_id=%s message_id=%s",
                   approval.approval_id, approval.setup_id, self._allowed_chat_id, message_id)
        return updated

    # -------------------------------------------------------------- callback intake

    def handle_callback(self, parsed) -> str:
        """Returns the terminal reason_code/state this callback resolved to -- always
        a string, never an exception for an expected outcome. Every branch answers the
        callback query exactly once (Telegram requires this within its own timeout)."""
        user_check = check_user_authorized(parsed.user_id, self._allowed_user_ids)
        if not user_check.authorized:
            logger.warning("blocked callback: unauthorized user user_id=%s approval_id=%s",
                           parsed.user_id, parsed.approval_id)
            self._safe_answer(parsed.callback_query_id, "Unauthorized")
            return REASON_UNAUTHORIZED_TELEGRAM_USER

        if parsed.chat_id is None:
            chat_check = check_chat_authorized(-1, self._allowed_chat_id)
        else:
            chat_check = check_chat_authorized(parsed.chat_id, self._allowed_chat_id)
        if not chat_check.authorized:
            logger.warning("blocked callback: unauthorized chat chat_id=%s approval_id=%s",
                           parsed.chat_id, parsed.approval_id)
            self._safe_answer(parsed.callback_query_id, "Unauthorized chat")
            return REASON_UNAUTHORIZED_TELEGRAM_CHAT

        approval = self._store.get(parsed.approval_id)
        if approval is None:
            logger.warning("blocked callback: unknown approval_id=%s", parsed.approval_id)
            self._safe_answer(parsed.callback_query_id, "Unknown ticket")
            return REASON_APPROVAL_NOT_FOUND

        from notifications.telegram_client import ACTION_DETAILS, ACTION_EXECUTE, ACTION_REJECT

        if parsed.action == ACTION_DETAILS:
            return self._handle_details(parsed, approval)
        if parsed.action == ACTION_REJECT:
            return self._handle_reject(parsed, approval)
        if parsed.action == ACTION_EXECUTE:
            return self._handle_execute(parsed, approval)
        # notifications.telegram_client.parse_callback_data already rejects any action
        # outside {x, r, d} before this gateway ever sees it -- unreachable in
        # practice, kept as an explicit fail-closed branch rather than an assumption.
        self._safe_answer(parsed.callback_query_id, "Unsupported action")
        return "UNSUPPORTED_ACTION"

    def _safe_answer(self, callback_query_id: str, text: str) -> None:
        try:
            self._client.answer_callback_query(callback_query_id, text=text)
        except Exception:  # noqa: BLE001 -- answering is best-effort; backend state is authoritative regardless
            logger.warning("answerCallbackQuery failed callback_query_id=%s", callback_query_id)

    # --------------------------------------------------------------- action: details

    def _handle_details(self, parsed, approval: ExecutionApproval) -> str:
        """Read-only: no approval/proposal mutation of any kind (spec section 15/29)."""
        from notifications.trade_ticket_formatter import format_details

        proposal = self._proposal_lookup(approval.setup_id)
        if proposal is None:
            self._safe_answer(parsed.callback_query_id, "Proposal unavailable")
            return REASON_PROPOSAL_NOT_FOUND
        self._safe_answer(parsed.callback_query_id, "Details shown")
        if approval.telegram_chat_id is not None and approval.telegram_message_id is not None:
            self._client.edit_message_text(approval.telegram_chat_id, approval.telegram_message_id,
                                           format_details(proposal, approval),
                                           reply_markup=self._current_keyboard(approval))
        return "DETAILS_SHOWN"

    # ---------------------------------------------------------------- action: reject

    def _handle_reject(self, parsed, approval: ExecutionApproval) -> str:
        from notifications.trade_ticket_formatter import format_rejected

        result = self._store.reject(approval.approval_id)
        final = result.approval or approval
        self._safe_answer(parsed.callback_query_id,
                          "Rejected" if result.success else result.reason_code)
        proposal = self._proposal_lookup(final.setup_id)
        self._finalize_message(proposal, final,
                               text=format_rejected(proposal, final) if proposal else None)
        return result.reason_code

    # --------------------------------------------------------------- action: execute

    def _handle_execute(self, parsed, approval: ExecutionApproval) -> str:
        from notifications.trade_ticket_formatter import format_execution_result

        claim = self._store.claim(approval.approval_id)
        if not claim.success:
            current = claim.approval or approval
            self._safe_answer(parsed.callback_query_id, claim.reason_code)
            self._finalize_if_terminal(current)
            return claim.reason_code

        claimed = claim.approval
        proposal = self._proposal_lookup(claimed.setup_id)
        if proposal is None:
            failed = self._store.mark_failed(claimed.approval_id, failure_reason=REASON_PROPOSAL_NOT_FOUND)
            self._safe_answer(parsed.callback_query_id, REASON_PROPOSAL_NOT_FOUND)
            self._finalize_message(None, failed, text=None)
            return REASON_PROPOSAL_NOT_FOUND

        if not self._store.verify_integrity(claimed, proposal):
            failed = self._store.mark_failed(claimed.approval_id, failure_reason=REASON_PROPOSAL_INTEGRITY_MISMATCH)
            logger.error("PROPOSAL_INTEGRITY_MISMATCH approval_id=%s setup_id=%s", claimed.approval_id,
                        claimed.setup_id)
            self._safe_answer(parsed.callback_query_id, REASON_PROPOSAL_INTEGRITY_MISMATCH)
            self._finalize_message(proposal, failed,
                                   text=format_execution_result(proposal, failed, success=False,
                                                               detail=REASON_PROPOSAL_INTEGRITY_MISMATCH))
            return REASON_PROPOSAL_INTEGRITY_MISMATCH

        # Phase D1: strategy demo-execution authorization is rechecked HERE, at
        # click-time, against the live registry -- never inferred from ticket-creation
        # time state, never cached (spec section 13/14). A block here happens strictly
        # before mark_executing() and before the execution handler is ever invoked --
        # broker calls = 0 for this outcome, same "no execution-handler call" posture as
        # the proposal-not-found/integrity-mismatch branches above.
        from notifications.trade_ticket_formatter import format_blocked_strategy_not_authorized

        strategy_check = self._strategy_authorization_check(proposal.strategy_id)
        if not strategy_check.authorized:
            failed = self._store.mark_failed(claimed.approval_id, failure_reason=strategy_check.reason_code)
            self._safe_answer(parsed.callback_query_id, strategy_check.reason_code)
            self._finalize_message(proposal, failed,
                                   text=format_blocked_strategy_not_authorized(
                                       proposal, failed, reason_code=strategy_check.reason_code))
            return strategy_check.reason_code

        self._store.mark_executing(claimed.approval_id)
        self._safe_answer(parsed.callback_query_id, "Executing...")

        # The ONE call site that ever reaches "execution" in this milestone -- always
        # the caller-injected handler, never a broker import of any kind.
        outcome = self._execution_handler(proposal, claimed)

        if outcome.success:
            final = self._store.mark_executed(claimed.approval_id, approved_by_user_id=parsed.user_id,
                                              result_reference=outcome.result_reference)
        else:
            final = self._store.mark_failed(claimed.approval_id, failure_reason=outcome.detail)

        self._finalize_message(proposal, final,
                               text=format_execution_result(proposal, final, success=outcome.success,
                                                           detail=outcome.detail))
        return final.state

    # ------------------------------------------------------------------- messaging

    def _current_keyboard(self, approval: ExecutionApproval):
        from notifications.trade_ticket_formatter import keyboard_for_state
        return keyboard_for_state(approval, approval.approval_id)

    def _finalize_if_terminal(self, approval: ExecutionApproval) -> None:
        """Used when a claim/reject attempt loses a race -- the approval may already
        be terminal by the time we look; make sure the Telegram message reflects that
        (keyboard removed) even though THIS callback did not cause the transition."""
        if approval.state not in (STATE_EXECUTED, STATE_REJECTED, STATE_EXPIRED):
            return
        proposal = self._proposal_lookup(approval.setup_id)
        self._finalize_message(proposal, approval, text=None)

    def _finalize_message(self, proposal: Optional[TradeProposal], approval: Optional[ExecutionApproval], *,
                          text: Optional[str]) -> None:
        if approval is None or approval.telegram_chat_id is None or approval.telegram_message_id is None:
            return
        keyboard = self._current_keyboard(approval)  # None once terminal -- removes the buttons
        if text is not None:
            self._client.edit_message_text(approval.telegram_chat_id, approval.telegram_message_id, text,
                                           reply_markup=keyboard)
        elif keyboard is None:
            # No new text to show, but the approval just became terminal (e.g. a
            # losing race on claim/reject) -- still strip the executable keyboard so a
            # stale message never looks actionable (spec section 32).
            self._client.edit_message_reply_markup(approval.telegram_chat_id, approval.telegram_message_id,
                                                   reply_markup=None)
