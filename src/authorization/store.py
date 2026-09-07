"""Durable, restart-safe storage for ExecutionApproval records.

Reuses existing repository conventions rather than inventing new ones:
  - record persistence: runtime_state.store.JsonKeyValueStore (the same atomic
    temp-file + os.replace store post_asian_pilot/btc_sweep_research already use);
  - the one-time atomic claim: the exact O_EXCL exclusive-create idiom
    execution.journal.claim_command already uses for Forex command claims -- proven,
    cross-process/cross-thread safe, and correct on Windows (this repo's own
    environment). A restart never re-opens a claim: the lock file's mere existence is
    the fail-closed guarantee.

Resource-first note: no existing local project (see this milestone's discovery pass)
provided an approval/authorization store to adapt -- this module is net-new, but every
individual mechanism it uses (JSON store, O_EXCL claim) is reused verbatim from
elsewhere in this repository, not invented.
"""
from __future__ import annotations

import dataclasses
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from execution.adapter import TradeProposal
from runtime_state.store import JsonKeyValueStore

from .integrity import compute_proposal_hash, verify_proposal_integrity
from .models import (
    STATE_CLAIMED,
    STATE_CREATED,
    STATE_EXECUTED,
    STATE_EXECUTING,
    STATE_EXPIRED,
    STATE_FAILED,
    STATE_PENDING,
    STATE_REJECTED,
    ENVIRONMENT_DEMO,
    REASON_APPROVAL_ALREADY_PROCESSED,
    REASON_APPROVAL_EXPIRED,
    REASON_APPROVAL_NOT_FOUND,
    REASON_PROPOSAL_INTEGRITY_MISMATCH,
    REASON_UNAUTHORIZED_TELEGRAM_CHAT,
    REASON_UNAUTHORIZED_TELEGRAM_USER,
    AuthorizationCheckResult,
    ClaimResult,
    ExecutionApproval,
)

DEFAULT_STATE_DIR = "journal/telegram_execution_gateway"
DEFAULT_TTL_SECONDS = 900  # 15 minutes -- spec section 17 default, configurable per call


def generate_approval_id() -> str:
    """Opaque token only -- never derived from proposal/execution parameters (spec
    section 12: callback data must never encode execution-critical fields). Short
    enough to fit comfortably inside Telegram's 64-byte callback_data limit alongside
    a single-character action prefix (e.g. "x:<approval_id>")."""
    return secrets.token_urlsafe(9)


def _serialize(approval: ExecutionApproval) -> dict:
    record = dataclasses.asdict(approval)
    for key in ("created_at", "expires_at", "approved_at", "rejected_at"):
        value = record.get(key)
        if isinstance(value, datetime):
            record[key] = value.isoformat()
    return record


def _deserialize(record: dict) -> ExecutionApproval:
    def _dt(key: str) -> Optional[datetime]:
        value = record.get(key)
        return datetime.fromisoformat(value) if value else None

    return ExecutionApproval(
        approval_id=record["approval_id"], setup_id=record["setup_id"],
        proposal_hash=record["proposal_hash"], venue=record["venue"],
        environment=record["environment"], state=record["state"],
        created_at=_dt("created_at"), expires_at=_dt("expires_at"),
        telegram_chat_id=record.get("telegram_chat_id"),
        telegram_message_id=record.get("telegram_message_id"),
        approved_by_user_id=record.get("approved_by_user_id"),
        approved_at=_dt("approved_at"), result_reference=record.get("result_reference"),
        rejected_at=_dt("rejected_at"), failure_reason=record.get("failure_reason"),
    )


class ExecutionApprovalStore:
    """One instance = one on-disk approval ledger + one claim-lock directory. Tests
    should inject a tmp_path-backed state_dir directly (same convention as
    OpenPositionGuard/DailyLossGuard's own tests) rather than sharing the real
    journal/ directory."""

    def __init__(self, state_dir: str = DEFAULT_STATE_DIR):
        self._state_dir = state_dir
        self._records = JsonKeyValueStore(os.path.join(state_dir, "approvals.json"))

    @classmethod
    def default(cls) -> "ExecutionApprovalStore":
        return cls()

    def _lock_path(self, approval_id: str) -> str:
        return os.path.join(self._state_dir, f"approval_{approval_id}.lock")

    def _try_acquire_lock(self, approval_id: str) -> bool:
        """Atomic, one-winner-only lock acquisition -- the same O_EXCL idiom as
        execution.journal.claim_command. Used for EVERY transition out of PENDING
        (claim AND reject), so a claim and a reject racing on the same approval can
        never both succeed."""
        os.makedirs(self._state_dir, exist_ok=True)
        try:
            fd = os.open(self._lock_path(approval_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            return False
        os.close(fd)
        return True

    # ------------------------------------------------------------------ creation

    def create(
        self, proposal: TradeProposal, *, venue: str, environment: str = ENVIRONMENT_DEMO,
        ttl_seconds: int = DEFAULT_TTL_SECONDS, now: Optional[datetime] = None,
    ) -> ExecutionApproval:
        if environment != ENVIRONMENT_DEMO:
            raise ValueError(f"this milestone supports only {ENVIRONMENT_DEMO!r}, got {environment!r}")
        now = now or datetime.now(timezone.utc)
        approval = ExecutionApproval(
            approval_id=generate_approval_id(), setup_id=proposal.setup_id,
            proposal_hash=compute_proposal_hash(proposal), venue=venue, environment=environment,
            state=STATE_CREATED, created_at=now, expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self._records.put(approval.approval_id, _serialize(approval))
        return approval

    def get(self, approval_id: str) -> Optional[ExecutionApproval]:
        record = self._records.get(approval_id)
        return _deserialize(record) if record is not None else None

    def find_by_setup_id(self, setup_id: str) -> Optional[ExecutionApproval]:
        """Phase D1: lets a publisher (e.g. scripts/run_telegram_execution_gateway.py's
        `publish-actionable`) ask "does an approval already exist for this real
        proposal" before creating a second one -- approval_id is intentionally opaque
        (generate_approval_id) and never derived from setup_id, so this is a scan
        rather than a direct key lookup. Read-only; never mutates state."""
        for record in self._records.all().values():
            if record.get("setup_id") == setup_id:
                return _deserialize(record)
        return None

    def mark_sent_to_telegram(
        self, approval_id: str, *, chat_id: int, message_id: int,
    ) -> Optional[ExecutionApproval]:
        """CREATED -> PENDING, once the ticket has actually been delivered. Not
        exclusive-locked: only the creator process calls this, once, immediately after
        create() -- no concurrent caller could be racing this transition."""
        approval = self.get(approval_id)
        if approval is None or approval.state != STATE_CREATED:
            return None
        updated = dataclasses.replace(
            approval, state=STATE_PENDING, telegram_chat_id=chat_id, telegram_message_id=message_id,
        )
        self._records.put(approval_id, _serialize(updated))
        return updated

    # ------------------------------------------------------------------- lifecycle

    def claim(self, approval_id: str, *, now: Optional[datetime] = None) -> ClaimResult:
        """Atomic PENDING -> CLAIMED. A second concurrent call (double-click, or two
        processes racing the same callback) always returns success=False for exactly
        one of them -- never both True."""
        now = now or datetime.now(timezone.utc)
        approval = self.get(approval_id)
        if approval is None:
            return ClaimResult(False, REASON_APPROVAL_NOT_FOUND)
        if approval.state != STATE_PENDING:
            return ClaimResult(False, REASON_APPROVAL_ALREADY_PROCESSED, approval)
        if approval.is_expired(now):
            expired = dataclasses.replace(approval, state=STATE_EXPIRED)
            self._records.put(approval_id, _serialize(expired))
            return ClaimResult(False, REASON_APPROVAL_EXPIRED, expired)
        if not self._try_acquire_lock(approval_id):
            # Someone else (claim or reject) won the race first -- re-read current state.
            current = self.get(approval_id) or approval
            return ClaimResult(False, REASON_APPROVAL_ALREADY_PROCESSED, current)

        claimed = dataclasses.replace(approval, state=STATE_CLAIMED)
        self._records.put(approval_id, _serialize(claimed))
        return ClaimResult(True, STATE_CLAIMED, claimed)

    def reject(self, approval_id: str, *, now: Optional[datetime] = None) -> ClaimResult:
        """Atomic PENDING -> REJECTED. Broker calls = 0 by construction -- rejection
        never touches ExecutionCoordinator."""
        now = now or datetime.now(timezone.utc)
        approval = self.get(approval_id)
        if approval is None:
            return ClaimResult(False, REASON_APPROVAL_NOT_FOUND)
        if approval.state != STATE_PENDING:
            return ClaimResult(False, REASON_APPROVAL_ALREADY_PROCESSED, approval)
        if approval.is_expired(now):
            expired = dataclasses.replace(approval, state=STATE_EXPIRED)
            self._records.put(approval_id, _serialize(expired))
            return ClaimResult(False, REASON_APPROVAL_EXPIRED, expired)
        if not self._try_acquire_lock(approval_id):
            current = self.get(approval_id) or approval
            return ClaimResult(False, REASON_APPROVAL_ALREADY_PROCESSED, current)

        rejected = dataclasses.replace(approval, state=STATE_REJECTED, rejected_at=now)
        self._records.put(approval_id, _serialize(rejected))
        return ClaimResult(True, STATE_REJECTED, rejected)

    def mark_executing(self, approval_id: str) -> Optional[ExecutionApproval]:
        """CLAIMED -> EXECUTING. Only the caller that already holds the claim (i.e. the
        one that received success=True from claim()) should ever call this -- no
        additional locking needed since ownership is already established."""
        approval = self.get(approval_id)
        if approval is None or approval.state != STATE_CLAIMED:
            return None
        updated = dataclasses.replace(approval, state=STATE_EXECUTING)
        self._records.put(approval_id, _serialize(updated))
        return updated

    def mark_executed(
        self, approval_id: str, *, approved_by_user_id: int, result_reference: str,
        now: Optional[datetime] = None,
    ) -> Optional[ExecutionApproval]:
        approval = self.get(approval_id)
        if approval is None or approval.state != STATE_EXECUTING:
            return None
        now = now or datetime.now(timezone.utc)
        updated = dataclasses.replace(
            approval, state=STATE_EXECUTED, approved_by_user_id=approved_by_user_id,
            approved_at=now, result_reference=result_reference,
        )
        self._records.put(approval_id, _serialize(updated))
        return updated

    def mark_failed(self, approval_id: str, *, failure_reason: str) -> Optional[ExecutionApproval]:
        """Accepts CLAIMED or EXECUTING as the precondition: a claimed approval can
        fail before ever reaching EXECUTING (e.g. PROPOSAL_NOT_FOUND or
        PROPOSAL_INTEGRITY_MISMATCH discovered right after claim, before the injected
        execution handler is ever called -- spec section 13/16), not only after a real
        execution attempt was made."""
        approval = self.get(approval_id)
        if approval is None or approval.state not in (STATE_CLAIMED, STATE_EXECUTING):
            return None
        updated = dataclasses.replace(approval, state=STATE_FAILED, failure_reason=failure_reason)
        self._records.put(approval_id, _serialize(updated))
        return updated

    # ------------------------------------------------------------------- integrity

    def verify_integrity(self, approval: ExecutionApproval, proposal: TradeProposal) -> bool:
        return verify_proposal_integrity(proposal, approval.proposal_hash)


# --------------------------------------------------------------------- Telegram authz

def check_user_authorized(user_id: int, allowed_user_ids: Iterable[int]) -> AuthorizationCheckResult:
    """Uses the numeric Telegram user ID as the principal (spec section 18) -- never a
    username, which is mutable and not guaranteed unique/present."""
    if user_id in set(allowed_user_ids):
        return AuthorizationCheckResult(True)
    return AuthorizationCheckResult(False, REASON_UNAUTHORIZED_TELEGRAM_USER)


def check_chat_authorized(chat_id: int, allowed_chat_id: int) -> AuthorizationCheckResult:
    if chat_id == allowed_chat_id:
        return AuthorizationCheckResult(True)
    return AuthorizationCheckResult(False, REASON_UNAUTHORIZED_TELEGRAM_CHAT)
