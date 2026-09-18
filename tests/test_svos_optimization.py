"""Tests for svos.hypothesis + svos.optimization (P5/P6)."""
from __future__ import annotations

import pytest

from svos.hypothesis import HypothesisContract, SearchBudget
from svos.optimization import (
    BoundedOptimizer,
    ProtectedDataAccessError,
    SearchBudgetExceededError,
)


def _frozen_hypothesis(max_candidates: int = 5, max_budget: int = 10,
                       minimum: float = 0.10) -> HypothesisContract:
    return HypothesisContract(
        hypothesis_id="HYP_X",
        parent_strategy="ST_TEST_V1",
        parent_version="1.0.0",
        mechanism="widen stop buffer to reduce premature stop-outs",
        single_primary_delta="stop_buffer_multiplier",
        frozen_dimensions={"atr_period": 14},
        development_dataset="DEV_DS",
        protected_datasets=("CONFIRM_DS", "OOS_DS", "HOLDOUT_DS"),
        evaluation_metric="net_expectancy_R",
        acceptance_rule={"metric": "net_expectancy_R", "minimum": minimum},
        search_budget=SearchBudget(max_candidates=max_candidates, max_search_budget=max_budget),
    ).freeze()


def test_preregistration_hash_freezes_contract():
    h = _frozen_hypothesis()
    assert h.is_frozen() and h.verify()


def test_any_edit_breaks_hash():
    h = _frozen_hypothesis()
    tampered = HypothesisContract(
        hypothesis_id="HYP_X", parent_strategy="ST_TEST_V1", parent_version="1.0.0",
        mechanism="changed", single_primary_delta="stop_buffer_multiplier",
        frozen_dimensions={"atr_period": 14}, development_dataset="DEV_DS",
        protected_datasets=("CONFIRM_DS", "OOS_DS", "HOLDOUT_DS"),
        evaluation_metric="net_expectancy_R",
        acceptance_rule={"metric": "net_expectancy_R", "minimum": 0.10},
        search_budget=h.search_budget, preregistration_hash=h.preregistration_hash,
    )
    assert not tampered.verify()


def test_optimizer_rejects_unfrozen_hypothesis():
    with pytest.raises(ValueError):
        h = _frozen_hypothesis()
        unfrozen = HypothesisContract(
            hypothesis_id=h.hypothesis_id, parent_strategy=h.parent_strategy,
            parent_version=h.parent_version, mechanism=h.mechanism,
            single_primary_delta=h.single_primary_delta,
            frozen_dimensions=h.frozen_dimensions, development_dataset=h.development_dataset,
            protected_datasets=h.protected_datasets, evaluation_metric=h.evaluation_metric,
            acceptance_rule=h.acceptance_rule, search_budget=h.search_budget,
        )
        BoundedOptimizer(unfrozen)


def test_optimizer_blocks_protected_data():
    opt = BoundedOptimizer(_frozen_hypothesis())
    with pytest.raises(ProtectedDataAccessError):
        opt.evaluate("c1", {"x": 1}, 0.5, "HOLDOUT")
    with pytest.raises(ProtectedDataAccessError):
        opt.evaluate("c1", {"x": 1}, 0.5, "OOS")
    with pytest.raises(ProtectedDataAccessError):
        opt.evaluate("c1", {"x": 1}, 0.5, "CONFIRMATION")


def test_optimizer_enforces_budgets():
    opt = BoundedOptimizer(_frozen_hypothesis(max_candidates=2, max_budget=2))
    opt.evaluate("c1", {"x": 1}, 0.5, "OPTIMIZATION")
    opt.evaluate("c2", {"x": 2}, 0.6, "OPTIMIZATION")
    with pytest.raises(SearchBudgetExceededError):
        opt.evaluate("c3", {"x": 3}, 0.7, "OPTIMIZATION")


def test_hypothesis_not_supported_when_none_meets_rule():
    opt = BoundedOptimizer(_frozen_hypothesis(minimum=1.0))
    opt.evaluate("c1", {"x": 1}, 0.1, "OPTIMIZATION")
    opt.evaluate("c2", {"x": 2}, 0.2, "OPTIMIZATION")
    outcome = opt.conclude()
    assert outcome.status == "HYPOTHESIS_NOT_SUPPORTED"
    assert outcome.accepted_candidate_id is None


def test_supported_picks_best_candidate():
    opt = BoundedOptimizer(_frozen_hypothesis(minimum=0.10))
    opt.evaluate("c1", {"x": 1}, 0.3, "OPTIMIZATION")
    opt.evaluate("c2", {"x": 2}, 0.5, "OPTIMIZATION")
    outcome = opt.conclude()
    assert outcome.status == "SUPPORTED"
    assert outcome.accepted_candidate_id == "c2"


def test_every_candidate_frozen_with_lineage():
    opt = BoundedOptimizer(_frozen_hypothesis())
    result = opt.evaluate("c1", {"x": 1}, 0.3, "OPTIMIZATION")
    assert result.lineage == ("ST_TEST_V1", "1.0.0", "HYP_X")
    assert result.evaluation_hash
