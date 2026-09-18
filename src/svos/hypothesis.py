"""Hypothesis preregistration + bounded-optimization governance contracts (P5).

A HypothesisContract is frozen BEFORE any optimization starts; its
`preregistration_hash` binds every field except itself (computed with the repository's
canonical hasher, post_asian_pilot.fingerprint). Nothing here performs a search; see
svos.optimization for the bounded optimizer that consumes this contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Tuple

from post_asian_pilot.fingerprint import fingerprint


@dataclass(frozen=True)
class SearchBudget:
    max_candidates: int
    max_search_budget: int  # total candidate evaluations permitted across the search


@dataclass(frozen=True)
class HypothesisContract:
    hypothesis_id: str
    parent_strategy: str
    parent_version: str
    mechanism: str
    single_primary_delta: str
    frozen_dimensions: Mapping[str, object]
    development_dataset: str
    protected_datasets: Tuple[str, ...]  # confirmation / oos / holdout dataset ids
    evaluation_metric: str
    acceptance_rule: Mapping[str, object]
    search_budget: SearchBudget
    preregistration_hash: str = ""  # bound at freeze; empty only before freeze

    def _payload(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "parent_strategy": self.parent_strategy,
            "parent_version": self.parent_version,
            "mechanism": self.mechanism,
            "single_primary_delta": self.single_primary_delta,
            "frozen_dimensions": dict(sorted(self.frozen_dimensions.items())),
            "development_dataset": self.development_dataset,
            "protected_datasets": tuple(sorted(self.protected_datasets)),
            "evaluation_metric": self.evaluation_metric,
            "acceptance_rule": dict(sorted(self.acceptance_rule.items())),
            "search_budget": {
                "max_candidates": self.search_budget.max_candidates,
                "max_search_budget": self.search_budget.max_search_budget,
            },
        }

    def compute_preregistration_hash(self) -> str:
        return fingerprint(self._payload())

    def is_frozen(self) -> bool:
        return bool(self.preregistration_hash)

    def freeze(self) -> "HypothesisContract":
        return replace(self, preregistration_hash=self.compute_preregistration_hash())

    def verify(self) -> bool:
        """True only if the recorded hash matches a recomputation -- i.e. the contract
        has not been edited after freezing."""
        return self.preregistration_hash == self.compute_preregistration_hash()
