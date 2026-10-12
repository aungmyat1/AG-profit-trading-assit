"""Append-only execution lifecycle evidence for the guarded C14/S1 DEMO boundary.

Every guarded state transition writes exactly one TICKET_STORE_V1 outcome row for the ticket:

    AUTHORIZED -> CHECKED -> SENT -> BROKER_ACK -> POSITION_TRACKED -> CLOSED -> RECONCILED

Each row carries the ticket id, the authority id that was re-validated for that transition, the
single-use authorization id where the step authorizes or completes a broker-facing call, the
broker order/deal/position ids where the state has them, and aware UTC timestamps. Transitions
are strictly ordered: a state may be recorded only directly after its predecessor, never twice,
and never out of order. HALT may be recorded from any non-terminal state; only RECONCILED may
follow a HALT, and nothing may follow RECONCILED. An unknown outcome is therefore always
HALT + reconcile, never a resubmission.

These rows are audit evidence, not the idempotency claim: the restart-safe send claim remains
``demo_execution.idempotency.ExecutionLedger`` (DEMO_EXECUTION_SENDING / _UNCERTAIN /
_RECONCILED). The kind below deliberately does not share that prefix, so the claim ledger's
unknown-state detector keeps seeing only its own rows.

This module never calls a broker and never submits, retries or cancels anything.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ticket_store.store import (
    LIVE,
    OUTCOME_FIELDS,
    TicketStore,
    TicketStoreError,
    build_outcome,
)

AUTHORIZED = "AUTHORIZED"
CHECKED = "CHECKED"
SENT = "SENT"
BROKER_ACK = "BROKER_ACK"
POSITION_TRACKED = "POSITION_TRACKED"
CLOSED = "CLOSED"
RECONCILED = "RECONCILED"
HALT = "HALT"

LIFECYCLE_STATES = (AUTHORIZED, CHECKED, SENT, BROKER_ACK, POSITION_TRACKED, CLOSED, RECONCILED)
LIFECYCLE_KIND = "DEMO_LIFECYCLE_EVIDENCE"

# Strictly linear. HALT is reachable from every non-terminal state; RECONCILED is the only
# state reachable after a HALT, and nothing is reachable after RECONCILED.
_ALLOWED_NEXT: dict[str, tuple[str, ...]] = {
    AUTHORIZED: (CHECKED, HALT),
    CHECKED: (SENT, HALT),
    SENT: (BROKER_ACK, HALT),
    BROKER_ACK: (POSITION_TRACKED, HALT),
    POSITION_TRACKED: (CLOSED, HALT),
    CLOSED: (RECONCILED, HALT),
    HALT: (RECONCILED,),
    RECONCILED: (),
}
# Broker identifiers a state must carry. A step that has no broker id yet carries none.
_REQUIRED_BROKER_IDS: dict[str, tuple[str, ...]] = {
    BROKER_ACK: ("broker_order_id",),
    POSITION_TRACKED: ("broker_position_id",),
    CLOSED: ("broker_deal_id",),
}
# Steps that authorize or complete a broker-facing call are bound to a single-use id.
_REQUIRES_AUTHORIZATION_ID = frozenset({AUTHORIZED, CHECKED, SENT, BROKER_ACK})

_PAYLOAD_FIELDS = (
    "ticket_id", "state", "authority_id", "authorization_id", "transitioned_at_utc", "prior_state",
    "broker_order_id", "broker_deal_id", "broker_position_id", "terminal_result", "reason_code",
    "evidence",
)

TICKET_ID_MISSING = "TICKET_ID_MISSING"
LIFECYCLE_STATE_UNKNOWN = "LIFECYCLE_STATE_UNKNOWN"
LIFECYCLE_TIMESTAMP_INVALID = "LIFECYCLE_TIMESTAMP_INVALID"
LIFECYCLE_TIMESTAMP_OUT_OF_ORDER = "LIFECYCLE_TIMESTAMP_OUT_OF_ORDER"
LIFECYCLE_AUTHORITY_MISSING = "LIFECYCLE_AUTHORITY_MISSING"
LIFECYCLE_AUTHORIZATION_ID_MISSING = "LIFECYCLE_AUTHORIZATION_ID_MISSING"
LIFECYCLE_BROKER_EVIDENCE_MISSING = "LIFECYCLE_BROKER_EVIDENCE_MISSING"
LIFECYCLE_ORDER_INVALID = "LIFECYCLE_ORDER_INVALID"
LIFECYCLE_ALREADY_RECONCILED = "LIFECYCLE_ALREADY_RECONCILED"
LIFECYCLE_ALREADY_RECORDED = "LIFECYCLE_ALREADY_RECORDED"
LIFECYCLE_HALT_REASON_MISSING = "LIFECYCLE_HALT_REASON_MISSING"
LIFECYCLE_EVIDENCE_UNREADABLE = "LIFECYCLE_EVIDENCE_UNREADABLE"
LIFECYCLE_EVIDENCE_CONFLICT = "LIFECYCLE_EVIDENCE_CONFLICT"
LIFECYCLE_EVIDENCE_INVALID = "LIFECYCLE_EVIDENCE_INVALID"
LIFECYCLE_WRITE_FAILED = "LIFECYCLE_WRITE_FAILED"
HALT_UNKNOWN_RESULT = "HALT_UNKNOWN_RESULT"
RECONCILIATION_EVIDENCE_INVALID = "RECONCILIATION_EVIDENCE_INVALID"

_LOCK_GUARD = threading.Lock()
_TICKET_LOCKS: dict[tuple[str, str], threading.Lock] = {}


@dataclass(frozen=True)
class LifecycleState:
    """One recorded transition, read back from the append-only store."""

    state: str
    recorded_at_utc: datetime
    authority_id: str
    authorization_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    broker_deal_id: Optional[str] = None
    broker_position_id: Optional[str] = None
    terminal_result: Optional[str] = None
    reason_code: Optional[str] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LifecycleTrail:
    """The ordered trail for one ticket, or the reason it could not be trusted."""

    states: tuple[LifecycleState, ...]
    reason_code: Optional[str] = None

    @property
    def current(self) -> Optional[str]:
        return self.states[-1].state if self.states else None

    def state_row(self, state: str) -> Optional[LifecycleState]:
        for row in reversed(self.states):
            if row.state == state:
                return row
        return None


@dataclass(frozen=True)
class TransitionResult:
    recorded: bool
    reason_code: str
    state: Optional[str] = None
    prior_state: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)


def _ticket_lock(store: TicketStore, ticket_id: str) -> threading.Lock:
    key = (str(store.root), ticket_id)
    with _LOCK_GUARD:
        return _TICKET_LOCKS.setdefault(key, threading.Lock())


def _as_utc(value: Any) -> Optional[datetime]:
    """Aware UTC from a datetime or an ISO-8601 string (the store persists strings)."""
    if isinstance(value, str) and value.strip():
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _seal_is_intact(record: Any) -> bool:
    """True only when the row is exactly a TICKET_STORE_V1 outcome this repo would have built."""
    if not isinstance(record, dict) or set(record) != set(OUTCOME_FIELDS):
        return False
    if record.get("outcome_kind") != LIFECYCLE_KIND:
        return False
    try:
        rebuilt = build_outcome(**{key: record[key] for key in OUTCOME_FIELDS})
    except (TicketStoreError, TypeError, ValueError):
        return False
    return rebuilt == record


def _row_from(record: Mapping[str, Any]) -> Optional[LifecycleState]:
    payload = record.get("payload")
    if not isinstance(payload, dict) or set(payload) != set(_PAYLOAD_FIELDS):
        return None
    recorded_at = _as_utc(record.get("recorded_at_utc"))
    if recorded_at is None or not _non_empty(payload.get("authority_id")):
        return None
    if payload.get("state") not in LIFECYCLE_STATES and payload.get("state") != HALT:
        return None
    if payload.get("transitioned_at_utc") != record.get("recorded_at_utc"):
        return None
    evidence = payload.get("evidence")
    return LifecycleState(
        state=str(payload["state"]),
        recorded_at_utc=recorded_at,
        authority_id=str(payload["authority_id"]),
        authorization_id=payload.get("authorization_id"),
        broker_order_id=payload.get("broker_order_id"),
        broker_deal_id=payload.get("broker_deal_id"),
        broker_position_id=payload.get("broker_position_id"),
        terminal_result=payload.get("terminal_result"),
        reason_code=payload.get("reason_code"),
        evidence=evidence if isinstance(evidence, dict) else {},
    )


class ExecutionLifecycle:
    """Ordered lifecycle evidence for one ticket attempt, over the existing TicketStore."""

    def __init__(self, store: TicketStore) -> None:
        self.store = store

    def trail(self, ticket_id: str) -> LifecycleTrail:
        """Read the ordered trail. Any malformed, unsealed or contradictory row fails closed."""
        if not _non_empty(ticket_id):
            return LifecycleTrail((), TICKET_ID_MISSING)
        try:
            rows = self.store.outcomes(ticket_id)
        except (OSError, ValueError, TypeError, KeyError, TicketStoreError):
            return LifecycleTrail((), LIFECYCLE_EVIDENCE_UNREADABLE)
        evidence_rows = [row for row in rows
                         if isinstance(row, dict) and row.get("outcome_kind") == LIFECYCLE_KIND]
        states: list[LifecycleState] = []
        for row in evidence_rows:
            if not _seal_is_intact(row):
                return LifecycleTrail((), LIFECYCLE_EVIDENCE_CONFLICT)
            parsed = _row_from(row)
            if parsed is None:
                return LifecycleTrail((), LIFECYCLE_EVIDENCE_CONFLICT)
            states.append(parsed)
        seen: set[str] = set()
        previous: Optional[LifecycleState] = None
        for row in states:
            # Store order is append order; a timestamp that goes backwards means the trail was
            # written by a clock that is not monotonic, so it cannot be trusted as an ordering.
            if previous is not None and row.recorded_at_utc < previous.recorded_at_utc:
                return LifecycleTrail((), LIFECYCLE_TIMESTAMP_OUT_OF_ORDER)
            if row.state in seen:
                return LifecycleTrail((), LIFECYCLE_EVIDENCE_CONFLICT)
            seen.add(row.state)
            expected = (AUTHORIZED,) if previous is None else _ALLOWED_NEXT[previous.state]
            if row.state not in expected:
                return LifecycleTrail((), LIFECYCLE_ORDER_INVALID)
            previous = row
        return LifecycleTrail(tuple(states))

    def append(
        self,
        ticket_id: str,
        state: str,
        *,
        now_utc: datetime,
        authority_id: str,
        authorization_id: Optional[str] = None,
        broker_order_id: Optional[str] = None,
        broker_deal_id: Optional[str] = None,
        broker_position_id: Optional[str] = None,
        terminal_result: Optional[str] = None,
        reason_code: Optional[str] = None,
        evidence: Optional[Mapping[str, Any]] = None,
    ) -> TransitionResult:
        """Append one transition. Refuses anything that is not the immediate next state."""
        if not _non_empty(ticket_id):
            return TransitionResult(False, TICKET_ID_MISSING)
        if state not in LIFECYCLE_STATES and state != HALT:
            return TransitionResult(False, LIFECYCLE_STATE_UNKNOWN)
        recorded_at = _as_utc(now_utc)
        if recorded_at is None:
            return TransitionResult(False, LIFECYCLE_TIMESTAMP_INVALID)
        if not _non_empty(authority_id):
            return TransitionResult(False, LIFECYCLE_AUTHORITY_MISSING)
        if state in _REQUIRES_AUTHORIZATION_ID and not _non_empty(authorization_id):
            return TransitionResult(False, LIFECYCLE_AUTHORIZATION_ID_MISSING)
        if state == HALT and not _non_empty(reason_code):
            return TransitionResult(False, LIFECYCLE_HALT_REASON_MISSING)
        if state == RECONCILED and (not _non_empty(terminal_result)
                                    or str(terminal_result).upper() == "UNKNOWN"):
            return TransitionResult(False, RECONCILIATION_EVIDENCE_INVALID)
        for identifier in (broker_order_id, broker_deal_id, broker_position_id, terminal_result,
                           reason_code, authorization_id):
            if identifier is not None and not _non_empty(identifier):
                return TransitionResult(False, LIFECYCLE_EVIDENCE_INVALID)
        if evidence is not None and not isinstance(evidence, Mapping):
            return TransitionResult(False, LIFECYCLE_EVIDENCE_INVALID)
        for key in _REQUIRED_BROKER_IDS.get(state, ()):
            value = {"broker_order_id": broker_order_id, "broker_deal_id": broker_deal_id,
                     "broker_position_id": broker_position_id}[key]
            if not _non_empty(value):
                return TransitionResult(False, LIFECYCLE_BROKER_EVIDENCE_MISSING, state,
                                        {"missing_broker_id": key})

        with _ticket_lock(self.store, ticket_id):
            trail = self.trail(ticket_id)
            if trail.reason_code is not None:
                return TransitionResult(False, trail.reason_code, state)
            prior = trail.current
            if prior == RECONCILED:
                return TransitionResult(False, LIFECYCLE_ALREADY_RECONCILED, state, prior)
            if prior == HALT and state != RECONCILED:
                return TransitionResult(False, HALT_UNKNOWN_RESULT, state, prior)
            allowed = (AUTHORIZED,) if prior is None else _ALLOWED_NEXT[prior]
            if state not in allowed:
                return TransitionResult(False, LIFECYCLE_ORDER_INVALID, state, prior)
            if trail.states and recorded_at < trail.states[-1].recorded_at_utc:
                return TransitionResult(False, LIFECYCLE_TIMESTAMP_OUT_OF_ORDER, state, prior)
            if state == RECONCILED and trail.state_row(BROKER_ACK) is not None \
                    and not _non_empty(broker_order_id):
                return TransitionResult(False, LIFECYCLE_BROKER_EVIDENCE_MISSING, state, prior,
                                        {"missing_broker_id": "broker_order_id"})

            payload = {
                "ticket_id": ticket_id,
                "state": state,
                "authority_id": authority_id,
                "authorization_id": authorization_id,
                "transitioned_at_utc": recorded_at.isoformat(),
                "prior_state": prior,
                "broker_order_id": broker_order_id,
                "broker_deal_id": broker_deal_id,
                "broker_position_id": broker_position_id,
                "terminal_result": terminal_result,
                "reason_code": reason_code,
                "evidence": dict(evidence or {}),
            }
            record = build_outcome(
                ticket_id=ticket_id,
                source=LIVE,
                outcome_kind=LIFECYCLE_KIND,
                recorded_at_utc=recorded_at.isoformat(),
                result=state,
                payload=payload,
                provenance={"writer": "demo_execution.lifecycle.ExecutionLifecycle.append"},
            )
            try:
                wrote = self.store.append_outcome(record)
            except (OSError, ValueError, TicketStoreError):
                return TransitionResult(False, LIFECYCLE_WRITE_FAILED, state, prior)
            if not wrote:
                return TransitionResult(False, LIFECYCLE_ALREADY_RECORDED, state, prior)
        return TransitionResult(True, "LIFECYCLE_RECORDED", state, prior,
                                {"outcome_id": record["outcome_id"]})
