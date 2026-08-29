"""Persistence-backed SMC_CONDITIONAL runtime (spec sections 12, 17-22, 24, 33-34).
Wraps smc_watcher.watcher.SMCConditionWatcher unchanged -- OR-routing, consolidation,
and the M5-handoff call all stay exactly as verified in the previous phase. This module
adds only what SMCConditionWatcher's in-memory `_seen` set cannot survive: persistence
before publish, restart-safe dedup, and resumable M5-candidate tracking.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from entry_confirmation.models import EntryConfirmationRequest
from runtime_state.store import JsonKeyValueStore
from smc_watcher.models import (
    ALERT_STATE_CONFIRMED,
    ALERT_STATE_NOT_CONFIRMED,
    ALERT_STATE_WAITING_M5_CONFIRMATION,
    SMCConditionAlert,
    SMCConditionResult,
)
from smc_watcher.watcher import SMCConditionWatcher, request_m5_confirmation

from .ids import bar_cursor_key, smc_alert_id

SMC_CONFIRMATION_EXPIRY_RULE = "UNDEFINED"  # spec section 20 -- no signed expiry rule exists; never invented


def _serialize_alert(alert: SMCConditionAlert, alert_id: str) -> Dict[str, Any]:
    record = dataclasses.asdict(alert)
    record["alert_id"] = alert_id  # canonical persistent key, may differ in format from watcher's own alert_id field
    record["notification_status"] = "PENDING"
    record["expires_at"] = None
    record["expiry_reason"] = f"SMC_CONFIRMATION_EXPIRY_RULE_{SMC_CONFIRMATION_EXPIRY_RULE}"
    record["invalidated_at"] = None
    record["invalidation_reason"] = None
    return record


class PersistentSMCRuntime:
    def __init__(
        self,
        alert_store: JsonKeyValueStore,
        bar_cursor_store: JsonKeyValueStore,
        alert_sink: Optional[Any] = None,
    ):
        self.alert_store = alert_store
        self.bar_cursor_store = bar_cursor_store
        self.alert_sink = alert_sink

    def evaluate_and_persist(
        self,
        strategy_id: str,
        symbol: str,
        e1_result: Optional[SMCConditionResult] = None,
        e2_result: Optional[SMCConditionResult] = None,
        e3_result: Optional[SMCConditionResult] = None,
        current_price: Optional[float] = None,
        evaluation_time: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        triggered = [r for r in (e1_result, e2_result, e3_result) if r is not None and r.triggered]
        if not triggered:
            return None  # SMC_STATE = WATCHING -- nothing to persist or publish

        alert_id = smc_alert_id(strategy_id, symbol, [(r.condition_id, r.source_key) for r in triggered])
        existing = self.alert_store.get(alert_id)
        if existing is not None:
            if existing.get("notification_status") == "FAILED" and self.alert_sink is not None:
                return self._retry_notification(alert_id, existing)
            return existing  # same underlying event(s) already alerted -- persistent dedup, restart-safe

        watcher = SMCConditionWatcher()  # fresh in-memory dedup; the store above is authoritative
        alert = watcher.evaluate(
            strategy_id, symbol, e1_result=e1_result, e2_result=e2_result, e3_result=e3_result,
            current_price=current_price, evaluation_time=evaluation_time,
        )
        if alert is None:
            return None

        record = _serialize_alert(alert, alert_id)
        self.alert_store.put(alert_id, record)  # persist BEFORE publish (spec section 33)

        if self.alert_sink is not None:
            try:
                self.alert_sink.publish(alert)
                record["notification_status"] = "SENT"
            except Exception as exc:  # noqa: BLE001 -- publish failures must not lose the persisted event
                record["notification_status"] = "FAILED"
                record["notification_error"] = str(exc)
            self.alert_store.put(alert_id, record)

        return self.alert_store.get(alert_id)  # re-read so first-call and cached-call shapes match exactly

    def _retry_notification(self, alert_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """One retry per call, applied to the SAME persisted event -- a failed publish
        never mints a new alert_id merely because notification retry is due (spec
        sections 32-33: retry the event, don't recreate it)."""
        record = dict(record)
        try:
            self.alert_sink.publish(record)
            record["notification_status"] = "SENT"
            record.pop("notification_error", None)
        except Exception as exc:  # noqa: BLE001 -- a retry failure must not lose the persisted event either
            record["notification_status"] = "FAILED"
            record["notification_error"] = str(exc)
        self.alert_store.put(alert_id, record)
        return self.alert_store.get(alert_id)

    def has_new_closed_bar(self, symbol: str, timeframe: str, watcher_name: str, bar_time: datetime) -> bool:
        key = bar_cursor_key(symbol, timeframe, watcher_name)
        last = self.bar_cursor_store.get(key)
        return last is None or bar_time.isoformat() > last

    def mark_bar_evaluated(self, symbol: str, timeframe: str, watcher_name: str, bar_time: datetime) -> None:
        key = bar_cursor_key(symbol, timeframe, watcher_name)
        self.bar_cursor_store.put(key, bar_time.isoformat())

    def advance_m5(
        self, alert_id: str, m5_request: EntryConfirmationRequest, m5_bar_time: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Spec section 18: call the existing M5 engine only for a persisted candidate
        still WAITING_M5_CONFIRMATION, and only once per closed M5 bar (spec section 16)."""
        record = self.alert_store.get(alert_id)
        if record is None:
            return None
        if record.get("alert_state") != ALERT_STATE_WAITING_M5_CONFIRMATION:
            return record  # already resolved (CONFIRMED/NOT_CONFIRMED) -- candidate does not keep evolving

        if m5_bar_time is not None and not self.has_new_closed_bar(record["symbol"], "M5", alert_id, m5_bar_time):
            return record  # same closed candle already evaluated for this candidate -- no duplicate transition

        result = request_m5_confirmation(m5_request)
        overall = result.overall_state.value
        if overall == "CONFIRMED":
            record["alert_state"] = ALERT_STATE_CONFIRMED
        elif overall == "NOT_CONFIRMED":
            record["alert_state"] = ALERT_STATE_NOT_CONFIRMED
        # PARTIAL / INDETERMINATE -- stays WAITING_M5_CONFIRMATION, candidate remains active
        record["confirmation_state"] = overall
        record["execution_eligible"] = False  # spec section 19/47 -- never true, regardless of outcome
        record["last_m5_evaluation_time"] = datetime.now(timezone.utc).isoformat()

        self.alert_store.put(alert_id, record)
        if m5_bar_time is not None:
            self.mark_bar_evaluated(record["symbol"], "M5", alert_id, m5_bar_time)
        return record
