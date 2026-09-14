from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from external_candidate.research_factory import (
    PRE_HOLDOUT_FILES,
    canonical_import_check,
    compare_semantic_records,
    export_candidate_package,
    freeze_candidate_package,
    holdout_firewall,
    validate_candidate_manifest,
    validate_dataset_manifest,
    validate_economic_contract,
    verify_artifact_persistence,
)


H = "a" * 64


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2).encode()


def _package(tmp_path: Path) -> Path:
    root = tmp_path / "CANDIDATE_TEST_ONLY"
    root.mkdir(parents=True)
    artifacts = {
        "candidate.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY", "strategy_id": "ST_TEST", "strategy_version": "1.0.0"}),
        "effective_candidate_config.yaml": b"candidate_id: CANDIDATE_TEST_ONLY\nstrategy_id: ST_TEST\nstrategy_version: 1.0.0\n",
        "strategy_rules.md": b"TEST ONLY\n",
        "provenance.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY", "strategy_id": "ST_TEST", "strategy_version": "1.0.0"}),
        "dataset_manifest.json": _json({"schema_version": "AG_DATASET_MANIFEST_V1", "dataset_id": "DS", "symbol": "EURUSD", "timeframe": "M1", "source": "TEST", "timezone": "UTC", "start_timestamp": "2026-01-01T00:00:00Z", "end_timestamp": "2026-02-01T00:00:00Z", "row_count": 10, "sha256": H, "creation_timestamp": "2026-09-14T00:00:00Z", "mutable": False}),
        "split_manifest.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY", "strategy_id": "ST_TEST", "strategy_version": "1.0.0", "effective_config_hash": "PENDING", "economic_contract_hash": "PENDING", "dataset_hashes": {"DS": H}, "split_hashes": {"VALIDATION": H}}),
        "economic_contract.json": _json({"schema_version": "AG_ECONOMIC_CONTRACT_V1", "minimum_sample": 30, "minimum_net_expectancy": 0.0, "profit_factor_requirement": 1.0, "maximum_drawdown": 10.0, "friction_stress_requirements": ["BASE"], "walk_forward_requirements": {"minimum_folds": 1}, "parameter_stability_requirements": {}, "semantic_parity_requirement": 1.0, "holdout_requirements": {"max_runs": 1}, "failure_conditions": ["threshold_failure"], "frozen": True}),
        "discovery_result.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY"}),
        "validation_result.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY", "strategy_id": "ST_TEST", "strategy_version": "1.0.0"}),
        "walkforward_result.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY"}),
        "friction_report.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY"}),
        "robustness_report.json": _json({"candidate_id": "CANDIDATE_TEST_ONLY"}),
        "red_team_report.md": b"TEST ONLY PASS\n",
        "occurrences.parquet": b"TEST_ONLY_OCCURRENCES",
        "trades.parquet": b"TEST_ONLY_TRADES",
        "README_IMPORT.md": b"TEST ONLY\n",
    }
    config_hash = hashlib.sha256(artifacts["effective_candidate_config.yaml"]).hexdigest()
    econ_hash = hashlib.sha256(artifacts["economic_contract.json"]).hexdigest()
    for name in ("split_manifest.json", "validation_result.json"):
        value = json.loads(artifacts[name])
        value.update(effective_config_hash=config_hash, economic_contract_hash=econ_hash,
                     dataset_hashes={"DS": H, "HOLDOUT": H}, split_hashes={"VALIDATION": H, "HOLDOUT": H})
        artifacts[name] = _json(value)
    manifest = {"schema_version": "AG_CANDIDATE_MANIFEST_V1", "candidate_id": "CANDIDATE_TEST_ONLY", "generation_id": "GEN_TEST", "strategy_id": "ST_TEST", "strategy_version": "1.0.0", "strategy_family": "TEST", "candidate_state": "FROZEN_FOR_HOLDOUT", "rules_hash": H, "code_hash": H, "effective_config_hash": config_hash, "dataset_hashes": {"DS": H, "HOLDOUT": H}, "split_hashes": {"VALIDATION": H, "HOLDOUT": H}, "economic_contract_hash": econ_hash, "parameters": {"x": 1}, "risk_contract": {"risk": 0.1}, "friction_contract": {"spread": 1}, "session_contract": {"window": "TEST"}, "source_commit": H, "creation_timestamp": "2026-09-14T00:00:00Z", "mutable": False}
    freeze_candidate_package(root, artifacts, manifest)
    return root


def test_valid_complete_package_passes_double_reopen(tmp_path):
    result = verify_artifact_persistence(_package(tmp_path))
    assert result.passed and result.first_pass_hash_stable and result.second_pass_hash_stable


def test_export_preserves_every_verified_byte(tmp_path):
    source = _package(tmp_path / "source")
    destination = tmp_path / "export" / source.name
    result = export_candidate_package(source, destination)
    assert result.passed
    assert (source / "SHA256SUMS.txt").read_bytes() == (destination / "SHA256SUMS.txt").read_bytes()


@pytest.mark.parametrize("missing", ["effective_candidate_config.yaml", "provenance.json"])
def test_missing_required_artifact_fails(tmp_path, missing):
    root = _package(tmp_path)
    (root / missing).unlink()
    assert not verify_artifact_persistence(root).passed


@pytest.mark.parametrize("bad", ["abc", "g" * 64])
def test_invalid_hash_rejected(bad):
    manifest = {"schema_version": "AG_DATASET_MANIFEST_V1", "dataset_id": "D", "symbol": "X", "timeframe": "M1", "source": "T", "timezone": "UTC", "start_timestamp": "a", "end_timestamp": "b", "row_count": 1, "sha256": bad, "creation_timestamp": "now", "mutable": False}
    assert validate_dataset_manifest(manifest)


def test_modified_candidate_or_config_fails(tmp_path):
    root = _package(tmp_path)
    (root / "effective_candidate_config.yaml").write_bytes(b"changed")
    assert not verify_artifact_persistence(root).passed


def test_reopen_failure_blocks_holdout(tmp_path):
    root = _package(tmp_path)
    def broken(path):
        raise OSError("TEST reopen failure")
    result = verify_artifact_persistence(root, opener=broken)
    assert not result.passed and not result.first_pass_hash_stable


def test_second_pass_instability_blocks_holdout(tmp_path):
    root = _package(tmp_path)
    calls = {}
    def unstable(path):
        calls[path] = calls.get(path, 0) + 1
        data = path.read_bytes()
        return data if calls[path] == 1 else data + b"changed"
    result = verify_artifact_persistence(root, opener=unstable)
    assert not result.passed and not result.second_pass_hash_stable


def test_candidate_and_economic_schema_are_fail_closed():
    assert validate_candidate_manifest({"schema_version": "AG_CANDIDATE_MANIFEST_V1"})
    assert validate_economic_contract({"schema_version": "AG_ECONOMIC_CONTRACT_V1", "frozen": False})


def test_dataset_and_economic_hash_mismatch_fail(tmp_path):
    root = _package(tmp_path)
    manifest = json.loads((root / "candidate_manifest.json").read_text())
    manifest["economic_contract_hash"] = "b" * 64
    (root / "candidate_manifest.json").write_text(json.dumps(manifest))
    assert not verify_artifact_persistence(root).passed


def test_evidence_candidate_mismatch_fails(tmp_path):
    root = _package(tmp_path)
    value = json.loads((root / "validation_result.json").read_text())
    value["candidate_id"] = "OTHER"
    (root / "validation_result.json").write_text(json.dumps(value))
    assert not verify_artifact_persistence(root).passed


def test_holdout_blocked_before_persistence_and_cannot_run_twice(tmp_path):
    root = _package(tmp_path)
    ledger = tmp_path / "holdout-ledger.json"
    first = holdout_firewall(root, ledger, "AUTH-1")
    assert first.allowed
    assert not holdout_firewall(root, ledger, "AUTH-2").allowed
    assert json.loads(ledger.read_text())["runs"][0]["holdout_state"] == "CONSUMED"


def test_mlflow_record_without_package_cannot_pass(tmp_path):
    assert not verify_artifact_persistence(tmp_path / "missing").passed


def test_canonical_import_recomputes_and_requires_passing_holdout(tmp_path):
    root = _package(tmp_path)
    result = canonical_import_check(root)
    assert not result.passed
    manifest = json.loads((root / "candidate_manifest.json").read_text())
    holdout = {"candidate_id": manifest["candidate_id"], "candidate_hash": result.candidate_hash, "effective_config_hash": manifest["effective_config_hash"], "economic_contract_hash": manifest["economic_contract_hash"], "holdout_dataset_hash": H, "holdout_split_hash": H, "run_id": "RUN1", "run_number": 1, "execution_timestamp": "2026-09-14T00:00:00Z", "trade_count": 1, "net_R": 1, "net_expectancy_R": 1, "profit_factor": 2, "max_drawdown_R": 0, "friction_results": {}, "result": "PASS", "holdout_state": "CONSUMED"}
    (root / "holdout_result.json").write_bytes(_json(holdout))
    assert canonical_import_check(root).passed


def test_semantic_mismatch_is_parity_fail():
    left = [{"occurrence_id": "1", "symbol": "EURUSD", "timestamp": "t", "direction": "LONG", "setup_type": "S1", "decision_state": "READY", "reason_codes": [], "entry": 1.0, "stop_loss": .9, "take_profit": 1.2, "campaign_admission": True}]
    right = [dict(left[0], direction="SHORT")]
    assert compare_semantic_records(left, right).status == "PARITY_FAIL"


def test_r6_and_demo_and_live_authority_remain_separate():
    from external_candidate.research_factory import governance_transition
    assert governance_transition("R6_PASS") == {"demo_eligible": False, "demo_authorized": False, "live_authorized": False}
    assert governance_transition("DEMO_AUTHORIZED")["live_authorized"] is False
