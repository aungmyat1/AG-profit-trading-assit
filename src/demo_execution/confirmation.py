"""Single-use, ticket-bound owner confirmations stored in the append-only TICKET_STORE.

This module does not prompt for or infer owner intent. A caller may append a confirmation
only after an explicit owner action; admission consumes that record once. Confirmation and
consumption events are ordinary TICKET_STORE_V1 outcome rows, not a second storage engine.
"""
from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ticket_store.store import (
    LIVE,
    OUTCOME_FIELDS,
    TicketStore,
    TicketStoreError,
    build_outcome,
)

OWNER_CONFIRMATION_KIND = "DEMO_OWNER_ORDER_CONFIRM"
OWNER_CONFIRMATION_USED_KIND = "DEMO_OWNER_ORDER_CONFIRM_USED"


@dataclass(frozen=True)
class OwnerConfirmationCheck:
    allowed: bool
    reason_codes: tuple[str, ...] = ()
    confirmation_id: Optional[str] = None
    status: str = ""


_LOCK_GUARD = threading.Lock()
_STORE_LOCKS: dict[str, threading.RLock] = {}


def _store_lock(store: TicketStore) -> threading.RLock:
    key = os.path.abspath(store.root)
    with _LOCK_GUARD:
        return _STORE_LOCKS.setdefault(key, threading.RLock())


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _ticket_binding(ticket: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Return the S1 identity tuple and bind both branch representations when present."""
    ticket_id = ticket.get("ticket_id")
    strategy_id = ticket.get("strategy_id")
    raw_version = ticket.get("strategy_version")
    symbol = ticket.get("symbol")
    session = ticket.get("cycle", ticket.get("session"))
    setup = ticket.get("setup")
    branch = setup
    if branch is None:
        branch = str(ticket.get("branch") or "").split(":", 1)[0]
    direction = ticket.get("direction")
    version = str(raw_version) if raw_version is not None else ""
    values = (ticket_id, strategy_id, version, symbol, session, branch, direction)
    if not all(isinstance(value, str) and value.strip() for value in values):
        return None
    raw_branch = ticket.get("branch")
    if (setup is not None and not isinstance(setup, str)) or (
        raw_branch is not None and not isinstance(raw_branch, str)
    ):
        return None
    return {
        "ticket_id": ticket_id,
        "strategy_id": strategy_id,
        "strategy_version": version,
        "symbol": symbol,
        "session": session,
        "branch": branch,
        "direction": direction,
        "ticket_branch": raw_branch,
        "ticket_setup": setup,
    }


def _ticket_window(ticket: Mapping[str, Any]) -> tuple[Optional[datetime], Optional[datetime]]:
    creation_times: list[datetime] = []
    for key in ("created_at", "evaluated_at"):
        if key in ticket and ticket[key] is not None:
            parsed = _as_utc(ticket[key])
            if parsed is None:
                return None, None
            creation_times.append(parsed)
    if not creation_times:
        return None, None

    validity_key = "valid_until" if "valid_until" in ticket else "valid_until_utc"
    valid_until = _as_utc(ticket.get(validity_key))
    return max(creation_times), valid_until


def _failure(status: str, *reasons: str) -> OwnerConfirmationCheck:
    ordered = tuple(dict.fromkeys(("OWNER_CONFIRM_REQUIRED", *reasons)))
    return OwnerConfirmationCheck(False, ordered, status=status)


def _valid_outcome(record: Any, outcome_kind: str) -> bool:
    if not isinstance(record, dict) or set(record) != set(OUTCOME_FIELDS):
        return False
    if record.get("outcome_kind") != outcome_kind:
        return False
    try:
        rebuilt = build_outcome(**{key: record[key] for key in OUTCOME_FIELDS})
    except (TicketStoreError, TypeError, ValueError):
        return False
    return rebuilt == record


def _valid_confirmation_record(record: Any) -> bool:
    if not _valid_outcome(record, OWNER_CONFIRMATION_KIND):
        return False
    payload = record.get("payload")
    return (
        isinstance(payload, dict)
        and payload.get("decision") == "CONFIRM"
        and isinstance(payload.get("confirm_id"), str)
        and bool(payload["confirm_id"].strip())
    )


def append_owner_confirmation(
    store: TicketStore,
    ticket: Mapping[str, Any],
    *,
    confirmed_at_utc: datetime,
    confirm_id: Optional[str] = None,
) -> str:
    """Append an explicit owner confirmation for this exact ticket identity and window.

    The host/UI is responsible for calling this only after a fresh owner confirmation. This
    function validates and stores the binding; it cannot create owner intent by itself.
    """
    if not isinstance(ticket, Mapping):
        raise ValueError("owner confirmation requires a ticket mapping")
    binding = _ticket_binding(ticket)
    if binding is None:
        raise ValueError("ticket identity is incomplete for owner confirmation")
    created_at, valid_until = _ticket_window(ticket)
    confirmed_at = _as_utc(confirmed_at_utc)
    if created_at is None or valid_until is None or valid_until <= created_at:
        raise ValueError("ticket creation/validity timestamps are missing or invalid")
    if confirmed_at is None or not (created_at < confirmed_at < valid_until):
        raise ValueError("owner confirmation must be after ticket creation and before ticket expiry")
    if confirm_id is None:
        confirm_id = uuid.uuid4().hex
    elif not isinstance(confirm_id, str) or not confirm_id.strip():
        raise ValueError("confirm_id must be a non-empty string")

    record = build_outcome(
        ticket_id=binding["ticket_id"],
        source=LIVE,
        outcome_kind=OWNER_CONFIRMATION_KIND,
        recorded_at_utc=confirmed_at.isoformat(),
        result="CONFIRMED",
        payload={
            **binding,
            "ticket_created_at_utc": created_at.isoformat(),
            "ticket_valid_until_utc": valid_until.isoformat(),
            "confirm_id": confirm_id,
            "decision": "CONFIRM",
        },
        provenance={"writer": "demo_execution.confirmation.append_owner_confirmation"},
    )
    with _store_lock(store):
        store.append_outcome(record)
    return confirm_id


def check_and_consume_owner_confirmation(
    store: Optional[TicketStore],
    ticket: Mapping[str, Any],
    *,
    now_utc: datetime,
    consume: bool = True,
) -> OwnerConfirmationCheck:
    """Validate a bound confirmation and append a one-time consumption marker.

    TICKET_STORE_V1 has a single-writer-per-root contract. This function additionally
    serializes check-and-append operations across threads in this process. A malformed,
    missing, expired, mismatched, future, or already consumed record always fails closed.
    """
    if not isinstance(ticket, Mapping):
        return _failure("INVALID_TICKET", "OWNER_CONFIRM_TICKET_INVALID")
    binding = _ticket_binding(ticket)
    if binding is None:
        return _failure("INVALID_BINDING", "OWNER_CONFIRM_BINDING_INVALID")

    created_at, valid_until = _ticket_window(ticket)
    now = _as_utc(now_utc)
    if created_at is None or valid_until is None or valid_until <= created_at:
        return _failure("INVALID_WINDOW", "OWNER_CONFIRM_TICKET_VALIDITY_INVALID")
    if now is None:
        return _failure("INVALID_NOW", "OWNER_CONFIRM_TIMESTAMP_INVALID")
    if now >= valid_until:
        return _failure("TICKET_EXPIRED", "TICKET_EXPIRED")
    if store is None:
        return _failure("STORE_UNAVAILABLE", "OWNER_CONFIRM_STORE_UNAVAILABLE")

    with _store_lock(store):
        try:
            outcomes = store.outcomes()
        except (OSError, ValueError, TypeError, KeyError, TicketStoreError):
            return _failure("STORE_UNREADABLE", "OWNER_CONFIRM_STORE_UNAVAILABLE")

        if any(not isinstance(row, dict) for row in outcomes):
            return _failure("STORE_UNREADABLE", "OWNER_CONFIRM_STORE_UNAVAILABLE")
        confirmation_rows = [row for row in outcomes if row.get("outcome_kind") == OWNER_CONFIRMATION_KIND]
        used_rows = [row for row in outcomes if row.get("outcome_kind") == OWNER_CONFIRMATION_USED_KIND]
        eligible: list[tuple[datetime, str, dict[str, Any]]] = []
        wrong_ticket = False
        binding_mismatch = False
        invalid_record = False
        precedes_ticket = False
        outside_window = False
        future_record = False

        tuple_keys = (
            "strategy_id", "strategy_version", "symbol", "session", "branch", "direction",
            "ticket_branch", "ticket_setup",
        )
        for row in confirmation_rows:
            payload = row.get("payload") if isinstance(row, dict) else None
            if not isinstance(payload, dict):
                if isinstance(row, dict) and row.get("ticket_id") == binding["ticket_id"]:
                    invalid_record = True
                continue
            matches_order_tuple = all(payload.get(key) == binding[key] for key in tuple_keys)
            if row.get("ticket_id") != binding["ticket_id"]:
                if matches_order_tuple:
                    wrong_ticket = True
                continue
            if not _valid_confirmation_record(row):
                invalid_record = True
                continue
            if payload.get("ticket_id") != binding["ticket_id"]:
                binding_mismatch = True
                continue
            if not all(payload.get(key) == value for key, value in binding.items()):
                binding_mismatch = True
                continue
            if (
                _as_utc(payload.get("ticket_created_at_utc")) != created_at
                or _as_utc(payload.get("ticket_valid_until_utc")) != valid_until
            ):
                binding_mismatch = True
                continue

            recorded_at = _as_utc(row.get("recorded_at_utc"))
            if recorded_at is None:
                invalid_record = True
                continue
            if recorded_at <= created_at:
                precedes_ticket = True
                continue
            if recorded_at >= valid_until:
                outside_window = True
                continue
            if recorded_at > now:
                future_record = True
                continue
            confirm_id = payload.get("confirm_id")
            eligible.append((recorded_at, confirm_id, row))

        if not eligible:
            diagnostics: list[str] = []
            if wrong_ticket:
                diagnostics.append("OWNER_CONFIRM_TICKET_MISMATCH")
            if binding_mismatch:
                diagnostics.append("OWNER_CONFIRM_BINDING_MISMATCH")
            if precedes_ticket:
                diagnostics.append("OWNER_CONFIRM_PRECEDES_TICKET")
            if outside_window:
                diagnostics.append("OWNER_CONFIRM_OUTSIDE_VALIDITY_WINDOW")
            if future_record:
                diagnostics.append("OWNER_CONFIRM_TIMESTAMP_IN_FUTURE")
            if invalid_record:
                diagnostics.append("OWNER_CONFIRM_RECORD_INVALID")
            return _failure("MISSING_OR_INVALID", *diagnostics)

        id_counts: dict[str, int] = {}
        for row in confirmation_rows:
            payload = row.get("payload") if isinstance(row, dict) else None
            confirm_id = payload.get("confirm_id") if isinstance(payload, dict) else None
            if isinstance(confirm_id, str):
                id_counts[confirm_id] = id_counts.get(confirm_id, 0) + 1
        used_ids = {
            payload.get("confirm_id")
            for row in used_rows
            if isinstance((payload := row.get("payload")), dict)
            and isinstance(payload.get("confirm_id"), str)
        }
        unconsumed = [row for row in eligible
                      if id_counts.get(row[1], 0) == 1 and row[1] not in used_ids]
        if not unconsumed:
            return _failure("REUSED", "OWNER_CONFIRM_REUSED")

        recorded_at, confirm_id, confirmation = max(unconsumed, key=lambda item: item[0])
        if not consume:
            return OwnerConfirmationCheck(True, confirmation_id=confirm_id, status="MATCHED")

        used_record = build_outcome(
            ticket_id=binding["ticket_id"],
            source=LIVE,
            outcome_kind=OWNER_CONFIRMATION_USED_KIND,
            recorded_at_utc=now.isoformat(),
            result="CONSUMED",
            payload={
                "confirm_id": confirm_id,
                "confirmation_outcome_id": confirmation.get("outcome_id"),
                "ticket_id": binding["ticket_id"],
                "confirmed_at_utc": recorded_at.isoformat(),
            },
            provenance={"writer": "demo_execution.confirmation.check_and_consume_owner_confirmation"},
        )
        try:
            appended = store.append_outcome(used_record)
        except (OSError, ValueError, TicketStoreError):
            return _failure("STORE_WRITE_FAILED", "OWNER_CONFIRM_STORE_WRITE_FAILED")
        if not appended:
            return _failure("REUSED", "OWNER_CONFIRM_REUSED")
        return OwnerConfirmationCheck(True, confirmation_id=confirm_id, status="CONSUMED")
