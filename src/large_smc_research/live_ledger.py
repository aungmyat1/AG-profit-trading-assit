"""Cross-run persistence for ST_LARGE_SMC_V1's setup-history evidence
(AG_PROPOSAL_RUNTIME_LARGE_SMC_WATCH_AND_PERFORMANCE_HISTORY_V1, narrow-batch scope;
hardened in AG_LARGE_SMC_VERSION_HARDENING_PERFORMANCE_AND_POST_CHECKPOINT_ACTIVATION_V1).

`historical_replay.orchestrator.run_replay` already builds a complete, correct
`SetupLedger` (every E/M/direction combination ever observed, keyed by `setup_id`,
frozen once a row reaches a terminal state) -- see that module's own docstrings. What
does NOT exist yet is persistence of that ledger ACROSS separate runs: every time
`run_replay` is invoked it starts a fresh, in-memory `SetupLedger` and forgets it on
exit. A daily live-batch watcher (scripts/run_large_smc_live_watch.py) re-runs
`run_replay` once per day over a rolling window that overlaps the previous day's window
(so nothing is missed at the boundary) -- this module's only job is to fold each day's
freshly-computed `SetupLedgerRow`s into one durable store on disk, without losing any
row a prior run already saw and without duplicating rows.

TERMINOLOGY (corrected from the prior pass): this is a RESTART-SAFE, IDEMPOTENT UPSERT
STATE STORE, not a fully immutable ledger. A row's `state`/`final_state`/etc. can
legitimately change across runs while a setup is still active (a later replay day
learns more about the same setup_id as it progresses toward ready_time/invalidation/
expiry). It is still loss-free in the sense that matters for research: no row is ever
deleted, and a row already `terminal=True` can never be overwritten again (mirrors
`SetupLedger.observe`'s own terminal-state freeze -- a later run's possibly-stale
replay of the same historical setup_id can never regress an already-final outcome).
See STORAGE_SEMANTICS below for the exact machine-checkable claims this module makes.

Built on `runtime_state.store.JsonKeyValueStore`, the same one-JSON-file-per-store
convention `btc_sweep_research.ledger.BTCResearchLedger` already uses.

VERSION-SAFE IDENTITY: the underlying `setup_id`/occurrence-identity contract
(historical_replay.orchestrator, proposals/occurrence_identity.py) is unchanged --
this module does not alter or duplicate that identity scheme. It composes a separate,
storage-only key `f"{strategy_id}:{strategy_version}:{setup_id}"` so the SAME setup_id
computed under a future strategy_version can never collide with -- or be silently
folded into -- this version's row. `setup_id` itself remains present, unmodified, in
the stored record for anyone reading it directly.

One store instance is scoped to exactly one (strategy_id, strategy_version): if the
underlying JSON file already contains a row attributed to a different strategy_id or
strategy_version than the store was constructed for, every write is refused
(StrategyIdentityMismatch) rather than silently commingling two versions' evidence in
one file -- a version bump must point at a new path, never reuse the previous
version's file.

This module records the FULL funnel, not just successes: WATCH-only, NO_TRADE,
EXPIRED, and INVALIDATED rows are stored exactly like RESEARCH_QUALIFIED-equivalent
rows -- required for honest performance research (AGENTS.md fail-closed rule).
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any, Dict, Tuple

from runtime_state.store import JsonKeyValueStore

from historical_replay.orchestrator import SetupLedgerRow
from large_smc_research.decision import STRATEGY_ID
from large_smc_research.engine import STRATEGY_VERSION

DEFAULT_PATH = "journal/large_smc_research/setup_ledger.json"
EVIDENCE_BASIS_DAILY_BATCH = "FORWARD_RESEARCH_DAILY_BATCH"

# One file per (strategy_id, strategy_version) -- see module docstring "VERSION-SAFE
# IDENTITY". Machine-checkable storage-semantics claims a caller (a status report, a
# test) can assert against without re-deriving them from behavior.
STORAGE_SEMANTICS = {
    "restart_safe": True,
    "idempotent": True,
    "rows_deleted": False,
    "terminal_rows_frozen": True,
    "current_state_mutable_until_terminal": True,
    "storage_immutability": False,  # non-terminal rows may legitimately change; see docstring
}


class StrategyIdentityMismatch(RuntimeError):
    """Raised when the persisted store already contains a row attributed to a
    different strategy_id/strategy_version than this LargeSMCSetupLedger instance is
    scoped to. No row is written when this is raised (fail closed, all-or-nothing)."""


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _storage_key(strategy_id: str, strategy_version: str, setup_id: str) -> str:
    return f"{strategy_id}:{strategy_version}:{setup_id}"


class LargeSMCSetupLedger:
    """Durable, restart-safe fold of `SetupLedgerRow`s across separate `run_replay`
    invocations, scoped to exactly one (strategy_id, strategy_version). One row per
    setup_id within that scope; never deletes; never overwrites a row already stored
    as terminal; refuses to write anything if the store already holds a foreign
    strategy identity (see StrategyIdentityMismatch)."""

    def __init__(
        self,
        path: str = DEFAULT_PATH,
        strategy_id: str = STRATEGY_ID,
        strategy_version: str = STRATEGY_VERSION,
        application_release: str = "AG_TRADE_ASSISTANT_V1_0_3",
        evidence_basis: str = EVIDENCE_BASIS_DAILY_BATCH,
    ):
        self._store = JsonKeyValueStore(path)
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.application_release = application_release
        self.evidence_basis = evidence_basis

    def _key(self, setup_id: str) -> str:
        return _storage_key(self.strategy_id, self.strategy_version, setup_id)

    def get(self, setup_id: str) -> Dict[str, Any]:
        return self._store.get(self._key(setup_id))

    def count(self) -> int:
        return len(self._store.all())

    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._store.all()

    def _assert_no_foreign_identity(self) -> None:
        for key, record in self._store.all().items():
            row_strategy_id = record.get("strategy_id")
            row_strategy_version = record.get("strategy_version")
            if row_strategy_id is None and row_strategy_version is None:
                continue  # pre-hardening row written by the earlier, unversioned pass
            if row_strategy_id != self.strategy_id or row_strategy_version != self.strategy_version:
                raise StrategyIdentityMismatch(
                    f"STRATEGY_IDENTITY_MISMATCH: store already contains {key!r} attributed to "
                    f"strategy_id={row_strategy_id!r} strategy_version={row_strategy_version!r}, "
                    f"but this ledger is scoped to strategy_id={self.strategy_id!r} "
                    f"strategy_version={self.strategy_version!r}. A version bump must use a new "
                    "store path, never commingle with a prior version's rows."
                )

    def upsert_many(self, rows: Tuple[SetupLedgerRow, ...]) -> Dict[str, int]:
        """Folds `rows` (typically `ReplayResult.setup_ledger` from one `run_replay`
        call) into the durable store, tagging each with this ledger's strategy
        identity/application_release/evidence_basis. Returns counts for the caller's
        report -- `new`, `updated` (already present, not yet terminal, row content
        changed), `unchanged` (already present, identical), and
        `skipped_terminal_frozen` (already present AND already terminal -- the
        existing row is kept verbatim even if `rows` disagrees).

        Raises StrategyIdentityMismatch, writing nothing, if the store already holds a
        row attributed to a different strategy identity than this instance."""
        self._assert_no_foreign_identity()

        counts = {"new": 0, "updated": 0, "unchanged": 0, "skipped_terminal_frozen": 0}
        for row in rows:
            key = self._key(row.setup_id)
            existing = self._store.get(key)
            new_raw = {k: _serialize(v) for k, v in dataclasses.asdict(row).items()}
            new_raw["application_release"] = self.application_release
            new_raw["strategy_id"] = self.strategy_id
            new_raw["strategy_version"] = self.strategy_version
            new_raw["evidence_basis"] = self.evidence_basis

            if existing is None:
                self._store.put(key, new_raw)
                counts["new"] += 1
                continue
            if existing.get("terminal") is True:
                counts["skipped_terminal_frozen"] += 1
                continue
            if existing == new_raw:
                counts["unchanged"] += 1
                continue
            self._store.put(key, new_raw)
            counts["updated"] += 1
        return counts
