"""WP4.4 (missed-checkpoint catch-up) and WP6-completion (bounded retry/backoff)
policy interfaces.

Resource-first check performed before writing this module (2026-09-08): searched
docs/plans/, docs/contracts/, config/governance/ for any existing signed FX
ticket-delivery catch-up duration or retry/backoff bound. None exists. The only
related document, docs/contracts/AG_BTC_CATCHUP_CONTRACT_AMENDMENT_V1_PROPOSED.md, is
itself explicitly PROPOSED / not authorized, is scoped to BTC daily observations (a
different domain with different counting semantics), and does not apply here even by
analogy without its own separate sign-off.

Therefore:

    CATCH_UP_DURATION = UNSIGNED
    RETRY_MAX_ATTEMPTS = UNSIGNED
    RETRY_BASE_DELAY   = UNSIGNED
    RETRY_MAX_DELAY    = UNSIGNED

Both policies below implement the MECHANISM only: a fully testable, deterministic,
fail-closed interface that requires an explicit, caller-supplied policy value to do
anything. Neither policy has a production default. Operational activation (choosing
and signing real values, then wiring a real config source) is a separate, explicitly
deferred decision -- see docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

REASON_CATCH_UP_POLICY_NOT_CONFIGURED = "CATCH_UP_POLICY_NOT_CONFIGURED"
REASON_OUTSIDE_CATCH_UP_WINDOW = "OUTSIDE_CATCH_UP_WINDOW"
REASON_PREMATURE = "BEFORE_CYCLE_CHECKPOINT"

REASON_RETRY_POLICY_NOT_CONFIGURED = "RETRY_POLICY_NOT_CONFIGURED"
REASON_MAX_ATTEMPTS_EXHAUSTED = "RETRY_MAX_ATTEMPTS_EXHAUSTED"


@dataclass(frozen=True)
class CatchUpPolicy:
    """No production default. `max_catch_up_age=None` (the only way to construct this
    with zero arguments) means "not configured" -- every evaluation is then refused,
    never silently allowed. A caller must explicitly pass a signed
    `datetime.timedelta` to activate catch-up evaluation at all."""

    max_catch_up_age: Optional[dt.timedelta] = None

    def evaluate(self, *, checkpoint: dt.datetime, now: dt.datetime) -> "CatchUpDecision":
        if now < checkpoint:
            return CatchUpDecision(allowed=False, reason_code=REASON_PREMATURE)
        if self.max_catch_up_age is None:
            return CatchUpDecision(allowed=False, reason_code=REASON_CATCH_UP_POLICY_NOT_CONFIGURED)
        age = now - checkpoint
        if age > self.max_catch_up_age:
            return CatchUpDecision(allowed=False, reason_code=REASON_OUTSIDE_CATCH_UP_WINDOW)
        return CatchUpDecision(allowed=True, reason_code=None)


@dataclass(frozen=True)
class CatchUpDecision:
    allowed: bool
    reason_code: Optional[str]


@dataclass(frozen=True)
class RetryPolicy:
    """No production default -- `max_attempts=None` means "not configured", and
    `should_retry()`/`next_delay()` both refuse to operate at all in that state
    (fail closed, never silently applying an arbitrary bound). A caller must supply
    explicit, signed values to activate retries."""

    max_attempts: Optional[int] = None
    base_delay_seconds: Optional[float] = None
    max_delay_seconds: Optional[float] = None

    def is_configured(self) -> bool:
        return self.max_attempts is not None and self.base_delay_seconds is not None and self.max_delay_seconds is not None

    def should_retry(self, *, attempt_number: int, classification: str) -> "RetryDecision":
        if classification != "RETRYABLE":
            # Terminal and ambiguous classifications are never retried by this policy,
            # regardless of configuration -- that invariant does not depend on whether
            # a numeric bound is signed.
            return RetryDecision(should_retry=False, reason_code=None, delay_seconds=None)
        if not self.is_configured():
            return RetryDecision(should_retry=False, reason_code=REASON_RETRY_POLICY_NOT_CONFIGURED, delay_seconds=None)
        if attempt_number >= self.max_attempts:
            return RetryDecision(should_retry=False, reason_code=REASON_MAX_ATTEMPTS_EXHAUSTED, delay_seconds=None)
        return RetryDecision(should_retry=True, reason_code=None, delay_seconds=self.next_delay(attempt_number))

    def next_delay(self, attempt_number: int) -> float:
        """Deterministic exponential backoff: base * 2^(attempt-1), capped at
        max_delay. Pure function of (attempt_number, policy) -- no randomness, no
        wall-clock read, fully unit-testable without sleeping."""
        if not self.is_configured():
            raise ValueError("RetryPolicy is not configured (base_delay_seconds/max_delay_seconds unset)")
        delay = self.base_delay_seconds * (2 ** max(0, attempt_number - 1))
        return min(delay, self.max_delay_seconds)


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    reason_code: Optional[str]
    delay_seconds: Optional[float]
