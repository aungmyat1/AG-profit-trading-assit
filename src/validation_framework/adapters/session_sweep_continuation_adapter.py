"""AG_EGSVF_V1 adapter -- ST_SESSION_SWEEP_CONTINUATION_V1.

Minimal, read-only translator following the same pattern as fx_adapter.py. This
strategy's current lifecycle_stage is OFFLINE_RESEARCH (config/governance/
strategy_lifecycle.yaml), which requires NO gates to have passed
(evaluator.get_cumulative_required_gates(OFFLINE_RESEARCH) == ()) -- so this adapter
does not claim SHADOW_SERIES_COMPLETION, OOS_VALIDATION, or any later-stage gate. Its
only job at this milestone is to report the FOUNDATIONAL_INVARIANTS gates truthfully
(SPEC_FIDELITY/DETERMINISM/NO_LOOKAHEAD/HISTORICAL_REPLAY) so a future evaluation of
OFFLINE_RESEARCH -> FORWARD_RESEARCH has real evidence to read, never a fabricated PASS.

promotion_eligible/promotion_blockers on the returned record are the verbatim output of
evaluator.evaluate_transition() -- this adapter is not a second promotion authority.
"""
from __future__ import annotations

from datetime import datetime, timezone

from validation_framework.evaluator import evaluate_transition
from validation_framework.lifecycle_registry import get_lifecycle_stage, get_next_stage
from validation_framework.models import (
    GateResult,
    GateStatus,
    StrategyIdentity,
    StrategyValidationRecord,
)

STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
SEMANTIC_VERSION = "1.0.1"
EVALUATOR_VERSION = "AG_EGSVF_V1"


def build_session_sweep_continuation_record(repo_root: str = ".") -> StrategyValidationRecord:
    now = datetime.now(timezone.utc)
    identity = StrategyIdentity(strategy_id=STRATEGY_ID, semantic_version=SEMANTIC_VERSION)

    def gate(name, status, refs, details=None):
        return GateResult(
            gate_name=name, status=status, evidence_refs=refs, evaluated_at=now,
            evaluator_version=EVALUATOR_VERSION, details=details or {},
        )

    gates = {
        "SPEC_FIDELITY": gate(
            "SPEC_FIDELITY", GateStatus.PASS,
            ("strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml",),
            {"note": "Config matches implemented engine parameters (session_sweep_continuation.config.load_config)."},
        ),
        "DETERMINISM": gate(
            "DETERMINISM", GateStatus.PARTIAL,
            (
                "tests/test_session_sweep_continuation_replay_determinism.py",
                "tests/test_session_sweep_continuation_swing_structure.py",
            ),
            {"note": "Unit-level determinism proven against synthetic fixtures only; no real historical dataset re-run performed this milestone."},
        ),
        "NO_LOOKAHEAD": gate(
            "NO_LOOKAHEAD", GateStatus.PASS,
            (
                "tests/test_session_sweep_continuation_sessions.py",
                "tests/test_session_sweep_continuation_swing_structure.py",
            ),
            {"note": "Reference-session/swing-confirmation/BOS candle-close guards tested directly."},
        ),
        "HISTORICAL_REPLAY": gate(
            "HISTORICAL_REPLAY", GateStatus.NOT_VERIFIED,
            (),
            {"note": "Isolated deterministic replay driver implemented (session_sweep_continuation/replay.py) and unit-tested against synthetic candle fixtures; no live historical price dataset run performed, no resolved outcome-resolution artifacts exist yet for this strategy."},
        ),
    }

    lifecycle_stage = get_lifecycle_stage(STRATEGY_ID, SEMANTIC_VERSION, repo_root)
    next_transition = get_next_stage(lifecycle_stage)
    evaluation = evaluate_transition(lifecycle_stage, next_transition, gates, strategy_id=STRATEGY_ID)

    return StrategyValidationRecord(
        identity=identity,
        lifecycle_stage=lifecycle_stage,
        gates=gates,
        execution_capability="NONE",
        execution_capability_evidence=(),
        execution_authority="RESEARCH_ONLY",
        execution_authority_evidence=("strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml: demo_eligible=false, demo_authorized=false",),
        next_transition=next_transition,
        promotion_eligible=evaluation.eligible,
        promotion_blockers=evaluation.blocking_gates,
        last_updated=now,
        details={
            "required_gates": evaluation.required_gates,
            "passed_gates": evaluation.passed_gates,
            "evaluation_violations": evaluation.violations,
            "milestone": "OFFLINE_RESEARCH implementation milestone -- Phases F/G/H/I (walk-forward, forward shadow, demo_eligible, owner-authorized demo) explicitly out of scope, not claimed.",
        },
    )
