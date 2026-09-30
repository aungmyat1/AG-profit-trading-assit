"""Append-only, immutable archive for canonical daily report JSON. Reuses the same
atomic temp-file + os.replace write convention as runtime_state.store.JsonKeyValueStore
-- no new persistence mechanism invented.

A report is compared by its full content EXCLUDING generated_at_utc (the one field
expected to legitimately differ between two runs of an otherwise-identical
evaluation): an identical re-generation is an idempotent no-op (same file, no
duplicate), and a semantically different re-generation for an already-archived date is
preserved as a numbered correction record -- the original file is never overwritten
(spec: "historical daily evidence must never be silently overwritten").

Generic over report_type (e.g. "fx", "btc", "combined") so this is the one archive
helper for all of them -- not a per-domain reimplementation.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
from typing import Any, Dict, Optional

DEFAULT_ARCHIVE_ROOT = "journal/reports"


def _content_key(report: Dict[str, Any]) -> Dict[str, Any]:
    stripped = copy.deepcopy(report)
    stripped.pop("generated_at_utc", None)
    return stripped


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)
    os.replace(tmp_path, path)


def _read(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def archive_path(report_type: str, trading_date: dt.date, root: str = DEFAULT_ARCHIVE_ROOT) -> str:
    return os.path.join(root, report_type, str(trading_date.year), f"{trading_date.isoformat()}.json")


def write_report(
    report_type: str, trading_date: dt.date, report: Dict[str, Any],
    root: str = DEFAULT_ARCHIVE_ROOT, correction_reason: Optional[str] = None,
) -> str:
    """Idempotent, restart-safe. Returns the path actually written -- or the
    pre-existing path unchanged if this call was a no-op (identical content)."""
    base_path = archive_path(report_type, trading_date, root)
    existing = _read(base_path)

    if existing is None:
        _atomic_write(base_path, report)
        return base_path

    if _content_key(existing) == _content_key(report):
        return base_path  # identical re-generation -- idempotent no-op, not a re-write

    directory = os.path.dirname(base_path)
    stem = trading_date.isoformat()
    n = 1
    while os.path.exists(os.path.join(directory, f"{stem}.correction-{n:03d}.json")):
        n += 1
    correction_path = os.path.join(directory, f"{stem}.correction-{n:03d}.json")
    supersedes = base_path if n == 1 else os.path.join(directory, f"{stem}.correction-{n - 1:03d}.json")
    correction_record = {
        "original_record_identity": base_path,
        "correction_reason": correction_reason or "REGENERATED_WITH_DIFFERENT_CONTENT",
        "corrected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "supersedes": supersedes,
        "new_record": report,
    }
    _atomic_write(correction_path, correction_record)
    return correction_path
