"""Data shapes for AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1's authorization core.

Resource-first note (this milestone's own discovery pass, 2026-09-05): no existing
Telegram trade-approval, Bybit Demo client, or MT5-Telegram execution bridge was found
anywhere under D:\\ddev. The only related local artifact is
`Integrated_Claude_Forex_PQTA_System_upgraded/integrated_system/ops/telegram_relay.py`
-- a deliberately one-way, stdlib-only notification relay with NO callback_query/
inline-keyboard handling and no execution capability by design ("It cannot place,
modify, or close an order"). Its transport conventions (plain `urllib` HTTP calls,
offset-based `getUpdates` polling, single-instance file lock, safe logging) are useful
reference for a later Telegram-transport phase, but there is no approval/authorization
model to adapt -- this module is net-new.

An ExecutionApproval authorizes exactly one immutable execution.adapter.TradeProposal.
It never carries execution-critical fields itself (entry/SL/TP/volume/etc.) -- those
live only on the TradeProposal it references; this record exists to answer "was THIS
exact proposal explicitly authorized, by whom, exactly once" without ever becoming a
second source of truth for what the trade actually is (see integrity.py for how that
identity is pinned via a hash, not by copying fields here).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Venue/environment vocabulary -- deliberately small and explicit rather than free-text,
# so a typo can never silently create a new, unguarded venue/environment pair.
VENUE_MT5 = "MT5"
VENUE_BYBIT = "BYBIT"

ENVIRONMENT_DEMO = "DEMO"
# No ENVIRONMENT_LIVE/ENVIRONMENT_MAINNET constant exists in this module on purpose --
# this milestone (and the feature's own frozen scope) never authorizes anything but
# DEMO. Adding one later is a deliberate, separately-reviewed scope change, not a typo
# away.

# Deterministic approval state machine (spec section 14). PENDING -> CLAIMED is the one
# transition that MUST be atomic (see store.py); every other transition only ever
# happens after a caller already holds the claim, so a plain write is sufficient there.
STATE_CREATED = "CREATED"
STATE_PENDING = "PENDING"
STATE_REJECTED = "REJECTED"
STATE_EXPIRED = "EXPIRED"
STATE_CLAIMED = "CLAIMED"
STATE_EXECUTING = "EXECUTING"
STATE_EXECUTED = "EXECUTED"
STATE_FAILED = "FAILED"

TERMINAL_STATES = frozenset({STATE_REJECTED, STATE_EXPIRED, STATE_EXECUTED, STATE_FAILED})

# Reason codes (spec section 46) -- reuse existing execution vocabulary where an
# equivalent concept already exists (e.g. DUPLICATE_REQUEST already exists in
# execution.coordinator); only introduce a new spelling for a genuinely new concept.
REASON_APPROVAL_PENDING = "APPROVAL_PENDING"
REASON_APPROVAL_REJECTED = "APPROVAL_REJECTED"
REASON_APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
REASON_APPROVAL_ALREADY_PROCESSED = "APPROVAL_ALREADY_PROCESSED"
REASON_UNAUTHORIZED_TELEGRAM_USER = "UNAUTHORIZED_TELEGRAM_USER"
REASON_UNAUTHORIZED_TELEGRAM_CHAT = "UNAUTHORIZED_TELEGRAM_CHAT"
REASON_PROPOSAL_NOT_FOUND = "PROPOSAL_NOT_FOUND"
REASON_PROPOSAL_INTEGRITY_MISMATCH = "PROPOSAL_INTEGRITY_MISMATCH"
REASON_APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"

# Phase D1 (AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_REAL_PROPOSAL_INTEGRATION):
# a strategy's own registry-level demo authorization is rechecked at click-time, fully
# independently of Telegram/authorization-core state -- neither of these ever gets
# copied into a Telegram-side config or cached across a claim (see
# authorization.strategy_authority).
REASON_STRATEGY_NOT_DEMO_AUTHORIZED = "BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED"
REASON_STRATEGY_NOT_REGISTERED = "STRATEGY_NOT_REGISTERED"
# Defense-in-depth only (spec section 15): reached solely if demo_authorized ever
# unexpectedly resolved true during this milestone -- Phase D1 ships no execution
# handler capable of succeeding regardless of strategy authorization state.
REASON_PHASE_D1_BROKER_EXECUTION_DISABLED = "PHASE_D1_BROKER_EXECUTION_DISABLED"


@dataclass(frozen=True)
class ExecutionApproval:
    """Durable, immutable-once-terminal authorization record for one TradeProposal.

    `proposal_hash` (see integrity.py) is the ONLY link back to execution-critical
    trade parameters -- this record never duplicates entry/SL/TP/volume/etc. itself, so
    there is no second place those values could silently drift out of sync with the
    proposal that produced them.
    """

    approval_id: str
    setup_id: str
    proposal_hash: str
    venue: str  # VENUE_MT5 / VENUE_BYBIT
    environment: str  # ENVIRONMENT_DEMO (only value this milestone supports)
    state: str
    created_at: datetime
    expires_at: datetime
    telegram_chat_id: Optional[int] = None
    telegram_message_id: Optional[int] = None
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    result_reference: Optional[str] = None
    rejected_at: Optional[datetime] = None
    failure_reason: Optional[str] = None

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass(frozen=True)
class ClaimResult:
    """Deterministic outer shape for an atomic claim attempt -- always returned, never
    an exception for an expected outcome (same convention as
    execution.coordinator.CoordinatorResult / execution.models.ExecutionReport)."""

    success: bool
    reason_code: str
    approval: Optional[ExecutionApproval] = None


@dataclass(frozen=True)
class AuthorizationCheckResult:
    """Outer shape for a Telegram user/chat authorization check."""

    authorized: bool
    reason_code: Optional[str] = None
