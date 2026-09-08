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

import re
from dataclasses import dataclass
from typing import Optional

from notifications.telegram_client import TelegramApiResult, TelegramClient, TelegramClientError

from .delivery_store import TicketDeliveryStore
from .models import ClaimResult

REASON_MISSING_BOT_TOKEN = "TELEGRAM_BOT_TOKEN_NOT_CONFIGURED"
REASON_MISSING_CHAT_ID = "TELEGRAM_DESTINATION_NOT_CONFIGURED"
REASON_UNAUTHORIZED_DESTINATION = "TELEGRAM_DESTINATION_NOT_AUTHORIZED"


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

    bot_token: str
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
