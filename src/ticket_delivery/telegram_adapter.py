"""WP5 (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md) -- message-only
Telegram delivery adapter.

Reuses notifications.telegram_client.TelegramClient.send_message() ONLY -- no other
method on that class is ever called here (get_updates / answer_callback_query /
edit_message_* / callback-parsing functions are all approval/polling-shaped and
deliberately unused). Does NOT reuse notifications.trade_ticket_formatter (it is
ExecutionApproval-coupled and builds inline keyboards) or authorization.telegram_gateway
(the approval-callback surface) -- see tests/test_ticket_delivery_execution_boundary.py
for the static proof neither is importable from this package.

Destination/token are configuration-only, injected by the caller -- this module never
reads an environment variable or a default itself, so "no default destination" and
"configuration absence fails closed" are enforced at the caller boundary
(TelegramDestinationConfig.from_values / a caller's own env lookup), not hidden inside
this adapter.
"""
from __future__ import annotations

import dataclasses
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional

from notifications.telegram_client import TelegramApiResult, TelegramClient, TelegramClientError

from .delivery_store import TicketDeliveryStore
from .models import ClaimResult
from .policy import RetryPolicy

REASON_MISSING_BOT_TOKEN = "TELEGRAM_BOT_TOKEN_NOT_CONFIGURED"
REASON_MISSING_CHAT_ID = "TELEGRAM_DESTINATION_NOT_CONFIGURED"
REASON_UNAUTHORIZED_DESTINATION = "TELEGRAM_DESTINATION_NOT_AUTHORIZED"
REASON_INVALID_CHAT_ID = "TELEGRAM_DESTINATION_MALFORMED"
REASON_RETRY_ATTEMPTS_EXHAUSTED = "RETRY_MAX_ATTEMPTS_EXHAUSTED"


class TelegramConfigError(RuntimeError):
    """Configuration absence/mismatch -- fails closed before any network call is made."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass(frozen=True)
class TelegramDestinationConfig:
    """No default chat_id/bot_token anywhere in this dataclass or its factory -- both
    are required, non-empty inputs. `authorized_chat_ids` is the explicit allow-list a
    caller must supply; a destination outside it is rejected before send_message is
    ever called."""

    bot_token: str = field(repr=False)
    chat_id: int
    authorized_chat_ids: frozenset

    @classmethod
    def from_values(cls, *, bot_token: Optional[str], chat_id: Optional[int], authorized_chat_ids) -> "TelegramDestinationConfig":
        if not bot_token:
            raise TelegramConfigError(REASON_MISSING_BOT_TOKEN, "no bot token supplied")
        if not chat_id:
            raise TelegramConfigError(REASON_MISSING_CHAT_ID, "no destination chat_id supplied")
        allow_list = frozenset(authorized_chat_ids or ())
        if chat_id not in allow_list:
            raise TelegramConfigError(
                REASON_UNAUTHORIZED_DESTINATION, f"chat_id {chat_id} is not in the authorized destination list",
            )
        return cls(bot_token=bot_token, chat_id=chat_id, authorized_chat_ids=allow_list)

    @classmethod
    def from_env(cls, *, authorized_chat_ids, env: Optional[Mapping[str, str]] = None) -> "TelegramDestinationConfig":
        """WP7: reads the existing repository-convention env vars TELEGRAM_BOT_TOKEN /
        TELEGRAM_CHAT_ID (already used by
        authorization.config.TelegramGatewayConfig.from_env() for the separate,
        forbidden-import approval-gateway path -- reused here only by env-var NAME
        convention, this module never imports that one). `authorized_chat_ids` is
        ALWAYS caller-supplied (typically the signed config's own allow-list) -- it is
        never read from an environment variable and never inferred from
        TELEGRAM_CHAT_ID itself, so "the destination is authorized" can never become a
        tautology. Delegates all fail-closed behavior (missing token, missing/malformed
        chat id, unauthorized destination) to from_values() -- no parallel validation
        path. Never logs, reprs, or otherwise surfaces the raw token value."""
        env = env if env is not None else os.environ
        bot_token = env.get("TELEGRAM_BOT_TOKEN") or None
        chat_id_raw = env.get("TELEGRAM_CHAT_ID")
        chat_id: Optional[int] = None
        if chat_id_raw:
            try:
                chat_id = int(chat_id_raw)
            except (TypeError, ValueError):
                raise TelegramConfigError(
                    REASON_INVALID_CHAT_ID, "TELEGRAM_CHAT_ID is not a valid integer",
                )
        return cls.from_values(bot_token=bot_token, chat_id=chat_id, authorized_chat_ids=authorized_chat_ids)


def _redact(text: str, bot_token: str) -> str:
    """Strips the bot token from any string before it is ever persisted as failure
    evidence, logged, or returned to a caller -- requests' own exception messages can
    embed the full request URL (which contains /bot<TOKEN>/...), so this is applied to
    every piece of evidence this module produces, not only ones that look suspicious."""
    if not text:
        return text
    redacted = text.replace(bot_token, "***REDACTED***")
    # Also catch the URL-embedded form even if partially percent-encoded by a transport
    # layer -- belt and suspenders, cheap to apply.
    return re.sub(re.escape(bot_token), "***REDACTED***", redacted)


@dataclass(frozen=True)
class DeliveryOutcome:
    claimed: bool
    final_state: str
    reason_code: Optional[str] = None
    provider_response_id: Optional[str] = None


def deliver_informational_ticket(
    *, store: TicketDeliveryStore, logical_ticket_id: str, message_text: str,
    client: TelegramClient, destination: TelegramDestinationConfig,
) -> DeliveryOutcome:
    """archived READY ticket -> durable claim -> send informational message -> record
    provider outcome. `message_text` is expected to already be the fully-rendered,
    plain-text (no button/keyboard) ticket body from renderer.format_message_text() --
    this function does not itself decide ticket content."""
    claim: ClaimResult = store.claim_for_delivery(logical_ticket_id)
    if not claim.success:
        return DeliveryOutcome(claimed=False, final_state=claim.record.state if claim.record else "UNKNOWN", reason_code=claim.reason_code)

    try:
        result: TelegramApiResult = client.send_message(destination.chat_id, message_text)
    except TelegramClientError as exc:
        evidence = _redact(str(exc), destination.bot_token)
        reason_code = getattr(exc, "reason_code", "TELEGRAM_REQUEST_FAILED")
        if reason_code in ("SENDMESSAGE_REQUEST_FAILED",):
            # Transport-level failure with no HTTP response at all -- cannot distinguish
            # "definitely not sent" from "sent, ack lost" (WP6: timeout/connection
            # failure is ambiguous, never assumed to be a clean non-send).
            store.mark_ambiguous(logical_ticket_id, evidence_redacted=evidence)
            return DeliveryOutcome(claimed=True, final_state="DELIVERY_AMBIGUOUS", reason_code=reason_code)
        store.mark_failed_terminal(logical_ticket_id, evidence_redacted=evidence)
        return DeliveryOutcome(claimed=True, final_state="DELIVERY_FAILED_TERMINAL", reason_code=reason_code)

    if result.ok:
        message_id = None
        if isinstance(result.result, dict):
            message_id = result.result.get("message_id")
        store.mark_delivered(logical_ticket_id, provider_response_id=str(message_id) if message_id is not None else "SENT_NO_ID")
        return DeliveryOutcome(claimed=True, final_state="DELIVERED", provider_response_id=str(message_id) if message_id is not None else None)

    # Telegram answered but ok=false -- a real, non-ambiguous provider decision.
    evidence = _redact(f"error_code={result.error_code} description={result.description}", destination.bot_token)
    if result.error_code == 429:
        store.mark_failed_retryable(logical_ticket_id, evidence_redacted=evidence)
        return DeliveryOutcome(claimed=True, final_state="DELIVERY_FAILED_RETRYABLE", reason_code="RATE_LIMITED")
    store.mark_failed_terminal(logical_ticket_id, evidence_redacted=evidence)
    return DeliveryOutcome(claimed=True, final_state="DELIVERY_FAILED_TERMINAL", reason_code=f"TELEGRAM_ERROR_{result.error_code}")


def deliver_informational_ticket_with_retry(
    *, store: TicketDeliveryStore, logical_ticket_id: str, message_text: str,
    client: TelegramClient, destination: TelegramDestinationConfig, retry_policy: RetryPolicy,
    sleeper: Optional[Callable[[float], None]] = None,
    attempt_journal: Optional["object"] = None,
) -> DeliveryOutcome:
    """WP7 retry design (A) -- IN-PROCESS WAIT-AND-RETRY, chosen and recorded explicitly
    per docs/status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md's
    open question: after a RETRYABLE outcome, sleep the signed policy's next_delay()
    seconds (30s, then 60s under the signed max_attempts=3/base=30s/max=300s contract)
    and re-attempt through the SAME deliver_informational_ticket() / TicketDeliveryStore
    path -- no parallel/untested send path. `sleeper` is injectable (defaults to
    time.sleep) so no test in this repository ever sleeps for real.

    Terminates as soon as an outcome is not a fresh RETRYABLE claim: a successful
    DELIVERED, a *_TERMINAL, an AMBIGUOUS, or an unclaimed outcome (e.g. the ticket is
    already DELIVERED from a prior invocation -- idempotent, zero further provider
    calls) all return immediately. When retries are genuinely exhausted
    (RetryPolicy.should_retry() refuses further attempts), the last RETRYABLE outcome is
    returned with `reason_code` overridden to REASON_RETRY_ATTEMPTS_EXHAUSTED so a
    caller can distinguish "still retryable, caller gave up early" (impossible here --
    this function always runs the policy to exhaustion) from "policy-exhausted"; the
    persisted DeliveryRecord itself remains DELIVERY_FAILED_RETRYABLE (unlocked, so a
    LATER separate invocation, e.g. the next scheduled tick, may still claim and retry
    it again -- exhaustion here is scoped to this one invocation's in-process loop, it
    does not itself mark the logical ticket as permanently failed).

    `attempt_journal`: optional WP7 durable append-only attempt log (see
    attempt_journal.AttemptJournal) -- when supplied, one entry is appended after every
    attempt in this loop. `None` (the default) is a no-op, preserving every
    pre-WP7 caller."""
    sleep = sleeper or time.sleep
    while True:
        outcome = deliver_informational_ticket(
            store=store, logical_ticket_id=logical_ticket_id, message_text=message_text,
            client=client, destination=destination,
        )
        if attempt_journal is not None:
            record = store.get(logical_ticket_id)
            if record is not None:
                attempt_journal.record(record=record, outcome=outcome)

        if not outcome.claimed or outcome.final_state != "DELIVERY_FAILED_RETRYABLE":
            return outcome

        record = store.get(logical_ticket_id)
        attempt_number = record.attempt_number if record is not None else 1
        decision = retry_policy.should_retry(attempt_number=attempt_number, classification="RETRYABLE")
        if not decision.should_retry:
            return dataclasses.replace(outcome, reason_code=REASON_RETRY_ATTEMPTS_EXHAUSTED)
        sleep(decision.delay_seconds)
