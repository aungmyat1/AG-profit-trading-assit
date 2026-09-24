from __future__ import annotations

import pytest

from external_candidate.models import DatasetRole as LegacyDatasetRole
from performance.models import NOT_EVALUATED, TradeMetrics
from svos.hypothesis import HypothesisContract, SearchBudget
from strategy_optimization.metrics import compare_control_candidate
from strategy_optimization.models import (
    Arm,
    BaselineStatus,
    CandidateStrategy,
    ComparisonStatus,
    DatasetManifest,
    DatasetRole,
    ExperimentHypothesis,
    ExperimentManifest,
    ExperimentMetrics,
    ExperimentResult,
    HypothesisStatus,
    MetricStatus,
    PromotionDecision,
    PromotionDisposition,
    StrategyBaseline,
    to_legacy_dataset_role,
)


def _baseline(strategy_id: str = "ST_TEST_V1") -> StrategyBaseline:
    return StrategyBaseline(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        canonical_config_ref="strategies/ST_TEST_V1.yaml",
        canonical_config_sha256="a" * 64,
        baseline_status=BaselineStatus.NOT_REPRODUCIBLE,
        blockers=("BASELINE_NOT_REPRODUCED",),
    )


def _candidate(strategy_id: str = "ST_TEST_V1") -> CandidateStrategy:
    return CandidateStrategy(
        strategy_id=strategy_id,
        parent_version="1.0.0",
        candidate_version=None,
        candidate_config_sha256="b" * 64,
        candidate_implementation_sha256="c" * 64,
        implementation_ref="working-tree:test-candidate",
        permitted_delta=("one declared engineering delta",),
        forbidden_deltas=("no unrelated changes",),
        version_assignment_status="PENDING_OWNER_ASSIGNMENT",
    )


def _hypothesis(strategy_id: str = "ST_TEST_V1") -> ExperimentHypothesis:
    return ExperimentHypothesis(
        hypothesis_id="HYP_TEST_001",
        strategy_id=strategy_id,
        parent_version="1.0.0",
        statement="A test hypothesis, not an economic claim.",
        mechanism="test-only mechanism",
        permitted_delta=("one declared delta",),
        forbidden_deltas=("no other delta",),
        status=HypothesisStatus.NOT_PREREGISTERED,
    )


def _manifest(experiment_id: str = "EXP_TEST_001") -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id=experiment_id,
        strategy_id="ST_TEST_V1",
        baseline=_baseline(),
        hypothesis=_hypothesis(),
        candidate=_candidate(),
        dataset=None,
        created_at_utc="2026-09-24T00:00:00Z",
    )


def test_dataset_role_mapping_keeps_protected_roles_out_of_optimizer() -> None:
    assert to_legacy_dataset_role(DatasetRole.DEVELOPMENT) is LegacyDatasetRole.OPTIMIZATION
    assert to_legacy_dataset_role(DatasetRole.DEVELOPMENT_REUSED) is LegacyDatasetRole.OPTIMIZATION
    assert to_legacy_dataset_role(DatasetRole.REPLICATION) is LegacyDatasetRole.VALIDATION
    assert to_legacy_dataset_role(DatasetRole.OOS) is LegacyDatasetRole.VALIDATION
    assert to_legacy_dataset_role(DatasetRole.FINAL_HOLDOUT) is LegacyDatasetRole.HOLDOUT
    assert to_legacy_dataset_role(DatasetRole.FORWARD_SHADOW) is None


def test_reproducible_baseline_requires_population_and_friction_provenance() -> None:
    with pytest.raises(ValueError, match="reproducible baseline missing identity"):
        StrategyBaseline(
            strategy_id="ST_TEST_V1",
            strategy_version="1.0.0",
            canonical_config_ref="strategies/ST_TEST_V1.yaml",
            canonical_config_sha256="a" * 64,
            baseline_status=BaselineStatus.REPRODUCIBLE,
            baseline_sha256="b" * 64,
        )


def test_experiment_manifest_rejects_cross_strategy_hypothesis_or_dataset() -> None:
    other = _hypothesis("ST_OTHER_V1")
    with pytest.raises(ValueError, match="CROSS_STRATEGY_EXPERIMENT_FORBIDDEN"):
        ExperimentManifest(
            experiment_id="EXP_CROSS_001",
            strategy_id="ST_TEST_V1",
            baseline=_baseline(),
            hypothesis=other,
            candidate=_candidate(),
            dataset=None,
            created_at_utc="2026-09-24T00:00:00Z",
        )
    with pytest.raises(ValueError, match="CROSS_STRATEGY_DATASET_FORBIDDEN"):
        ExperimentManifest(
            experiment_id="EXP_CROSS_002",
            strategy_id="ST_TEST_V1",
            baseline=_baseline(),
            hypothesis=_hypothesis(),
            candidate=_candidate(),
            dataset=DatasetManifest(
                strategy_id="ST_OTHER_V1",
                dataset_id="OTHER_DEV_001",
                role=DatasetRole.DEVELOPMENT,
                source_ref="metadata-only://fixture",
                dataset_sha256="d" * 64,
            ),
            created_at_utc="2026-09-24T00:00:00Z",
        )


def test_hypothesis_adapter_freezes_with_canonical_svos_hash() -> None:
    forbidden = ("no other delta",)
    acceptance = {"min_net_expectancy_R": 0.2}
    dimensions = {"symbol": "EURUSD", "forbidden_deltas": list(forbidden)}
    expected = HypothesisContract(
        hypothesis_id="HYP_TEST_002",
        parent_strategy="ST_TEST_V1",
        parent_version="1.0.0",
        mechanism="test mechanism",
        single_primary_delta="one declared delta",
        frozen_dimensions=dimensions,
        development_dataset="DEV_SET_001",
        protected_datasets=("OOS_001", "FINAL_001"),
        evaluation_metric="net_expectancy_R",
        acceptance_rule=acceptance,
        search_budget=SearchBudget(max_candidates=2, max_search_budget=5),
    ).freeze()
    hypothesis = ExperimentHypothesis(
        hypothesis_id="HYP_TEST_002",
        strategy_id="ST_TEST_V1",
        parent_version="1.0.0",
        statement="test preregistration",
        mechanism="test mechanism",
        permitted_delta=("one declared delta",),
        forbidden_deltas=forbidden,
        status=HypothesisStatus.PREREGISTERED,
        development_dataset_id="DEV_SET_001",
        protected_dataset_ids=("OOS_001", "FINAL_001"),
        evaluation_metric="net_expectancy_R",
        acceptance_rule=(("min_net_expectancy_R", 0.2),),
        frozen_dimensions=(("symbol", "EURUSD"),),
        max_candidates=2,
        max_search_budget=5,
        preregistration_sha256=expected.preregistration_hash,
    )
    adapted = hypothesis.to_svos_contract()
    assert adapted.verify()
    assert adapted.preregistration_hash == expected.preregistration_hash


def test_unregistered_hypothesis_cannot_be_adapted_for_svos_search() -> None:
    with pytest.raises(ValueError, match="HYPOTHESIS_NOT_PREREGISTERED"):
        _hypothesis().to_svos_contract()


def test_candidate_freeze_reuses_svos_and_requires_owner_assigned_version() -> None:
    with pytest.raises(ValueError, match="OWNER_ASSIGNED_CANDIDATE_VERSION_REQUIRED"):
        _candidate().freeze_with_svos(
            dataset_role=DatasetRole.DEVELOPMENT,
            parameters={"period": 5},
            friction_contract="friction-v1",
            session_contract="session-v1",
            decision_tf="H1",
            execution_tf="M5",
            risk_contract="risk-v1",
        )
    candidate = CandidateStrategy(
        strategy_id="ST_TEST_V1",
        parent_version="1.0.0",
        candidate_version="1.1.0",
        candidate_config_sha256="b" * 64,
        candidate_implementation_sha256="c" * 64,
        implementation_ref="candidate:test",
        permitted_delta=("one declared delta",),
        forbidden_deltas=("no other delta",),
    )
    frozen = candidate.freeze_with_svos(
        dataset_role=DatasetRole.DEVELOPMENT,
        parameters={"period": 5},
        friction_contract="friction-v1",
        session_contract="session-v1",
        decision_tf="H1",
        execution_tf="M5",
        risk_contract="risk-v1",
    )
    assert frozen.verify()
    assert frozen.candidate_id.startswith("ST_TEST_V1@1.1.0:")


def test_gross_friction_net_and_sample_metrics_are_not_zero_filled() -> None:
    metrics = ExperimentMetrics()
    assert metrics.status is MetricStatus.NOT_EVALUATED
    assert metrics.sample_size is None
    assert metrics.setup_count is None
    assert metrics.gross_R is None
    assert metrics.friction_R is None
    assert metrics.net_R is None
    assert metrics.gross_expectancy_R is None
    assert metrics.net_expectancy_R is None


def test_empty_performance_snapshot_stays_not_evaluated() -> None:
    # Empty-sample sentinel only; no trade data or economic result is constructed here.
    trade_metrics = TradeMetrics(
        sample_size=0,
        wins=0,
        losses=0,
        breakevens=0,
        gross_total_R=0.0,
        gross_expectancy_R=0.0,
        net_total_R=NOT_EVALUATED,
        net_expectancy_R=NOT_EVALUATED,
        win_rate=0.0,
        average_win_R=NOT_EVALUATED,
        average_loss_R=NOT_EVALUATED,
        profit_factor=NOT_EVALUATED,
        max_drawdown_R=NOT_EVALUATED,
        max_consecutive_losses=0,
        cost_status=NOT_EVALUATED,
    )
    adapted = ExperimentMetrics.from_trade_metrics(trade_metrics)
    assert adapted.status is MetricStatus.NOT_EVALUATED
    assert adapted.gross_R is None
    assert adapted.friction_R is None
    assert adapted.net_R is None


def test_comparison_stays_not_evaluated_without_real_arm_results() -> None:
    control = ExperimentResult(
        experiment_id="EXP_PAIR_METADATA_ONLY",
        strategy_id="ST_TEST_V1",
        arm=Arm.CONTROL,
        metrics=ExperimentMetrics(),
    )
    candidate = ExperimentResult(
        experiment_id="EXP_PAIR_METADATA_ONLY",
        strategy_id="ST_TEST_V1",
        arm=Arm.CANDIDATE,
        metrics=ExperimentMetrics(),
    )
    with pytest.raises(TypeError, match="baseline"):
        compare_control_candidate(control, candidate)
    comparison = compare_control_candidate(control, candidate, baseline=_baseline())
    assert comparison.status is ComparisonStatus.NOT_EVALUATED
    assert comparison.blockers == ("CONTROL_OR_CANDIDATE_METRICS_NOT_EVALUATED",)
    assert comparison.paired_sample_size is None
    assert comparison.deltas.gross_R is None
    assert comparison.deltas.friction_R is None
    assert comparison.deltas.net_R is None


def test_evaluated_metric_record_requires_a_resolved_sample_size() -> None:
    with pytest.raises(ValueError, match="EVALUATED metrics require sample_size"):
        ExperimentMetrics(status=MetricStatus.EVALUATED)


def test_promotion_decision_is_an_owner_record_not_an_authority_mutation() -> None:
    decision = PromotionDecision(
        decision_id="OWNER_DEC_001",
        experiment_id="EXP_TEST_001",
        strategy_id="ST_TEST_V1",
        disposition=PromotionDisposition.HOLD,
        rationale="hold for additional owner review",
        decided_by="strategy-owner",
        decided_at_utc="2026-09-24T00:00:00Z",
        authority_ref="docs/decisions/owner-decision.md",
    )
    assert decision.execution_authority_changed is False
    with pytest.raises(ValueError, match="CANNOT_CHANGE_EXECUTION_AUTHORITY"):
        PromotionDecision(
            decision_id="OWNER_DEC_002",
            experiment_id="EXP_TEST_001",
            strategy_id="ST_TEST_V1",
            disposition=PromotionDisposition.HOLD,
            rationale="invalid test record",
            decided_by="strategy-owner",
            decided_at_utc="2026-09-24T00:00:00Z",
            authority_ref="owner.md",
            execution_authority_changed=True,
        )


def test_dataset_reuse_requires_explicit_parent_experiment() -> None:
    with pytest.raises(ValueError, match="DEVELOPMENT_REUSED must name the prior experiment"):
        DatasetManifest(
            strategy_id="ST_TEST_V1",
            dataset_id="DEV_REUSE_001",
            role=DatasetRole.DEVELOPMENT_REUSED,
            source_ref="metadata-only://fixture",
            dataset_sha256="d" * 64,
        )
