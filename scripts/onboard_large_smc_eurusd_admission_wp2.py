"""Portability WP2: re-evaluate ST_LARGE_SMC_V1/EURUSD's VALIDATION_ADMISSION after
defining the missing admission contracts (dataset roles, friction policy, validation
policy, baseline/hypothesis mode, holdout boundary) -- see
artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/.

Does NOT supersede or overwrite scripts/onboard_large_smc_portability_wp1.py's
committed WP1 report (PORTABILITY_WP1_ADMISSION_REPORT.json), which remains the
historical WP1 snapshot for the full EURUSD/GBPUSD/USDJPY/XAUUSD universe. This script
produces a separate, dated EURUSD-only WP2 report reflecting the newly-defined (but
still PROPOSED/NOT_AVAILABLE) contracts.

Read-only: no strategy execution, no G0/G2/G3 evaluation, no holdout access, no
optimization, no file write to any governance/strategy file. Symbols other than EURUSD
are out of scope for this mission (canonical universe unchanged:
large_smc_research.engine.FROZEN_INSTRUMENT_UNIVERSE = ("EURUSD",)).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validation_framework.ag_validation_methodology import METHODOLOGY_ID  # noqa: E402
from validation_framework.svos_contracts import StrategyValidationProfile  # noqa: E402
from validation_framework.validation_admission import run_validation_admission  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTRACTS_DIR = os.path.join(REPO_ROOT, "artifacts", "validation", "ST_LARGE_SMC_V1", "EURUSD_ADMISSION_CONTRACTS")


def _sha256_of_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load_contract(filename: str) -> dict:
    with open(os.path.join(CONTRACTS_DIR, filename), encoding="utf-8") as fh:
        return json.load(fh)


def build_large_smc_eurusd_profile_v2() -> StrategyValidationProfile:
    spec_path = os.path.join(REPO_ROOT, "docs", "specs", "LARGE_SMC_V1_SPEC.md")

    dataset_contract = _load_contract("dataset_role_contract.json")
    friction_contract = _load_contract("friction_policy_contract.json")
    validation_contract = _load_contract("validation_policy_contract.json")
    baseline_contract = _load_contract("baseline_hypothesis_mode.json")
    holdout_contract = _load_contract("holdout_boundary_contract.json")

    # Dataset roles: only the CONFIRMED-consumed DEVELOPMENT window is declared --
    # never the UNKNOWN remainder (fail-closed, per dataset_role_contract.json).
    dataset_roles = {
        entry["dataset_id"]: entry["assigned_role"]
        for entry in dataset_contract["consumed_windows"]
    }

    # Friction/validation policy stay None: both contracts are status=PROPOSED,
    # owner_signature=REQUIRED -- a PROPOSED contract must never be treated as SIGNED
    # (WP2-7). Only a SIGNED contract may ever populate these ref fields.
    friction_policy_ref = None
    assert friction_contract["status"] == "PROPOSED"
    validation_policy_ref = None
    assert validation_contract["status"] == "PROPOSED"

    # Hypothesis/baseline mode IS a mode determination (not a governance signature) --
    # safe to record now.
    hypothesis_state = baseline_contract["mode"]

    # Holdout stays None: HOLDOUT_BOUNDARY_STATUS = NOT_AVAILABLE.
    holdout_metadata = None
    assert holdout_contract["HOLDOUT_BOUNDARY_STATUS"] == "NOT_AVAILABLE"

    return StrategyValidationProfile(
        strategy_id="ST_LARGE_SMC_V1",
        strategy_version="1.0.7",
        methodology_id=METHODOLOGY_ID,
        strategy_spec_ref="docs/specs/LARGE_SMC_V1_SPEC.md",
        strategy_spec_hash=_sha256_of_file(spec_path),
        implementation_ref="src/large_smc_research/engine.py",
        symbols=("EURUSD",),
        timeframes=("D1", "H1", "M5"),
        session_timezone_contract_ref=(
            "strategies/ST_LARGE_SMC_V1.yaml: timezone=UTC; "
            "daily_or_session_reset=NOT_APPLICABLE (no session/day boundary participates in identity)"
        ),
        dataset_roles=dataset_roles,
        friction_policy_ref=friction_policy_ref,
        validation_policy_ref=validation_policy_ref,
        hypothesis_state=hypothesis_state,
        mutable_parameters={},
        immutable_parameters={
            "c10_atr_timeframe": "M5", "c10_atr_period": 14, "c10_atr_multiplier": 0.35,
            "c10_min_buffer_pips": 1.5,
        },
        holdout_metadata=holdout_metadata,
        execution_authority_metadata={
            "demo_authorized": False, "live_authorized": False, "proposal_generation_authorized": False,
        },
    )


def main() -> dict:
    profile = build_large_smc_eurusd_profile_v2()
    admission = run_validation_admission(profile, symbol="EURUSD")

    report = {
        "schema_version": "1.0",
        "wp": "PORTABILITY_WP2",
        "strategy_id": profile.strategy_id,
        "strategy_version": profile.strategy_version,
        "symbol": "EURUSD",
        "methodology_id": profile.methodology_id,
        "dataset_roles": dict(profile.dataset_roles),
        "hypothesis_state": profile.hypothesis_state,
        "friction_policy_status": "PROPOSED (owner_signature REQUIRED) -- see EURUSD_ADMISSION_CONTRACTS/friction_policy_contract.json",
        "validation_policy_status": "PROPOSED (owner_signature REQUIRED, reuses config/governance/economic_gate_contract.yaml) -- see EURUSD_ADMISSION_CONTRACTS/validation_policy_contract.json",
        "holdout_boundary_status": "NOT_AVAILABLE -- see EURUSD_ADMISSION_CONTRACTS/holdout_boundary_contract.json",
        "admission": {
            "result": admission.result.value,
            "reason_codes": list(admission.reason_codes),
        },
        "g0_readiness": "NOT_READY" if admission.result.value != "PASS" else "READY_FOR_G0_EVALUATION",
        "owner_decisions_required": [
            "Sign or reject artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_policy_contract.json",
            "Sign config/governance/economic_gate_contract.yaml (repository-wide; reused as Large SMC's validation policy)",
            "Authorize a dedicated holdout-provenance audit for the UNKNOWN remainder of EURUSD_M5_202504211715_202607310000",
        ],
    }

    out_path = os.path.join(CONTRACTS_DIR, "..", "EURUSD_ADMISSION_WP2_REPORT.json")
    out_path = os.path.normpath(out_path)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")

    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
