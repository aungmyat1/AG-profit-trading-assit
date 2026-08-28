"""Append-only per-command execution journal. One JSON object per line under
journal/execution_<command_id>.jsonl -- never rewritten, only appended to, so the
history stays auditable. Mirrors trade_management/journal.py's existing convention
exactly (same append-only shape, same journal/ directory) rather than inventing a
second logging format.

execution/executor.py's duplicate-protection check reads completed_command_ids() to
decide whether a command_id has already resulted in a real order_send -- belt-and-
suspenders against double-firing the same "execute it" instruction twice.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import FrozenSet

_EXECUTED_EVENT = "ORDER_EXECUTED"


def _journal_path(command_id: str, base_dir: str = "journal") -> str:
    return os.path.join(base_dir, f"execution_{command_id}.jsonl")


def record_event(command_id: str, event: str, base_dir: str = "journal", **payload) -> None:
    path = _journal_path(command_id, base_dir)
    os.makedirs(base_dir, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "command_id": command_id, "event": event}
    entry.update(payload)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def read_events(command_id: str, base_dir: str = "journal") -> list:
    path = _journal_path(command_id, base_dir)
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def has_executed(command_id: str, base_dir: str = "journal") -> bool:
    return any(event.get("event") == _EXECUTED_EVENT for event in read_events(command_id, base_dir))
