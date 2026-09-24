"""Small append-only, hash-chained JSONL ledger primitive used by the program registry."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from post_asian_pilot.fingerprint import fingerprint

_RESERVED = frozenset({"sequence", "previous_hash", "event_sha256"})


class HashChainError(ValueError):
    pass


def _lock(handle: Any, *, exclusive: bool) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        mode = msvcrt.LK_LOCK if exclusive else msvcrt.LK_RLCK
        msvcrt.locking(handle.fileno(), mode, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)


def _unlock(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _parse_lines(text: str, genesis_hash: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    previous = genesis_hash
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise HashChainError(f"blank line at line {line_number}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HashChainError(f"invalid JSON at line {line_number}") from exc
        if not isinstance(record, dict):
            raise HashChainError(f"event at line {line_number} is not an object")
        event_hash = record.get("event_sha256")
        payload = {key: value for key, value in record.items() if key != "event_sha256"}
        if record.get("sequence") != len(events) + 1:
            raise HashChainError(f"sequence mismatch at line {line_number}")
        if record.get("previous_hash") != previous:
            raise HashChainError(f"previous_hash mismatch at line {line_number}")
        if event_hash != fingerprint(payload):
            raise HashChainError(f"event hash mismatch at line {line_number}")
        previous = event_hash
        events.append(record)
    return events


def read_chained_events(path: Path, genesis_hash: str) -> List[Dict[str, Any]]:
    """Read and verify the whole chain. Any truncation/tampering fails closed."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        _lock(handle, exclusive=False)
        try:
            return _parse_lines(handle.read(), genesis_hash)
        finally:
            _unlock(handle)


def append_chained_event(
    path: Path,
    genesis_hash: str,
    payload: Mapping[str, Any],
    *,
    precondition: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
) -> Dict[str, Any]:
    """Append one fsynced event while holding a process-safe exclusive file lock."""
    collision = _RESERVED.intersection(payload)
    if collision:
        raise HashChainError(f"event payload uses reserved keys: {', '.join(sorted(collision))}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # a+ gives one persistent inode for the lock and append; Windows also creates the
    # file before locking. The chain is re-read while locked to serialize sequence/hash.
    with path.open("a+", encoding="utf-8", newline="\n") as handle:
        _lock(handle, exclusive=True)
        try:
            handle.seek(0)
            existing = _parse_lines(handle.read(), genesis_hash)
            if precondition is not None:
                precondition(existing)
            previous_hash = existing[-1]["event_sha256"] if existing else genesis_hash
            record: Dict[str, Any] = {
                "sequence": len(existing) + 1,
                "previous_hash": previous_hash,
                **dict(payload),
            }
            record["event_sha256"] = fingerprint(record)
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
            handle.seek(0, os.SEEK_END)
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            return record
        finally:
            _unlock(handle)


__all__ = ["HashChainError", "append_chained_event", "read_chained_events"]
