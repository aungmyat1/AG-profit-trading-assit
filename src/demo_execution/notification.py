"""Read-only pre-order Telegram receipt validation; never sends a message or an order."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ticket_store.store import (
    OUTCOME_FIELDS,
    TicketStore,
    TicketStoreError,
    build_outcome,
)

NOTICE_KIND = "S1_PRE_ORDER_TELEGRAM_NOTICE"


def notice_binding(ticket: Mapping[str, Any]) -> str:
    """Bind delivery to this ticket's scope, signal, geometry and eligibility window."""
    keys = ("ticket_id", "strategy_id", "strategy_version", "symbol", "cycle", "setup", "direction",
            "logic_identity", "entry", "stop_loss", "signal_close_utc", "valid_until")
    payload = {key: ticket.get(key) for key in keys}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                    default=str).encode()).hexdigest()


def _utc(value: Any) -> Optional[datetime]:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def check_notification_failure_policy(policy: Any, delivery_evidence: Any = None, *,
                                      ticket: Optional[Mapping[str, Any]] = None,
                                      now_utc: Optional[datetime] = None) -> Optional[str]:
    """Only a sealed, matching, explicitly delivered Telegram API receipt passes."""
    if policy == "PENDING_OWNER":
        return "NOTIFICATION_FAILURE_POLICY_PENDING_OWNER"
    if policy != "BLOCK_NEW_ORDERS":
        return "NOTIFICATION_FAILURE_POLICY_UNRESOLVED"
    if delivery_evidence is None:
        return "PRE_ORDER_NOTIFICATION_MISSING"
    if not isinstance(delivery_evidence, dict) or set(delivery_evidence) != set(OUTCOME_FIELDS):
        return "PRE_ORDER_NOTIFICATION_INVALID"
    try:
        rebuilt = build_outcome(**delivery_evidence)
    except (TicketStoreError, TypeError, ValueError):
        return "PRE_ORDER_NOTIFICATION_INVALID"
    if rebuilt != delivery_evidence or delivery_evidence.get("outcome_kind") != NOTICE_KIND \
            or delivery_evidence.get("source") != "LIVE":
        return "PRE_ORDER_NOTIFICATION_INVALID"
    payload = delivery_evidence.get("payload")
    if not isinstance(payload, Mapping) or not isinstance(ticket, Mapping):
        return "PRE_ORDER_NOTIFICATION_INVALID"
    if delivery_evidence.get("ticket_id") != ticket.get("ticket_id") or payload.get("ticket_binding") != notice_binding(ticket):
        return "PRE_ORDER_NOTIFICATION_TICKET_MISMATCH"
    observed, now = _utc(delivery_evidence.get("recorded_at_utc")), _utc(now_utc)
    created = _utc(ticket.get("created_at") or ticket.get("evaluated_at"))
    expiry = _utc(ticket.get("valid_until"))
    if None in (observed, now, created, expiry) or not created <= observed <= now <= expiry:
        return "PRE_ORDER_NOTIFICATION_TIMESTAMP_INVALID"
    if delivery_evidence.get("result") != "DELIVERED" or payload.get("delivered") is not True:
        return "PRE_ORDER_NOTIFICATION_NOT_DELIVERED"
    message_id = payload.get("message_id")
    if payload.get("channel") != "TELEGRAM" or payload.get("api_ok") is not True or isinstance(message_id, bool) \
            or not isinstance(message_id, int) or message_id <= 0:
        return "PRE_ORDER_NOTIFICATION_INVALID"
    return None


def notification_gate(policy: Any, store: Optional[TicketStore], ticket: Mapping[str, Any],
                      now_utc: datetime) -> Optional[str]:
    """Re-read the latest receipt; never fall back to a previous success after failure."""
    if policy != "BLOCK_NEW_ORDERS":
        return check_notification_failure_policy(policy)
    if store is None:
        return "PRE_ORDER_NOTIFICATION_MISSING"
    try:
        receipts = [row for row in store.outcomes(str(ticket.get("ticket_id") or ""))
                    if row.get("outcome_kind") == NOTICE_KIND]
        if not receipts:
            return "PRE_ORDER_NOTIFICATION_MISSING"
        if any(_utc(row.get("recorded_at_utc")) is None for row in receipts):
            return "PRE_ORDER_NOTIFICATION_INVALID"
        receipt = max(receipts, key=lambda row: _utc(row["recorded_at_utc"]))
        if sum(_utc(row["recorded_at_utc"]) == _utc(receipt["recorded_at_utc"]) for row in receipts) > 1:
            return "PRE_ORDER_NOTIFICATION_INVALID"
    except (OSError, TicketStoreError, TypeError, ValueError):
        return "PRE_ORDER_NOTIFICATION_INVALID"
    return check_notification_failure_policy(policy, receipt, ticket=ticket, now_utc=now_utc)
