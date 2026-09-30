"""Restart-safe persistence for SetupState, built on runtime_state.store.JsonKeyValueStore
(the repo's one established persistence convention) -- not a new state-storage mechanism.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Optional

from runtime_state.store import JsonKeyValueStore

from .models import SetupState

DEFAULT_PATH = "journal/ag_sweep_retest_setup_state.json"


def _serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class SweepRetestStateStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self._store = JsonKeyValueStore(path)

    def load(self, setup_id: str) -> Optional[SetupState]:
        raw = self._store.get(setup_id)
        if raw is None:
            return None
        return SetupState(**raw)

    def save(self, state: SetupState) -> None:
        raw = {k: _serialize(v) for k, v in asdict(state).items()}
        self._store.put(state.setup_id, raw)
