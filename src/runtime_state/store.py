"""JsonKeyValueStore: one JSON file per entity type, keyed dict of plain-serializable
records. Same shape as trade_management/claims.py's load_claims/_save_all (full
read/rewrite, atomic via temp-file + os.replace) -- the only established persistence
convention in this repo. Fails loudly on a corrupt file (spec section 31: a state-store
failure must block evaluation, never silently reset to an empty store and risk
re-emitting a duplicate proposal/alert).

Concurrency fix (AG_DEMO_EXECUTION_GATEWAY_PHASE_D2_API_AND_EXECUTION_WIRING_V1,
2026-09-08): the original implementation had no locking at all around its
load-modify-save cycle. That is not merely a Windows test artifact -- it is a genuine
TOCTOU race (two threads' `load()` can both miss each other's pending `put()`, silently
losing an update) and, on Windows specifically, a concurrent reader's open file handle
can make a writer's `os.replace()` raise `PermissionError` (Windows file-locking is
stricter than POSIX about a rename/replace targeting a path someone else has open).
`authorization.store.ExecutionApprovalStore`'s O_EXCL claim-lock already correctly
decides *which* caller wins a race -- that primitive was never the problem. The problem
was that the winner's subsequent JSON write (via this class) could still race a loser's
concurrent read of the same file. Fixed by serializing every read AND write to a given
path through one `threading.Lock` per absolute path (shared across every
`JsonKeyValueStore` instance pointing at that path, since a real deployment may
construct a fresh store per request/callback rather than reusing one instance), plus a
short bounded retry around `os.replace()` itself as defense-in-depth against transient
external interference (AV/indexer) even when our own callers are correctly serialized.

Scope: this guarantees exactly-once semantics for concurrent *threads within one
process* -- the actual deployment shape here (one execution-runtime process owns the
one MT5 terminal connection; see AGENTS.md "Authority order"). It does not add
cross-process/cross-host locking; nothing in this repository runs this store from more
than one process today, so that is a documented scope boundary, not a silent gap.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

_PATH_LOCKS: Dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()

_REPLACE_MAX_ATTEMPTS = 5
_REPLACE_RETRY_BASE_SECONDS = 0.01  # 10ms, 20ms, 40ms, 80ms, 160ms -- ~310ms worst case


class StateStoreCorrupted(RuntimeError):
    """Raised when a state file exists but cannot be parsed as a JSON object."""


def _lock_for(path: str) -> threading.Lock:
    """One lock per absolute path, shared across every JsonKeyValueStore instance that
    targets it -- a per-instance lock would not help two independently-constructed
    stores pointed at the same file (e.g. a fresh ExecutionApprovalStore built per HTTP
    request/Telegram callback)."""
    key = os.path.abspath(path)
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


class JsonKeyValueStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = _lock_for(path)

    def load(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._load_unlocked().get(key)

    def all(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            data = self._load_unlocked()
            data[key] = value
            self._save_all_unlocked(data)

    def remove(self, key: str) -> None:
        with self._lock:
            data = self._load_unlocked()
            if key in data:
                del data[key]
                self._save_all_unlocked(data)

    def _load_unlocked(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise StateStoreCorrupted(f"STATE_STORE_UNAVAILABLE: cannot read {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise StateStoreCorrupted(f"STATE_STORE_UNAVAILABLE: {self.path} did not parse to a JSON object")
        return raw

    def _save_all_unlocked(self, data: Dict[str, Any]) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        # Per-call-unique tmp name (not just f"{path}.tmp"): two callers that ever did
        # reach this point concurrently (should not happen now that the path lock
        # covers this whole method, but kept as defense-in-depth) must never share one
        # tmp file.
        tmp_path = f"{self.path}.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, default=str)
        self._replace_with_retry(tmp_path, self.path)

    @staticmethod
    def _replace_with_retry(tmp_path: str, final_path: str) -> None:
        """Windows can transiently refuse os.replace() while an external process (AV,
        indexer) briefly holds the target open, even with no contention from our own
        callers. Bounded retry, not a silent infinite loop -- re-raises the last error
        if it never clears."""
        last_exc: Optional[OSError] = None
        for attempt in range(_REPLACE_MAX_ATTEMPTS):
            try:
                os.replace(tmp_path, final_path)
                return
            except PermissionError as exc:
                last_exc = exc
                if attempt < _REPLACE_MAX_ATTEMPTS - 1:
                    time.sleep(_REPLACE_RETRY_BASE_SECONDS * (2 ** attempt))
        assert last_exc is not None
        raise last_exc
