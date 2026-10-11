"""Restart-safe DEMO attempt claims on the existing append-only TICKET_STORE_V1.

A durable SENDING row is written before a future adapter may touch a broker. If a
process restarts with SENDING but no reconciled terminal result, the ticket is
HALTED as uncertain; this module never retries or calls a broker. TicketStore's
existing contract is one writer per store root; the local lock also serializes
threads in this process. Its `source=LIVE` field below denotes live-data
provenance; the payload separately pins `account_mode=DEMO`.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ticket_store.store import LIVE, TicketStore, TicketStoreError, build_outcome

SENDING = "DEMO_EXECUTION_SENDING"
UNCERTAIN = "DEMO_EXECUTION_UNCERTAIN"
RECONCILED = "DEMO_EXECUTION_RECONCILED"
_EXECUTION_KINDS = frozenset({SENDING, UNCERTAIN, RECONCILED})
_LOCK_GUARD = threading.Lock()
_TICKET_LOCKS: dict[tuple[str, str], threading.Lock] = {}


@dataclass(frozen=True)
class LedgerCheck:
    available: bool
    reason_code: str
    prior_state: Optional[str] = None


def _ticket_lock(store: TicketStore, ticket_id: str) -> threading.Lock:
    key = (str(store.root), ticket_id)
    with _LOCK_GUARD:
        return _TICKET_LOCKS.setdefault(key, threading.Lock())


def _aware_iso(now_utc: datetime) -> Optional[str]:
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None or now_utc.utcoffset() is None:
        return None
    return now_utc.astimezone(timezone.utc).isoformat()


class ExecutionLedger:
    """Narrow execution-state adapter over the repository's existing TicketStore."""

    def __init__(self, store: TicketStore) -> None:
        self.store = store

    def _execution_rows(self, ticket_id: str) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
        try:
            all_rows = self.store.outcomes(ticket_id)
        except (OSError, ValueError, TypeError, KeyError, TicketStoreError):
            return None, "EXECUTION_LEDGER_UNREADABLE"
        execution_rows = [row for row in all_rows
                          if isinstance(row.get("outcome_kind"), str)
                          and row["outcome_kind"].startswith("DEMO_EXECUTION_")]
        if any(row.get("outcome_kind") not in _EXECUTION_KINDS for row in execution_rows):
            return None, "EXECUTION_LEDGER_UNKNOWN_STATE"
        rows = execution_rows
        for row in rows:
            payload = row.get("payload")
            if not isinstance(payload, dict) or payload.get("idempotency_key") != ticket_id:
                return None, "EXECUTION_LEDGER_CONFLICT"
        return rows, None

    def inspect(self, ticket_id: str) -> LedgerCheck:
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            return LedgerCheck(False, "TICKET_ID_MISSING")
        rows, error = self._execution_rows(ticket_id)
        if error:
            return LedgerCheck(False, error)
        assert rows is not None
        states = [row["outcome_kind"] for row in rows]
        if states.count(RECONCILED) > 1 or states.count(SENDING) > 1 or states.count(UNCERTAIN) > 1:
            return LedgerCheck(False, "EXECUTION_LEDGER_CONFLICT")
        if UNCERTAIN in states:
            return LedgerCheck(False, "HALT_UNKNOWN_RESULT", UNCERTAIN)
        if RECONCILED in states:
            if SENDING not in states:
                return LedgerCheck(False, "EXECUTION_LEDGER_CONFLICT")
            return LedgerCheck(False, "DUPLICATE_TICKET_ID", RECONCILED)
        if SENDING in states:
            return LedgerCheck(False, "HALT_UNCERTAIN_SEND", SENDING)
        return LedgerCheck(True, "IDEMPOTENCY_KEY_AVAILABLE")

    def reserve_before_send(self, ticket_id: str, *, strategy_id: str, symbol: str,
                            logic_identity: str, now_utc: datetime) -> LedgerCheck:
        """Persist the ticket-id claim before any future C11 adapter call; does not send."""
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            return LedgerCheck(False, "TICKET_ID_MISSING")
        recorded_at = _aware_iso(now_utc)
        if recorded_at is None:
            return LedgerCheck(False, "EXECUTION_LEDGER_TIMESTAMP_INVALID")
        with _ticket_lock(self.store, ticket_id):
            prior = self.inspect(ticket_id)
            if not prior.available:
                return prior
            record = build_outcome(
                ticket_id=ticket_id,
                source=LIVE,
                outcome_kind=SENDING,
                recorded_at_utc=recorded_at,
                result="SEND_PENDING",
                payload={
                    "idempotency_key": ticket_id,
                    "lifecycle_state": "SENDING",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "logic_identity": logic_identity,
                    "account_mode": "DEMO",
                },
                provenance={"writer": "demo_execution.idempotency.ExecutionLedger.reserve_before_send"},
            )
            try:
                wrote = self.store.append_outcome(record)
            except (OSError, ValueError, TicketStoreError):
                return LedgerCheck(False, "EXECUTION_LEDGER_WRITE_FAILED")
            if not wrote:
                return self.inspect(ticket_id)
        # The caller may cross the broker boundary exactly once after this durable write.
        # A later process that only inspects the same row will receive HALT_UNCERTAIN_SEND.
        return LedgerCheck(True, "SEND_CLAIM_PERSISTED", SENDING)

    def record_unknown(self, ticket_id: str, *, reason_code: str, now_utc: datetime) -> LedgerCheck:
        """Append an unknown-send marker. Every later inspection halts; no retry is offered."""
        recorded_at = _aware_iso(now_utc)
        if (not isinstance(ticket_id, str) or not ticket_id.strip() or recorded_at is None
                or not isinstance(reason_code, str) or not reason_code.strip()):
            return LedgerCheck(False, "EXECUTION_LEDGER_INPUT_INVALID")
        with _ticket_lock(self.store, ticket_id):
            rows, error = self._execution_rows(ticket_id)
            if error:
                return LedgerCheck(False, error)
            assert rows is not None
            states = [row["outcome_kind"] for row in rows]
            if SENDING not in states:
                return LedgerCheck(False, "SENDING_CLAIM_MISSING")
            if UNCERTAIN in states:
                return LedgerCheck(False, "HALT_UNKNOWN_RESULT", UNCERTAIN)
            if RECONCILED in states:
                return LedgerCheck(False, "EXECUTION_LEDGER_CONFLICT")
            record = build_outcome(
                ticket_id=ticket_id,
                source=LIVE,
                outcome_kind=UNCERTAIN,
                recorded_at_utc=recorded_at,
                result="UNKNOWN",
                payload={"idempotency_key": ticket_id, "lifecycle_state": "HALT", "reason_code": reason_code},
                provenance={"writer": "demo_execution.idempotency.ExecutionLedger.record_unknown"},
            )
            try:
                self.store.append_outcome(record)
            except (OSError, ValueError, TicketStoreError):
                return LedgerCheck(False, "EXECUTION_LEDGER_WRITE_FAILED")
        return LedgerCheck(False, "HALT_UNKNOWN_RESULT", UNCERTAIN)

    def record_reconciled(self, ticket_id: str, *, reconciliation: Mapping[str, Any],
                          now_utc: datetime) -> LedgerCheck:
        """Append a caller-supplied terminal reconciliation record; performs no query itself."""
        recorded_at = _aware_iso(now_utc)
        if (not isinstance(ticket_id, str) or not ticket_id.strip() or recorded_at is None
                or not isinstance(reconciliation, Mapping)
                or reconciliation.get("reconciled") is not True
                or not isinstance(reconciliation.get("terminal_result"), str)
                or not reconciliation.get("terminal_result")
                or reconciliation.get("terminal_result").upper() == "UNKNOWN"):
            return LedgerCheck(False, "RECONCILIATION_EVIDENCE_INVALID")
        with _ticket_lock(self.store, ticket_id):
            rows, error = self._execution_rows(ticket_id)
            if error:
                return LedgerCheck(False, error)
            assert rows is not None
            states = [row["outcome_kind"] for row in rows]
            if SENDING not in states:
                return LedgerCheck(False, "SENDING_CLAIM_MISSING")
            if UNCERTAIN in states:
                return LedgerCheck(False, "HALT_UNKNOWN_RESULT", UNCERTAIN)
            if RECONCILED in states:
                return LedgerCheck(False, "DUPLICATE_TICKET_ID", RECONCILED)
            payload = dict(reconciliation)
            payload.update({"idempotency_key": ticket_id, "lifecycle_state": "RECONCILED"})
            record = build_outcome(
                ticket_id=ticket_id,
                source=LIVE,
                outcome_kind=RECONCILED,
                recorded_at_utc=recorded_at,
                result="RECONCILED",
                payload=payload,
                provenance={"writer": "demo_execution.idempotency.ExecutionLedger.record_reconciled"},
            )
            try:
                self.store.append_outcome(record)
            except (OSError, ValueError, TicketStoreError):
                return LedgerCheck(False, "EXECUTION_LEDGER_WRITE_FAILED")
        return LedgerCheck(False, "DUPLICATE_TICKET_ID", RECONCILED)
