"""Focused tests for src/external_candidate/admission.py. Uses ONLY the TEST_ONLY
synthetic fixture (tests/_fixtures_external_candidate.py) -- never real strategy
evidence -- so these tests can never be tuned toward a desired admission outcome
for a real candidate.
"""
from __future__ import annotations

import dataclasses

from _fixtures_external_candidate import make_candidate_package, make_dataset

from external_candidate.admission import validate_external_candidate_package
from external_candidate.models import AdmissionStatus, DatasetRole


def test_well_formed_synthetic_candidate_is_accepted():
    package = make_candidate_package()
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.ACCEPTED, result.reasons
    assert result.accepted


def test_unfrozen_candidate_is_rejected():
    package = make_candidate_package(candidate_frozen=False)
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.REJECTED_NOT_FROZEN


def test_holdout_used_for_optimization_is_rejected():
    package = make_candidate_package(holdout_used_for_optimization=True)
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.REJECTED_HOLDOUT_LEAKAGE
    assert any("holdout_used_for_optimization" in r for r in result.reasons)


def test_rules_changed_after_holdout_is_rejected():
    package = make_candidate_package(rules_changed_after_holdout=True)
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.REJECTED_HOLDOUT_LEAKAGE
    assert any("rules_changed_after_holdout" in r for r in result.reasons)


def test_missing_holdout_declaration_is_incomplete():
    package = make_candidate_package()
    package = dataclasses.replace(package, holdout=None)
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.INCOMPLETE


def test_overlapping_holdout_and_optimization_ranges_is_holdout_leakage():
    package = make_candidate_package(
        holdout_start="2026-06-01T00:00:00+00:00", holdout_end="2026-07-31T00:00:00+00:00",
        optimization_start="2026-01-01T00:00:00+00:00", optimization_end="2026-06-15T00:00:00+00:00",
    )
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.REJECTED_HOLDOUT_LEAKAGE
    assert "overlaps" in result.reasons[0]


def test_missing_rule_section_is_incomplete():
    package = make_candidate_package()
    trimmed_sections = dict(package.rules.rule_sections)
    del trimmed_sections["sl_logic"]
    package = dataclasses.replace(package, rules=dataclasses.replace(package.rules, rule_sections=trimmed_sections))
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.INCOMPLETE
    assert any("sl_logic" in r for r in result.reasons)


def test_empty_parameters_is_incomplete():
    package = make_candidate_package()
    package = dataclasses.replace(package, rules=dataclasses.replace(package.rules, parameters={}))
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.INCOMPLETE


def test_no_holdout_dataset_partition_is_incomplete():
    package = make_candidate_package()
    optimization_only = tuple(ds for ds in package.datasets if ds.role != DatasetRole.HOLDOUT)
    package = dataclasses.replace(package, datasets=optimization_only)
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.INCOMPLETE
    assert any("HOLDOUT" in r for r in result.reasons)


def test_incomplete_friction_is_incomplete():
    package = make_candidate_package()
    package = dataclasses.replace(package, friction=dataclasses.replace(package.friction, slippage=None))
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.INCOMPLETE
    assert any("friction" in r for r in result.reasons)


def test_parent_version_conflict_against_lifecycle_registry_is_rejected():
    # config/governance/strategy_lifecycle.yaml records ST_ASIAN_SWEEP_5R_V1 at 1.1.1
    # (real, committed governance file) -- a candidate claiming a different parent
    # version for that real strategy_id is a version-identity conflict.
    package = make_candidate_package(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", parent_strategy_version="9.9.9", candidate_version="1.2.0",
    )
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.REJECTED_VERSION_CONFLICT


def test_candidate_version_equal_to_parent_version_is_rejected():
    package = make_candidate_package(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", parent_strategy_version="1.1.1", candidate_version="1.1.1",
    )
    result = validate_external_candidate_package(package, repo_root=".")
    assert result.status is AdmissionStatus.REJECTED_VERSION_CONFLICT


def test_version_mutation_against_known_fingerprints_is_rejected():
    package = make_candidate_package(candidate_version="2.0.0", config_hash="sha256:new-config")
    known = {(package.strategy_id, "2.0.0"): "sha256:different-old-config"}
    result = validate_external_candidate_package(package, repo_root=".", known_version_fingerprints=known)
    assert result.status is AdmissionStatus.REJECTED_VERSION_MUTATION


def test_identical_resubmission_under_known_fingerprint_is_accepted():
    package = make_candidate_package(candidate_version="2.0.0", config_hash="sha256:same-config")
    known = {(package.strategy_id, "2.0.0"): "sha256:same-config"}
    result = validate_external_candidate_package(package, repo_root=".", known_version_fingerprints=known)
    assert result.accepted
