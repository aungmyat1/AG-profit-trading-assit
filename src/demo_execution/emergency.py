"""Durable DEMO emergency stop: no new orders while engaged.

A latch on the existing append-only TICKET_STORE_V1 (its own pseudo ticket id and outcome kind, so the
claim ledger and the lifecycle trail never see these rows). It is engaged by the reconciliation monitor
on an ORPHAN / MISSING / mismatched position or a send whose outcome stays unknown past its timeout,
and is read by the guard before every order_check and order_send authorization. Engaging never closes,
modifies or cancels anything at the broker. Only the owner clears it (a decision id is required); an
unreadable latch counts as engaged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ticket_store.store import LIVE, TicketStore, TicketStoreError, build_outcome

STOP_TICKET_ID = "DEMO_EMERGENCY_STOP"
STOP_KIND = "DEMO_EMERGENCY_STOP_LATCH"
ENGAGED = "ENGAGED"
CLEARED = "CLEARED"
EMERGENCY_STOP_ENGAGED = "EMERGENCY_STOP_ENGAGED"
EMERGENCY_STOP_UNREADABLE = "EMERGENCY_STOP_UNREADABLE"


@dataclass(frozen=True)
class StopStatus:
    engaged: bool
    reason_code: Optional[str] = None
    engaged_at_utc: Optional[str] = None


def _iso(now_utc: datetime) -> Optional[str]:
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None or now_utc.utcoffset() is None:
        return None
    return now_utc.astimezone(timezone.utc).isoformat()


def status(store: TicketStore) -> StopStatus:
    """The latest latch row decides; no row = not engaged; an unreadable latch = engaged."""
    try:
        rows = [r for r in store.outcomes(STOP_TICKET_ID) if r.get("outcome_kind") == STOP_KIND]
    except (OSError, ValueError, TypeError, KeyError, TicketStoreError):
        return StopStatus(True, EMERGENCY_STOP_UNREADABLE)
    if not rows:
        return StopStatus(False)
    last = rows[-1]
    payload = last.get("payload") if isinstance(last.get("payload"), dict) else {}
    if last.get("result") == CLEARED:
        return StopStatus(False)
    return StopStatus(True, str(payload.get("reason_code") or EMERGENCY_STOP_ENGAGED),
                      last.get("recorded_at_utc"))


def _write(store: TicketStore, result: str, payload: Mapping[str, Any], now_utc: datetime) -> bool:
    recorded_at = _iso(now_utc)
    if recorded_at is None:
        return False
    record = build_outcome(ticket_id=STOP_TICKET_ID, source=LIVE, outcome_kind=STOP_KIND,
                           recorded_at_utc=recorded_at, result=result, payload=dict(payload),
                           provenance={"writer": f"demo_execution.emergency.{result.lower()}"})
    try:
        store.append_outcome(record)
    except (OSError, ValueError, TicketStoreError):
        return False
    return True


def engage(store: TicketStore, *, reason_code: str, now_utc: datetime,
           evidence: Optional[Mapping[str, Any]] = None) -> bool:
    """Engage (or re-assert) the stop. Returns False only when the row could not be written."""
    if not isinstance(reason_code, str) or not reason_code.strip():
        reason_code = EMERGENCY_STOP_ENGAGED
    return _write(store, ENGAGED, {"reason_code": reason_code.strip(), "evidence": dict(evidence or {}),
                                   "broker_action": "NONE"}, now_utc)


def clear(store: TicketStore, *, owner_decision_id: str, now_utc: datetime) -> bool:
    """Owner-only release. Never called by the monitor or the guard."""
    if not isinstance(owner_decision_id, str) or not owner_decision_id.strip():
        return False
    return _write(store, CLEARED, {"owner_decision_id": owner_decision_id.strip()}, now_utc)
