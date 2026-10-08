"""WP7 durable, append-only delivery-attempt journal.

TicketDeliveryStore's `delivery_records.json` (see delivery_store.py) is a
current-STATE store: each logical_ticket_id maps to exactly one record that is
overwritten on every transition (claim -> delivered / failed / ambiguous). That is by
design (WP1/WP6) and is what claim_for_delivery()'s exactly-once guarantee is built on.

This module is additive, not a replacement: it appends one newline-delimited JSON line
per delivery ATTEMPT outcome to a separate file, purely for audit/evidence purposes
(docs/status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md's
"evidence files WP7 should produce"). Never opened for reading by any control-flow
path in this package -- claim_for_delivery()/TicketDeliveryStore remain the single
source of truth for "has this been delivered yet". Never writes a bot token, API
secret, or any raw failure evidence beyond what DeliveryRecord/DeliveryOutcome already
carry (both of which are already redacted by telegram_adapter._redact() before being
persisted at all -- see mark_failed_retryable/mark_failed_terminal/mark_ambiguous).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import DeliveryRecord

DEFAULT_JOURNAL_PATH = "journal/ticket_delivery/attempt_journal.jsonl"


@dataclass(frozen=True)
class AttemptJournal:
    """One instance = one append-only .jsonl file. Construction never touches the
    filesystem -- the parent directory is created lazily, only on the first `record()`
    call, matching TicketDeliveryStore's own lazy-directory-creation convention."""

    path: str = DEFAULT_JOURNAL_PATH

    def record(self, *, record: DeliveryRecord, outcome: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """`outcome` is a telegram_adapter.DeliveryOutcome (kept loosely typed here to
        avoid a circular import -- this module is imported BY telegram_adapter-adjacent
        callers, not the reverse). Returns the entry actually written, for tests."""
        now = now or datetime.now(timezone.utc)
        entry = {
            "recorded_at": now.isoformat(),
            "logical_ticket_id": record.logical_ticket_id,
            "delivery_attempt_id": record.delivery_attempt_id,
            "attempt_number": record.attempt_number,
            "provider": record.provider,
            "strategy_id": record.strategy_id,
            "strategy_version": record.strategy_version,
            "symbol": record.symbol,
            "cycle": record.cycle,
            "trading_date": record.trading_date,
            "final_state": getattr(outcome, "final_state", None),
            "reason_code": getattr(outcome, "reason_code", None),
            "provider_response_id": getattr(outcome, "provider_response_id", None),
        }
        self._append(entry)
        return entry

    def record_host_attempt(self, *, attempt_id: str, kind: str, value: str, ref: Optional[str], status: str,
                            provider_message_id: Optional[str], error: Optional[str] = None,
                            code_sha: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
        """One line per host-runner Telegram attempt (scripts/host/live_candles_smoke.py `_notify`).
        `provider_message_id` is Telegram's message_id for a SENT attempt (None otherwise): the
        first link of the message_id -> owner command -> attempt_id audit chain. `error` must
        already be sanitized (class / HTTP code only)."""
        now = now or datetime.now(timezone.utc)
        entry = {
            "schema": HOST_ATTEMPT_SCHEMA, "recorded_at": now.isoformat(), "attempt_id": attempt_id,
            "provider": "TELEGRAM", "kind": kind, "value": value, "ref": ref, "final_state": status,
            "provider_response_id": provider_message_id, "error": error, "code_sha": code_sha,
        }
        self._append(entry)
        return entry

    def _append(self, entry: Dict[str, Any]) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


HOST_ATTEMPT_SCHEMA = "HOST_DELIVERY_ATTEMPT_V1"
OWNER_COMMAND_SCHEMA = "OWNER_COMMAND_IDENTITY_V1"


@dataclass(frozen=True)
class OwnerCommandIdentity:
    """Schema only (owner decision D8 prerequisites "Telegram message_id", "approval command
    identity", "attempt_id"). Records WHO answered WHICH delivered message, so a future
    approval can be audited back to the exact delivery attempt. Nothing in the repo receives,
    parses or acts on owner commands, and this record never authorizes anything:
    `execution_authorized` is always False and validate() rejects any other value. Raw chat
    ids and command text are never stored, only SHA-256 digests."""

    command_id: str
    reply_to_message_id: str          # Telegram message_id of the delivered alert/ticket
    attempt_id: str                   # HOST_DELIVERY_ATTEMPT_V1.attempt_id that produced that message
    logical_ref: str                  # ticket / confirmation identity the message carried
    owner_chat_id_sha256: str
    command_text_sha256: str
    received_at: str                  # ISO-8601 UTC
    schema: str = OWNER_COMMAND_SCHEMA
    execution_authorized: bool = False

    def validate(self) -> List[str]:
        errors = [f"{k} missing" for k in ("command_id", "reply_to_message_id", "attempt_id", "logical_ref",
                                           "owner_chat_id_sha256", "command_text_sha256", "received_at")
                  if not getattr(self, k)]
        errors += [f"{k} is not a SHA-256 hex digest" for k in ("owner_chat_id_sha256", "command_text_sha256")
                   if getattr(self, k) and (len(getattr(self, k)) != 64
                                            or any(c not in "0123456789abcdef" for c in getattr(self, k)))]
        if self.schema != OWNER_COMMAND_SCHEMA:
            errors.append("schema mismatch")
        if self.execution_authorized is not False:
            errors.append("execution_authorized must be False: an owner command record grants no authority")
        return errors
