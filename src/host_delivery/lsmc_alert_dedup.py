"""Persistent delivery deduplication for Large-SMC OPPORTUNITY confirmations.

WatchTracker transitions remain unchanged.  This layer suppresses duplicate notifications for
one strategy/version/symbol/direction/POI/CHoCH confirmation, even if the tracker re-enters an
OPPORTUNITY after STALE or a sibling sweep changes its reference parameters.

A durable PENDING claim is written before the transport call.  If the process dies during the
request, the next run upgrades that claim to DELIVERY_UNCERTAIN and never blindly retries it.
This uses the host runner's existing single-instance lock; it never holds a TICKET_STORE or other
main journal transaction across network I/O.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, Optional

from runtime_state.store import JsonKeyValueStore

UTC = dt.timezone.utc
PENDING = "PENDING"
SENT = "SENT"
DELIVERY_UNCERTAIN = "DELIVERY_UNCERTAIN"
RETRYABLE_STATES = frozenset({"NOT_SENT_POLICY", "BLOCKED", "FAILED", "DELIVERY_FAILED", "RETRYABLE_REJECTED", "ERROR"})
DUPLICATE_SENT = "SUPPRESSED_DUPLICATE_CONFIRMATION"
DUPLICATE_UNCERTAIN = "SUPPRESSED_UNCERTAIN_CONFIRMATION"


def _now() -> str:
    return dt.datetime.now(UTC).isoformat()


def confirmation_key(event: Dict[str, Any]) -> Optional[str]:
    """Identity of the confirmed setup behind an OPPORTUNITY event; None when incomplete."""
    opportunity = (event.get("payload") or {}).get("opportunity") or {}
    parts = (event.get("strategy_id"), event.get("strategy_version"), event.get("symbol"),
             opportunity.get("direction"), opportunity.get("poi_id"), opportunity.get("choch_time"))
    if not all(value is not None and str(value) for value in parts):
        return None
    return "|".join(str(value) for value in parts)


class AlertLedger:
    """Small durable confirmation-state store. PENDING is recovered conservatively as uncertain."""

    def __init__(self, path: str):
        self.store = JsonKeyValueStore(path)

    def claim(self, key: str, record: Dict[str, Any]) -> str:
        previous = self.store.get(key)
        if previous is not None and not isinstance(previous, dict):
            raise ValueError("invalid alert-ledger record")
        state = previous.get("state") if isinstance(previous, dict) else None
        if state == SENT:
            return DUPLICATE_SENT
        if state == DELIVERY_UNCERTAIN:
            return DUPLICATE_UNCERTAIN
        if state == PENDING:
            self.store.put(key, {**previous, "state": DELIVERY_UNCERTAIN,
                                 "recovered_at_utc": _now(), "recovery_reason": "PENDING_AFTER_RESTART"})
            return DELIVERY_UNCERTAIN
        if previous is not None and state not in RETRYABLE_STATES:
            raise ValueError("unknown alert-ledger state")
        # Explicit policy/recipient rejection and known HTTP failures are eligible for a later
        # owner-authorized run. The previous state remains in delivery_status JSONL diagnostics.
        self.store.put(key, {**record, "state": PENDING, "claimed_at_utc": _now()})
        return "CLAIMED"

    def finish(self, key: str, record: Dict[str, Any], status: str) -> None:
        if status == SENT:
            state = SENT
        elif status == DELIVERY_UNCERTAIN:
            state = DELIVERY_UNCERTAIN
        else:
            state = status
        self.store.put(key, {**record, "state": state, "completed_at_utc": _now()})

    def list_uncertain(self):
        """Recover crash-left claims and return uncertainty without exposing message data."""
        rows = []
        for key, value in self.store.all().items():
            if isinstance(value, dict) and value.get("state") == PENDING:
                value = {**value, "state": DELIVERY_UNCERTAIN, "recovered_at_utc": _now(),
                         "recovery_reason": "PENDING_AFTER_RESTART"}
                self.store.put(key, value)
            if isinstance(value, dict) and value.get("state") == DELIVERY_UNCERTAIN:
                rows.append({"identity": key, "state": DELIVERY_UNCERTAIN,
                             "reference_id": value.get("reference_id"),
                             "transition_id": value.get("transition_id")})
        return sorted(rows, key=lambda row: row["identity"])


def deliver_once(event: Dict[str, Any], ledger: Optional[AlertLedger], send: Callable[[], str]) -> str:
    """Deliver one OPPORTUNITY unless it is sent, ambiguous, unidentifiable, or unjournaled.

    Non-OPPORTUNITY transitions and `ledger=None` retain the legacy caller behavior. For an
    OPPORTUNITY with a ledger, identity and durable claim are mandatory before invoking `send`.
    """
    if ledger is None or event.get("to_state") != "OPPORTUNITY":
        try:
            return send()
        except Exception:  # noqa: BLE001 -- unknown transport result is never retried blindly
            return DELIVERY_UNCERTAIN
    key = confirmation_key(event)
    if key is None:
        return "IDENTITY_UNAVAILABLE"
    record = {"reference_id": event.get("reference_id"),
              "transition_id": event.get("transition_id"),
              "evaluated_at": event.get("evaluated_at")}
    try:
        claim = ledger.claim(key, record)
    except Exception:  # noqa: BLE001 -- a failed durable claim must prevent untracked delivery
        return "LEDGER_UNAVAILABLE"
    if claim != "CLAIMED":
        return claim
    try:
        status = send()
    except Exception:  # noqa: BLE001 -- unknown result is ambiguous
        status = DELIVERY_UNCERTAIN
    try:
        ledger.finish(key, record, status)
    except Exception:  # noqa: BLE001 -- the surviving PENDING state recovers as uncertain
        return DELIVERY_UNCERTAIN if status in (SENT, DELIVERY_UNCERTAIN) else "LEDGER_UNAVAILABLE"
    return status
