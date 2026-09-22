"""PANEL_R5B: durable, restart-safe execution identity and idempotency.

Scope (see docs/status/AG_PANEL_R5B_DURABLE_IDEMPOTENCY_STATUS.md for the full
discovery/design record): this module establishes ONLY the persistence/state contract
R5C (risk/execution gate), R5D (MT5 Demo submission), and R6 (broker reconciliation)
will consume. It never imports execution.executor, execution.mt5_gateway, or anything
that can call order_send, and never sets user_confirmed=True. It is not wired into any
HTTP route or into owner_decision.bridge (R3, frozen) by this package -- that wiring is
explicitly deferred to a later package.

Reuses, rather than reimplements, two already-established, restart-proven repository
primitives (discovery recorded in the status doc):
  - runtime_state.store.JsonKeyValueStore for the mutable per-decision_id record
    (atomic temp-file + os.replace; fails loudly/closed via StateStoreCorrupted on a
    corrupt or unreadable file) -- the SAME store authorization.store.
    ExecutionApprovalStore already uses for its own durable ledger.
  - the O_EXCL exclusive-create claim-lock idiom (authorization.store._try_acquire_lock
    / execution.journal.claim_command) for atomic first-writer-wins creation.
  - authorization.integrity.compute_proposal_hash's canonicalization convention
    (json.dumps(sort_keys=True, separators=(",", ":")) + hashlib.sha256) for the
    request fingerprint below -- never Python's built-in hash() (not stable across
    processes/runs, and not even guaranteed stable within one process across runs
    with PYTHONHASHSEED randomization for str).

Canonical execution identity (P1 discovery): owner_decision.models.OwnerDecision.
decision_id is already the repository's canonical idempotency key for this chain
("decision_id is the caller-supplied idempotency key" -- that module's own docstring).
This module durably persists, keyed by that SAME decision_id, one record spanning:

    proposal_id (== CanonicalProposal.proposal_envelope_id)
        -> decision_id (== OwnerDecision.decision_id)
        -> execution_id (this module's own durable identity, deterministic from
           decision_id)
        -> command_id (== execution.models.TradeCommand.command_id, when known)
        -> broker_order_id / broker_position_id (nullable; attached only by a later
           package, once execution actually reaches a broker -- never by this module)
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from runtime_state.store import JsonKeyValueStore, StateStoreCorrupted

# --------------------------------------------------------------------------- states
# P6: the minimum execution lifecycle later packages will consume. R5B activates only
# PREPARED/AUTHORIZED/REJECTED (create_or_get's own initial states); SUBMISSION_PENDING,
# SUBMISSION_UNKNOWN, BROKER_ACCEPTED, and RECONCILED are reserved names R5C/R5D/R6 will
# transition into -- defining them here now means no later package invents a second,
# divergent state vocabulary for this same record.
STATE_PREPARED = "PREPARED"
STATE_AUTHORIZED = "AUTHORIZED"
STATE_SUBMISSION_PENDING = "SUBMISSION_PENDING"
STATE_SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
STATE_BROKER_ACCEPTED = "BROKER_ACCEPTED"
STATE_REJECTED = "REJECTED"
STATE_RECONCILED = "RECONCILED"

ALL_STATES = frozenset({
    STATE_PREPARED, STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_SUBMISSION_UNKNOWN,
    STATE_BROKER_ACCEPTED, STATE_REJECTED, STATE_RECONCILED,
})

# P7 crash-safety invariant: "If the system cannot prove that a previous broker
# submission did NOT occur, it must not automatically issue another broker submission."
# A later package's retry logic MUST consult is_retry_safe() before ever resubmitting;
# this module cannot enforce that on a caller it doesn't control, but it defines the
# single authoritative answer so no later package invents its own, possibly-wrong,
# notion of "safe to retry".
RETRY_FORBIDDEN_STATES = frozenset({STATE_SUBMISSION_PENDING, STATE_SUBMISSION_UNKNOWN, STATE_BROKER_ACCEPTED})

# Broker identity may only be attached once a submission is at least in flight --
# never on a record that is merely PREPARED/AUTHORIZED/REJECTED (P13 #10).
BROKER_ID_ELIGIBLE_STATES = frozenset({
    STATE_SUBMISSION_PENDING, STATE_SUBMISSION_UNKNOWN, STATE_BROKER_ACCEPTED, STATE_RECONCILED,
})

DEFAULT_STATE_DIR = "journal/execution_idempotency"


class IdempotencyStateUnavailable(RuntimeError):
    """Fail-closed (P10): persistence could not be read -- missing/corrupt/truncated
    file, unreadable directory, or any other I/O failure. NEVER interpreted as "no
    previous execution exists"; a caller catching this must stop, not proceed as if no
    record was found (that could cause a duplicate broker submission)."""


class FingerprintConflict(RuntimeError):
    """P5: the same decision_id was already recorded with a DIFFERENT fingerprint --
    i.e. this looks like a different trade reusing an old idempotency key. Fails
    closed: never silently returns the old authorization for the new request."""

    def __init__(self, decision_id: str, existing_fingerprint: str, requested_fingerprint: str) -> None:
        self.decision_id = decision_id
        self.existing_fingerprint = existing_fingerprint
        self.requested_fingerprint = requested_fingerprint
        super().__init__(
            f"decision_id {decision_id!r} already has durable fingerprint "
            f"{existing_fingerprint!r}; refusing to reuse it for a different "
            f"fingerprint {requested_fingerprint!r}."
        )


def compute_execution_fingerprint(
    *,
    decision_id: str,
    proposal_envelope_id: str,
    action: str,
    symbol: str,
    environment: str,
    side: Optional[str] = None,
    order_type: Optional[str] = None,
    volume: Optional[float] = None,
    entry: Optional[float] = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    risk_percent: Optional[float] = None,
) -> str:
    """P4: a deterministic SHA-256 over the immutable execution intent, using
    execution.models.TradeCommand's own field vocabulary (side/order_type/volume/
    entry/sl/tp/risk_percent) plus the decision/proposal identity fields -- not an
    invented schema. Deliberately excludes anything volatile (timestamps, actor,
    request source, HTTP metadata) so a genuine retry of the identical instruction
    always reproduces the identical fingerprint, and deliberately never uses Python's
    built-in hash() (process-local, not a durable cross-process/cross-restart
    identity)."""
    payload = {
        "decision_id": decision_id,
        "proposal_envelope_id": proposal_envelope_id,
        "action": action,
        "symbol": symbol,
        "environment": environment,
        "side": side,
        "order_type": order_type,
        "volume": volume,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "risk_percent": risk_percent,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DurableExecutionRecord:
    """P3: one canonical durable execution record. Every identifier here is an
    existing repository concept (proposal_id == CanonicalProposal.
    proposal_envelope_id, decision_id == OwnerDecision.decision_id, command_id ==
    TradeCommand.command_id) except execution_id, which this module mints
    deterministically from decision_id (never randomly -- so re-deriving it from the
    same decision_id is itself idempotent)."""

    execution_id: str
    proposal_id: str
    decision_id: str
    command_id: Optional[str]
    fingerprint: str
    state: str
    created_at: str
    updated_at: str
    broker_order_id: Optional[str] = None
    broker_position_id: Optional[str] = None
    failure_reason: Optional[str] = None


def execution_id_for(decision_id: str) -> str:
    """Deterministic, not random -- the same decision_id always maps to the same
    execution_id, in this process or after a restart."""
    return f"EXEC:{decision_id}"


def _serialize(record: DurableExecutionRecord) -> dict:
    return dataclasses.asdict(record)


def _deserialize(data: dict) -> DurableExecutionRecord:
    return DurableExecutionRecord(**data)


class DurableExecutionStore:
    """Restart-safe, cross-process (within this repo's documented one-process-per-MT5-
    terminal deployment shape -- see runtime_state.store.JsonKeyValueStore's own scope
    note) idempotency ledger, keyed by decision_id.

    Durability guarantee, precisely stated (P15): durable EXECUTION INTENT IDENTITY,
    plus fail-closed handling of an uncertain-submission state, across process
    restarts, for concurrent callers within one process. This is NOT broker
    exactly-once execution -- that requires R6's broker reconciliation, which this
    module does not implement -- and NOT cross-machine/multi-instance safety.
    """

    def __init__(self, state_dir: str = DEFAULT_STATE_DIR):
        self._state_dir = state_dir
        self._records = JsonKeyValueStore(os.path.join(state_dir, "executions.json"))

    def _lock_path(self, decision_id: str) -> str:
        digest = hashlib.sha256(decision_id.encode("utf-8")).hexdigest()
        return os.path.join(self._state_dir, f"execution_{digest}.lock")

    def _try_acquire_lock(self, decision_id: str) -> bool:
        try:
            os.makedirs(self._state_dir, exist_ok=True)
            fd = os.open(self._lock_path(decision_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            return False
        except OSError as exc:
            # P10: a directory that cannot be created/written (permissions, a path
            # component that is actually a file, a missing volume, ...) is
            # "persistence unavailable", never "no lock is held" -- must not be
            # silently treated as this caller being free to proceed as if it won the
            # claim.
            raise IdempotencyStateUnavailable(f"IDEMPOTENCY_STATE_UNAVAILABLE: {exc}") from exc
        os.close(fd)
        return True

    def get(self, decision_id: str) -> Optional[DurableExecutionRecord]:
        try:
            raw = self._records.get(decision_id)
        except StateStoreCorrupted as exc:
            raise IdempotencyStateUnavailable(
                f"IDEMPOTENCY_STATE_UNAVAILABLE: {exc}"
            ) from exc
        return _deserialize(raw) if raw is not None else None

    def create_or_get(
        self,
        *,
        decision_id: str,
        proposal_id: str,
        fingerprint: str,
        command_id: Optional[str] = None,
        initial_state: str = STATE_PREPARED,
    ) -> DurableExecutionRecord:
        """P5/P8/P9: same decision_id + same fingerprint -> returns the existing
        durable record unchanged (never re-authorizes, never creates a second row, and
        this holds across a process restart -- the record lives in
        runtime_state.store.JsonKeyValueStore's on-disk file, not in memory). Same
        decision_id + a DIFFERENT fingerprint -> raises FingerprintConflict. Two
        concurrent callers racing to create the SAME never-yet-seen decision_id: the
        O_EXCL lock ensures exactly one of them creates the record; every other caller
        waits (bounded) for that write to become visible and returns the same record --
        never proceeds believing it created a row no one else can see."""
        if initial_state not in ALL_STATES:
            raise ValueError(f"unknown initial_state {initial_state!r}")

        existing = self.get(decision_id)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise FingerprintConflict(decision_id, existing.fingerprint, fingerprint)
            return existing

        acquired = self._try_acquire_lock(decision_id)
        if not acquired:
            return self._await_created(decision_id, fingerprint)

        now = datetime.now(timezone.utc).isoformat()
        record = DurableExecutionRecord(
            execution_id=execution_id_for(decision_id),
            proposal_id=proposal_id,
            decision_id=decision_id,
            command_id=command_id,
            fingerprint=fingerprint,
            state=initial_state,
            created_at=now,
            updated_at=now,
        )
        self._put(record)
        return record

    def _await_created(
        self, decision_id: str, fingerprint: str, *, attempts: int = 200, delay_seconds: float = 0.005,
    ) -> DurableExecutionRecord:
        for _ in range(attempts):
            existing = self.get(decision_id)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise FingerprintConflict(decision_id, existing.fingerprint, fingerprint)
                return existing
            time.sleep(delay_seconds)
        raise IdempotencyStateUnavailable(
            f"decision_id {decision_id!r}'s creation lock is held but no record became "
            f"visible within the bounded wait -- refusing to guess or proceed."
        )

    def transition(
        self,
        decision_id: str,
        *,
        state: str,
        broker_order_id: Optional[str] = None,
        broker_position_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> DurableExecutionRecord:
        """Updates an EXISTING record's mutable fields; never creates one (callers go
        through create_or_get first). Broker identity is only ever attached here, only
        additively (an already-set broker_order_id/broker_position_id is never
        silently overwritten with a different value -- P13 #10), and only while the
        TARGET state is one where a submission is at least in flight
        (BROKER_ID_ELIGIBLE_STATES) -- never on a PREPARED/AUTHORIZED/REJECTED
        transition."""
        if state not in ALL_STATES:
            raise ValueError(f"unknown state {state!r}")
        if (broker_order_id is not None or broker_position_id is not None) and state not in BROKER_ID_ELIGIBLE_STATES:
            raise ValueError(
                f"broker identity may only be attached when transitioning into "
                f"{sorted(BROKER_ID_ELIGIBLE_STATES)}, not {state!r}."
            )

        record = self.get(decision_id)
        if record is None:
            raise IdempotencyStateUnavailable(
                f"no durable execution record exists for decision_id {decision_id!r}; "
                f"cannot transition a record that was never created."
            )
        if (
            record.broker_order_id is not None
            and broker_order_id is not None
            and record.broker_order_id != broker_order_id
        ):
            raise ValueError(
                f"decision_id {decision_id!r} already has broker_order_id "
                f"{record.broker_order_id!r}; refusing to overwrite with "
                f"{broker_order_id!r}."
            )
        if (
            record.broker_position_id is not None
            and broker_position_id is not None
            and record.broker_position_id != broker_position_id
        ):
            raise ValueError(
                f"decision_id {decision_id!r} already has broker_position_id "
                f"{record.broker_position_id!r}; refusing to overwrite with "
                f"{broker_position_id!r}."
            )

        updated = dataclasses.replace(
            record,
            state=state,
            broker_order_id=broker_order_id if broker_order_id is not None else record.broker_order_id,
            broker_position_id=(
                broker_position_id if broker_position_id is not None else record.broker_position_id
            ),
            failure_reason=failure_reason if failure_reason is not None else record.failure_reason,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._put(updated)
        return updated

    def _put(self, record: DurableExecutionRecord) -> None:
        try:
            self._records.put(record.decision_id, _serialize(record))
        except StateStoreCorrupted as exc:
            raise IdempotencyStateUnavailable(f"IDEMPOTENCY_STATE_UNAVAILABLE: {exc}") from exc
        except OSError as exc:
            # Same fail-closed posture as the lock-acquisition path above -- a write
            # failure that is not "content is corrupt" (e.g. disk full, directory
            # became unwritable) must never be swallowed or treated as "nothing was
            # persisted, safe to proceed".
            raise IdempotencyStateUnavailable(f"IDEMPOTENCY_STATE_UNAVAILABLE: {exc}") from exc


def is_retry_safe(state: str) -> bool:
    """P7: SUBMISSION_PENDING/SUBMISSION_UNKNOWN/BROKER_ACCEPTED are NEVER retry-safe
    -- a caller must not treat them as "safe to automatically resubmit". This function
    only reports that fail-closed answer; it never itself submits, resubmits, or
    contacts a broker."""
    return state not in RETRY_FORBIDDEN_STATES
