"""Structured runtime-error provenance (prospective, additive) --
AG_FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_REMEDIATION_V1.

Complements (never replaces) the existing aggregate MonitoringCounters
COUNTER_DATA_ERRORS counter (monitor.py) at the same 3 already-established increment
sites in pipeline.py::_evaluate_pair (asian-window get_candles, build_asian_session_
snapshot, post-session-window get_candles). The aggregate counter alone answers only
"how many times did a runtime error occur"; this log additionally answers which unit/
operation, when, whether it was retried, whether it recovered, and its final state --
without requiring source archaeology (see the prior reconciliation finding referenced in
docs/status/AG_FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_REMEDIATION_STATUS.md).

Built on the same JsonKeyValueStore convention (runtime_state.store) as every other
journal/* store in this repo -- one JSON file, atomic write, restart-durable. No new
persistence architecture is introduced (P12 of the remediation mission).

Historical firewall (P7): this module has no backfill path. It only ever appends a new
event when pipeline.py observes a fresh runtime error/recovery AFTER this code is live --
nothing here reads or reinterprets already-persisted decision/counter records from before
this remediation landed. Old days keep whatever aggregate-only evidence they already had.

Backward compatibility (P13): a persisted decision/counters record from before this
remediation simply has no corresponding entry in this store -- callers must treat a
missing key (or a day with zero events) as "no structured provenance available", never
synthesize recovered=True/False for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from runtime_state.store import JsonKeyValueStore

DEFAULT_RUNTIME_ERROR_LOG_PATH = "journal/post_asian_pilot/runtime_error_log.json"

# The 3 established increment sites this log tracks -- see pipeline.py::_evaluate_pair
# (asian get_candles ~L125, build_asian_session_snapshot DATA_ERROR ~L137,
# post-session-window get_candles ~L170), each already unconditionally paired with a
# MonitoringCounters COUNTER_DATA_ERRORS increment and a data_error_decision save.
OP_ASIAN_CANDLES_FETCH = "ASIAN_CANDLES_FETCH"
OP_ASIAN_SNAPSHOT_BUILD = "ASIAN_SNAPSHOT_BUILD"
OP_POST_SESSION_CANDLES_FETCH = "POST_SESSION_CANDLES_FETCH"

_KNOWN_OPERATIONS = (OP_ASIAN_CANDLES_FETCH, OP_ASIAN_SNAPSHOT_BUILD, OP_POST_SESSION_CANDLES_FETCH)

# Bounded, authority-bearing classification -- never a free-text string (P3). Any
# human-readable detail (e.g. the raw MarketDataError reason_code) travels in
# `error_class`, which is itself already a bounded reason_code from mt5.market_data /
# post_asian_pilot.snapshot, not an ad hoc message.
FINAL_STATE_UNRESOLVED = "UNRESOLVED"
FINAL_STATE_RECOVERED = "RECOVERED"


def _unit_key(strategy_id: str, symbol: str, trading_date: date, reference_session: str, operation: str) -> str:
    return f"{strategy_id}|{symbol}|{trading_date.isoformat()}|{reference_session}|{operation}"


@dataclass(frozen=True)
class RuntimeErrorLog:
    store: JsonKeyValueStore

    @classmethod
    def default(cls, path: str = DEFAULT_RUNTIME_ERROR_LOG_PATH) -> "RuntimeErrorLog":
        return cls(JsonKeyValueStore(path))

    def record_error(
        self, strategy_id: str, symbol: str, trading_date: date, reference_session: str,
        operation: str, error_class: str, now: datetime,
    ) -> Dict[str, Any]:
        """Appends a new failed-attempt event for this exact (unit, operation) identity.
        `attempt` is the 1-based count of failed attempts recorded so far for this unit+
        operation, including this one; `retry_occurred` is True from attempt 2 onward.
        Never mutates or removes a prior event -- each attempt is its own immutable
        record, individually explainable alongside every other symbol/operation's events
        (multiple runtime errors never collapse into one unexplained counter)."""
        if operation not in _KNOWN_OPERATIONS:
            raise ValueError(f"unknown runtime-error operation {operation!r}")
        key = _unit_key(strategy_id, symbol, trading_date, reference_session, operation)
        events: List[Dict[str, Any]] = list(self.store.get(key) or [])
        attempt = len(events) + 1
        event = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "trading_date": trading_date.isoformat(),
            "reference_session": reference_session,
            "operation": operation,
            "error_class": error_class,
            "timestamp": now.isoformat(),
            "attempt": attempt,
            "retry_occurred": attempt > 1,
            "recovered": False,
            "recovered_at": None,
            "final_state": FINAL_STATE_UNRESOLVED,
        }
        events.append(event)
        self.store.put(key, events)
        return event

    def record_recovery(
        self, strategy_id: str, symbol: str, trading_date: date, reference_session: str,
        operation: str, now: datetime,
    ) -> Optional[Dict[str, Any]]:
        """Marks the most recent still-unresolved failed attempt for this (unit,
        operation) as recovered. A no-op (returns None, writes nothing) when there is no
        unresolved prior failure -- an ordinary successful evaluation with no preceding
        error must never create or alter a structured event."""
        if operation not in _KNOWN_OPERATIONS:
            raise ValueError(f"unknown runtime-error operation {operation!r}")
        key = _unit_key(strategy_id, symbol, trading_date, reference_session, operation)
        events: List[Dict[str, Any]] = list(self.store.get(key) or [])
        for idx in range(len(events) - 1, -1, -1):
            if not events[idx].get("recovered"):
                updated = dict(events[idx])
                updated["recovered"] = True
                updated["recovered_at"] = now.isoformat()
                updated["final_state"] = FINAL_STATE_RECOVERED
                events[idx] = updated
                self.store.put(key, events)
                return updated
        return None

    def events_for_date(self, strategy_id: str, trading_date: date) -> List[Dict[str, Any]]:
        """All structured events for this strategy/date across every symbol and
        operation -- used by the reporting layer. Read-only; never mutates and never
        fabricates an event for a key/day that isn't actually present."""
        prefix = f"{strategy_id}|"
        target_date = trading_date.isoformat()
        out: List[Dict[str, Any]] = []
        for key, events in self.store.all().items():
            if not key.startswith(prefix):
                continue
            parts = key.split("|")
            if len(parts) < 3 or parts[2] != target_date:
                continue
            out.extend(events)
        return out
