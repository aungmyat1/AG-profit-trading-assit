"""WP8 Persistent Proposal Ledger (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1).

Durable, restart-safe canonical proposal storage keyed by proposal_envelope_id (WP7's
adopted canonical proposal_id -- see the WP0 identity-reconciliation section of
docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md). Reuses
runtime_state.store.JsonKeyValueStore verbatim (this repo's established atomic,
thread-safe persistence convention -- already used by post_asian_pilot and
proposals/lifecycle.py) rather than inventing a new storage mechanism.

Only PROPOSAL_READY envelopes are recorded as canonical proposals (plan WP8: "Only an
accepted formation attempt creates a proposal. NO_TRADE, WATCHING, data failures, and
rejected formations remain evaluation evidence and must not inflate the proposal
population.") -- record_proposal() raises ProposalLedgerError for any other
proposal_state, matching this repo's fail-closed convention (never silently drop, never
silently store the wrong thing under a proposal identity).

Idempotency: recording the same proposal_envelope_id again with IDENTICAL geometry
(direction/entry/stop/targets) is a no-op that returns the ALREADY-persisted original
unchanged -- safe across rerun, scheduler overlap, API retry, and restart (a fresh
ProposalLedger instance over the same path sees the same record; JsonKeyValueStore's
per-path lock already serializes concurrent writers within one process). Recording the
same identity again with DIFFERENT geometry is preserved as a linked correction
(version incremented, correction_of set, original entry kept in history) -- original
geometry is never overwritten in place, per the plan's "preserve immutable original
geometry, append linked corrections, never rewrite historical evidence" invariant.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

from runtime_state.store import JsonKeyValueStore

from .models import (
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    PROPOSAL_READY,
    WatcherOccurrenceTimestamps,
)

DEFAULT_LEDGER_PATH = "state/proposal_ledger/proposal_ledger.json"


class ProposalLedgerError(RuntimeError):
    pass


def _to_record(envelope: CanonicalProposal) -> Dict[str, Any]:
    return dataclasses.asdict(envelope)


def _from_record(record: Dict[str, Any]) -> CanonicalProposal:
    data = dict(record)
    data["data_provenance"] = DataProvenance(**data["data_provenance"])
    data["cost_assumptions"] = CostAssumptions(**data["cost_assumptions"])
    data["timestamps"] = WatcherOccurrenceTimestamps(**data["timestamps"])
    data["targets"] = tuple(data["targets"])
    data["reasons"] = tuple(data["reasons"])
    return CanonicalProposal(**data)


def _geometry_matches(a: CanonicalProposal, b: CanonicalProposal) -> bool:
    return (a.direction, a.entry, a.stop, a.targets) == (b.direction, b.entry, b.stop, b.targets)


class ProposalLedger:
    def __init__(self, path: str = DEFAULT_LEDGER_PATH):
        self._store = JsonKeyValueStore(path)

    def record_proposal(self, envelope: CanonicalProposal) -> CanonicalProposal:
        if envelope.proposal_state != PROPOSAL_READY:
            raise ProposalLedgerError(
                f"PROPOSAL_LEDGER_REJECTED_NON_READY: proposal_state={envelope.proposal_state!r} "
                "-- only PROPOSAL_READY envelopes may be persisted as canonical proposals"
            )

        key = envelope.proposal_envelope_id
        existing_entry = self._store.get(key)
        if existing_entry is None:
            self._store.put(key, {"current": _to_record(envelope), "history": []})
            return envelope

        current = _from_record(existing_entry["current"])
        if _geometry_matches(current, envelope):
            return current  # idempotent rerun/overlap/restart -- return the original, unmodified

        next_version = current.version + 1
        corrected = dataclasses.replace(
            envelope, version=next_version, correction_of=current.proposal_envelope_id,
        )
        new_history = list(existing_entry["history"]) + [existing_entry["current"]]
        self._store.put(key, {"current": _to_record(corrected), "history": new_history})
        return corrected

    def get_proposal(self, proposal_envelope_id: str) -> Optional[CanonicalProposal]:
        entry = self._store.get(proposal_envelope_id)
        if entry is None:
            return None
        return _from_record(entry["current"])

    def list_active_proposals(self) -> List[CanonicalProposal]:
        return [_from_record(entry["current"]) for entry in self._store.all().values()]

    def get_history(self, proposal_envelope_id: str) -> List[CanonicalProposal]:
        entry = self._store.get(proposal_envelope_id)
        if entry is None:
            return []
        return [_from_record(r) for r in entry["history"]] + [_from_record(entry["current"])]
