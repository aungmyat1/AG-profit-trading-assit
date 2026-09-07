"""AG_EGSVF_V1 FX adapter -- ST_ASIAN_SWEEP_5R_V1.

Read-only translator. Produces GateResults/evidence only -- promotion_eligible and
promotion_blockers on the returned record are the verbatim output of
evaluator.evaluate_transition(), never independently computed here (see
AG_EGSVF_V1_PROMOTION_INVARIANT_HARDENING: PromotionEvaluator is the sole authority for
eligibility/blockers; this adapter must not become a second one).

Discovered evidence sources (see docs/architecture/AG_EGSVF_V1_LEDGER.md for the full
search trail):

- Identity/authority:  strategies/ST_ASIAN_SWEEP_5R_V1.yaml (version),
                        strategies/registry.yaml (demo_authorized/live_authorized).
- Determinism:         docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_RELEASE_IDENTITY_
                        REMEDIATION_STATUS.md -- a real re-run of
                        scripts/run_post_asian_pilot.py's daily report against the same
                        2026-09-03 journals produced byte-identical decisions/proposals
                        (only the release label differed). Actual repeat-run evidence,
                        not inferred from a test file's existence.
- No-lookahead:        tests/test_strategy_decision_no_lookahead.py (StrategyDecision
                        wrapper, scoped to ST_ASIAN_SWEEP_5R_V1 fixtures) and
                        tests/test_historical_replay_no_lookahead.py (shared
                        historical_replay module bar-visibility guarantees).
- Historical replay:   artifacts/outcome_resolution/records/ST_ASIAN_SWEEP_5R_V1_*.json
                        -- read directly below, not re-resolved. Each record already
                        carries strategy_version and an explicit cost_status field.
- Friction:             the outcome-resolution records above uniformly stamp
                        cost_status="NOT_INCLUDED" -- a real, current, self-declared gap,
                        not an assumption carried from historical discussion.
- OOS/forward:         no dedicated FX out-of-sample/walk-forward artifact or test was
                        found repository-wide (only a shared advisory-skill walk-forward
                        test scoped to Structure/Supply-Demand/Liquidity, not
                        ST_ASIAN_SWEEP_5R_V1's own signal economics).
- Shadow series:       docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_00N_
                        STATUS.md, the dated, frozen classification record for each
                        evaluated day of AG_V1_0_3_FX_SHADOW_SERIES_002. Counts here are
                        read from those documents (as of this evaluation), not recomputed.
- Shadow-entry evidence (concrete resolution of the abstract SHADOW_ENTRY_EVIDENCE
                        milestone gate, AG_EGSVF_V1_STRATEGY_STAGE_CONTRACT_
                        RECONCILIATION -- see evaluator.MILESTONE_GATE_MAP):
                        docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_
                        PREFLIGHT_CLOSURE_STATUS.md, `shadow_entry_ready = YES`,
                        classification `PREFLIGHT_PASS_SHADOW_READY` -- the real, dated
                        governance event that made FX's shadow-validation series
                        eligible to begin. Deliberately NOT sourced from Series 001's own
                        evidence: Series 001 Day 1 was EXCLUDED_DAY and Day 2
                        PENDING_RECONCILIATION (see PROJECT_STATUS.md) -- pre-remediation,
                        non-counting evidence the project itself never treated as
                        qualifying, so it is not treated as qualifying here either.
- Execution capability: execution/executor.py + execution/mt5_gateway.py, DEMO_VERIFIED
                        2026-08-28 (generic MT5 Demo round trip).
- Execution authority:  strategies/registry.yaml -- demo_authorized: false.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Tuple

from validation_framework.adapters.determinism_evidence import load_determinism_evidence
from validation_framework.evaluator import evaluate_transition
from validation_framework.lifecycle_registry import get_lifecycle_stage, get_next_stage
from validation_framework.models import (
    GateResult,
    GateStatus,
    LifecycleStage,
    StrategyIdentity,
    StrategyValidationRecord,
)

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
SEMANTIC_VERSION = "1.1.1"  # strategies/ST_ASIAN_SWEEP_5R_V1.yaml:4 -- read by caller, not hardcoded silently; see build_fx_record's version check

EVALUATOR_VERSION = "AG_EGSVF_V1"

_OUTCOME_RECORDS_DIR = os.path.join(
    "artifacts", "outcome_resolution", "records"
)

# Frozen, dated classification counters for AG_V1_0_3_FX_SHADOW_SERIES_002, read from
# the dated status documents named above (as of this evaluation; re-run the adapter
# after a new dated status doc lands to pick up a new count -- this module does not
# poll or recompute the classification itself).
_SHADOW_SERIES_ID = "AG_V1_0_3_FX_SHADOW_SERIES_002"
_SHADOW_TARGET_VALID_DAYS = 20
_SHADOW_VALID_DAYS = 0
_SHADOW_INVALID_DAYS = 1
_SHADOW_EXCLUDED_DAYS = 0
_SHADOW_PENDING_DAYS = 0
_SHADOW_EVIDENCE_REFS = (
    "docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md",
    "docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_002_STATUS.md",
)


def _read_outcome_records(repo_root: str) -> Tuple[list, Tuple[str, ...]]:
    directory = os.path.join(repo_root, _OUTCOME_RECORDS_DIR)
    refs = []
    records = []
    if not os.path.isdir(directory):
        return records, ()
    for name in sorted(os.listdir(directory)):
        if not name.startswith(STRATEGY_ID) or not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        with open(path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        if record.get("strategy_version") != SEMANTIC_VERSION:
            # Version-bound evidence invariant: never attribute another version's
            # resolved outcome to this identity.
            continue
        records.append(record)
        refs.append(os.path.join(_OUTCOME_RECORDS_DIR, name).replace("\\", "/"))
    return records, tuple(refs)


def build_fx_record(repo_root: str = ".") -> StrategyValidationRecord:
    now = datetime.now(timezone.utc)
    identity = StrategyIdentity(strategy_id=STRATEGY_ID, semantic_version=SEMANTIC_VERSION)

    records, record_refs = _read_outcome_records(repo_root)

    def gate(name, status, refs, details=None):
        return GateResult(
            gate_name=name,
            status=status,
            evidence_refs=refs,
            evaluated_at=now,
            evaluator_version=EVALUATOR_VERSION,
            details=details or {},
        )

    gates = {}

    gates["SPEC_FIDELITY"] = gate(
        "SPEC_FIDELITY",
        GateStatus.PASS,
        ("strategies/ST_ASIAN_SWEEP_5R_V1.yaml", "strategies/registry.yaml"),
        {"note": "entry_order_type resolved to MARKET as of v1.1.1 (AG_EXECUTION_RUNTIME_READINESS_V1, 2026-08-31)"},
    )

    determinism_status, determinism_refs, determinism_details = load_determinism_evidence(
        repo_root, STRATEGY_ID, SEMANTIC_VERSION
    )
    gates["DETERMINISM"] = gate(
        "DETERMINISM",
        determinism_status,
        determinism_refs
        + (
            "docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_RELEASE_IDENTITY_REMEDIATION_STATUS.md",
        ),
        {
            **determinism_details,
            "note": (
                "Full semantic pipeline (strategy_engine.engine.evaluate -> "
                "map_trade_signal_to_decision) proven repeat-run-identical over a fixed "
                "fixture (AG_EGSVF_V1_CROSS_STRATEGY_DETERMINISM_EVIDENCE_RECONCILIATION); "
                "the release-identity repeat-run remains additional supporting evidence."
            ),
        },
    )

    gates["NO_LOOKAHEAD"] = gate(
        "NO_LOOKAHEAD",
        GateStatus.PASS,
        (
            "tests/test_strategy_decision_no_lookahead.py",
            "tests/test_historical_replay_no_lookahead.py",
        ),
    )

    if records:
        cost_included = sum(1 for r in records if r.get("cost_status") == "INCLUDED")
        historical_status = GateStatus.PARTIAL
        historical_details = {
            "resolved_record_count": len(records),
            "resolution_contract_version": records[0].get("resolution_contract_version"),
            "note": "Resolved outcomes exist and are version-bound to 1.1.1, but the resolution contract is itself labeled DRAFT.",
        }
    else:
        historical_status = GateStatus.NOT_VERIFIED
        historical_details = {"resolved_record_count": 0}
    gates["HISTORICAL_REPLAY"] = gate("HISTORICAL_REPLAY", historical_status, record_refs, historical_details)

    if records:
        not_included = sum(1 for r in records if r.get("cost_status") == "NOT_INCLUDED")
        if not_included == len(records):
            friction_status = GateStatus.NOT_VERIFIED
        elif not_included == 0:
            friction_status = GateStatus.PASS
        else:
            friction_status = GateStatus.PARTIAL
    else:
        friction_status = GateStatus.NOT_VERIFIED
    gates["FRICTION_STRESS_TEST"] = gate(
        "FRICTION_STRESS_TEST",
        friction_status,
        record_refs,
        {"note": "Every resolved outcome record's own cost_status field is read verbatim, not inferred."},
    )

    gates["OOS_VALIDATION"] = gate(
        "OOS_VALIDATION",
        GateStatus.NOT_VERIFIED,
        (),
        {"note": "No FX-scoped out-of-sample/walk-forward artifact or test found repository-wide."},
    )

    shadow_status = (
        GateStatus.PASS
        if _SHADOW_VALID_DAYS >= _SHADOW_TARGET_VALID_DAYS
        else GateStatus.PARTIAL
    )
    gates["SHADOW_SERIES_COMPLETION"] = gate(
        "SHADOW_SERIES_COMPLETION",
        shadow_status,
        _SHADOW_EVIDENCE_REFS,
        {
            "series_id": _SHADOW_SERIES_ID,
            "valid_days": _SHADOW_VALID_DAYS,
            "target_valid_days": _SHADOW_TARGET_VALID_DAYS,
            "invalid_days": _SHADOW_INVALID_DAYS,
            "excluded_days": _SHADOW_EXCLUDED_DAYS,
            "pending_days": _SHADOW_PENDING_DAYS,
        },
    )

    # Concrete resolution of the abstract SHADOW_ENTRY_EVIDENCE milestone gate for this
    # strategy family (evaluator.MILESTONE_GATE_MAP["ST_ASIAN_SWEEP_5R_V1"]). See module
    # docstring for why this is sourced from the MT5 data-readiness preflight closure,
    # not from Series 001 (non-counting, pre-remediation evidence).
    gates["FX_SHADOW_ENTRY_PREFLIGHT_PASS"] = gate(
        "FX_SHADOW_ENTRY_PREFLIGHT_PASS",
        GateStatus.PASS,
        (
            "docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md",
        ),
        {
            "note": "shadow_entry_ready=YES, classification=PREFLIGHT_PASS_SHADOW_READY -- MT5 IPC connected to a demo account, EURUSD/GBPUSD both resolved with 24 well-formed closed M15 bars, session/clock contract validated, no broker mutation.",
        },
    )

    execution_capability = "MT5_DEMO_AVAILABLE"
    execution_capability_evidence = (
        "execution/executor.py",
        "execution/mt5_gateway.py",
        "docs/status/ (2026-08-28 DEMO_VERIFIED round trip, ticket 1879685149)",
    )
    execution_authority = "SHADOW_PROPOSAL_ONLY"
    execution_authority_evidence = ("strategies/registry.yaml: ST_ASIAN_SWEEP_5R_V1.demo_authorized=false",)

    # Sole lifecycle-stage authority: config/governance/strategy_lifecycle.yaml (see
    # lifecycle_registry.py). Fails closed (raises LifecycleRegistryError) rather than
    # ever guessing a stage -- including on a semantic-version mismatch between this
    # constant and the registry's own recorded version for this strategy.
    lifecycle_stage = get_lifecycle_stage(STRATEGY_ID, SEMANTIC_VERSION, repo_root)
    next_transition = get_next_stage(lifecycle_stage)

    # Sole promotion authority: evaluator.evaluate_transition(), never a hand-picked
    # subset of gates. Cumulative inheritance means this call also re-checks
    # FOUNDATIONAL_INVARIANTS even though FX's current `lifecycle_stage` label is
    # already OPERATIONAL_SHADOW -- that label was assigned before AG-EGSVF existed and
    # is not itself proof those gates were ever evaluated (see
    # docs/architecture/AG_EGSVF_V1_LEDGER.md, "legacy stage assignments are not
    # evidence"). Passing strategy_id resolves the abstract SHADOW_ENTRY_EVIDENCE gate to
    # FX_SHADOW_ENTRY_PREFLIGHT_PASS above -- not to BTC's NATURAL_CAMPAIGN_ACCRUAL.
    evaluation = evaluate_transition(lifecycle_stage, next_transition, gates, strategy_id=STRATEGY_ID)

    return StrategyValidationRecord(
        identity=identity,
        lifecycle_stage=lifecycle_stage,
        gates=gates,
        execution_capability=execution_capability,
        execution_capability_evidence=execution_capability_evidence,
        execution_authority=execution_authority,
        execution_authority_evidence=execution_authority_evidence,
        next_transition=next_transition,
        promotion_eligible=evaluation.eligible,
        promotion_blockers=evaluation.blocking_gates,
        last_updated=now,
        details={
            "candidate_geometry_status": "SESSION_RANGE_25 remains candidate/research-only (artifacts/candidate_research/model_a_session_range_25/), not wired into active runtime, no promotion performed by this framework or this task.",
            "required_gates": evaluation.required_gates,
            "passed_gates": evaluation.passed_gates,
            "evaluation_violations": evaluation.violations,
            "stage_assignment_provenance": "LEGACY_PRE_EGSVF",
        },
    )
