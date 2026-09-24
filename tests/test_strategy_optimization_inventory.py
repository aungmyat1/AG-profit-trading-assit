from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from strategy_optimization.inventory import InventoryError, build_initial_inventory, write_inventory_once
from strategy_optimization.models import BaselineStatus
from strategy_optimization.registry import ExperimentRegistry
from strategy_optimization.state_machine import CandidateState
from strategy_optimization.task_c import (
    TASK_C_BASELINE_SEARCH_REF,
    TASK_C_EXPERIMENT_ID,
    build_task_c_manifest,
    register_task_c_experiment,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_initial_inventory_freezes_four_independent_canonical_tracks_without_replay() -> None:
    inventory = build_initial_inventory(REPO_ROOT, generated_at_utc="2026-09-24T00:00:00Z")
    assert inventory["schema_version"] == "AG_STRATEGY_OPTIMIZATION_FRAMEWORK_V1_INITIAL_INVENTORY"
    tracks = {track["strategy_id"]: track for track in inventory["strategy_tracks"]}
    assert set(tracks) == {
        "ST_SESSION_SWEEP_CONTINUATION_V1",
        "ST_LIQUIDITY_SWEEP_RETEST_V1",
        "ST_LARGE_SMC_V1",
        "ST_ASIAN_SWEEP_5R_V1",
    }
    assert tracks["ST_SESSION_SWEEP_CONTINUATION_V1"]["canonical_version"] == "1.0.1"
    assert tracks["ST_LIQUIDITY_SWEEP_RETEST_V1"]["canonical_version"] == "2.0.0"
    assert tracks["ST_LARGE_SMC_V1"]["canonical_lifecycle_stage"] == "FORWARD_RESEARCH"
    assert tracks["ST_ASIAN_SWEEP_5R_V1"]["canonical_lifecycle_stage"] == "OPERATIONAL_SHADOW"
    assert tracks["ST_SESSION_SWEEP_CONTINUATION_V1"]["version_conflicts"] == [{
        "source": "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json",
        "canonical_version": "1.0.1",
        "observed_version": "1.0.0",
        "classification": "STALE_OR_VERSION_MISMATCHED_EVIDENCE_SNAPSHOT_NOT_CANONICAL_AUTHORITY",
    }]
    assert all(track["strategy_authority"]["demo_authorized"] is False for track in tracks.values())
    assert all(track["strategy_authority"]["live_authorized"] is False for track in tracks.values())
    assert inventory["optimization_admission"]["contract_status"] == "PROPOSED"
    assert inventory["optimization_admission"]["current_evaluation_status"] == "OPTIMIZATION_BLOCKED"
    assert inventory["dataset_roles"] == [
        "DEVELOPMENT", "DEVELOPMENT_REUSED", "REPLICATION", "OOS", "FINAL_HOLDOUT", "FORWARD_SHADOW",
    ]
    assert inventory["dataset_role_invariants"]["only_optimizer_roles"] == [
        "DEVELOPMENT", "DEVELOPMENT_REUSED",
    ]
    assert inventory["inventory_builder_scope"]["market_data_rows_consumed_by_builder"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", inventory["inventory_sha256"])


def test_inventory_write_once_never_replaces_existing_snapshot(tmp_path: Path) -> None:
    inventory = build_initial_inventory(REPO_ROOT, generated_at_utc="2026-09-24T00:00:00Z")
    output = tmp_path / "inventory.json"
    first_hash = write_inventory_once(output, inventory)
    assert first_hash == inventory["inventory_sha256"]
    assert json.loads(output.read_text(encoding="utf-8"))["inventory_sha256"] == first_hash
    with pytest.raises(InventoryError, match="immutable"):
        write_inventory_once(output, inventory)


def test_task_c_manifest_is_implemented_but_blocked_and_has_no_economic_claim() -> None:
    manifest = build_task_c_manifest(REPO_ROOT, created_at_utc="2026-09-24T00:00:00Z")
    assert manifest.experiment_id == TASK_C_EXPERIMENT_ID
    assert manifest.strategy_id == "ST_LIQUIDITY_SWEEP_RETEST_V1"
    assert manifest.baseline.baseline_status is BaselineStatus.NOT_REPRODUCIBLE
    assert manifest.baseline.baseline_sha256 is None
    assert manifest.baseline.dataset_id is None
    assert manifest.dataset is None
    assert manifest.hypothesis.status.value == "NOT_PREREGISTERED"
    assert manifest.candidate.candidate_version is None
    assert manifest.candidate.version_assignment_status == "PENDING_OWNER_ASSIGNMENT"
    assert re.fullmatch(r"[0-9a-f]{64}", manifest.candidate.candidate_implementation_sha256)
    assert any("99 setups / 50 taken / 49 blocked / 48 historical rejections" in note for note in manifest.notes)
    assert any("Economic claim: NOT_AVAILABLE" in note for note in manifest.notes)
    assert TASK_C_BASELINE_SEARCH_REF in manifest.related_evidence_refs
    assert manifest.dataset is None


def test_task_c_bootstrap_enters_terminal_reproducibility_block_only(tmp_path: Path) -> None:
    manifest = register_task_c_experiment(
        REPO_ROOT,
        tmp_path / "optimization-registry",
        actor="test-bootstrap",
        created_at_utc="2026-09-24T00:00:00Z",
    )
    registry = ExperimentRegistry(tmp_path / "optimization-registry", repo_root=REPO_ROOT)
    assert registry.state(manifest.experiment_id) is CandidateState.BLOCKED_REPRODUCIBILITY
    events = registry.events(manifest.experiment_id)
    assert events[-1]["event_type"] == "TRANSITION"
    assert events[-1]["state_after"] == "BLOCKED_REPRODUCIBILITY"
    assert events[-1]["details"]["implementation_status"] == "IMPLEMENTED"
    assert events[-1]["details"]["economic_claim"] == "NOT_AVAILABLE"
    assert not (tmp_path / "optimization-registry/experiments" / manifest.experiment_id / "results").exists()


def test_provenance_report_keeps_exact_baseline_unverified() -> None:
    report_path = REPO_ROOT / TASK_C_BASELINE_SEARCH_REF
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["conclusion"]["exact_baseline_reproduced"] is False
    assert report["conclusion"]["population_reproduced"] is False
    assert report["conclusion"]["friction_assumptions_reproduced"] is False
    assert report["conclusion"]["candidate_comparison_authorized"] is False
    assert report["reported_control_claim"]["verification_status"] == "UNVERIFIED_PROVENANCE_CLAIM_NOT_AN_EXPERIMENT_RESULT"
