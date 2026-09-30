"""WP1 state vocabulary + WP6 delivery-journal record shape.

State set merges docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md WP1's core
five states with two states the same document's WP6 test list requires behaviorally
(ambiguous-timeout handling, a distinct terminal-failure state) but doesn't separately
name in WP1's own list -- both are additive to, not a replacement of, the WP1 vocabulary:

  NOT_APPLICABLE            -- WATCH/NO_TRADE/DATA_ERROR/BLOCKED cycles: archived, never delivered
  READY_TO_DELIVER          -- a READY cycle's ticket exists, no attempt claimed yet
  DELIVERY_CLAIMED          -- one worker atomically claimed this attempt (WP6 dedup)
  DELIVERED                 -- confirmed provider acknowledgement received
  DELIVERY_FAILED_RETRYABLE -- known non-terminal failure (e.g. rate limit) -- WP1's "DELIVERY_PENDING" is this repository's DELIVERY_CLAIMED + DELIVERY_FAILED_RETRYABLE combined, split here for auditability
  DELIVERY_FAILED_TERMINAL  -- known terminal failure (e.g. destination rejected)
  DELIVERY_AMBIGUOUS        -- outcome unprovable (timeout with no ack) -- WP6: never auto-resend from here
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

STATE_NOT_APPLICABLE = "NOT_APPLICABLE"
STATE_READY_TO_DELIVER = "READY_TO_DELIVER"
STATE_DELIVERY_CLAIMED = "DELIVERY_CLAIMED"
STATE_DELIVERED = "DELIVERED"
STATE_DELIVERY_FAILED_RETRYABLE = "DELIVERY_FAILED_RETRYABLE"
STATE_DELIVERY_FAILED_TERMINAL = "DELIVERY_FAILED_TERMINAL"
STATE_DELIVERY_AMBIGUOUS = "DELIVERY_AMBIGUOUS"

ALL_STATES = frozenset({
    STATE_NOT_APPLICABLE, STATE_READY_TO_DELIVER, STATE_DELIVERY_CLAIMED, STATE_DELIVERED,
    STATE_DELIVERY_FAILED_RETRYABLE, STATE_DELIVERY_FAILED_TERMINAL, STATE_DELIVERY_AMBIGUOUS,
})

# A state a fresh retry attempt is permitted to be created from. DELIVERY_AMBIGUOUS is
# deliberately excluded -- WP6: "never silently resend an ambiguous delivery" without an
# explicit, separately-signed reconciliation decision (see delivery_store.py).
RETRYABLE_STATES = frozenset({STATE_DELIVERY_FAILED_RETRYABLE})

# Terminal for the purposes of "no further automatic action" -- DELIVERED and
# DELIVERY_FAILED_TERMINAL are both final; DELIVERY_AMBIGUOUS is NOT included here even
# though no automatic action follows it either, because it requires manual/reconciled
# resolution, unlike a genuine terminal state.
AUTOMATIC_TERMINAL_STATES = frozenset({STATE_DELIVERED, STATE_DELIVERY_FAILED_TERMINAL})

REASON_ALREADY_CLAIMED = "DELIVERY_ALREADY_CLAIMED"
REASON_LOGICAL_TICKET_NOT_FOUND = "LOGICAL_TICKET_NOT_FOUND"
REASON_NOT_RETRYABLE = "DELIVERY_STATE_NOT_RETRYABLE"
REASON_EXPIRED = "TICKET_EXPIRED"


@dataclass(frozen=True)
class DeliveryRecord:
    logical_ticket_id: str
    delivery_attempt_id: str
    state: str
    attempt_number: int
    created_at: datetime
    updated_at: datetime
    strategy_id: str
    strategy_version: str
    application_release: str
    symbol: str
    cycle: str
    trading_date: str  # ISO date string -- kept as str for plain-JSON round-tripping
    payload_hash: str
    provider: str = "TELEGRAM"
    provider_response_id: Optional[str] = None
    retry_classification: Optional[str] = None
    failure_evidence_redacted: Optional[str] = None
    expires_at: Optional[datetime] = None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at


@dataclass(frozen=True)
class ClaimResult:
    success: bool
    reason_code: Optional[str] = None
    record: Optional[DeliveryRecord] = None
