"""V2-2B durable OpportunityCandidate store + transition ledger.

Reuses runtime_state.store.JsonKeyValueStore for the repository's established
atomic/thread-safe JSON persistence primitive. Candidate and transition history
for one logical occurrence are stored in ONE value under candidate_id, so a
candidate update and its transition cannot be torn across two files/writes.

This is opportunity-domain persistence only. It does not reuse the proposal
ledger keyspace/schema and never converts OpportunityCandidate to CanonicalProposal.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from runtime_state.store import JsonKeyValueStore

from .contracts import CandidateGeometry, OpportunityCandidate
from .transitions import FunnelTransition


class CandidateStoreError(RuntimeError):
    pass


class CandidateConflictError(CandidateStoreError):
    pass


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value is not None else None


def _candidate_to_dict(candidate: OpportunityCandidate) -> Dict[str, Any]:
    raw = asdict(candidate)
    for name in ("detected_at", "last_evaluated_at", "expires_at"):
        value = getattr(candidate, name)
        raw[name] = value.isoformat() if value is not None else None
    if candidate.geometry is not None:
        raw["geometry"]["targets"] = list(candidate.geometry.targets)
    return raw


def _candidate_from_dict(raw: Mapping[str, Any]) -> OpportunityCandidate:
    data = dict(raw)
    data["detected_at"] = _dt(data["detected_at"])
    data["last_evaluated_at"] = _dt(data["last_evaluated_at"])
    data["expires_at"] = _dt(data.get("expires_at"))
    geometry = data.get("geometry")
    if geometry is not None:
        geometry = dict(geometry)
        geometry["targets"] = tuple(geometry.get("targets", ()))
        data["geometry"] = CandidateGeometry(**geometry)
    return OpportunityCandidate(**data)


def _transition_to_dict(transition: FunnelTransition) -> Dict[str, Any]:
    raw = asdict(transition)
    raw["evaluated_at"] = transition.evaluated_at.isoformat()
    raw["reason_codes"] = list(transition.reason_codes)
    return raw


def _transition_from_dict(raw: Mapping[str, Any]) -> FunnelTransition:
    data = dict(raw)
    data["evaluated_at"] = _dt(data["evaluated_at"])
    data["reason_codes"] = tuple(data.get("reason_codes", ()))
    return FunnelTransition(**data)


class CandidateStore:
    """Atomic per-candidate persistence with append-only transition history."""

    def __init__(self, path: str):
        self._store = JsonKeyValueStore(path)

    def get(self, candidate_id: str) -> Optional[OpportunityCandidate]:
        record = self._store.get(candidate_id)
        return None if record is None else _candidate_from_dict(record["candidate"])

    def transitions(self, candidate_id: str) -> Tuple[FunnelTransition, ...]:
        record = self._store.get(candidate_id)
        if record is None:
            return ()
        return tuple(_transition_from_dict(item) for item in record.get("transitions", ()))

    def all_candidates(self) -> Tuple[OpportunityCandidate, ...]:
        records = self._store.all()
        return tuple(_candidate_from_dict(records[key]["candidate"]) for key in sorted(records))

    def persist(self, candidate: OpportunityCandidate, transition: FunnelTransition) -> OpportunityCandidate:
        """Atomically persist a candidate revision and its transition.

        Idempotent replay of the exact same transition is accepted. Conflicting
        reuse of candidate/transition identity or non-contiguous revisions fails
        closed. JsonKeyValueStore's one put is the atomic unit.
        """
        if transition.candidate_id != candidate.candidate_id:
            raise CandidateConflictError("transition candidate_id does not match candidate")
        if candidate.latest_transition_id != transition.transition_id:
            raise CandidateConflictError("candidate latest_transition_id does not match transition")

        existing = self._store.get(candidate.candidate_id)
        candidate_dict = _candidate_to_dict(candidate)
        transition_dict = _transition_to_dict(transition)

        if existing is None:
            if candidate.revision != 1:
                raise CandidateConflictError("first persisted candidate revision must be 1")
            self._store.put(candidate.candidate_id, {
                "candidate": candidate_dict,
                "transitions": [transition_dict],
            })
            return candidate

        previous = _candidate_from_dict(existing["candidate"])
        history: List[Dict[str, Any]] = list(existing.get("transitions", ()))
        by_id = {item["transition_id"]: item for item in history}
        known = by_id.get(transition.transition_id)
        if known is not None:
            if known != transition_dict or _candidate_to_dict(previous) != candidate_dict:
                raise CandidateConflictError("identity reused with different candidate/transition content")
            return previous

        if candidate.occurrence_id != previous.occurrence_id:
            raise CandidateConflictError("occurrence_id changed for existing candidate")
        for field in ("strategy_id", "strategy_version", "strategy_engine_version", "symbol", "market", "venue", "market_data_mode"):
            if getattr(candidate, field) != getattr(previous, field):
                raise CandidateConflictError(f"candidate authority changed: {field}")
        if candidate.revision != previous.revision + 1:
            raise CandidateConflictError("candidate revision must advance by exactly one")
        if transition.from_stage != previous.stage or transition.from_outcome != previous.outcome:
            raise CandidateConflictError("transition does not link from persisted candidate state")

        history.append(transition_dict)
        self._store.put(candidate.candidate_id, {
            "candidate": candidate_dict,
            "transitions": history,
        })
        return candidate
