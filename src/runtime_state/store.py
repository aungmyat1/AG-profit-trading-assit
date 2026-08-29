"""JsonKeyValueStore: one JSON file per entity type, keyed dict of plain-serializable
records. Same shape as trade_management/claims.py's load_claims/_save_all (full
read/rewrite, atomic via temp-file + os.replace) -- the only established persistence
convention in this repo. Fails loudly on a corrupt file (spec section 31: a state-store
failure must block evaluation, never silently reset to an empty store and risk
re-emitting a duplicate proposal/alert).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


class StateStoreCorrupted(RuntimeError):
    """Raised when a state file exists but cannot be parsed as a JSON object."""


class JsonKeyValueStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> Dict[str, Any]:
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

    def get(self, key: str) -> Optional[Any]:
        return self.load().get(key)

    def all(self) -> Dict[str, Any]:
        return self.load()

    def put(self, key: str, value: Any) -> None:
        data = self.load()
        data[key] = value
        self._save_all(data)

    def remove(self, key: str) -> None:
        data = self.load()
        if key in data:
            del data[key]
            self._save_all(data)

    def _save_all(self, data: Dict[str, Any]) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, default=str)
        os.replace(tmp_path, self.path)
