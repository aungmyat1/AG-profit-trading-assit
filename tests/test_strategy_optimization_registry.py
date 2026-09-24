from __future__ import annotations

import json
from pathlib import Path

import pytest

from strategy_optimization.dataset_firewall import DatasetAccessFirewall
from strategy_optimization.models import (
    Arm,
    BaselineStatus,
    CandidateStrategy,
    DatasetManifest,
    DatasetRole,
    ExperimentHypothesis,
    ExperimentManifest,
    ExperimentMetrics,
    ExperimentResult,
    HypothesisStatus,
    PromotionDecision,
    PromotionDisposition,
    StrategyBaseline,
)
from strategy_optimization.registry import (
    CorruptRegistry,
    ExperimentRegistry,
    ImmutableRecordExists,
    RegistryError,
    TransitionRejected,
)
from strategy_optimization.state_machine import CandidateState
from svos.hypothesis import HypothesisContract, SearchBudget


CONDITIONS = {
    "economic_gate_result": "FAIL",
    "data_integrity": "PASS",
    "semantic_integrity": "PASS",
    "population_role": "DEVELOPMENT",
    "failure_diagnosis_complete": True,
    "mechanism_identified": True,
    "hypothesis_preregistered": True,
    "search_budget_frozen": True,
    "protected_data_access_count": 0,
    "optimization_population_authorized": True,
}


def _manifest(experiment_id: str = "EXP_REGISTRY_001") -> ExperimentManifest:
    strategy_id = "ST_TEST_V1"
    return ExperimentManifest(
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        baseline=StrategyBaseline(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            canonical_config_ref="strategies/ST_TEST_V1.yaml",
            canonical_config_sha256="a" * 64,
            baseline_status=BaselineStatus.NOT_REPRODUCIBLE,
            blockers=("BASELINE_NOT_REPRODUCED",),
        ),
        hypothesis=ExperimentHypothesis(
            hypothesis_id="HYP_TEST_001",
            strategy_id=strategy_id,
            parent_version="1.0.0",
            statement="Test-only, not an economic hypothesis.",
            mechanism="test",
            permitted_delta=("single test delta",),
            forbidden_deltas=("all other changes",),
            status=HypothesisStatus.NOT_PREREGISTERED,
        ),
        candidate=CandidateStrategy(
            strategy_id=strategy_id,
            parent_version="1.0.0",
            candidate_version=None,
            candidate_config_sha256="b" * 64,
            candidate_implementation_sha256="c" * 64,
            implementation_ref="test://candidate",
            permitted_delta=("single test delta",),
            forbidden_deltas=("all other changes",),
            version_assignment_status="PENDING_OWNER_ASSIGNMENT",
        ),
        dataset=None,
        created_at_utc="2026-09-24T00:00:00Z",
    )


def _preregisterable_manifest(experiment_id: str) -> ExperimentManifest:
    strategy_id = "ST_TEST_V1"
    dataset = DatasetManifest(
        strategy_id=strategy_id,
        dataset_id=f"DEV_{experiment_id}",
        role=DatasetRole.DEVELOPMENT,
        source_ref="metadata-only://registry-test-fixture",
        dataset_sha256="d" * 64,
        description="Test-only identity fixture; no market data is present.",
    )
    permitted = ("single test delta",)
    forbidden = ("all other changes",)
    frozen_dimensions = (("test_dimension", "frozen"),)
    acceptance_rule = (("minimum_sample_size", 1),)
    budget = SearchBudget(max_candidates=1, max_search_budget=1)
    contract = HypothesisContract(
        hypothesis_id=f"HYP_{experiment_id}",
        parent_strategy=strategy_id,
        parent_version="1.0.0",
        mechanism="test-only mechanism",
        single_primary_delta=permitted[0],
        frozen_dimensions={**dict(frozen_dimensions), "forbidden_deltas": list(forbidden)},
        development_dataset=dataset.dataset_id,
        protected_datasets=("OOS_TEST_ONLY", "HOLDOUT_TEST_ONLY"),
        evaluation_metric="net_expectancy_R",
        acceptance_rule=dict(acceptance_rule),
        search_budget=budget,
    ).freeze()
    hypothesis = ExperimentHypothesis(
        hypothesis_id=f"HYP_{experiment_id}",
        strategy_id=strategy_id,
        parent_version="1.0.0",
        statement="Test-only preregistration; not an economic claim.",
        mechanism="test-only mechanism",
        permitted_delta=permitted,
        forbidden_deltas=forbidden,
        status=HypothesisStatus.PREREGISTERED,
        development_dataset_id=dataset.dataset_id,
        protected_dataset_ids=("OOS_TEST_ONLY", "HOLDOUT_TEST_ONLY"),
        evaluation_metric="net_expectancy_R",
        acceptance_rule=acceptance_rule,
        frozen_dimensions=frozen_dimensions,
        max_candidates=1,
        max_search_budget=1,
        preregistration_sha256=contract.preregistration_hash,
    )
    return ExperimentManifest(
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        baseline=StrategyBaseline(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            canonical_config_ref="strategies/ST_TEST_V1.yaml",
            canonical_config_sha256="a" * 64,
            baseline_status=BaselineStatus.REPRODUCIBLE,
            baseline_sha256="b" * 64,
            dataset_id=dataset.dataset_id,
            dataset_sha256=dataset.dataset_sha256,
            population_hash="e" * 64,
            friction_profile_ref="metadata-only://test-friction-profile",
            friction_profile_sha256="f" * 64,
        ),
        hypothesis=hypothesis,
        candidate=CandidateStrategy(
            strategy_id=strategy_id,
            parent_version="1.0.0",
            candidate_version=None,
            candidate_config_sha256="c" * 64,
            candidate_implementation_sha256="9" * 64,
            implementation_ref="test://candidate",
            permitted_delta=permitted,
            forbidden_deltas=forbidden,
            version_assignment_status="PENDING_OWNER_ASSIGNMENT",
        ),
        dataset=dataset,
        created_at_utc="2026-09-24T00:00:00Z",
    )


def _signed_contract(repo_root: Path, status: str = "SIGNED") -> None:
    path = repo_root / "config/governance/optimization_admission_contract.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "schema_version: '1'\nidentity:\n  contract_id: AG_OPTIMIZATION_ADMISSION_CONTRACT_V1\n  status: " + status + "\n",
        encoding="utf-8",
    )


def _advance_to_owner_review(registry: ExperimentRegistry, experiment_id: str) -> None:
    steps = [
        (CandidateState.PREREGISTERED, "baseline_reproduction", None),
        (CandidateState.DEVELOPMENT_TESTED, "control_candidate_development_result", CONDITIONS),
        (CandidateState.ROBUSTNESS_PASS, "robustness_report", CONDITIONS),
        (CandidateState.CANDIDATE_FROZEN, "candidate_freeze", None),
        (CandidateState.REPLICATION_PASS, "independent_replication_result", None),
        (CandidateState.OOS_PASS, "oos_result", None),
        (CandidateState.HOLDOUT_PASS, "final_holdout_result", None),
        (CandidateState.PARITY_PASS, "paper_demo_parity_report", None),
        (CandidateState.FORWARD_RESEARCH, "owner_forward_authorization", None),
        (CandidateState.OWNER_REVIEW, "forward_summary", None),
    ]
    for state, first_evidence, conditions in steps:
        evidence = {first_evidence: [f"evidence://{first_evidence}"]}
        if state is CandidateState.PREREGISTERED:
            evidence.update({
                "data_integrity": ["evidence://data"],
                "semantic_integrity": ["evidence://semantics"],
                "economic_diagnosis": ["evidence://diagnosis"],
                "hypothesis_preregistration": ["evidence://hypothesis"],
            })
        if state is CandidateState.FORWARD_RESEARCH:
            evidence["canonical_lifecycle_evaluation"] = ["evidence://canonical-lifecycle"]
        if state is CandidateState.OWNER_REVIEW:
            evidence["owner_review_packet"] = ["evidence://owner-packet"]
        registry.transition(
            experiment_id,
            state,
            actor="test-operator",
            evidence_refs=evidence,
            optimization_conditions=conditions,
        )


def test_registry_records_terminal_reproducibility_block_immutably(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "registry", repo_root=tmp_path)
    manifest = _manifest()
    manifest_sha = registry.register(manifest, actor="test-agent", at_utc="2026-09-24T00:00:00Z")
    assert len(manifest_sha) == 64
    assert registry.state(manifest.experiment_id) is CandidateState.DRAFT
    with pytest.raises(ImmutableRecordExists):
        registry.register(manifest, actor="test-agent")
    with pytest.raises(TransitionRejected, match="BASELINE_NOT_REPRODUCIBLE"):
        registry.transition(
            manifest.experiment_id,
            CandidateState.PREREGISTERED,
            actor="test-agent",
            evidence_refs={
                "baseline_reproduction": ["baseline.json"],
                "data_integrity": ["data.json"],
                "semantic_integrity": ["semantics.json"],
                "economic_diagnosis": ["diagnosis.json"],
                "hypothesis_preregistration": ["hypothesis.json"],
            },
        )

    registry.transition(
        manifest.experiment_id,
        CandidateState.BLOCKED_REPRODUCIBILITY,
        actor="test-agent",
        evidence_refs={"baseline_provenance_search": ["search-report.json"]},
        details={"economic_claim": "NOT_AVAILABLE"},
        at_utc="2026-09-24T00:01:00Z",
    )
    assert registry.state(manifest.experiment_id) is CandidateState.BLOCKED_REPRODUCIBILITY
    assert len(registry.events(manifest.experiment_id)) == 2
    with pytest.raises(TransitionRejected, match="TERMINAL_STATE_REQUIRES_NEW_EXPERIMENT_ID"):
        registry.transition(
            manifest.experiment_id,
            CandidateState.PREREGISTERED,
            actor="test-agent",
            evidence_refs={
                "baseline_reproduction": ["baseline"],
                "data_integrity": ["data"],
                "semantic_integrity": ["semantics"],
                "economic_diagnosis": ["diagnosis"],
                "hypothesis_preregistration": ["hypothesis"],
            },
        )

    event_path = tmp_path / "registry/experiments" / manifest.experiment_id / "events.jsonl"
    text = event_path.read_text(encoding="utf-8")
    event_path.write_text(text.replace("test-agent", "test-tamper", 1), encoding="utf-8")
    with pytest.raises(CorruptRegistry, match="event chain invalid"):
        registry.events(manifest.experiment_id)


def test_development_replay_requires_signed_contract_and_all_admission_conditions(tmp_path: Path) -> None:
    _signed_contract(tmp_path, status="PROPOSED")
    registry = ExperimentRegistry(tmp_path / "registry", repo_root=tmp_path)
    manifest = _preregisterable_manifest("EXP_REGISTRY_002")
    registry.register(manifest, actor="test-agent")
    # PREREGISTERED needs every independent evidence class, not just a baseline citation.
    registry.transition(
        manifest.experiment_id,
        CandidateState.PREREGISTERED,
        actor="test-operator",
        evidence_refs={
            "baseline_reproduction": ["baseline.json"],
            "data_integrity": ["dataset-audit.json"],
            "semantic_integrity": ["semantic-audit.json"],
            "economic_diagnosis": ["diagnosis.json"],
            "hypothesis_preregistration": ["hypothesis.json"],
        },
    )
    with pytest.raises(TransitionRejected, match="CONTRACT_NOT_SIGNED"):
        registry.transition(
            manifest.experiment_id,
            CandidateState.DEVELOPMENT_TESTED,
            actor="test-operator",
            evidence_refs={"control_candidate_development_result": ["result.json"]},
            optimization_conditions=CONDITIONS,
        )
    assert registry.state(manifest.experiment_id) is CandidateState.PREREGISTERED

    _signed_contract(tmp_path, status="SIGNED")
    with pytest.raises(TransitionRejected, match="MISSING_ECONOMIC_GATE_RESULT"):
        registry.transition(
            manifest.experiment_id,
            CandidateState.DEVELOPMENT_TESTED,
            actor="test-operator",
            evidence_refs={"control_candidate_development_result": ["result.json"]},
            optimization_conditions={"data_integrity": "PASS"},
        )
    registry.transition(
        manifest.experiment_id,
        CandidateState.DEVELOPMENT_TESTED,
        actor="test-operator",
        evidence_refs={"control_candidate_development_result": ["result.json"]},
        optimization_conditions=CONDITIONS,
    )
    assert registry.state(manifest.experiment_id) is CandidateState.DEVELOPMENT_TESTED
    admission_event = registry.events(manifest.experiment_id)[-1]
    assert admission_event["optimization_admission_passed"] is True
    assert admission_event["details"]["optimization_admission"]["contract_status"] == "SIGNED"
    assert len(admission_event["details"]["optimization_admission"]["contract_sha256"]) == 64


def test_full_candidate_workflow_ends_in_owner_review_without_auto_promotion(tmp_path: Path) -> None:
    _signed_contract(tmp_path, status="SIGNED")
    registry = ExperimentRegistry(tmp_path / "registry", repo_root=tmp_path)
    registry.register(_preregisterable_manifest("EXP_REGISTRY_002"), actor="test-agent")
    _advance_to_owner_review(registry, "EXP_REGISTRY_002")
    assert registry.state("EXP_REGISTRY_002") is CandidateState.OWNER_REVIEW

    decision = PromotionDecision(
        decision_id="DECISION_001",
        experiment_id="EXP_REGISTRY_002",
        strategy_id="ST_TEST_V1",
        disposition=PromotionDisposition.OWNER_APPROVED_CANDIDATE_VERSION,
        rationale="owner accepts this for candidate version assignment only",
        decided_by="strategy-owner",
        decided_at_utc="2026-09-24T00:05:00Z",
        authority_ref="owner-decision.md",
        candidate_version="1.1.0",
    )
    registry.record_promotion_decision(decision, actor="strategy-owner")
    assert registry.state("EXP_REGISTRY_002") is CandidateState.OWNER_REVIEW
    assert registry.events("EXP_REGISTRY_002")[-1]["event_type"] == "OWNER_DECISION_RECORDED"
    with pytest.raises(RegistryError, match="already immutably recorded"):
        registry.record_promotion_decision(decision, actor="strategy-owner")


def test_owner_rejection_is_an_explicit_terminal_outcome(tmp_path: Path) -> None:
    _signed_contract(tmp_path, status="SIGNED")
    registry = ExperimentRegistry(tmp_path / "registry", repo_root=tmp_path)
    experiment_id = "EXP_REGISTRY_REJECT_001"
    registry.register(_preregisterable_manifest(experiment_id), actor="test-agent")
    _advance_to_owner_review(registry, experiment_id)
    with pytest.raises(TransitionRejected, match="OWNER_DECISION_API_REQUIRED"):
        registry.transition(
            experiment_id,
            CandidateState.REJECTED_OWNER_DECISION,
            actor="test-operator",
            evidence_refs={"owner_rejection_record": ["owner-decision.md"]},
        )

    decision = PromotionDecision(
        decision_id="DECISION_REJECT_001",
        experiment_id=experiment_id,
        strategy_id="ST_TEST_V1",
        disposition=PromotionDisposition.REJECT,
        rationale="owner rejects the candidate; no strategy or execution change is authorized",
        decided_by="strategy-owner",
        decided_at_utc="2026-09-24T00:05:00Z",
        authority_ref="owner-decision.md",
    )
    registry.record_promotion_decision(decision, actor="strategy-owner")
    assert registry.state(experiment_id) is CandidateState.REJECTED_OWNER_DECISION
    assert registry.events(experiment_id)[-1]["evidence_refs"]["owner_rejection_record"] == [
        "owner-decision.md"
    ]
    with pytest.raises(TransitionRejected, match="TERMINAL_STATE_REQUIRES_NEW_EXPERIMENT_ID"):
        registry.transition(
            experiment_id,
            CandidateState.PREREGISTERED,
            actor="test-operator",
            evidence_refs={"hypothesis_preregistration": ["new-hypothesis.json"]},
        )


def test_baseline_control_result_requires_completed_firewall_read(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    experiment_id = "EXP_REGISTRY_BASELINE_001"
    registry = ExperimentRegistry(root, repo_root=tmp_path)
    manifest = _manifest(experiment_id)
    registry.register(manifest, actor="test-agent")

    dataset = DatasetManifest(
        strategy_id="ST_TEST_V1",
        dataset_id="DEV_BASELINE_001",
        role=DatasetRole.DEVELOPMENT,
        source_ref="metadata-only://test-fixture",
        dataset_sha256="d" * 64,
        description="Unit-test metadata only; no market data or observed trading result.",
    )
    firewall = DatasetAccessFirewall(root, repo_root=tmp_path)
    firewall.register(dataset)
    result = ExperimentResult(
        experiment_id=experiment_id,
        strategy_id="ST_TEST_V1",
        arm=Arm.CONTROL,
        metrics=ExperimentMetrics(status="EVALUATED", sample_size=1, setup_count=1),
        dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.dataset_sha256,
        dataset_role=dataset.role,
        population_hash="e" * 64,
        friction_profile_sha256="f" * 64,
        candidate_config_sha256="a" * 64,
        run_id="TEST_BASELINE_READ_001",
    )

    with pytest.raises(RegistryError, match="lacks a completed pre-read firewall access"):
        registry.record_result(result, actor="test-agent")
    assert registry.events(experiment_id)[-1]["event_type"] == "REGISTERED"

    firewall.access(
        dataset.dataset_id,
        experiment_id=experiment_id,
        strategy_id="ST_TEST_V1",
        state=CandidateState.DRAFT,
        purpose="BASELINE_REPRODUCTION",
        actor="test-reader",
        reader=lambda _dataset: None,
    )
    registry.record_result(result, actor="test-agent")
    events = registry.events(experiment_id)
    assert registry.state(experiment_id) is CandidateState.DRAFT
    assert events[-1]["event_type"] == "RESULT_RECORDED"
    assert events[-1]["evidence_refs"]["dataset_access_ledger"] == [
        f"dataset_access/{dataset.dataset_id}.jsonl"
    ]


def test_registry_loads_write_once_manifest_identity(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "registry")
    manifest = _manifest()
    registry.register(manifest, actor="test-agent")
    payload = registry.load_manifest(manifest.experiment_id)
    assert payload["strategy_id"] == "ST_TEST_V1"
    assert payload["baseline"]["baseline_status"] == "NOT_REPRODUCIBLE"
    assert registry.manifest_sha256(manifest.experiment_id) == manifest.manifest_sha256
