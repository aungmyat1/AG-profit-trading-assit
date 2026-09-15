"""Generates the ONE canonical compact SVOS context artifact for
ST_SESSION_SWEEP_CONTINUATION_V1 (Cycle-1 remediation P1-06 / V2 CONTEXT OUTPUT).

Read-only with respect to all existing evidence: every hash/value below is copied from
an already-existing, already-verified artifact (see the inline citations). Nothing is
computed, inferred, or fabricated. Run manually (`python scripts/export_ssc_svos_context.py`)
-- not wired into any automated pipeline, matching this repository's existing convention
that governance artifacts are produced by an explicit, reviewed action.

`svos_lifecycle_stage` is read from the REAL canonical registry via
`validation_gate_state.describe_validation_gate_state` (fails closed if missing) --
never an AG-invented label. G0 evidence is deliberately OMITTED (not assumed PASS): no
artifact under `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/` records a
canonical AG_VALIDATION_G0_G10_V1-shaped G0 (Contract Audit) result for HYP_002 -- the
closest existing artifact, `HYP_002_G1_G3_MISSION_20260915/G1_AUDIT_REPORT.json`,
audits mission-starting-state consistency under this strategy's own ad hoc
"STAGE_1/STAGE_2" numbering, not the canonical G0 Contract Audit definition (see
ag_validation_methodology.COMPATIBILITY_NOTES). Treating it as G0 evidence would be
exactly the "unknown lineage becomes PASS evidence" failure mode this mission must
avoid, so this script surfaces the gap as a blocking issue instead -- and because G0 is
absent, `furthest_verified_gate` is correctly None (a gap at G0 blocks every later
gate from counting, even though G1/G2/G3 all have real evidence).
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone  # noqa: E402

from validation_framework.evidence_reconciliation import (  # noqa: E402
    EvidenceClassification,
    satisfies_gate,
    verify_lineage,
)
from validation_framework.models import GateResult, GateStatus  # noqa: E402
from validation_framework.svos_contracts import HoldoutState  # noqa: E402
from validation_framework.svos_context_export import build_svos_context, write_svos_context  # noqa: E402
from validation_framework.validation_gate_state import describe_validation_gate_state  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION = "1.0.0"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def main() -> str:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    head_sha = _git("rev-parse", "HEAD")

    # HYP_002_SETUP_SELECTIVITY -- real, closed evidence (see docs/status/
    # AG_SSC_HYP002_SETUP_SELECTIVITY_VALIDATION_STATUS.md and
    # artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json).
    now = datetime.now(timezone.utc)
    g1 = GateResult(
        gate_name="G1", status=GateStatus.PASS,
        evidence_refs=("artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_PREREGISTRATION/HYP_002_SETUP_SELECTIVITY_PREREGISTRATION.md",),
        evaluated_at=now, evaluator_version="manual_reconciliation_v1",
        details={"preregistration_hash": "4e2e4f21c8bf2fe5b461b29ceff670e769445be913d3f193a73e96cc84492fb7"},
    )
    g2 = GateResult(
        gate_name="G2", status=GateStatus.PASS,
        evidence_refs=("artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_POPULATION_ATTEMPT_2/population_manifest.json",),
        evaluated_at=now, evaluator_version="manual_reconciliation_v1",
        details={"population_hash": "cf098f9a1d6459618d6c775a087b5cb443b7f1f7d915f650eeb8268381c2eb94", "reproducible": True},
    )
    g3 = GateResult(
        gate_name="G3", status=GateStatus.FAIL,
        evidence_refs=("artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_ECONOMIC_RESULT_ATTEMPT_2/economic_evaluation.json",),
        evaluated_at=now, evaluator_version="manual_reconciliation_v1",
        details={"treatment_net_expectancy_R": -0.35642188306694594, "hyp002_result": "FAIL"},
    )

    gate_results = {"G1": g1, "G2": g2, "G3": g3}

    # Fails closed if the strategy has no canonical SVOS registry entry -- see
    # validation_gate_state.describe_validation_gate_state.
    summary = describe_validation_gate_state(
        STRATEGY_ID, STRATEGY_VERSION, "HYP_002_SETUP_SELECTIVITY", gate_results, repo_root=REPO_ROOT,
    )

    # P1-05: independently reconfirm the GBPUSD lane's population lineage mismatch is
    # still correctly excluded (defensive -- this context export does not cite that
    # population as evidence for anything, but verifies no caller could accidentally
    # treat it as COUNTING).
    gbpusd_lineage = verify_lineage(
        "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_GBPUSD_REPLICATION_R1/POPULATION/population_manifest.json",
        recorded_hash="b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e",
        frozen_hash="7ee1554cc041c950540f2c75931719e9fefd351d9c5fba5561fa87104c2eaa22",
        superseded_hashes=("b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e",),
    )
    assert gbpusd_lineage.classification == EvidenceClassification.NON_COUNTING_LINEAGE_MISMATCH
    assert satisfies_gate(gbpusd_lineage) is False

    holdout = HoldoutState(strategy_id=STRATEGY_ID, sealed=True, access_count=0, last_accessed_utc=None)

    blocking_issues = [
        "G0 (Contract Audit) has no canonical AG_VALIDATION_G0_G10_V1-shaped evidence "
        "for HYP_002 -- omitted rather than assumed PASS, so furthest_verified_gate is "
        "None even though G1/G2/G3 each have real evidence.",
        "HYP_002_SETUP_SELECTIVITY closed VALIDATED_NEGATIVE at G3 -- terminal, must "
        "not be rerun, reinterpreted, or continued through parameter tuning.",
        "HYP_001_EXIT_CAPTURE (v1.1.0 candidate) blocked at G1: candidate_manifest.json "
        "missing, branch lineage unreconciled (NEEDS_PREREGISTRATION_REPAIR).",
        "HYP_001_GBPUSD_REPLICATION_R1 population is NON_COUNTING_LINEAGE_MISMATCH "
        "(POPULATION_BOUND_TO_SUPERSEDED_PREREGISTRATION) -- independently reverified "
        f"by this export ({gbpusd_lineage.reason}).",
    ]

    context = build_svos_context(
        strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
        hypothesis_id="HYP_002_SETUP_SELECTIVITY", branch=branch, head_sha=head_sha,
        svos_lifecycle_stage=summary.svos_lifecycle_stage.value,
        furthest_verified_gate=summary.furthest_verified_gate,
        gate_results=gate_results,
        evidence_hashes={
            "g1_preregistration": g1.details["preregistration_hash"],
            "g2_population": g2.details["population_hash"],
            "g3_economic_result": None,
        },
        holdout=holdout, blocking_issues=blocking_issues,
        next_authorized_action="Owner adjudication of HYP_001_EXIT_CAPTURE preregistration repair. No Cycle-2 (G4+) work authorized.",
    )

    out_path = os.path.join(
        REPO_ROOT, "artifacts", "validation", STRATEGY_ID, "svos_context.json",
    )
    return write_svos_context(context, out_path)


if __name__ == "__main__":
    print(main())
