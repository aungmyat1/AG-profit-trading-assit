"""WP6 durable delivery journal + atomic deduplication.

Persistence: runtime_state.store.JsonKeyValueStore (already fixed for concurrent
thread-safety within one process -- see its own module docstring,
AG_DEMO_EXECUTION_GATEWAY_PHASE_D2_API_AND_EXECUTION_WIRING_V1).

Atomic claim: the exact O_EXCL exclusive-create idiom authorization.store.
ExecutionApprovalStore._try_acquire_lock() and execution.journal.claim_command already
use -- CreateFile(..., CREATE_NEW) / os.O_EXCL is atomic at the OS level on Windows
(this repository's actual environment) and proven safe under concurrent-thread and
restart tests in that module's own test suite. Reused verbatim here, not reinvented.

Scope, same as authorization.store: exactly-once semantics for concurrent *threads
within one process* -- the scheduler/report process is the only writer, matching this
repository's existing single-process execution-runtime model.
"""
from __future__ import annotations

import dataclasses
import os
from datetime import datetime, timezone
from typing import Optional

from runtime_state.store import JsonKeyValueStore

from .models import (
    ALL_STATES,
    AUTOMATIC_TERMINAL_STATES,
    REASON_ALREADY_CLAIMED,
    REASON_EXPIRED,
    REASON_LOGICAL_TICKET_NOT_FOUND,
    REASON_NOT_RETRYABLE,
    RETRYABLE_STATES,
    STATE_DELIVERED,
    STATE_DELIVERY_AMBIGUOUS,
    STATE_DELIVERY_CLAIMED,
    STATE_DELIVERY_FAILED_RETRYABLE,
    STATE_DELIVERY_FAILED_TERMINAL,
    STATE_NOT_APPLICABLE,
    STATE_READY_TO_DELIVER,
    ClaimResult,
    DeliveryRecord,
)

DEFAULT_STATE_DIR = "journal/ticket_delivery"


def _serialize(record: DeliveryRecord) -> dict:
    d = dataclasses.asdict(record)
    for key in ("created_at", "updated_at", "expires_at"):
        value = d.get(key)
        if isinstance(value, datetime):
            d[key] = value.isoformat()
    return d


def _deserialize(raw: dict) -> DeliveryRecord:
    def _dt(key: str) -> Optional[datetime]:
        v = raw.get(key)
        return datetime.fromisoformat(v) if v else None

    return DeliveryRecord(
        logical_ticket_id=raw["logical_ticket_id"], delivery_attempt_id=raw["delivery_attempt_id"],
        state=raw["state"], attempt_number=raw["attempt_number"],
        created_at=_dt("created_at"), updated_at=_dt("updated_at"),
        strategy_id=raw["strategy_id"], strategy_version=raw["strategy_version"],
        application_release=raw["application_release"], symbol=raw["symbol"], cycle=raw["cycle"],
        trading_date=raw["trading_date"], payload_hash=raw["payload_hash"],
        provider=raw.get("provider", "TELEGRAM"), provider_response_id=raw.get("provider_response_id"),
        retry_classification=raw.get("retry_classification"),
        failure_evidence_redacted=raw.get("failure_evidence_redacted"), expires_at=_dt("expires_at"),
    )


class TicketDeliveryStore:
    """One instance = one on-disk delivery ledger + one claim-lock directory, keyed by
    logical_ticket_id (NOT delivery_attempt_id -- exactly one attempt may be active per
    logical ticket at a time; that is the whole point of the claim)."""

    def __init__(self, state_dir: str = DEFAULT_STATE_DIR):
        self._state_dir = state_dir
        self._records = JsonKeyValueStore(os.path.join(state_dir, "delivery_records.json"))

    @classmethod
    def default(cls) -> "TicketDeliveryStore":
        return cls()

    def _lock_path(self, logical_ticket_id: str) -> str:
        # Sanitized: logical_ticket_id already only contains identity.py's
        # _SAFE_FIELD-validated characters plus "|" separators; "|" is not valid in a
        # Windows filename, so it is replaced for the lock-file name only (the
        # persisted record itself keeps the real id unchanged).
        safe = logical_ticket_id.replace("|", "_")
        return os.path.join(self._state_dir, f"claim_{safe}.lock")

    def _try_acquire_lock(self, logical_ticket_id: str) -> bool:
        os.makedirs(self._state_dir, exist_ok=True)
        try:
            fd = os.open(self._lock_path(logical_ticket_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            return False
        os.close(fd)
        return True

    def _release_lock(self, logical_ticket_id: str) -> None:
        # Released only on a definitively-resolved outcome (DELIVERED / *_TERMINAL) so
        # a fresh retry attempt can claim again -- an AMBIGUOUS or still-CLAIMED state
        # deliberately keeps the lock held, which is exactly what prevents an automatic
        # duplicate send while the outcome is unresolved.
        try:
            os.remove(self._lock_path(logical_ticket_id))
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------- creation

    def ensure_ready_to_deliver(
        self, *, logical_ticket_id: str, strategy_id: str, strategy_version: str,
        application_release: str, symbol: str, cycle: str, trading_date: str,
        payload_hash: str, expires_at: Optional[datetime] = None, now: Optional[datetime] = None,
    ) -> DeliveryRecord:
        """Idempotent: if a record already exists for this logical_ticket_id, returns
        it unchanged (never creates a second one -- 'duplicate scheduler trigger' /
        'repeated identical run' safety). Only creates a fresh READY_TO_DELIVER record
        when none exists yet."""
        existing = self._records.get(logical_ticket_id)
        if existing is not None:
            return _deserialize(existing)

        now = now or datetime.now(timezone.utc)
        record = DeliveryRecord(
            logical_ticket_id=logical_ticket_id, delivery_attempt_id="", state=STATE_READY_TO_DELIVER,
            attempt_number=0, created_at=now, updated_at=now, strategy_id=strategy_id,
            strategy_version=strategy_version, application_release=application_release,
            symbol=symbol, cycle=cycle, trading_date=trading_date, payload_hash=payload_hash,
            expires_at=expires_at,
        )
        self._records.put(logical_ticket_id, _serialize(record))
        return record

    def record_not_applicable(
        self, *, logical_ticket_id: str, strategy_id: str, strategy_version: str,
        application_release: str, symbol: str, cycle: str, trading_date: str,
        now: Optional[datetime] = None,
    ) -> DeliveryRecord:
        """WATCH/NO_TRADE/DATA_ERROR/BLOCKED cycles: archived (ticket_delivery.archive)
        but never delivered. Recorded here too so a caller can distinguish "nothing to
        deliver, by design" from "should have been delivered but wasn't"."""
        existing = self._records.get(logical_ticket_id)
        if existing is not None:
            return _deserialize(existing)
        now = now or datetime.now(timezone.utc)
        record = DeliveryRecord(
            logical_ticket_id=logical_ticket_id, delivery_attempt_id="", state=STATE_NOT_APPLICABLE,
            attempt_number=0, created_at=now, updated_at=now, strategy_id=strategy_id,
            strategy_version=strategy_version, application_release=application_release,
            symbol=symbol, cycle=cycle, trading_date=trading_date, payload_hash="",
        )
        self._records.put(logical_ticket_id, _serialize(record))
        return record

    def get(self, logical_ticket_id: str) -> Optional[DeliveryRecord]:
        raw = self._records.get(logical_ticket_id)
        return _deserialize(raw) if raw is not None else None

    # ------------------------------------------------------------------- claim/lifecycle

    def claim_for_delivery(self, logical_ticket_id: str, *, now: Optional[datetime] = None) -> ClaimResult:
        """Atomic READY_TO_DELIVER -> DELIVERY_CLAIMED (first attempt), or
        DELIVERY_FAILED_RETRYABLE -> DELIVERY_CLAIMED (a retry). Exactly one concurrent
        caller succeeds; every other caller (10-way concurrency, duplicate scheduler
        trigger, restart-and-retry racing a still-running original) gets
        success=False/DELIVERY_ALREADY_CLAIMED and the current record, never a second
        DELIVERY_CLAIMED. Never claims from DELIVERY_AMBIGUOUS -- that requires
        resolve_ambiguous_outcome() first."""
        now = now or datetime.now(timezone.utc)
        record = self.get(logical_ticket_id)
        if record is None:
            return ClaimResult(False, REASON_LOGICAL_TICKET_NOT_FOUND)
        if record.is_expired(now):
            return ClaimResult(False, REASON_EXPIRED, record)
        if record.state not in (STATE_READY_TO_DELIVER, *RETRYABLE_STATES):
            return ClaimResult(False, REASON_NOT_RETRYABLE, record)

        if not self._try_acquire_lock(logical_ticket_id):
            current = self.get(logical_ticket_id) or record
            return ClaimResult(False, REASON_ALREADY_CLAIMED, current)

        # Re-read under the lock: another attempt may have completed between the
        # unlocked read above and winning the O_EXCL race (e.g. a fast successful
        # DELIVERED that already released and re-locked is not possible since the lock
        # is only released on a terminal outcome -- but re-check defensively anyway).
        current = self.get(logical_ticket_id) or record
        if current.state not in (STATE_READY_TO_DELIVER, *RETRYABLE_STATES):
            self._release_lock(logical_ticket_id)
            return ClaimResult(False, REASON_ALREADY_CLAIMED, current)

        claimed = dataclasses.replace(
            current, delivery_attempt_id=f"{logical_ticket_id}|attempt-{current.attempt_number + 1:03d}",
            attempt_number=current.attempt_number + 1, state=STATE_DELIVERY_CLAIMED, updated_at=now,
        )
        self._records.put(logical_ticket_id, _serialize(claimed))
        return ClaimResult(True, record=claimed)

    def mark_delivered(self, logical_ticket_id: str, *, provider_response_id: str, now: Optional[datetime] = None) -> Optional[DeliveryRecord]:
        record = self.get(logical_ticket_id)
        if record is None or record.state != STATE_DELIVERY_CLAIMED:
            return None
        now = now or datetime.now(timezone.utc)
        updated = dataclasses.replace(
            record, state=STATE_DELIVERED, provider_response_id=provider_response_id, updated_at=now,
        )
        self._records.put(logical_ticket_id, _serialize(updated))
        self._release_lock(logical_ticket_id)
        return updated

    def mark_failed_retryable(self, logical_ticket_id: str, *, evidence_redacted: str, now: Optional[datetime] = None) -> Optional[DeliveryRecord]:
        record = self.get(logical_ticket_id)
        if record is None or record.state != STATE_DELIVERY_CLAIMED:
            return None
        now = now or datetime.now(timezone.utc)
        updated = dataclasses.replace(
            record, state=STATE_DELIVERY_FAILED_RETRYABLE, failure_evidence_redacted=evidence_redacted,
            retry_classification="RETRYABLE", updated_at=now,
        )
        self._records.put(logical_ticket_id, _serialize(updated))
        self._release_lock(logical_ticket_id)  # a fresh claim_for_delivery() retry may now proceed
        return updated

    def mark_failed_terminal(self, logical_ticket_id: str, *, evidence_redacted: str, now: Optional[datetime] = None) -> Optional[DeliveryRecord]:
        record = self.get(logical_ticket_id)
        if record is None or record.state != STATE_DELIVERY_CLAIMED:
            return None
        now = now or datetime.now(timezone.utc)
        updated = dataclasses.replace(
            record, state=STATE_DELIVERY_FAILED_TERMINAL, failure_evidence_redacted=evidence_redacted,
            retry_classification="TERMINAL", updated_at=now,
        )
        self._records.put(logical_ticket_id, _serialize(updated))
        self._release_lock(logical_ticket_id)
        return updated

    def mark_ambiguous(self, logical_ticket_id: str, *, evidence_redacted: str, now: Optional[datetime] = None) -> Optional[DeliveryRecord]:
        """WP6: a timeout/network failure where the provider's actual outcome cannot be
        proven. The claim lock is deliberately NOT released -- no automatic retry may
        ever pull this logical ticket back into claim_for_delivery() again. Only
        resolve_ambiguous_outcome() (an explicit, separately-signed reconciliation
        action) may move it forward."""
        record = self.get(logical_ticket_id)
        if record is None or record.state != STATE_DELIVERY_CLAIMED:
            return None
        now = now or datetime.now(timezone.utc)
        updated = dataclasses.replace(
            record, state=STATE_DELIVERY_AMBIGUOUS, failure_evidence_redacted=evidence_redacted,
            retry_classification="AMBIGUOUS_REQUIRES_RECONCILIATION", updated_at=now,
        )
        self._records.put(logical_ticket_id, _serialize(updated))
        return updated

    def resolve_ambiguous_outcome(
        self, logical_ticket_id: str, *, resolved_state: str, provider_response_id: Optional[str] = None,
        evidence_redacted: Optional[str] = None, now: Optional[datetime] = None,
    ) -> Optional[DeliveryRecord]:
        """Explicit reconciliation only -- never called automatically by any retry/claim
        path. `resolved_state` must be one of the genuinely terminal outcomes; this
        function does not itself decide what happened, it only records a decision a
        caller has already made from authoritative external evidence (e.g. a manual
        check of the Telegram chat, or a provider-side delivery-status API)."""
        if resolved_state not in AUTOMATIC_TERMINAL_STATES:
            raise ValueError(f"resolved_state must be one of {AUTOMATIC_TERMINAL_STATES}, got {resolved_state!r}")
        record = self.get(logical_ticket_id)
        if record is None or record.state != STATE_DELIVERY_AMBIGUOUS:
            return None
        now = now or datetime.now(timezone.utc)
        updated = dataclasses.replace(
            record, state=resolved_state, provider_response_id=provider_response_id or record.provider_response_id,
            failure_evidence_redacted=evidence_redacted or record.failure_evidence_redacted, updated_at=now,
        )
        self._records.put(logical_ticket_id, _serialize(updated))
        self._release_lock(logical_ticket_id)
        return updated
