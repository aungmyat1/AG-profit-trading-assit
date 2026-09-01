"""Lightweight operational counters (spec section 21) -- NOT high-volume per-poll
telemetry, just event counts for the end-of-window report: MT5 disconnects, data
errors, stale-data events, new-closed-M15 cycles, READY transitions, proposal
creations, restart-recovery events, duplicate-suppression events, snapshot conflicts.
Built on the same JsonKeyValueStore convention as every other journal/* store.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from runtime_state.store import JsonKeyValueStore

DEFAULT_COUNTERS_PATH = "journal/post_asian_pilot/monitoring_counters.json"

COUNTER_MT5_DISCONNECTS = "mt5_disconnects"
COUNTER_DATA_ERRORS = "data_errors"
COUNTER_STALE_DATA = "stale_data_events"
COUNTER_NEW_CLOSED_M15 = "new_closed_m15_cycles"
COUNTER_READY_TRANSITIONS = "ready_transitions"
COUNTER_PROPOSALS_CREATED = "proposals_created"
COUNTER_RESTART_RECOVERY = "restart_recovery_events"
COUNTER_DUPLICATE_SUPPRESSED = "duplicate_suppressed_events"
COUNTER_SNAPSHOT_CONFLICTS = "snapshot_conflicts"

_ALL_COUNTERS = (
    COUNTER_MT5_DISCONNECTS, COUNTER_DATA_ERRORS, COUNTER_STALE_DATA, COUNTER_NEW_CLOSED_M15,
    COUNTER_READY_TRANSITIONS, COUNTER_PROPOSALS_CREATED, COUNTER_RESTART_RECOVERY,
    COUNTER_DUPLICATE_SUPPRESSED, COUNTER_SNAPSHOT_CONFLICTS,
)


@dataclass(frozen=True)
class MonitoringCounters:
    store: JsonKeyValueStore

    @classmethod
    def default(cls, path: str = DEFAULT_COUNTERS_PATH) -> "MonitoringCounters":
        return cls(JsonKeyValueStore(path))

    @staticmethod
    def _key(strategy_id: str, trading_date: date) -> str:
        return f"{strategy_id}:{trading_date.isoformat()}"

    def snapshot(self, strategy_id: str, trading_date: date) -> dict:
        record = self.store.get(self._key(strategy_id, trading_date)) or {}
        return {name: int(record.get(name, 0)) for name in _ALL_COUNTERS}

    def increment(self, strategy_id: str, trading_date: date, counter: str, by: int = 1) -> int:
        if counter not in _ALL_COUNTERS:
            raise ValueError(f"unknown counter {counter!r}")
        key = self._key(strategy_id, trading_date)
        record = self.store.get(key) or {name: 0 for name in _ALL_COUNTERS}
        record[counter] = int(record.get(counter, 0)) + by
        self.store.put(key, record)
        return record[counter]
