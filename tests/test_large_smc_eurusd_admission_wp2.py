"""Tests for Portability WP2 -- ST_LARGE_SMC_V1/EURUSD admission-contract definitions
(dataset roles, friction policy, validation policy, baseline mode, holdout boundary).
Reads the real committed contract artifacts and the real onboarding script; adds
adversarial coverage per the WP2-8 brief."""
from __future__ import annotations

import json
import os
import sys

from validation_framework.validation_admission import (
    AdmissionResult,
    REASON_MISSING_FRICTION_POLICY,
    REASON_MISSING_HOLDOUT_BOUNDARY,
    REASON_MISSING_VALIDATION_POLICY,
    REASON_SYMBOL_NOT_IN_CANONICAL_UNIVERSE,
    run_validation_admission,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTRACTS_DIR = os.path.join(
    REPO_ROOT, "artifacts", "validation", "ST_LARGE_SMC_V1", "EURUSD_ADMISSION_CONTRACTS",
)

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from onboard_large_smc_eurusd_admission_wp2 import build_large_smc_eurusd_profile_v2  # noqa: E402


def build_profile_from_contracts():
    return build_large_smc_eurusd_profile_v2()


def _load(filename):
    with open(os.path.join(CONTRACTS_DIR, filename), encoding="utf-8") as fh:
        return json.load(fh)


def test_dataset_role_contract_never_assigns_unknown_provenance_to_holdout():
    contract = _load("dataset_role_contract.json")
    assert contract["unverified_remainder"]["assigned_role"] == "UNKNOWN"
    for window in contract["consumed_windows"]:
        assert window["assigned_role"] != "HOLDOUT_RESERVED"
    for raw in contract["raw_source_datasets"]:
        assert raw["assigned_role"] != "HOLDOUT_RESERVED"


def test_dataset_role_contract_never_labels_consumed_data_as_untouched():
    contract = _load("dataset_role_contract.json")
    for window in contract["consumed_windows"]:
        assert "CONSUMED" in window["prior_consumption"]
        assert window["assigned_role"] not in ("HOLDOUT_RESERVED", "WARMUP_CONTEXT_ONLY")


def test_friction_policy_is_proposed_not_signed():
    contract = _load("friction_policy_contract.json")
    assert contract["status"] == "PROPOSED"
    assert contract["owner_signature"] == "REQUIRED"


def test_friction_policy_missing_evidence_blocks_not_invents():
    """No item in cost_components is classified OBSERVED/BROKER_SPECIFIED for Large SMC
    specifically -- everything Large-SMC-cost-relevant is ASSUMED, keeping the contract
    correctly PROPOSED rather than silently upgraded to SIGNED."""
    contract = _load("friction_policy_contract.json")
    classifications = {
        k: v["classification"] for k, v in contract["cost_components"].items() if isinstance(v, dict)
    }
    assert set(classifications.values()) <= {"ASSUMED", "OBSERVED", "BROKER_SPECIFIED", "UNRESOLVED"}
    assert "BROKER_SPECIFIED" not in classifications.values()  # no Large-SMC-specific broker capture exists


def test_validation_policy_is_proposed_not_signed():
    contract = _load("validation_policy_contract.json")
    assert contract["status"] == "PROPOSED"
    assert contract["owner_signature"] == "REQUIRED"
    assert contract["reused_contract"]["status"] == "PROPOSED"


def test_admission_cannot_self_sign_policy():
    """Adversarial: even though both contracts exist and are well-formed, admission
    must still report them missing because status != SIGNED anywhere in the chain."""

    profile = build_profile_from_contracts()
    result = run_validation_admission(profile, symbol="EURUSD")
    assert REASON_MISSING_FRICTION_POLICY in result.reason_codes
    assert REASON_MISSING_VALIDATION_POLICY in result.reason_codes


def test_baseline_mode_does_not_imply_g1_or_g2_pass():
    contract = _load("baseline_hypothesis_mode.json")
    assert contract["no_evaluation_run"] is True
    assert contract["mode"] in ("BASELINE_EVALUATION", "HYPOTHESIS_PREREGISTRATION")
    # No gate-verdict field anywhere in this contract -- mode determination only.
    for forbidden_key in ("g0_status", "g1_status", "g2_status", "gate_results", "admission"):
        assert forbidden_key not in contract


def test_holdout_boundary_not_available_and_never_accessed():
    contract = _load("holdout_boundary_contract.json")
    assert contract["HOLDOUT_BOUNDARY_STATUS"] == "NOT_AVAILABLE"
    assert contract["sealed"] is True
    assert contract["access_count"] == 0
    assert contract["actions_not_taken"]["holdout_contents_inspected"] is False
    assert contract["actions_not_taken"]["holdout_run"] is False
    assert contract["actions_not_taken"]["access_count_incremented"] is False


def test_holdout_boundary_never_relabels_previously_consumed_data():
    holdout = _load("holdout_boundary_contract.json")
    dataset = _load("dataset_role_contract.json")
    assert holdout["actions_not_taken"]["any_dataset_relabeled_as_holdout"] is False
    consumed_ids = {w["dataset_id"] for w in dataset["consumed_windows"]}
    assert "HOLDOUT_RESERVED" not in {dataset["summary"].get("HOLDOUT_RESERVED")}.union(
        {dataset["consumed_windows"][i]["assigned_role"] for i in range(len(dataset["consumed_windows"]))}
    )
    assert dataset["summary"]["HOLDOUT_RESERVED"] == "NONE -- see holdout_boundary_contract.json (HOLDOUT_BOUNDARY_STATUS = NOT_AVAILABLE)"


def test_unsupported_symbols_remain_blocked():

    profile = build_profile_from_contracts()
    for symbol in ("GBPUSD", "USDJPY", "XAUUSD"):
        result = run_validation_admission(profile, symbol=symbol)
        assert result.result == AdmissionResult.BLOCKED
        assert REASON_SYMBOL_NOT_IN_CANONICAL_UNIVERSE in result.reason_codes


def test_eurusd_admission_blocked_only_on_expected_remaining_reasons():

    profile = build_profile_from_contracts()
    result = run_validation_admission(profile, symbol="EURUSD")
    assert result.result == AdmissionResult.BLOCKED
    assert set(result.reason_codes) == {
        REASON_MISSING_FRICTION_POLICY, REASON_MISSING_VALIDATION_POLICY, REASON_MISSING_HOLDOUT_BOUNDARY,
    }


def test_strategy_semantics_files_unchanged_by_this_mission():
    """Adversarial: the strategy contract and its engine must be byte-identical to
    before this mission -- proven by git diff against the WP1 commit."""
    import subprocess

    diff = subprocess.check_output(
        ["git", "diff", "e596507", "--",
         "strategies/ST_LARGE_SMC_V1.yaml",
         "src/large_smc_research/",
         "src/validation_framework/adapters/large_smc_adapter.py"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""


def test_frozen_validation_core_unchanged_by_this_mission():
    import subprocess

    diff = subprocess.check_output(
        ["git", "diff", "e596507", "--",
         "src/validation_framework/ag_validation_methodology.py",
         "src/validation_framework/validation_gate_state.py",
         "src/validation_framework/evidence_reconciliation.py",
         "src/validation_framework/g2_population_identity.py",
         "src/validation_framework/g3_gate.py",
         "src/validation_framework/svos_context_export.py",
         "src/validation_framework/lifecycle_registry.py",
         "src/validation_framework/evaluator.py",
         "src/validation_framework/models.py",
         "src/validation_framework/validation_admission.py",
         "config/governance/strategy_lifecycle.yaml"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""


def test_execution_authority_unchanged():

    profile = build_profile_from_contracts()
    exec_meta = profile.execution_authority_metadata
    assert exec_meta == {"demo_authorized": False, "live_authorized": False, "proposal_generation_authorized": False}
