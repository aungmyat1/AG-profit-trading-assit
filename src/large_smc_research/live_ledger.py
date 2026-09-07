"""Cross-run persistence for ST_LARGE_SMC_V1's setup-history evidence
(AG_PROPOSAL_RUNTIME_LARGE_SMC_WATCH_AND_PERFORMANCE_HISTORY_V1, narrow-batch scope).

`historical_replay.orchestrator.run_replay` already builds a complete, correct
`SetupLedger` (every E/M/direction combination ever observed, keyed by `setup_id`,
frozen once a row reaches a terminal state) -- see that module's own docstrings. What
does NOT exist yet is persistence of that ledger ACROSS separate runs: every time
`run_replay` is invoked it starts a fresh, in-memory `SetupLedger` and forgets it on
exit. A daily live-batch watcher (scripts/run_large_smc_live_watch.py) re-runs
`run_replay` once per day over a rolling window that overlaps the previous day's window
(so nothing is missed at the boundary) -- this module's only job is to fold each day's
freshly-computed `SetupLedgerRow`s into one durable, restart-safe store on disk, without
losing any row a prior run already saw and without duplicating rows.

Built on `runtime_state.store.JsonKeyValueStore`, the same one-JSON-file-per-store
convention `btc_sweep_research.ledger.BTCResearchLedger` already uses. Unlike that
ledger (which is genuinely write-once because Bybit occurrence detection reports a
setup only once, at ENTRY_READY), a Large-SMC `SetupLedgerRow` legitimately CHANGES
across runs while a setup is still active (later replay days learn more about the same
setup_id as it progresses toward ready_time/invalidation/expiry) -- so this store is an
UPSERT (latest-known-state-per-setup_id), not a strict append-once ledger. It is still
loss-free: a row is never deleted, and a row already `terminal=True` is never
overwritten (mirrors `SetupLedger.observe`'s own terminal-state freeze, so a later run's
possibly-stale replay of the same historical setup_id can never regress an already-final
outcome).

This module records the FULL funnel, not just successes: WATCH-only, NO_TRADE,
EXPIRED, and INVALIDATED rows are stored exactly like RESEARCH_QUALIFIED-equivalent
rows -- required for honest performance research (AGENTS.md fail-closed rule; task
section 21, "never drop failed Large-SMC setups").
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any, Dict, Tuple

from runtime_state.store import JsonKeyValueStore

from historical_replay.orchestrator import SetupLedgerRow

DEFAULT_PATH = "journal/large_smc_research/setup_ledger.json"


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


class LargeSMCSetupLedger:
    """Durable, restart-safe fold of `SetupLedgerRow`s across separate `run_replay`
    invocations. One row per `setup_id`; never deletes; never overwrites a row already
    stored as terminal."""

    def __init__(self, path: str = DEFAULT_PATH):
        self._store = JsonKeyValueStore(path)

    def get(self, setup_id: str) -> Dict[str, Any]:
        return self._store.get(setup_id)

    def count(self) -> int:
        return len(self._store.all())

    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._store.all()

    def upsert_many(self, rows: Tuple[SetupLedgerRow, ...]) -> Dict[str, int]:
        """Folds `rows` (typically `ReplayResult.setup_ledger` from one `run_replay`
        call) into the durable store. Returns counts for the caller's report --
        `new` (setup_id not seen before this call), `updated` (already present,
        not yet terminal, row content changed), `unchanged` (already present,
        identical), and `skipped_terminal_frozen` (already present AND already
        terminal -- per this store's freeze rule, the existing row is kept verbatim
        even if `rows` disagrees, since a terminal outcome must never regress)."""
        counts = {"new": 0, "updated": 0, "unchanged": 0, "skipped_terminal_frozen": 0}
        for row in rows:
            existing = self._store.get(row.setup_id)
            new_raw = {k: _serialize(v) for k, v in dataclasses.asdict(row).items()}
            if existing is None:
                self._store.put(row.setup_id, new_raw)
                counts["new"] += 1
                continue
            if existing.get("terminal") is True:
                counts["skipped_terminal_frozen"] += 1
                continue
            if existing == new_raw:
                counts["unchanged"] += 1
                continue
            self._store.put(row.setup_id, new_raw)
            counts["updated"] += 1
        return counts
