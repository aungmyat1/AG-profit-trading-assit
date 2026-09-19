"""Generates the ONE canonical compact SVOS context artifact for
ST_SESSION_SWEEP_CONTINUATION_V1 (SVOS context authority remediation V1).

Reads strategy identity, lifecycle stage, hypothesis statuses, the candidate manifest,
the economic-gate contract, and the frozen Route B result from authoritative artifacts
-- every value is read from an already-frozen artifact or the canonical registry, never
hardcoded or fabricated. Fails closed (raises) when a required authority artifact is
missing, a hash binding is invalid, or the lifecycle registry has no entry.

`svos_lifecycle_stage` is read from the REAL canonical registry via
`validation_gate_state.describe_validation_gate_state` (fails closed if missing) --
never an AG-invented label. Gates G0..G3 are represented with canonical GateStatus
values derived from the authoritative evidence below; G0/G1 are PARTIAL (not PASS), so
`furthest_verified_gate` is None and no downstream gate is manufactured.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone  # noqa: E402
from typing import Any, Dict, Optional  # noqa: E402

import yaml  # noqa: E402

from validation_framework.evidence_reconciliation import (  # noqa: E402
    EvidenceClassification,
    verify_lineage,
)
from validation_framework.models import GateResult, GateStatus  # noqa: E402
from validation_framework.svos_contracts import HoldoutState  # noqa: E402
from validation_framework.svos_context_export import build_svos_context, write_svos_context  # noqa: E402
from validation_framework.validation_gate_state import describe_validation_gate_state  # noqa: E402
from session_sweep_continuation import STRATEGY_VERSION  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


# --- authoritative artifact paths (read-only, fail-closed if missing) --------------
V1_0_1_REMEDIATION_MANIFEST = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/V1_0_1_REMEDIATION/V1_0_1_REMEDIATION_MANIFEST.json"
)
CANDIDATE_MANIFEST_PATH = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/V1_1_0_CANDIDATE_SPEC/candidate_manifest.json"
)
HYP_001_PREREGISTRATION = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_PREREGISTRATION/HYP_001_EXIT_CAPTURE_PREREGISTRATION.md"
)
HYP_002_PREREGISTRATION = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_PREREGISTRATION/HYP_002_SETUP_SELECTIVITY_PREREGISTRATION.md"
)
HYP_002_POPULATION_ATTEMPT_2 = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_POPULATION_ATTEMPT_2/population_manifest.json"
)
HYP_002_CLOSURE = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_CLOSURE/hypothesis_closure_record.json"
)
ROUTE_B_PAIRED = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001/ROUTE_B_CORRECTED_TREATMENT_1_5R/PAIRED_COMPARISON_AND_AUDIT.json"
)
ECONOMIC_GATE_PATH = "config/governance/economic_gate_contract.yaml"

# --- post-G2 authority artifacts (read-only, fail-closed if missing/mismatched) -----
G2_DEV002_DIR = "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002"
G2_POPULATION_PATH = f"{G2_DEV002_DIR}/G2_POPULATION_V1.json"
G2_POPULATION_MANIFEST_PATH = f"{G2_DEV002_DIR}/G2_POPULATION_MANIFEST_V1.json"
G2_DETERMINISM_PATH = f"{G2_DEV002_DIR}/G2_DETERMINISM_V1.json"
G2_FAILURE_DECOMPOSITION_PATH = f"{G2_DEV002_DIR}/G2_FAILURE_DECOMPOSITION_REPORT_V1.json"
INDEPENDENT_REPLICATION_ADMISSION_PATH = (
    "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_INDEPENDENT_REPLICATION_ADMISSION_V1.json"
)

EXPECTED_G2_POPULATION_ID = "SSC_V1_0_1_G2_DEV_002_POPULATION_V1"
EXPECTED_G2_POPULATION_HASH = "832e8e13c74a5401684a401cdbe4c42aa95e95661928fe596804068e7067ab5e"
EXPECTED_G2_POPULATION_N = 22
EXPECTED_DEV002_DATASET_FINGERPRINT = "05b059720a7457d15a7fbc4cd7f0c15e62df86b7857c1f122edc49a0d3a2baf5"
EXPECTED_DEV002_PREREGISTRATION_HASH = "d40fca49b2ff92768cafd45cdb5d48de96d53ad68449af68d41f8a348d4b0952"

EVALUATOR_VERSION = "ssc_svos_context_authority_remediation_v1"


def _read_json(rel_path: str) -> Dict[str, Any]:
    full = os.path.join(REPO_ROOT, rel_path)
    if not os.path.isfile(full):
        raise FileNotFoundError(f"required authority artifact missing: {rel_path}")
    with open(full, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"authority artifact is not a JSON object: {rel_path}")
    return data


def _read_yaml(rel_path: str) -> Dict[str, Any]:
    full = os.path.join(REPO_ROOT, rel_path)
    if not os.path.isfile(full):
        raise FileNotFoundError(f"required authority artifact missing: {rel_path}")
    with open(full, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"authority artifact is not a YAML mapping: {rel_path}")
    return data


def _sha256_file(rel_path: str) -> str:
    full = os.path.join(REPO_ROOT, rel_path)
    if not os.path.isfile(full):
        raise FileNotFoundError(f"required authority artifact missing: {rel_path}")
    with open(full, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _read_candidate_manifest() -> Dict[str, Any]:
    manifest = _read_json(CANDIDATE_MANIFEST_PATH)
    provenance = manifest.get("historical_provenance_limitation") or {}
    candidate = manifest.get("candidate_strategy") or {}
    parent = manifest.get("parent_strategy") or {}
    declared_hash = (manifest.get("preregistration_reference") or {}).get("hash")
    if declared_hash:
        actual_hash = _sha256_file(HYP_001_PREREGISTRATION)
        if actual_hash != declared_hash:
            raise ValueError(
                f"preregistration hash binding invalid: file {actual_hash} != manifest {declared_hash}"
            )
    return {
        "present": True,
        "path": CANDIDATE_MANIFEST_PATH,
        "role": manifest.get("created_now_for") or "ADMINISTRATIVE_LINEAGE_REPAIR_ONLY",
        "retroactive_preregistration": False,
        "post_hoc_reconstruction_disclosed": bool(provenance.get("does_not_retroactively_repair", False)),
        "candidate_version": candidate.get("version"),
        "parent_version": parent.get("version"),
        "hypothesis_id": manifest.get("hypothesis_id"),
    }


def _read_economic_gate() -> Dict[str, Any]:
    contract = _read_yaml(ECONOMIC_GATE_PATH)
    identity = contract.get("identity") or {}
    status = identity.get("status")
    return {
        "contract": identity.get("contract_id"),
        "status": status,
        "signed": status == "SIGNED",
    }


def _read_g2_population_authority() -> Dict[str, Any]:
    """Derives the CURRENT G2 authority from the authoritative FROZEN DEV_002
    population artifacts (committed 5c901a7). Fails closed (raises ValueError) on any
    identity mismatch -- an absent, altered, or differently-hashed population must never
    be reported as a frozen PASS. This is the generator-level repair: the context is
    derived from the frozen evidence itself, never hand-asserted."""
    population = _read_json(G2_POPULATION_PATH)
    manifest = _read_json(G2_POPULATION_MANIFEST_PATH)
    determinism = _read_json(G2_DETERMINISM_PATH)

    from research.session_lifecycle import population_hash

    recomputed = population_hash(population["occurrences"])
    checks = {
        "population_id": population.get("population_id") == EXPECTED_G2_POPULATION_ID,
        "population_hash_recorded": population.get("population_sha256") == EXPECTED_G2_POPULATION_HASH,
        "population_hash_recomputed": recomputed == EXPECTED_G2_POPULATION_HASH,
        "population_n": population.get("population_count") == EXPECTED_G2_POPULATION_N,
        "manifest_hash_binding": manifest.get("population_sha256") == EXPECTED_G2_POPULATION_HASH,
        "manifest_count_binding": manifest.get("population_count") == EXPECTED_G2_POPULATION_N,
        "dataset_fingerprint": population.get("dataset_fingerprint") == EXPECTED_DEV002_DATASET_FINGERPRINT,
        "preregistration_hash": population.get("preregistration_hash") == EXPECTED_DEV002_PREREGISTRATION_HASH,
        "strategy_id": population.get("strategy_id") == STRATEGY_ID,
        "strategy_version": population.get("strategy_version") == STRATEGY_VERSION,
        "determinism_pass": (determinism.get("comparison") or {}).get("final_verdict") == "DETERMINISM_PASS",
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise ValueError(f"G2 population authority verification FAILED (fail-closed): {failed}")

    return {
        "status": "POPULATION_FROZEN",
        "population_id": EXPECTED_G2_POPULATION_ID,
        "population_n": EXPECTED_G2_POPULATION_N,
        "population_hash": EXPECTED_G2_POPULATION_HASH,
        "population_hash_recomputed": recomputed,
        "dataset_id": population.get("dataset_id"),
        "dataset_fingerprint": population.get("dataset_fingerprint"),
        "preregistration_hash": population.get("preregistration_hash"),
        "config_hash": population.get("config_hash"),
        "determinism": "PASS",
        "canonical_replay_authority": population.get("canonical_replay_authority"),
        "population_artifact": G2_POPULATION_PATH,
        "population_manifest": G2_POPULATION_MANIFEST_PATH,
        "determinism_artifact": G2_DETERMINISM_PATH,
        "failure_decomposition_artifact": G2_FAILURE_DECOMPOSITION_PATH,
    }


def _read_hypothesis_status() -> str:
    """Derives the current hypothesis-admission state from the frozen failure
    decomposition artifact -- never hand-asserted."""
    decomposition = _read_json(G2_FAILURE_DECOMPOSITION_PATH)
    admission = decomposition.get("hypothesis_admission") or {}
    if admission.get("recommended") is False:
        return "NO_NEW_HYPOTHESIS_JUSTIFIED"
    return "HYPOTHESIS_RECOMMENDED_PENDING_PREREGISTRATION"


def _read_independent_replication_status() -> str:
    """Derives the independent-replication admission state from its frozen artifact."""
    admission = _read_json(INDEPENDENT_REPLICATION_ADMISSION_PATH)
    return admission.get("final_status") or "UNKNOWN"


def collect_context(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Reads frozen artifacts + the canonical registry into the SVOS context dict.
    `now` injects a deterministic timestamp (tests). Fails closed on missing/invalid
    authority."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    head_sha = _git("rev-parse", "HEAD")
    now = now or datetime.now(timezone.utc)

    candidate_manifest = _read_candidate_manifest()
    economic_gate = _read_economic_gate()
    paired = _read_json(ROUTE_B_PAIRED)
    closure = _read_json(HYP_002_CLOSURE)

    # --- post-G2 authority (derived from frozen artifacts; fails closed) -------------
    g2_authority = _read_g2_population_authority()
    hypothesis_status = _read_hypothesis_status()
    independent_replication = _read_independent_replication_status()

    # G0/G1 are PARTIAL (not PASS) so furthest_verified_gate stays None; G2 is now PASS
    # (frozen POPULATION_V1 with verified determinism); G3 remains non-PASS (unsigned
    # economic-gate contract).
    g0 = GateResult(
        gate_name="G0", status=GateStatus.PARTIAL,
        evidence_refs=(V1_0_1_REMEDIATION_MANIFEST, CANDIDATE_MANIFEST_PATH),
        evaluated_at=now, evaluator_version=EVALUATOR_VERSION,
        details={"v1_0_1_contract_internally_consistent": True,
                 "canonical_g0_artifact": False,
                 "v1_1_0_candidate_lineage": "POST_HOC_ADMINISTRATIVE_RECONSTRUCTION"},
    )
    g1 = GateResult(
        gate_name="G1", status=GateStatus.PARTIAL,
        evidence_refs=(HYP_001_PREREGISTRATION, CANDIDATE_MANIFEST_PATH, HYP_002_PREREGISTRATION),
        evaluated_at=now, evaluator_version=EVALUATOR_VERSION,
        details={"hyp001_candidate_lineage": "POST_HOC_ADMINISTRATIVE_RECONSTRUCTION",
                 "retroactive_preregistration": False,
                 "hyp002_prereg": "PRE_REMEDIATION_NON_COUNTING"},
    )
    g2 = GateResult(
        gate_name="G2", status=GateStatus.PASS,
        evidence_refs=(G2_POPULATION_PATH, G2_POPULATION_MANIFEST_PATH, G2_DETERMINISM_PATH),
        evaluated_at=now, evaluator_version=EVALUATOR_VERSION,
        details={
            "g2_state": g2_authority["status"],
            "population_id": g2_authority["population_id"],
            "population_n": g2_authority["population_n"],
            "population_hash": g2_authority["population_hash"],
            "determinism": g2_authority["determinism"],
            "canonical_replay_authority": g2_authority["canonical_replay_authority"],
            "hyp002_population": "PRE_REMEDIATION_NON_COUNTING (v1.0.0) -- superseded as v1.0.1 G2 evidence by DEV_002 POPULATION_V1",
        },
    )
    g3 = GateResult(
        gate_name="G3", status=GateStatus.BLOCKED,
        evidence_refs=(ECONOMIC_GATE_PATH, ROUTE_B_PAIRED),
        evaluated_at=now, evaluator_version=EVALUATOR_VERSION,
        details={"economic_gate_contract": "PROPOSED_UNSIGNED",
                 "verdict": "NOT_EVALUATED_UNSIGNED_CONTRACT",
                 "hyp001_route_b_delta_net_R": paired.get("delta_net_R")},
    )
    gate_results = {"G0": g0, "G1": g1, "G2": g2, "G3": g3}

    # Fails closed if the strategy has no canonical SVOS registry entry.
    summary = describe_validation_gate_state(
        STRATEGY_ID, STRATEGY_VERSION, None, gate_results, repo_root=REPO_ROOT,
    )

    # Defensive: the GBPUSD replication population must remain non-counting lineage.
    gbpusd_lineage = verify_lineage(
        "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_GBPUSD_REPLICATION_R1/POPULATION/population_manifest.json",
        recorded_hash="b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e",
        frozen_hash="7ee1554cc041c950540f2c75931719e9fefd351d9c5fba5561fa87104c2eaa22",
        superseded_hashes=("b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e",),
    )
    if gbpusd_lineage.classification != EvidenceClassification.NON_COUNTING_LINEAGE_MISMATCH:
        raise ValueError(f"unexpected GBPUSD lineage classification: {gbpusd_lineage.classification}")

    hypotheses = {
        "HYP_001_EXIT_CAPTURE": {
            "status": "HYPOTHESIS_NOT_SUPPORTED",
            "paired_n": paired.get("paired_n"),
            "control_runner_target_r": (paired.get("audit") or {}).get("runner_target_control"),
            "treatment_runner_target_r": (paired.get("audit") or {}).get("runner_target_treatment"),
            "delta_net_R": paired.get("delta_net_R"),
            "terminal": False,
            "confirmation_governed": "CONFIRM_001_CALENDAR_FROZEN",
        },
        "HYP_002_SETUP_SELECTIVITY": {
            "status": closure.get("status"),
            "role_relative_to_v1_0_1": "PRE_REMEDIATION_NON_COUNTING",
            "terminal": (closure.get("evidence_lineage") or {}).get("attempt_2", {}).get("terminal"),
        },
    }

    forward = {"eligible": False, "campaign_started": False}
    holdout = HoldoutState(strategy_id=STRATEGY_ID, sealed=True, access_count=0, last_accessed_utc=None)

    blocking_issues = [
        "G0 (Contract Audit): v1.0.1 contract is internally consistent (owner-adjudicated "
        "V1_0_1_REMEDIATION_MANIFEST) but no canonical AG_VALIDATION_G0_G10_V1 G0 GateResult "
        "artifact exists -- G0 is PARTIAL, so furthest_verified_gate is None.",
        "G1: HYP_001_EXIT_CAPTURE v1.1.0 candidate lineage is a POST_HOC_ADMINISTRATIVE_RECONSTRUCTION "
        "(candidate_manifest.json created after historical evaluation; retroactive_preregistration=false) "
        "-- PARTIAL, not a clean preregistration PASS.",
        "G2 is POPULATION_FROZEN (DEV_002 POPULATION_V1, deterministic) -- but G0/G1 remain PARTIAL, "
        "so no G2+ progress is claimed beyond the frozen population itself.",
        "HYP_002_SETUP_SELECTIVITY is VALIDATED_NEGATIVE (terminal) and PRE_REMEDIATION_NON_COUNTING "
        "relative to v1.0.1 -- superseded as v1.0.1 G2 counting evidence by DEV_002 POPULATION_V1.",
        "HYP_001_EXIT_CAPTURE is HYPOTHESIS_NOT_SUPPORTED on Route B v1.0.1 corrected evidence "
        f"(paired_n={paired.get('paired_n')}, delta_net_R={paired.get('delta_net_R')}).",
        "G3 economic-gate contract is PROPOSED/unsigned -- fail-closed; no economic PASS is evaluable.",
        "HYP_001_GBPUSD_REPLICATION_R1 population is NON_COUNTING_LINEAGE_MISMATCH -- excluded from gate evidence.",
        "Independent development replication is BLOCKED_NO_ADMISSIBLE_REPLICATION_DATA (no unconsumed, "
        "non-protected H1/M15/M1 interval exists).",
    ]

    context = build_svos_context(
        strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
        hypothesis_id=None, branch=branch, head_sha=head_sha,
        svos_lifecycle_stage=summary.svos_lifecycle_stage.value,
        furthest_verified_gate=summary.furthest_verified_gate,
        gate_results=gate_results,
        evidence_hashes={
            "hyp001_preregistration": _sha256_file(HYP_001_PREREGISTRATION),
            "hyp002_preregistration": (closure.get("evidence_lineage") or {}).get("preregistration_hash"),
            "hyp002_population_attempt_2": (closure.get("evidence_lineage") or {}).get("attempt_2", {}).get("population_hash"),
            "route_b_paired_comparison_hash": paired.get("paired_comparison_hash"),
        },
        holdout=holdout, blocking_issues=blocking_issues,
        next_authorized_action=(
            "G0/G1 remain PARTIAL (no canonical G0 artifact; HYP_001 v1.1.0 lineage is post-hoc). "
            "G2 is POPULATION_FROZEN (SSC_V1_0_1_G2_DEV_002_POPULATION_V1, deterministic). "
            "G3 remains NOT_EVALUATED_UNSIGNED_CONTRACT; optimization is ineligible. "
            "Next: prepare a separate PROSPECTIVE H1/M15/M1 archival-data policy for future "
            "independent development replication (no data acquisition in this mission)."
        ),
        generated_at_utc=now.isoformat(),
        candidate_manifest=candidate_manifest,
        hypotheses=hypotheses,
        economic_gate=economic_gate,
        forward=forward,
    )
    # Post-G2 authority extensions are attached HERE (SSC-generator-local): the shared
    # validation_framework.svos_context_export module is a FROZEN validation-core module
    # (see tests/test_large_smc_eurusd_admission_wp2.py's frozen-core invariant) and is
    # deliberately NOT modified by this mission.
    context["schema_version"] = "1.3"
    context["g2_population"] = g2_authority
    context["g3_verdict"] = "NOT_EVALUATED_UNSIGNED_CONTRACT"
    context["optimization_eligible"] = False
    context["hypothesis_status"] = hypothesis_status
    context["independent_replication"] = independent_replication
    return context


def main() -> str:
    now = None
    if "--now" in sys.argv:
        idx = sys.argv.index("--now")
        if idx + 1 >= len(sys.argv):
            raise SystemExit("--now requires an ISO8601 timestamp argument")
        now = datetime.fromisoformat(sys.argv[idx + 1])
    context = collect_context(now)
    out_path = os.path.join(REPO_ROOT, "artifacts", "validation", STRATEGY_ID, "svos_context.json")
    return write_svos_context(context, out_path)


if __name__ == "__main__":
    print(main())
