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
import hashlib
import re
from datetime import datetime, timezone

_EXECUTED_EVENT = "ORDER_EXECUTED"
_LEGACY_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _journal_path(command_id: str, base_dir: str = "journal") -> str:
    digest = hashlib.sha256(command_id.encode("utf-8")).hexdigest()
    return os.path.join(base_dir, f"execution_{digest}.jsonl")


def _claim_path(command_id: str, base_dir: str = "journal") -> str:
    digest = hashlib.sha256(command_id.encode("utf-8")).hexdigest()
    return os.path.join(base_dir, f"execution_{digest}.claim")


def _legacy_journal_path(command_id: str, base_dir: str) -> str | None:
    if not _LEGACY_SAFE_ID.fullmatch(command_id):
        return None
    return os.path.join(base_dir, f"execution_{command_id}.jsonl")


def claim_command(command_id: str, base_dir: str = "journal") -> bool:
    """Atomically reserve one command ID across threads and processes.

    Claims deliberately survive process restarts. A crash after acquiring ownership is
    fail-closed: the same command ID cannot be submitted again without operator review.
    """
    if has_executed(command_id, base_dir):
        return False
    os.makedirs(base_dir, exist_ok=True)
    path = _claim_path(command_id, base_dir)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command_id": command_id,
        "state": "CLAIMED",
    }
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return True


def record_event(command_id: str, event: str, base_dir: str = "journal", **payload) -> None:
    path = _journal_path(command_id, base_dir)
    os.makedirs(base_dir, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "command_id": command_id, "event": event}
    entry.update(payload)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def read_events(command_id: str, base_dir: str = "journal") -> list:
    events = []
    paths = [_journal_path(command_id, base_dir)]
    legacy_path = _legacy_journal_path(command_id, base_dir)
    if legacy_path is not None and legacy_path != paths[0]:
        paths.append(legacy_path)
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    return events


def has_executed(command_id: str, base_dir: str = "journal") -> bool:
    return any(event.get("event") == _EXECUTED_EVENT for event in read_events(command_id, base_dir))
