"""Research-only append-only crypto signal lifecycle ledger (C15-CRYPTO).

This module has no broker, READY, registry or strategy-engine authority. Events are
pure data and can be replayed after restart without changing their sequence.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

EVENT_TYPES = {"EMIT", "WITHDRAWN", "EXPIRE", "REISSUE", "FILL"}


class EventOrderError(ValueError):
    """An event is out of chronological order or conflicts with an earlier id."""


class SignalEventLedger:
    def __init__(self, events: Sequence[Mapping[str, Any]] = ()) -> None:
        self.events: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self._state: dict[str, str] = {}
        self._last_time: Optional[datetime] = None
        for event in events:
            self._load(event)

    @staticmethod
    def event_id(kind: str, at: datetime, signal_id: str, reason: str) -> str:
        raw = f"{kind}|{at.isoformat()}|{signal_id}|{reason}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _load(self, source: Mapping[str, Any]) -> None:
        event = dict(source)
        if event.get("type") not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {event.get('type')}")
        at = datetime.fromisoformat(str(event["bar_close_utc"]))
        if at.tzinfo is None:
            raise ValueError("event timestamp must be timezone-aware")
        if self._last_time is not None and at < self._last_time:
            raise EventOrderError("out-of-order event timestamp")
        if event.get("seq") != len(self.events):
            raise EventOrderError("event sequence is not contiguous")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id is required")
        prior = self._by_id.get(event_id)
        if prior is not None:
            if prior != event:
                raise EventOrderError("conflicting duplicate event id")
            return
        self.events.append(event)
        self._by_id[event_id] = event
        signal_id = str(event["signal_id"])
        kind = event["type"]
        if kind in ("EMIT", "REISSUE"):
            self._state[signal_id] = "ACTIVE" if event.get("freshness") == "FRESH" else "EXPIRED"
        elif kind == "FILL":
            if self._state.get(signal_id) != "ACTIVE":
                raise EventOrderError("fill must follow an active emission")
            self._state[signal_id] = "FILLED"
        elif kind == "WITHDRAWN":
            if self._state.get(signal_id) == "FILLED":
                raise EventOrderError("a filled signal cannot be withdrawn")
            self._state[signal_id] = "WITHDRAWN"
        elif kind == "EXPIRE":
            if self._state.get(signal_id) != "FILLED":
                self._state[signal_id] = "EXPIRED"
        self._last_time = at

    def append(self, kind: str, at: datetime, signal_id: str, reason: str, **fields: Any) -> Optional[dict[str, Any]]:
        if kind not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {kind}")
        if at.tzinfo is None:
            raise ValueError("event timestamp must be timezone-aware")
        event_id = self.event_id(kind, at, signal_id, reason)
        candidate = {"seq": len(self.events), "event_id": event_id, "type": kind,
                     "bar_close_utc": at.isoformat(), "signal_id": signal_id, "reason": reason, **fields}
        prior = self._by_id.get(event_id)
        if prior is not None:
            if {k: v for k, v in prior.items() if k != "seq"} != {k: v for k, v in candidate.items() if k != "seq"}:
                raise EventOrderError("conflicting duplicate event id")
            return prior
        if self._last_time is not None and at < self._last_time:
            raise EventOrderError("out-of-order event timestamp")
        current = self._state.get(signal_id)
        if kind == "FILL" and current != "ACTIVE":
            raise EventOrderError("only an active unexpired signal may be filled")
        if kind == "WITHDRAWN" and current == "FILLED":
            return None
        self._load(candidate)
        return self.events[-1]

    def state(self, signal_id: str) -> Optional[str]:
        return self._state.get(signal_id)

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self.events]

    @classmethod
    def replay(cls, events: Sequence[Mapping[str, Any]]) -> "SignalEventLedger":
        return cls(events)
