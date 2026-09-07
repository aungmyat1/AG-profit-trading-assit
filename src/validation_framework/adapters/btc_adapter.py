"""AG_EGSVF_V1 BTC adapter -- ST_LIQUIDITY_SWEEP_RETEST_V1 (CRYPTO_PERP profile).

Read-only translator. Produces GateResults/evidence only -- promotion_eligible and
promotion_blockers on the returned record are the verbatim output of
evaluator.evaluate_transition(), never independently computed here (see
AG_EGSVF_V1_PROMOTION_INVARIANT_HARDENING: PromotionEvaluator is the sole authority for
eligibility/blockers; this adapter must not become a second one).

Discovered evidence sources:

- Identity/authority:  strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml (version),
                        strategies/registry.yaml (research=true, demo/live_authorized=false).
- Determinism:         tests/test_btc_occurrence_identity.py::test_deterministic_same_inputs_same_id
                        -- proves candidate-occurrence identity is a pure function of its
                        inputs. Scoped to identity generation only, not the full decision
                        pipeline end-to-end, so PARTIAL not PASS.
- No-lookahead:        no BTC-specific no-lookahead test was found (the shared
                        historical_replay no-lookahead suite --
                        tests/test_historical_replay_no_lookahead.py -- covers the
                        FX/Large-SMC replay path, not btc_sweep_research's own pipeline).
- Historical replay:   no BTC backtest/historical-replay artifact or test was found
                        repository-wide.
- Friction:            src/btc_sweep_research/costs.py (fees/slippage/funding),
                        actually wired into src/btc_sweep_research/pipeline.py (calls
                        costs.estimate_costs), with tests/test_btc_costs.py exercising
                        funding-crossing, fee/slippage scaling, and documented defaults.
- OOS/forward:         no OOS/walk-forward artifact found; forward evidence is the
                        observation campaign itself (see below).
- Natural campaign accrual: no archive directory exists under journal/reports/btc/ (the
                        FX equivalent, journal/reports/fx/, does exist and is populated)
                        -- there is no evidence of even one archived in-window
                        observation. Counted as 0, matching the owner-authorized
                        campaign's own stated status.
- Execution capability: execution.adapter.CryptoExecutionAdapter is NOT_IMPLEMENTED;
                        market-data-only capability exists (BybitLinearPerpFeed).
- Execution authority:  strategies/registry.yaml -- ST_LIQUIDITY_SWEEP_RETEST_V1
                        research=true, demo_authorized=false, live_authorized=false;
                        execution.executor rejects any non-TradeCommand object
                        (tests/test_btc_proposal_execution_boundary.py).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from validation_framework.evaluator import evaluate_transition
from validation_framework.models import (
    GateResult,
    GateStatus,
    LifecycleStage,
    StrategyIdentity,
    StrategyValidationRecord,
)

STRATEGY_ID = "ST_LIQUIDITY_SWEEP_RETEST_V1"
SEMANTIC_VERSION = "2.0.0"  # strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml:4

EVALUATOR_VERSION = "AG_EGSVF_V1"

_CAMPAIGN_TARGET = 30
_CAMPAIGN_ARCHIVE_DIR = os.path.join("journal", "reports", "btc")


def _campaign_observed_count(repo_root: str) -> int:
    """Counts archived in-window observation reports the same way the FX adapter counts
    archived daily reports (journal/reports/<market>/). Returns 0, verified by absence
    of the directory, rather than assuming a number from prose."""
    path = os.path.join(repo_root, _CAMPAIGN_ARCHIVE_DIR)
    if not os.path.isdir(path):
        return 0
    count = 0
    for root, _dirs, files in os.walk(path):
        count += sum(1 for f in files if f.endswith(".json") and ".correction-" not in f)
    return count


def build_btc_record(repo_root: str = ".") -> StrategyValidationRecord:
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
        ("strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml", "strategies/registry.yaml"),
    )

    gates["DETERMINISM"] = gate(
        "DETERMINISM",
        GateStatus.PARTIAL,
        ("tests/test_btc_occurrence_identity.py",),
        {"note": "Candidate-occurrence identity proven deterministic; full end-to-end decision pipeline determinism not separately tested."},
    )

    gates["NO_LOOKAHEAD"] = gate(
        "NO_LOOKAHEAD",
        GateStatus.NOT_VERIFIED,
        (),
        {"note": "No BTC-pipeline-scoped no-lookahead test found; the shared historical_replay no-lookahead suite does not cover btc_sweep_research.pipeline."},
    )

    gates["HISTORICAL_REPLAY"] = gate(
        "HISTORICAL_REPLAY",
        GateStatus.NOT_VERIFIED,
        (),
        {"note": "No BTC backtest/historical-replay artifact or test found repository-wide."},
    )

    gates["FRICTION_STRESS_TEST"] = gate(
        "FRICTION_STRESS_TEST",
        GateStatus.PASS,
        ("src/btc_sweep_research/costs.py", "tests/test_btc_costs.py", "src/btc_sweep_research/pipeline.py:164"),
    )

    gates["OOS_VALIDATION"] = gate(
        "OOS_VALIDATION",
        GateStatus.NOT_VERIFIED,
        (),
    )

    observed = _campaign_observed_count(repo_root)
    gates["NATURAL_CAMPAIGN_ACCRUAL"] = gate(
        "NATURAL_CAMPAIGN_ACCRUAL",
        GateStatus.PASS if observed >= _CAMPAIGN_TARGET else GateStatus.PARTIAL,
        (
            "docs/status/AG_V1_0_3_BTC_OBSERVATION_CAMPAIGN_AUTHORIZATION_STATUS.md",
            f"{_CAMPAIGN_ARCHIVE_DIR}/ (directory absent -> 0 archived observations)" if observed == 0 else _CAMPAIGN_ARCHIVE_DIR,
        ),
        {"observed_count": observed, "target_count": _CAMPAIGN_TARGET, "campaign_authorized": True},
    )

    execution_capability = "MARKET_DATA_ONLY (BybitLinearPerpFeed, public/read-only); NO_ORDER_ADAPTER"
    execution_capability_evidence = (
        "src/execution_runtime/bybit_linear_perp_feed.py",
        "execution/adapter.py: CryptoExecutionAdapter NOT_IMPLEMENTED",
    )
    execution_authority = "RESEARCH_ONLY"
    execution_authority_evidence = (
        "strategies/registry.yaml: ST_LIQUIDITY_SWEEP_RETEST_V1.demo_authorized=false, live_authorized=false",
        "tests/test_btc_proposal_execution_boundary.py",
    )

    lifecycle_stage = LifecycleStage.FORWARD_RESEARCH
    next_transition = LifecycleStage.OPERATIONAL_SHADOW

    # Sole promotion authority: evaluator.evaluate_transition(). Cumulative inheritance
    # re-checks FOUNDATIONAL_INVARIANTS (SPEC_FIDELITY/DETERMINISM/NO_LOOKAHEAD/
    # HISTORICAL_REPLAY) even though the transition being evaluated is
    # FORWARD_RESEARCH -> OPERATIONAL_SHADOW, not OFFLINE_RESEARCH -> FORWARD_RESEARCH --
    # BTC's current stage label does not itself prove those gates ever passed. Passing
    # strategy_id resolves the abstract SHADOW_ENTRY_EVIDENCE milestone gate to BTC's own
    # NATURAL_CAMPAIGN_ACCRUAL (evaluator.MILESTONE_GATE_MAP), not to FX's gate.
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
            "canonical_data_authority": "Bybit V5 linear perpetual, public/read-only (AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION, APPROVED_READ_ONLY_ONLY)",
            "required_gates": evaluation.required_gates,
            "passed_gates": evaluation.passed_gates,
            "evaluation_violations": evaluation.violations,
            "stage_assignment_provenance": "LEGACY_PRE_EGSVF",
        },
    )
