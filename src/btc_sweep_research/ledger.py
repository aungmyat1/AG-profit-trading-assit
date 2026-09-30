"""Uncapped BTC sweep-retest RESEARCH OBSERVATION ledger (spec section 21/22).

Built on runtime_state.store.JsonKeyValueStore -- the repo's one established persistence
convention (see strategy_engine/sweep_retest/state_store.py, which follows the identical
pattern: one JSON file, keyed by a stable id, full read/rewrite via JsonKeyValueStore.put).
No file-lock (post_asian_pilot.governor._ExclusiveFileLock) is added here: this ledger is
written from exactly one place (btc_sweep_research.pipeline, invoked by a single runner
process at a time per the --once/--watch CLI, never concurrently) -- the same posture
state_store.py's own SweepRetestStateStore already takes for the identical
JsonKeyValueStore usage pattern, so this does not add a new concurrency assumption beyond
what this package family already relies on.

ARCHITECTURALLY DISTINCT from any simulated-position/trade count (spec section 21/22):
this ledger only ever records "a qualified setup was OBSERVED" (ENTRY_READY reached),
keyed by occurrence_id (strategy_engine.sweep_retest.occurrence_identity.btc_occurrence_id)
-- it has no notion of an open/closed position, P&L, or execution. Re-observing the same
occurrence_id (e.g. the pipeline re-evaluates the same setup on a later poll before it
goes terminal) is a no-op (record() returns False); a genuinely different occurrence
(different sweep/MSS time, different day, different direction) always gets its own row.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any, Dict, Optional

from runtime_state.store import JsonKeyValueStore

from .proposal import BTCSweepResearchProposal

DEFAULT_PATH = "journal/btc_sweep_research/occurrences.json"


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


class BTCResearchLedger:
    def __init__(self, path: str = DEFAULT_PATH):
        self._store = JsonKeyValueStore(path)

    def has(self, occurrence_id: str) -> bool:
        return self._store.get(occurrence_id) is not None

    def get(self, occurrence_id: str) -> Optional[dict]:
        return self._store.get(occurrence_id)

    def record(self, proposal: BTCSweepResearchProposal) -> bool:
        """Records `proposal` under its occurrence_id. Returns True if this was a NEW
        row (genuinely new occurrence), False if this occurrence_id was already present
        (deduplicated re-observation, no-op -- the existing row is never overwritten, so
        the FIRST observation's evidence is always what is preserved)."""
        if self.has(proposal.occurrence_id):
            return False
        raw = {k: _serialize(v) for k, v in dataclasses.asdict(proposal).items()}
        self._store.put(proposal.occurrence_id, raw)
        return True

    def count(self) -> int:
        return len(self._store.all())

    def all(self) -> Dict[str, dict]:
        return self._store.all()
