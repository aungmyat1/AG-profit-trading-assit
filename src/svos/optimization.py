"""Bounded optimization (P6) -- controlled candidate evaluation under a frozen
HypothesisContract. Hard requirements enforced:

  * MAX_CANDIDATES / MAX_SEARCH_BUDGET never exceeded.
  * DEVELOPMENT_DATA_ONLY: any evaluation against a protected dataset
    (confirmation / oos / holdout) raises ProtectedDataAccessError.
  * Every tested candidate and its result are frozen (immutable, lineage-retaining).
  * If no candidate meets the preregistered acceptance rule -> HYPOTHESIS_NOT_SUPPORTED;
    the optimizer never auto-launches another search.

Reuses external_candidate.models.DatasetRole for dataset roles (no new vocabulary).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from external_candidate.models import DatasetRole
from post_asian_pilot.fingerprint import fingerprint

from .hypothesis import HypothesisContract

# The canonical "development" data role for bounded optimization is DatasetRole.
# OPTIMIZATION. The mission's "DEVELOPMENT_DATA_ONLY" requirement maps onto it; no new
# role vocabulary is introduced.
DEVELOPMENT_ROLE = DatasetRole.OPTIMIZATION.value
_PROTECTED_ROLES = frozenset({
    DatasetRole.VALIDATION.value,
    DatasetRole.HOLDOUT.value,
    "CONFIRMATION",  # mission vocabulary for confirmation data
    "OOS",           # mission vocabulary for out-of-sample data
})


class ProtectedDataAccessError(Exception):
    """Raised when an optimization evaluation touches a protected dataset
    (confirmation / oos / holdout) without explicit lifecycle authorization."""


class SearchBudgetExceededError(Exception):
    """Raised when a candidate evaluation would exceed MAX_CANDIDATES or
    MAX_SEARCH_BUDGET."""


@dataclass(frozen=True)
class FrozenCandidateResult:
    candidate_id: str
    parameters: Mapping[str, object]
    metric_value: float
    dataset_role: str
    lineage: Tuple[str, ...]  # (parent_strategy, parent_version, hypothesis_id)
    evaluation_hash: str


@dataclass(frozen=True)
class OptimizationOutcome:
    hypothesis_id: str
    status: str  # "SUPPORTED" | "HYPOTHESIS_NOT_SUPPORTED"
    candidates: Tuple[FrozenCandidateResult, ...]
    accepted_candidate_id: Optional[str]
    reason: str


class BoundedOptimizer:
    def __init__(self, hypothesis: HypothesisContract) -> None:
        if not hypothesis.is_frozen() or not hypothesis.verify():
            raise ValueError("hypothesis must be frozen (and unmodified) before optimization")
        self._hypothesis = hypothesis
        self._budget = hypothesis.search_budget
        self._candidates: list[FrozenCandidateResult] = []
        self._evaluations = 0

    @property
    def evaluations(self) -> int:
        return self._evaluations

    def evaluate(
        self,
        candidate_id: str,
        parameters: Mapping[str, object],
        metric_value: float,
        dataset_role: str,
    ) -> FrozenCandidateResult:
        """Evaluates one candidate. Fails closed on protected data and on budget
        exhaustion; every evaluation is frozen regardless of outcome (no result may be
        discarded or rewritten)."""
        if self._evaluations >= self._budget.max_search_budget:
            raise SearchBudgetExceededError(
                f"MAX_SEARCH_BUDGET={self._budget.max_search_budget} exhausted"
            )
        if len(self._candidates) >= self._budget.max_candidates:
            raise SearchBudgetExceededError(
                f"MAX_CANDIDATES={self._budget.max_candidates} exhausted"
            )
        if dataset_role in _PROTECTED_ROLES:
            raise ProtectedDataAccessError(
                f"candidate {candidate_id!r} evaluated on protected data role {dataset_role!r}"
            )
        if dataset_role != DEVELOPMENT_ROLE:
            raise ProtectedDataAccessError(
                f"candidate {candidate_id!r} evaluated on {dataset_role!r}; only "
                f"{DEVELOPMENT_ROLE!r} (development) data is permitted during optimization"
            )

        self._evaluations += 1
        result = FrozenCandidateResult(
            candidate_id=candidate_id,
            parameters=dict(parameters),
            metric_value=metric_value,
            dataset_role=dataset_role,
            lineage=(
                self._hypothesis.parent_strategy,
                self._hypothesis.parent_version,
                self._hypothesis.hypothesis_id,
            ),
            evaluation_hash=fingerprint(
                {
                    "candidate_id": candidate_id,
                    "parameters": dict(sorted(parameters.items())),
                    "metric_value": metric_value,
                    "dataset_role": dataset_role,
                    "lineage": (
                        self._hypothesis.parent_strategy,
                        self._hypothesis.parent_version,
                        self._hypothesis.hypothesis_id,
                    ),
                }
            ),
        )
        self._candidates.append(result)
        return result

    def _meets_acceptance(self, value: float) -> bool:
        rule = self._hypothesis.acceptance_rule
        metric = rule.get("metric", self._hypothesis.evaluation_metric)
        minimum = rule.get("minimum")
        return minimum is not None and value >= float(minimum)

    def conclude(self) -> OptimizationOutcome:
        """Applies the preregistered acceptance rule. Never launches another search."""
        accepted = [c for c in self._candidates if self._meets_acceptance(c.metric_value)]
        if accepted:
            best = max(accepted, key=lambda c: c.metric_value)
            return OptimizationOutcome(
                hypothesis_id=self._hypothesis.hypothesis_id,
                status="SUPPORTED",
                candidates=tuple(self._candidates),
                accepted_candidate_id=best.candidate_id,
                reason="candidate met preregistered acceptance rule",
            )
        return OptimizationOutcome(
            hypothesis_id=self._hypothesis.hypothesis_id,
            status="HYPOTHESIS_NOT_SUPPORTED",
            candidates=tuple(self._candidates),
            accepted_candidate_id=None,
            reason="no candidate met the preregistered acceptance rule",
        )
