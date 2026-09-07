"""Deterministic Telegram trade-ticket formatting.

Reads values off an existing execution.adapter.TradeProposal / authorization.models.
ExecutionApproval pair verbatim -- never recalculates or alters any value (spec
section 8: "Message formatting can improve readability but must not alter the
underlying proposal"). No strategy/risk logic lives here.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from authorization.models import ExecutionApproval, STATE_CREATED, STATE_PENDING, TERMINAL_STATES
from execution.adapter import TradeProposal
from notifications.telegram_client import ACTION_DETAILS, ACTION_EXECUTE, ACTION_REJECT, build_callback_data, inline_keyboard_markup

STATUS_AWAITING_APPROVAL = "AWAITING_OWNER_APPROVAL"


def _fmt(value) -> str:
    return "N/A" if value is None else str(value)


def format_ticket(proposal: TradeProposal, approval: ExecutionApproval) -> str:
    """Fields per spec section 8/10. Non-READY-shaped proposals never reach this
    function in the first place (see telegram_gateway.py's own "only READY/ENTRY_READY
    proposals get a ticket" gate) -- this formatter has no opinion about that, it only
    renders whatever proposal/approval pair it is given."""
    status = STATUS_AWAITING_APPROVAL if approval.state in (STATE_CREATED, STATE_PENDING) else approval.state
    lines: List[str] = [
        "AG TRADE TICKET",
        "",
        "Environment: DEMO",
        f"Venue: {approval.venue}",
        "",
        f"Strategy: {proposal.strategy_id}",
        f"Setup: {proposal.setup_id}",
        f"Symbol: {proposal.symbol}",
        f"Direction: {proposal.direction}",
        "",
        f"Entry: {proposal.entry}",
        f"Stop Loss: {proposal.stop_loss}",
        f"TP1: {proposal.tp1}",
    ]
    if proposal.tp2 is not None:
        lines.append(f"TP2: {proposal.tp2}")
    lines += [
        f"Volume: {proposal.volume}",
        f"Risk: {_fmt(proposal.risk_amount)}" + (f" ({proposal.risk_percent}%)" if proposal.risk_percent else ""),
        "",
        f"Created: {approval.created_at.isoformat()}",
        f"Expires: {approval.expires_at.isoformat()}",
        "",
        f"Status: {status}",
    ]
    return "\n".join(lines)


def build_ticket_keyboard(approval_id: str) -> dict:
    """Required V1 keyboard exactly (spec section 11): one Execute row, one
    Reject+Details row. No order-editing button exists anywhere in this module."""
    return inline_keyboard_markup([
        [{"text": "✅ Execute Demo", "callback_data": build_callback_data(ACTION_EXECUTE, approval_id)}],
        [
            {"text": "❌ Reject", "callback_data": build_callback_data(ACTION_REJECT, approval_id)},
            {"text": "\U0001f50e Details", "callback_data": build_callback_data(ACTION_DETAILS, approval_id)},
        ],
    ])


def format_details(proposal: TradeProposal, approval: ExecutionApproval) -> str:
    """Read-only expanded view (spec section 15) -- same fields as the ticket, no
    additional trust placed in anything Telegram-supplied."""
    return format_ticket(proposal, approval) + f"\n\nProposal ID: {approval.setup_id}\nApproval ID: {approval.approval_id}"


def format_execution_result(proposal: TradeProposal, approval: ExecutionApproval, *, success: bool,
                            detail: str) -> str:
    """Final message text after Execute Demo resolves (spec section 30/31). Never
    claims EXECUTED merely because a network call returned -- callers pass `success`
    already derived from the injected execution handler's own deterministic result,
    never inferred here."""
    header = "✅ DEMO ORDER EXECUTED" if success else "❌ DEMO ORDER NOT EXECUTED"
    lines = [
        header, "", f"Venue: {approval.venue}", f"Setup: {proposal.setup_id}", "",
        f"Result: {approval.state}", f"Detail: {detail}",
    ]
    if not success:
        lines.append("")
        lines.append("No retry has been performed automatically.")
    return "\n".join(lines)


def format_blocked_strategy_not_authorized(proposal: TradeProposal, approval: ExecutionApproval, *,
                                           reason_code: str) -> str:
    """Phase D1 terminal message (spec section 16): the owner's approval was recorded
    (their click IS honored as an authorization decision), but the strategy contract
    itself does not currently permit demo execution -- distinct from a NO_TRADE
    strategy decision, which this message must never claim (strategy_decision stays
    READY; only execution_result differs, see ExecutionApproval.state/failure_reason)."""
    return "\n".join([
        "⛔ DEMO EXECUTION BLOCKED", "",
        f"Strategy:\n{proposal.strategy_id}", "",
        f"Setup:\n{proposal.setup_id}", "",
        f"Reason:\n{reason_code}", "",
        "Your approval was recorded, but the strategy contract currently does not "
        "permit demo execution.", "", "No broker request was made.",
    ])


def format_rejected(proposal: TradeProposal, approval: ExecutionApproval) -> str:
    return "\n".join([
        "❌ PROPOSAL REJECTED", "", f"Venue: {approval.venue}", f"Setup: {proposal.setup_id}",
        "", "Status: REJECTED", "strategy_decision unchanged -- this is an owner execution decision only.",
    ])


def format_expired(proposal: TradeProposal, approval: ExecutionApproval) -> str:
    return "\n".join([
        "⏰ APPROVAL EXPIRED", "", f"Venue: {approval.venue}", f"Setup: {proposal.setup_id}",
        "", "Status: EXPIRED", "This ticket can no longer be executed.",
    ])


def keyboard_for_state(approval: ExecutionApproval, approval_id: str) -> Optional[dict]:
    """Terminal states get no keyboard at all (spec section 16/32: "remove or disable
    the execution keyboard" once terminal) -- a stale Telegram message must never
    still look executable."""
    if approval.state in TERMINAL_STATES:
        return None
    return build_ticket_keyboard(approval_id)
