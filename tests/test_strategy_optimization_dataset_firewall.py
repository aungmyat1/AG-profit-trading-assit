from __future__ import annotations

from pathlib import Path

import pytest

from external_candidate.models import DatasetRole as LegacyDatasetRole
from strategy_optimization.dataset_firewall import (
    DatasetAccessDenied,
    DatasetAccessFirewall,
    DatasetRegistryError,
    optimizer_role,
)
from strategy_optimization.hashchain import read_chained_events
from strategy_optimization.models import (
    BaselineStatus,
    CandidateStrategy,
    DatasetManifest,
    DatasetRole,
    ExperimentHypothesis,
    ExperimentManifest,
    HypothesisStatus,
    StrategyBaseline,
)
from strategy_optimization.registry import ExperimentRegistry
from strategy_optimization.state_machine import CandidateState
from svos.hypothesis import HypothesisContract, SearchBudget


def _dataset(dataset_id: str, role: DatasetRole, *, strategy_id: str = "ST_TEST_V1",
             data_hash: str = "d" * 64) -> DatasetManifest:
    return DatasetManifest(
        strategy_id=strategy_id,
        dataset_id=dataset_id,
        role=role,
        source_ref="metadata-only://fixture-no-market-data",
        dataset_sha256=data_hash if role is not DatasetRole.FORWARD_SHADOW else None,
        reused_from_experiment_id="EXP_PRIOR_001" if role is DatasetRole.DEVELOPMENT_REUSED else None,
        reused_from_dataset_id="DEV_SET_ORIGINAL" if role is DatasetRole.DEVELOPMENT_REUSED else None,
        symbols=("TEST",),
        description="Identity-only fixture used by policy tests.",
    )


def _write_signed_contract(repo_root: Path) -> None:
    path = repo_root / "config/governance/optimization_admission_contract.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "schema_version: '1'\nidentity:\n  contract_id: AG_OPTIMIZATION_ADMISSION_CONTRACT_V1\n  status: SIGNED\n",
        encoding="utf-8",
    )


def _registry_manifest(experiment_id: str, strategy_id: str) -> ExperimentManifest:
    dataset = DatasetManifest(
        strategy_id=strategy_id,
        dataset_id=f"DEV_{experiment_id}",
        role=DatasetRole.DEVELOPMENT,
        source_ref="metadata-only://test-fixture",
        dataset_sha256="d" * 64,
        description="Test-only identity fixture with no market data.",
    )
    permitted = ("test-only delta",)
    forbidden = ("all economic changes",)
    frozen_dimensions = (("test_dimension", "frozen"),)
    acceptance_rule = (("minimum_sample_size", 1),)
    budget = SearchBudget(max_candidates=1, max_search_budget=1)
    preregistration = HypothesisContract(
        hypothesis_id=f"HYP_{experiment_id}",
        parent_strategy=strategy_id,
        parent_version="1.0.0",
        mechanism="test fixture",
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
        statement="Test-only registry state fixture.",
        mechanism="test fixture",
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
        preregistration_sha256=preregistration.preregistration_hash,
    )
    return ExperimentManifest(
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        baseline=StrategyBaseline(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            canonical_config_ref=f"strategies/{strategy_id}.yaml",
            canonical_config_sha256="a" * 64,
            baseline_status=BaselineStatus.REPRODUCIBLE,
            baseline_sha256="b" * 64,
            dataset_id=dataset.dataset_id,
            dataset_sha256=dataset.dataset_sha256,
            population_hash="e" * 64,
            friction_profile_ref="metadata-only://test-friction",
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


_STAGE_SPECS = (
    (CandidateState.PREREGISTERED, {
        "baseline_reproduction": ["evidence://baseline"],
        "data_integrity": ["evidence://data"],
        "semantic_integrity": ["evidence://semantics"],
        "economic_diagnosis": ["evidence://diagnosis"],
        "hypothesis_preregistration": ["evidence://hypothesis"],
    }, None),
    (CandidateState.DEVELOPMENT_TESTED, {"control_candidate_development_result": ["evidence://development"]}, {
        "economic_gate_result": "FAIL", "data_integrity": "PASS", "semantic_integrity": "PASS",
        "population_role": "DEVELOPMENT", "failure_diagnosis_complete": True,
        "mechanism_identified": True, "hypothesis_preregistered": True,
        "search_budget_frozen": True, "protected_data_access_count": 0,
        "optimization_population_authorized": True,
    }),
    (CandidateState.ROBUSTNESS_PASS, {"robustness_report": ["evidence://robustness"]}, {
        "economic_gate_result": "FAIL", "data_integrity": "PASS", "semantic_integrity": "PASS",
        "population_role": "DEVELOPMENT", "failure_diagnosis_complete": True,
        "mechanism_identified": True, "hypothesis_preregistered": True,
        "search_budget_frozen": True, "protected_data_access_count": 0,
        "optimization_population_authorized": True,
    }),
    (CandidateState.CANDIDATE_FROZEN, {"candidate_freeze": ["evidence://freeze"]}, None),
    (CandidateState.REPLICATION_PASS, {"independent_replication_result": ["evidence://replication"]}, None),
    (CandidateState.OOS_PASS, {"oos_result": ["evidence://oos"]}, None),
    (CandidateState.HOLDOUT_PASS, {"final_holdout_result": ["evidence://holdout"]}, None),
    (CandidateState.PARITY_PASS, {"paper_demo_parity_report": ["evidence://parity"]}, None),
)


def _advance_registry(
    registry: ExperimentRegistry,
    target: CandidateState,
    *,
    experiment_id: str = "EXP_DATA_ACCESS_001",
) -> ExperimentRegistry:
    states = (CandidateState.DRAFT, *(spec[0] for spec in _STAGE_SPECS))
    if target not in states:
        raise ValueError(f"unsupported test target state: {target}")
    current = registry.state(experiment_id)
    if current not in states or states.index(target) < states.index(current):
        raise ValueError("test helper cannot move an experiment backward")
    if states.index(target) >= states.index(CandidateState.DEVELOPMENT_TESTED):
        _write_signed_contract(registry.repo_root or Path("."))
    start_index = states.index(current)
    target_index = states.index(target)
    for stage, evidence, conditions in _STAGE_SPECS[start_index:target_index]:
        registry.transition(
            experiment_id,
            stage,
            actor="test-fixture",
            evidence_refs=evidence,
            optimization_conditions=conditions,
        )
    if registry.state(experiment_id) is not target:
        raise AssertionError(f"test registry stopped at {registry.state(experiment_id)} not {target}")
    return registry


def _prepare_registry(
    root: Path,
    target: CandidateState,
    *,
    experiment_id: str = "EXP_DATA_ACCESS_001",
    strategy_id: str = "ST_TEST_V1",
    repo_root: Path | None = None,
) -> ExperimentRegistry:
    repo = repo_root or root.parent / "repo"
    registry = ExperimentRegistry(root, repo_root=repo)
    registry.register(_registry_manifest(experiment_id, strategy_id), actor="test-fixture")
    return _advance_registry(registry, target, experiment_id=experiment_id)


def test_protected_oos_read_is_denied_before_callback_and_attempt_is_one_shot(tmp_path: Path) -> None:
    root = tmp_path / "datasets"
    registry = _prepare_registry(root, CandidateState.DRAFT)
    firewall = DatasetAccessFirewall(root, repo_root=root.parent / "repo")
    manifest = _dataset("OOS_SET_001", DatasetRole.OOS)
    firewall.register(manifest)
    reader_calls = []

    def reader(dataset: DatasetManifest):
        reader_calls.append(dataset.dataset_id)
        return "read-result"

    with pytest.raises(DatasetAccessDenied, match="CANDIDATE_STATE_MISMATCH"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.REPLICATION_PASS,
            purpose="OOS_EVALUATION",
            actor="test-agent",
            reader=reader,
        )
    with pytest.raises(DatasetAccessDenied, match="NOT_AVAILABLE_AT_CANDIDATE_STATE"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.DRAFT,
            purpose="OOS_EVALUATION",
            actor="test-agent",
            reader=reader,
        )
    assert reader_calls == []
    _advance_registry(registry, CandidateState.REPLICATION_PASS)

    assert firewall.access(
        manifest.dataset_id,
        experiment_id="EXP_DATA_ACCESS_001",
        strategy_id="ST_TEST_V1",
        state=CandidateState.REPLICATION_PASS,
        purpose="OOS_EVALUATION",
        actor="test-agent",
        reader=reader,
    ) == "read-result"
    assert reader_calls == [manifest.dataset_id]

    with pytest.raises(DatasetAccessDenied, match="ALREADY_EXPOSED"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.REPLICATION_PASS,
            purpose="OOS_EVALUATION",
            actor="test-agent",
            reader=reader,
        )
    assert reader_calls == [manifest.dataset_id]

    log_path = tmp_path / "datasets/dataset_access/OOS_SET_001.jsonl"
    events = read_chained_events(log_path, manifest.manifest_sha256)
    assert [event["event_type"] for event in events] == [
        "DATASET_REGISTERED",
        "ACCESS_DENIED_NO_READ",
        "ACCESS_DENIED_NO_READ",
        "ACCESS_AUTHORIZED_BEFORE_READ",
        "READ_OUTCOME",
        "ACCESS_DENIED_NO_READ",
    ]
    assert events[3]["role"] == "OOS"
    assert events[3]["access_attempt"] == 1


def test_oos_holdout_and_forward_roles_never_enter_optimizer(tmp_path: Path) -> None:
    root = tmp_path / "datasets"
    _prepare_registry(root, CandidateState.PARITY_PASS)
    firewall = DatasetAccessFirewall(root, repo_root=root.parent / "repo")
    for role in (DatasetRole.REPLICATION, DatasetRole.OOS, DatasetRole.FINAL_HOLDOUT, DatasetRole.FORWARD_SHADOW):
        with pytest.raises(DatasetAccessDenied, match="PROTECTED_ROLE_CANNOT_ENTER_OPTIMIZER"):
            optimizer_role(role)
    assert optimizer_role(DatasetRole.DEVELOPMENT) is LegacyDatasetRole.OPTIMIZATION
    assert optimizer_role(DatasetRole.DEVELOPMENT_REUSED) is LegacyDatasetRole.OPTIMIZATION

    forward = _dataset("SHADOW_SET_001", DatasetRole.FORWARD_SHADOW)
    firewall.register(forward)
    calls = []
    for _ in range(2):
        assert firewall.access(
            forward.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.PARITY_PASS,
            purpose="FORWARD_OBSERVATION",
            actor="test-agent",
            reader=lambda dataset: calls.append(dataset.dataset_id) or "observation",
        ) == "observation"
    assert calls == [forward.dataset_id, forward.dataset_id]


def test_final_holdout_is_available_only_after_oos_pass_and_cannot_be_relabelled(tmp_path: Path) -> None:
    root = tmp_path / "datasets"
    registry = _prepare_registry(root, CandidateState.DRAFT)
    firewall = DatasetAccessFirewall(root, repo_root=root.parent / "repo")
    manifest = _dataset("FINAL_SET_001", DatasetRole.FINAL_HOLDOUT)
    firewall.register(manifest)
    reader_calls = []
    reader = lambda dataset: reader_calls.append(dataset.dataset_id) or "final"

    with pytest.raises(DatasetAccessDenied):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.REPLICATION_PASS,
            purpose="FINAL_HOLDOUT_EVALUATION",
            actor="test-agent",
            reader=reader,
        )
    assert reader_calls == []
    _advance_registry(registry, CandidateState.OOS_PASS)
    assert firewall.access(
        manifest.dataset_id,
        experiment_id="EXP_DATA_ACCESS_001",
        strategy_id="ST_TEST_V1",
        state=CandidateState.OOS_PASS,
        purpose="FINAL_HOLDOUT_EVALUATION",
        actor="test-agent",
        reader=reader,
    ) == "final"
    assert reader_calls == [manifest.dataset_id]

    with pytest.raises(DatasetRegistryError, match="write-once"):
        firewall.register(_dataset("FINAL_SET_001", DatasetRole.DEVELOPMENT, data_hash="a" * 64))
    with pytest.raises(DatasetRegistryError, match="ALREADY_PINNED_TO_ROLE"):
        firewall.register(_dataset("FINAL_COPY_AS_DEV", DatasetRole.DEVELOPMENT))


def test_cross_strategy_and_wrong_purpose_access_are_denied_without_read(tmp_path: Path) -> None:
    root = tmp_path / "datasets"
    _prepare_registry(root, CandidateState.DRAFT)
    firewall = DatasetAccessFirewall(root, repo_root=root.parent / "repo")
    manifest = _dataset("DEV_SET_001", DatasetRole.DEVELOPMENT)
    firewall.register(manifest)
    calls = []
    reader = lambda dataset: calls.append(dataset.dataset_id) or "bad"
    with pytest.raises(DatasetAccessDenied, match="CROSS_STRATEGY"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_OTHER_V1",
            state=CandidateState.DRAFT,
            purpose="DEVELOPMENT_EVALUATION",
            actor="test-agent",
            reader=reader,
        )
    with pytest.raises(DatasetAccessDenied, match="PURPOSE_NOT_PERMITTED"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.DRAFT,
            purpose="OOS_EVALUATION",
            actor="test-agent",
            reader=reader,
        )
    assert calls == []


def test_failed_reader_still_consumes_a_protected_dataset_attempt(tmp_path: Path) -> None:
    root = tmp_path / "datasets"
    _prepare_registry(root, CandidateState.CANDIDATE_FROZEN)
    firewall = DatasetAccessFirewall(root, repo_root=root.parent / "repo")
    manifest = _dataset("REPLICATION_SET_001", DatasetRole.REPLICATION)
    firewall.register(manifest)

    def failing_reader(_dataset: DatasetManifest):
        raise RuntimeError("reader failed after authorization")

    with pytest.raises(RuntimeError, match="reader failed"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.CANDIDATE_FROZEN,
            purpose="INDEPENDENT_REPLICATION",
            actor="test-agent",
            reader=failing_reader,
        )
    with pytest.raises(DatasetAccessDenied, match="ALREADY_EXPOSED"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.CANDIDATE_FROZEN,
            purpose="INDEPENDENT_REPLICATION",
            actor="test-agent",
            reader=lambda _dataset: pytest.fail("must not re-read replication data"),
        )


def test_development_reuse_must_be_hash_pinned_to_an_existing_same_strategy_dataset(tmp_path: Path) -> None:
    firewall = DatasetAccessFirewall(tmp_path / "datasets")
    original = _dataset("DEV_SET_ORIGINAL", DatasetRole.DEVELOPMENT, data_hash="2" * 64)
    firewall.register(original)
    reused = DatasetManifest(
        strategy_id="ST_TEST_V1",
        dataset_id="DEV_SET_REUSED_001",
        role=DatasetRole.DEVELOPMENT_REUSED,
        source_ref=original.source_ref,
        dataset_sha256=original.dataset_sha256,
        reused_from_experiment_id="EXP_PRIOR_001",
        reused_from_dataset_id=original.dataset_id,
    )
    firewall.register(reused)
    reused_again = DatasetManifest(
        strategy_id="ST_TEST_V1",
        dataset_id="DEV_SET_REUSED_002",
        role=DatasetRole.DEVELOPMENT_REUSED,
        source_ref=original.source_ref,
        dataset_sha256=original.dataset_sha256,
        reused_from_experiment_id="EXP_PRIOR_002",
        reused_from_dataset_id=original.dataset_id,
    )
    firewall.register(reused_again)

    cross_strategy = DatasetManifest(
        strategy_id="ST_OTHER_V1",
        dataset_id="DEV_SET_OTHER_STRATEGY",
        role=DatasetRole.DEVELOPMENT,
        source_ref="metadata-only://other",
        dataset_sha256=original.dataset_sha256,
    )
    with pytest.raises(DatasetRegistryError, match="CROSS_STRATEGY_ALIAS"):
        firewall.register(cross_strategy)

    orphan_reuse = DatasetManifest(
        strategy_id="ST_TEST_V1",
        dataset_id="DEV_SET_ORPHAN_REUSE",
        role=DatasetRole.DEVELOPMENT_REUSED,
        source_ref="metadata-only://missing",
        dataset_sha256="3" * 64,
        reused_from_experiment_id="EXP_PRIOR_001",
        reused_from_dataset_id="MISSING_DATASET",
    )
    with pytest.raises(DatasetRegistryError, match="SOURCE_DATASET_NOT_REGISTERED"):
        firewall.register(orphan_reuse)


def test_development_candidate_evaluation_requires_signed_repository_admission(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    contract_path = repo_root / "config/governance/optimization_admission_contract.yaml"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        "identity:\n  contract_id: AG_OPTIMIZATION_ADMISSION_CONTRACT_V1\n  status: PROPOSED\n",
        encoding="utf-8",
    )
    root = tmp_path / "framework"
    _prepare_registry(root, CandidateState.PREREGISTERED, repo_root=repo_root)
    firewall = DatasetAccessFirewall(root, repo_root=repo_root)
    manifest = _dataset("DEV_ADMISSION_001", DatasetRole.DEVELOPMENT, data_hash="4" * 64)
    firewall.register(manifest)
    reader_calls = []
    reader = lambda dataset: reader_calls.append(dataset.dataset_id) or "metadata-only-test-callback"

    with pytest.raises(DatasetAccessDenied, match="OPTIMIZATION_ADMISSION_BLOCKED:CONTRACT_NOT_SIGNED"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.PREREGISTERED,
            purpose="DEVELOPMENT_EVALUATION",
            actor="test-agent",
            reader=reader,
            optimization_conditions={
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
            },
        )
    assert reader_calls == []

    # A baseline-reproduction purpose is distinct from candidate development evaluation;
    # it uses a fresh DRAFT experiment and a fixed test callback, not source data.
    baseline_experiment_id = "EXP_DATA_BASELINE_001"
    _prepare_registry(
        root,
        CandidateState.DRAFT,
        experiment_id=baseline_experiment_id,
        repo_root=repo_root,
    )
    assert firewall.access(
        manifest.dataset_id,
        experiment_id=baseline_experiment_id,
        strategy_id="ST_TEST_V1",
        state=CandidateState.DRAFT,
        purpose="BASELINE_REPRODUCTION",
        actor="test-agent",
        reader=reader,
    ) == "metadata-only-test-callback"
    assert reader_calls == [manifest.dataset_id]


def test_prior_protected_exposure_blocks_development_admission(tmp_path: Path) -> None:
    root = tmp_path / "framework"
    repo_root = root.parent / "repo"
    _prepare_registry(root, CandidateState.REPLICATION_PASS, repo_root=repo_root)
    firewall = DatasetAccessFirewall(root, repo_root=repo_root)
    oos = _dataset("OOS_EXPOSED_001", DatasetRole.OOS, data_hash="5" * 64)
    development = _dataset("DEV_AFTER_OOS_001", DatasetRole.DEVELOPMENT, data_hash="6" * 64)
    firewall.register(oos)
    firewall.register(development)

    firewall.access(
        oos.dataset_id,
        experiment_id="EXP_DATA_ACCESS_001",
        strategy_id="ST_TEST_V1",
        state=CandidateState.REPLICATION_PASS,
        purpose="OOS_EVALUATION",
        actor="test-owner",
        reader=lambda _dataset: "metadata-only-test-token",
    )
    assert firewall.protected_access_count("EXP_DATA_ACCESS_001") == 1
    conditions = {
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
    reader_calls = []
    with pytest.raises(DatasetAccessDenied, match="CANDIDATE_STATE_MISMATCH"):
        firewall.access(
            development.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.PREREGISTERED,
            purpose="DEVELOPMENT_EVALUATION",
            actor="test-owner",
            reader=lambda dataset: reader_calls.append(dataset.dataset_id),
            optimization_conditions=conditions,
        )
    assert reader_calls == []


def test_missing_protected_access_ledger_fails_closed(tmp_path: Path) -> None:
    firewall = DatasetAccessFirewall(tmp_path / "datasets")
    manifest = _dataset("OOS_SET_NO_LEDGER", DatasetRole.OOS)
    firewall.register(manifest)
    log_path = tmp_path / "datasets/dataset_access/OOS_SET_NO_LEDGER.jsonl"
    log_path.unlink()
    with pytest.raises(DatasetRegistryError, match="LEDGER_MISSING_FAIL_CLOSED"):
        firewall.access(
            manifest.dataset_id,
            experiment_id="EXP_DATA_ACCESS_001",
            strategy_id="ST_TEST_V1",
            state=CandidateState.REPLICATION_PASS,
            purpose="OOS_EVALUATION",
            actor="test-agent",
            reader=lambda _dataset: pytest.fail("must not read without access ledger"),
        )
