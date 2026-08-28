"""Append-only per-ticket management journal (spec section 24). One JSON object per
line under journal/trade_management_<ticket>.jsonl -- never rewritten, only appended to,
so the history stays auditable.

completed_intent_ids() is also how validator.validate() learns an action has already
happened, independent of state.py's coarser state machine -- belt-and-suspenders against
double-firing the same milestone (spec section 15).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import FrozenSet, Optional

_CONFIRMED_SUFFIX = "_CONFIRMED"


def _journal_path(ticket: int, base_dir: str = "journal") -> str:
    return os.path.join(base_dir, f"trade_management_{ticket}.jsonl")


def record_event(ticket: int, event: str, base_dir: str = "journal", **payload) -> None:
    path = _journal_path(ticket, base_dir)
    os.makedirs(base_dir, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "ticket": ticket, "event": event}
    entry.update(payload)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_events(ticket: int, base_dir: str = "journal") -> list:
    path = _journal_path(ticket, base_dir)
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def completed_intent_ids(ticket: int, base_dir: str = "journal") -> FrozenSet[str]:
    ids = set()
    for event in read_events(ticket, base_dir):
        if event.get("event", "").endswith(_CONFIRMED_SUFFIX) and event.get("intent_id"):
            ids.add(event["intent_id"])
    return frozenset(ids)
