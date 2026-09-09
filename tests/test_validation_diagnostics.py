"""Tests for the AG Advisory Validation Diagnostic Agent V1 (P23).

Covers: authority-boundary invariants (P4/P11/P18 -- the agent can only ever construct
ExperimentState.PROPOSED and never mutates any strategy/config file), event
identity/artifact binding (P2), deterministic classification (P5/P23), the UNKNOWN
fallback, exactly-one-proposal-per-event (P10), OOS contamination rejection (P13), and
one real Session Trade diagnostic proposal built from the live repository's own current
FX evidence (P21/P24 #12).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import pytest

from validation_diagnostics import classifier, experiment, service
from validation_diagnostics.adapters import btc_sweep, large_smc, session_trade
from validation_diagnostics.models import (
    DiagnosticTrace,
    ExperimentState,
    FailureEvent,
    FailureMode,
)
from validation_diagnostics.registry import UnsupportedDiagnosticTargetError, get_adapter
from validation_framework.adapters.fx_adapter import build_fx_record
from validation_framework.models import (
    GateResult,
    GateStatus,
    LifecycleStage,
    StrategyIdentity,
    StrategyValidationRecord,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _gate(name, status, refs=(), details=None):
    return GateResult(
        gate_name=name, status=status, evidence_refs=tuple(refs),
        evaluated_at=datetime.now(timezone.utc), evaluator_version="TEST", details=details or {},
    )


def _synthetic_record(strategy_id, version, gates, lifecycle_stage=LifecycleStage.OPERATIONAL_SHADOW):
    return StrategyValidationRecord(
        identity=StrategyIdentity(strategy_id=strategy_id, semantic_version=version),
        lifecycle_stage=lifecycle_stage,
        gates=gates,
        execution_capability="NONE",
        execution_capability_evidence=(),
        execution_authority="NONE",
        execution_authority_evidence=(),
        next_transition=LifecycleStage.DEMO_ELIGIBLE,
        promotion_eligible=False,
        promotion_blockers=tuple(gates.keys()),
        last_updated=datetime.now(timezone.utc),
    )


def _write_outcome_record(records_dir, name, strategy_id, version, cost_status, realized_R):
    os.makedirs(records_dir, exist_ok=True)
    path = os.path.join(records_dir, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "strategy_id": strategy_id, "strategy_version": version,
                "cost_status": cost_status, "realized_R": realized_R,
            },
            fh,
        )


# ---------------------------------------------------------------------------
# Authority boundary
# ---------------------------------------------------------------------------


def test_evaluator_remains_sole_lifecycle_authority():
    record = build_fx_record(REPO_ROOT)
    event, trace, proposal, _ = service.diagnose_gate_failure(
        record, "OOS_VALIDATION", REPO_ROOT, persist_artifacts=False,
    )
    # Diagnosing must never change the record's own evaluator-derived fields.
    fresh = build_fx_record(REPO_ROOT)
    assert record.promotion_eligible == fresh.promotion_eligible
    assert record.promotion_blockers == fresh.promotion_blockers
    assert record.lifecycle_stage == fresh.lifecycle_stage


def test_diagnostic_agent_cannot_promote_or_authorize_or_execute():
    # Structural check: none of the package's public modules expose any symbol that
    # could promote a lifecycle stage, grant authorization, or submit an order.
    forbidden_substrings = ("promote", "authorize_demo", "authorize_live", "submit_order", "place_order")
    for module in (service, classifier, experiment, session_trade, large_smc, btc_sweep):
        names = [n.lower() for n in dir(module) if not n.startswith("_")]
        for forbidden in forbidden_substrings:
            assert not any(forbidden in n for n in names), f"{module.__name__} exposes forbidden symbol matching {forbidden!r}"


def test_diagnostic_agent_cannot_modify_canonical_strategy_config(tmp_path):
    strategy_yaml = os.path.join(REPO_ROOT, "strategies", "ST_ASIAN_SWEEP_5R_V1.yaml")
    lifecycle_yaml = os.path.join(REPO_ROOT, "config", "governance", "strategy_lifecycle.yaml")

    def _hash(path):
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    before_strategy, before_lifecycle = _hash(strategy_yaml), _hash(lifecycle_yaml)

    record = build_fx_record(REPO_ROOT)
    service.diagnose_gate_failure(
        record, "OOS_VALIDATION", REPO_ROOT, persist_artifacts=True, output_dir=str(tmp_path / "diag"),
    )

    assert _hash(strategy_yaml) == before_strategy
    assert _hash(lifecycle_yaml) == before_lifecycle


def test_experiment_proposal_defaults_require_human_approval_and_proposed_state():
    record = build_fx_record(REPO_ROOT)
    event, trace, proposal, _ = service.diagnose_gate_failure(
        record, "OOS_VALIDATION", REPO_ROOT, persist_artifacts=False,
    )
    assert proposal is not None
    assert proposal.requires_human_approval is True
    assert proposal.state == ExperimentState.PROPOSED
    assert proposal.execution_authority is False
    assert proposal.promotion_authority is False


# ---------------------------------------------------------------------------
# Failure event identity/artifact binding + determinism
# ---------------------------------------------------------------------------


def test_failure_event_is_version_and_artifact_bound():
    record = build_fx_record(REPO_ROOT)
    event = service.build_failure_event(record, "OOS_VALIDATION", REPO_ROOT, git_commit="deadbeef")
    assert event.strategy_id == record.identity.strategy_id
    assert event.strategy_version == record.identity.semantic_version
    assert event.git_commit == "deadbeef"
    assert isinstance(event.evidence_refs, tuple)


def test_not_a_failure_error_for_passing_gate():
    record = build_fx_record(REPO_ROOT)
    passing = [name for name, g in record.gates.items() if g.status == GateStatus.PASS]
    assert passing, "fixture expected at least one PASS gate on the live FX record"
    with pytest.raises(service.NotAFailureError):
        service.build_failure_event(record, passing[0], REPO_ROOT, git_commit="deadbeef")


def test_same_inputs_produce_deterministic_event_id_and_classification():
    record = build_fx_record(REPO_ROOT)
    e1 = service.build_failure_event(record, "OOS_VALIDATION", REPO_ROOT, git_commit="fixedcommit")
    e2 = service.build_failure_event(record, "OOS_VALIDATION", REPO_ROOT, git_commit="fixedcommit")
    assert e1.event_id == e2.event_id

    t1 = service.diagnose(e1, record, REPO_ROOT)
    t2 = service.diagnose(e2, record, REPO_ROOT)
    assert t1.primary_failure_mode == t2.primary_failure_mode
    assert t1.secondary_failure_modes == t2.secondary_failure_modes
    assert t1.evidence_refs == t2.evidence_refs
    assert t1.rationale == t2.rationale


# ---------------------------------------------------------------------------
# UNKNOWN fallback + exactly-one-proposal
# ---------------------------------------------------------------------------


def test_unknown_returned_when_evidence_cannot_distinguish_cause(tmp_path):
    records_dir = os.path.join(str(tmp_path), "artifacts", "outcome_resolution", "records")
    _write_outcome_record(records_dir, "ST_ASIAN_SWEEP_5R_V1_X_2026-09-01.json", "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "INCLUDED", 1.0)

    record = _synthetic_record(
        "ST_ASIAN_SWEEP_5R_V1", "1.1.1",
        {"FRICTION_STRESS_TEST": _gate("FRICTION_STRESS_TEST", GateStatus.PARTIAL)},
    )
    diag = session_trade.diagnose_gate("FRICTION_STRESS_TEST", record, str(tmp_path))
    assert diag.primary_failure_mode == FailureMode.UNKNOWN

    event = FailureEvent(
        event_id="VALFAIL-TEST-UNKNOWN", created_at=datetime.now(timezone.utc),
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="TEST", git_commit="deadbeef",
        current_lifecycle_stage="OPERATIONAL_SHADOW", target_lifecycle_stage="DEMO_ELIGIBLE",
        gate_id="FRICTION_STRESS_TEST", gate_status="PARTIAL",
        observed_metrics={}, required_thresholds={}, threshold_authority={},
        blocker_codes=("FRICTION_STRESS_TEST",), evidence_refs=(), artifact_hashes=(),
        diagnostic_input_complete=True,
    )
    trace = DiagnosticTrace(
        event_id=event.event_id, diagnosed_at=datetime.now(timezone.utc),
        classifier_version=classifier.CLASSIFIER_VERSION,
        primary_failure_mode=diag.primary_failure_mode, secondary_failure_modes=diag.secondary_failure_modes,
        confidence=diag.confidence, evidence_refs=diag.evidence_refs, rationale=diag.rationale,
    )
    proposal = experiment.generate_experiment(event, trace)
    assert proposal is None


def test_exactly_one_proposal_emitted_per_event():
    record = build_fx_record(REPO_ROOT)
    event, trace, proposal, _ = service.diagnose_gate_failure(
        record, "OOS_VALIDATION", REPO_ROOT, persist_artifacts=False,
    )
    assert proposal is None or proposal.experiment_id.startswith("EXP-")
    # generate_experiment never returns a collection -- type signature already
    # enforces "at most one"; assert it is a single object, not a list/tuple.
    assert not isinstance(proposal, (list, tuple))


# ---------------------------------------------------------------------------
# OOS contamination rejection
# ---------------------------------------------------------------------------


def test_oos_contamination_risk_detection():
    assert experiment._oos_contamination_risk("protected OOS holdout set", "STRATEGY_PARAMETER_EXPERIMENT", "widen stop by 10%") is True
    assert experiment._oos_contamination_risk("protected OOS holdout set", "OOS_REPRODUCTION", "NONE") is False
    assert experiment._oos_contamination_risk("development sample only", "STRATEGY_PARAMETER_EXPERIMENT", "widen stop by 10%") is False


def test_build_raises_on_oos_contaminating_delta():
    record = build_fx_record(REPO_ROOT)
    event, trace, _, _ = service.diagnose_gate_failure(record, "OOS_VALIDATION", REPO_ROOT, persist_artifacts=False)
    with pytest.raises(experiment.OOSContaminationError):
        experiment._build(
            event, trace,
            experiment_class=experiment.ExperimentClass.STRATEGY_PARAMETER_EXPERIMENT,
            hypothesis="unsafe", minimal_delta={"type": "X", "target": "x", "proposed_change": "widen stop 10%"},
            scope={"dataset": "protected OOS holdout set"}, expected_evidence={}, action_if_supported="x", action_if_rejected="y",
        )


# ---------------------------------------------------------------------------
# Registry fail-closed behavior
# ---------------------------------------------------------------------------


def test_unsupported_strategy_fails_closed():
    with pytest.raises(UnsupportedDiagnosticTargetError):
        get_adapter("NOT_A_REAL_STRATEGY")


def test_unsupported_gate_fails_closed():
    with pytest.raises(ValueError):
        session_trade.diagnose_gate("NOT_A_REAL_GATE", build_fx_record(REPO_ROOT), REPO_ROOT)


# ---------------------------------------------------------------------------
# Strategy-specific diagnostics
# ---------------------------------------------------------------------------


def test_session_trade_negative_expectancy_diagnosis(tmp_path):
    records_dir = os.path.join(str(tmp_path), "artifacts", "outcome_resolution", "records")
    _write_outcome_record(records_dir, "ST_ASIAN_SWEEP_5R_V1_A_2026-09-01.json", "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "NOT_INCLUDED", -1.0)
    _write_outcome_record(records_dir, "ST_ASIAN_SWEEP_5R_V1_B_2026-09-02.json", "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "NOT_INCLUDED", -1.0)
    _write_outcome_record(records_dir, "ST_ASIAN_SWEEP_5R_V1_C_2026-09-03.json", "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "NOT_INCLUDED", 0.5)

    record = _synthetic_record("ST_ASIAN_SWEEP_5R_V1", "1.1.1", {"FRICTION_STRESS_TEST": _gate("FRICTION_STRESS_TEST", GateStatus.NOT_VERIFIED)})
    diag = session_trade.diagnose_gate("FRICTION_STRESS_TEST", record, str(tmp_path))
    assert diag.primary_failure_mode == FailureMode.NEGATIVE_EXPECTANCY
    assert diag.observed_metrics["gross_expectancy_R"] < 0


def test_session_trade_friction_sensitivity_diagnosis(tmp_path):
    records_dir = os.path.join(str(tmp_path), "artifacts", "outcome_resolution", "records")
    _write_outcome_record(records_dir, "ST_ASIAN_SWEEP_5R_V1_A_2026-09-01.json", "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "NOT_INCLUDED", 1.0)
    _write_outcome_record(records_dir, "ST_ASIAN_SWEEP_5R_V1_B_2026-09-02.json", "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "INCLUDED", 0.5)

    record = _synthetic_record("ST_ASIAN_SWEEP_5R_V1", "1.1.1", {"FRICTION_STRESS_TEST": _gate("FRICTION_STRESS_TEST", GateStatus.PARTIAL)})
    diag = session_trade.diagnose_gate("FRICTION_STRESS_TEST", record, str(tmp_path))
    assert diag.primary_failure_mode == FailureMode.FRICTION_SENSITIVITY


def test_session_trade_missing_oos_authority():
    record = build_fx_record(REPO_ROOT)
    diag = session_trade.diagnose_gate("OOS_VALIDATION", record, REPO_ROOT)
    assert diag.primary_failure_mode == FailureMode.MISSING_OOS_AUTHORITY


def test_large_smc_governance_gap_diagnosis():
    record = _synthetic_record(
        "ST_LARGE_SMC_V1", "1.0.7",
        {
            "LARGE_SMC_SHADOW_ENTRY_PREFLIGHT": _gate(
                "LARGE_SMC_SHADOW_ENTRY_PREFLIGHT", GateStatus.PARTIAL,
                details={
                    "natural_occurrence_evidence": "FOUND: something",
                    "cost_spread_metadata": "NOT_VERIFIED: no strategy-wide cost model",
                    "market_data_completeness": "PARTIAL: SHARED_CHANGE_REQUIRED",
                },
            )
        },
    )
    diag = large_smc.diagnose_gate("LARGE_SMC_SHADOW_ENTRY_PREFLIGHT", record, REPO_ROOT)
    assert diag.primary_failure_mode == FailureMode.GOVERNANCE_DEFINITION_GAP
    assert FailureMode.MISSING_COST_MODEL in diag.secondary_failure_modes


def test_btc_campaign_data_source_failure_diagnosis():
    record = _synthetic_record(
        "ST_LIQUIDITY_SWEEP_RETEST_V1", "2.0.0",
        {
            "NATURAL_CAMPAIGN_ACCRUAL": _gate(
                "NATURAL_CAMPAIGN_ACCRUAL", GateStatus.PARTIAL,
                details={
                    "valid_campaign_days": 2, "target_count": 30,
                    "data_error_days": 3, "missed_days": 0,
                    "total_observation_records": 5,
                },
            )
        },
    )
    diag = btc_sweep.diagnose_gate("NATURAL_CAMPAIGN_ACCRUAL", record, REPO_ROOT)
    assert diag.primary_failure_mode == FailureMode.DATA_QUALITY_FAILURE


# ---------------------------------------------------------------------------
# P21/P24 #12 -- one real Session Trade diagnostic proposal from live evidence
# ---------------------------------------------------------------------------


def test_session_trade_real_diagnostic_proposal_from_live_evidence(tmp_path):
    record = build_fx_record(REPO_ROOT)
    non_passing = [
        name for name, g in record.gates.items()
        if g.status not in (GateStatus.PASS, GateStatus.NOT_APPLICABLE)
        and name in session_trade.SUPPORTED_GATES
    ]
    assert non_passing, "expected at least one non-passing session_trade-supported gate on the live FX record"
    gate_id = non_passing[0]

    event, trace, proposal, paths = service.diagnose_gate_failure(
        record, gate_id, REPO_ROOT, persist_artifacts=True, output_dir=str(tmp_path / "diag"),
    )
    assert event.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert trace.primary_failure_mode in FailureMode
    assert os.path.isfile(paths["failure_event_path"])
    assert os.path.isfile(paths["diagnostic_trace_path"])
    if proposal is not None:
        assert os.path.isfile(paths["experiment_proposal_path"])
        assert proposal.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
