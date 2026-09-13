"""Configuration-free experiment runner with a hard holdout boundary."""
from __future__ import annotations

import hashlib
import json
from typing import Iterable, Sequence

from .models import CanonicalOccurrence, ExperimentResult
from .policies import ExitPolicy


class ExperimentScopeError(ValueError):
    pass


def _population_hash(occurrences: Sequence[CanonicalOccurrence]) -> str:
    ids = sorted(item.occurrence_id for item in occurrences)
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode("utf-8")).hexdigest()


class CanonicalExperimentRunner:
    """Run exit hypotheses over one fixed population scope.

    The runner accepts explicit IDs rather than a directory, so a discovery caller
    cannot accidentally read holdout records through a broad filesystem glob.
    """

    def __init__(self, population: Iterable[CanonicalOccurrence], allowed_ids: Iterable[str], scope: str):
        all_records = {item.occurrence_id: item for item in population}
        ids = tuple(allowed_ids)
        missing = sorted(set(ids) - set(all_records))
        if missing:
            raise ExperimentScopeError(f"UNKNOWN_OCCURRENCE_IDS: {missing}")
        self._occurrences = tuple(all_records[item] for item in ids)
        self.scope = scope
        self.population_hash = _population_hash(self._occurrences)

    def run(self, policy: ExitPolicy) -> ExperimentResult:
        outcomes = []
        for occurrence in self._occurrences:
            decision = policy.evaluate(occurrence)
            risk = abs(occurrence.entry_price - occurrence.initial_sl)
            if risk <= 0:
                raise ValueError(f"INVALID_RISK_DISTANCE: {occurrence.occurrence_id}")
            direction = 1 if occurrence.side == "LONG" else -1
            gross_R = direction * (decision.exit_price - occurrence.entry_price) / risk
            cost_R = float(occurrence.cost_context.get("total_cost_R", 0.0))
            outcomes.append({
                "occurrence_id": occurrence.occurrence_id, "exit_timestamp": decision.exit_timestamp,
                "exit_reason": decision.exit_reason, "holding_minutes": decision.holding_minutes,
                "gross_R": gross_R, "cost_R": cost_R, "net_R": gross_R - cost_R,
            })
        return ExperimentResult(policy.policy_id, tuple(row["occurrence_id"] for row in outcomes), tuple(outcomes), self.population_hash)

    def run_suite(self, policies: Sequence[ExitPolicy]) -> tuple[ExperimentResult, ...]:
        return tuple(self.run(policy) for policy in policies)


def assert_same_population(results: Sequence[ExperimentResult]) -> None:
    hashes = {result.population_hash for result in results}
    if len(hashes) > 1:
        raise ExperimentScopeError("ENTRY_POPULATION_MUTATED")