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
from typing import Any, Dict, Optional

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
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        line = json.dumps(entry, sort_keys=True, default=str)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return entry
