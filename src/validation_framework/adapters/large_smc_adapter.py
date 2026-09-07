"""AG_EGSVF_V1 Large-SMC adapter -- ST_LARGE_SMC_V1.

Read-only translator. Produces GateResults/evidence and the one strategy-specific
additive requirement (C10_STOP_POLICY) only -- promotion_eligible and
promotion_blockers on the returned record are the verbatim output of
evaluator.evaluate_transition(), never independently computed here (see
AG_EGSVF_V1_PROMOTION_INVARIANT_HARDENING: PromotionEvaluator is the sole authority for
eligibility/blockers; this adapter must not become a second one).

Discovered evidence sources:

- Identity/authority:  strategies/ST_LARGE_SMC_V1.yaml (version, line 561:
                        initial_stop: UNSIGNED = C10; line 101:
                        proposal_generation_authorized: false), strategies/registry.yaml.
- Spec fidelity:       the strategy config correctly declares its own C10 gap
                        (UNSIGNED) and its own proposal-authorization state (false), and
                        tests/test_large_smc_execution_boundary.py (added this session)
                        proves the research package/runner scripts never import an
                        execution module -- the implementation enforces what the config
                        declares. Per AGENT PROMPT section 40, SPEC_FIDELITY = PASS here
                        is correct even though C10 itself is UNSIGNED: fidelity means
                        "the code correctly implements what the contract says," not
                        "every contract field is signed."
- No-lookahead:        tests/test_historical_replay_no_lookahead.py -- Large-SMC's
                        research engine composes historical_replay.stage2 (see
                        src/large_smc_research/ discovery notes), so this suite's D1/H1/
                        M5 bar-visibility guarantees apply to it directly, not by
                        analogy.
- Historical replay:   artifacts/backtests/golden/two_stage_golden_fixture_v1.json and
                        artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json
                        -- an existing frozen golden fixture + qualified-event corpus.
- Friction:            no Large-SMC-specific cost/friction model or test was found.
- OOS/forward:         no Large-SMC-specific out-of-sample/walk-forward artifact was
                        found (tests/test_smc_walkforward.py is scoped to the shared
                        advisory Structure/Supply-Demand/Liquidity skills, not
                        ST_LARGE_SMC_V1's own candidate economics).
- C10:                 strategies/ST_LARGE_SMC_V1.yaml:561, UNSIGNED.
- C14:                 strategies/registry.yaml's ST_LARGE_SMC_V1 note + PROJECT_STATUS.md's
                        "C14 (duplicate/re-entry) is PARTIALLY_RESOLVED" description:
                        occurrence/candidate identity resolved (proposals/occurrence_identity.py,
                        source_id fields on M1Result/M2Result/M3Result), migration into the
                        live proposals/lifecycle.py store still SHARED_CHANGE_REQUIRED, and
                        post-fill re-entry DEFERRED.
- Execution capability/authority: proposal_generation_authorized: false; no execution
                        module import anywhere in the research package (execution
                        boundary test above).
"""
from __future__ import annotations

from datetime import datetime, timezone

from validation_framework.evaluator import evaluate_transition
from validation_framework.models import (
    GateResult,
    GateStatus,
    LifecycleStage,
    StrategyIdentity,
    StrategyValidationRecord,
)

STRATEGY_ID = "ST_LARGE_SMC_V1"
SEMANTIC_VERSION = "1.0.6"  # strategies/ST_LARGE_SMC_V1.yaml:4

EVALUATOR_VERSION = "AG_EGSVF_V1"

# Strategy-specific stricter transition requirement (AGENT PROMPT section 21): even if
# generic OFFLINE_RESEARCH -> FORWARD_RESEARCH gates all passed, this strategy may not
# advance while its own signed-stop contract is UNSIGNED. Kept as a named, inspectable
# extra requirement rather than folded into SPEC_FIDELITY (which stays PASS -- see
# module docstring / AGENT PROMPT section 40).
STRATEGY_TRANSITION_OVERRIDES = {
    (LifecycleStage.OFFLINE_RESEARCH, LifecycleStage.FORWARD_RESEARCH): ("C10_STOP_POLICY",),
}


def build_large_smc_record(repo_root: str = ".") -> StrategyValidationRecord:
    now = datetime.now(timezone.utc)
    identity = StrategyIdentity(strategy_id=STRATEGY_ID, semantic_version=SEMANTIC_VERSION)

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
        ("strategies/ST_LARGE_SMC_V1.yaml", "tests/test_large_smc_execution_boundary.py"),
        {"note": "Config correctly declares its own C10/proposal-authorization gaps; implementation enforces them. See section 40 distinction: SPEC_FIDELITY != C10_SIGNED."},
    )

    gates["DETERMINISM"] = gate(
        "DETERMINISM",
        GateStatus.PARTIAL,
        ("proposals/occurrence_identity.py",),
        {"note": "Candidate-occurrence identity is deterministic and unit-tested; full research-engine determinism across the whole D1/H1/M5 pipeline not separately proven."},
    )

    gates["NO_LOOKAHEAD"] = gate(
        "NO_LOOKAHEAD",
        GateStatus.PASS,
        ("tests/test_historical_replay_no_lookahead.py",),
    )

    gates["HISTORICAL_REPLAY"] = gate(
        "HISTORICAL_REPLAY",
        GateStatus.PASS,
        (
            "artifacts/backtests/golden/two_stage_golden_fixture_v1.json",
            "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json",
        ),
    )

    gates["FRICTION_STRESS_TEST"] = gate(
        "FRICTION_STRESS_TEST",
        GateStatus.NOT_VERIFIED,
        (),
        {"note": "No Large-SMC-specific cost/friction model or test found."},
    )

    gates["OOS_VALIDATION"] = gate(
        "OOS_VALIDATION",
        GateStatus.NOT_VERIFIED,
        (),
        {"note": "tests/test_smc_walkforward.py is scoped to shared advisory skills (Structure/Supply-Demand/Liquidity), not ST_LARGE_SMC_V1's own candidate economics."},
    )

    gates["C10_STOP_POLICY"] = gate(
        "C10_STOP_POLICY",
        GateStatus.UNSIGNED,
        ("strategies/ST_LARGE_SMC_V1.yaml:561",),
        {"note": "initial_stop: UNSIGNED -- owner-selected conceptual model AG_NATIVE_INVALIDATION, implementation/contract-freeze still PENDING."},
    )

    gates["C14_DUPLICATE_REENTRY"] = gate(
        "C14_DUPLICATE_REENTRY",
        GateStatus.PARTIAL,
        ("strategies/registry.yaml", "proposals/occurrence_identity.py"),
        {
            "resolved_components": ["C14_OCCURRENCE_IDENTITY", "C14_DUPLICATE_SUPPRESSION"],
            "remaining_components": ["C14_LIVE_STORE_MIGRATION (SHARED_CHANGE_REQUIRED)", "C14_POST_FILL_REENTRY (DEFERRED)"],
        },
    )

    execution_capability = "NONE"
    execution_capability_evidence = ("tests/test_large_smc_execution_boundary.py",)
    execution_authority = "NONE"
    execution_authority_evidence = ("strategies/ST_LARGE_SMC_V1.yaml:101: proposal_generation_authorized=false",)

    lifecycle_stage = LifecycleStage.OFFLINE_RESEARCH
    next_transition = LifecycleStage.FORWARD_RESEARCH

    # Sole promotion authority: evaluator.evaluate_transition(). Required gates for
    # OFFLINE_RESEARCH -> FORWARD_RESEARCH are cumulative-through-FORWARD_RESEARCH
    # (FOUNDATIONAL_INVARIANTS) plus this strategy's own C10_STOP_POLICY addition --
    # NOT FRICTION_STRESS_TEST/OOS_VALIDATION, which belong to a later transition
    # (DEMO_ELIGIBLE) and must not block this earlier one (AGENT PROMPT section 29).
    # strategy_id is passed for consistency/future-proofing; it has no effect on THIS
    # transition since FORWARD_RESEARCH's cumulative set never reaches the abstract
    # SHADOW_ENTRY_EVIDENCE gate (that only enters at OPERATIONAL_SHADOW) -- no
    # concrete Large-SMC shadow-entry gate is invented here (AGENT PROMPT section 19).
    evaluation = evaluate_transition(
        lifecycle_stage,
        next_transition,
        gates,
        strategy_overrides=STRATEGY_TRANSITION_OVERRIDES,
        strategy_id=STRATEGY_ID,
    )

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
            "required_gates": evaluation.required_gates,
            "passed_gates": evaluation.passed_gates,
            "evaluation_violations": evaluation.violations,
            "stage_assignment_provenance": "LEGACY_PRE_EGSVF",
            "C10": "UNSIGNED",
            "C14_overall": "PARTIALLY_RESOLVED",
        },
    )
