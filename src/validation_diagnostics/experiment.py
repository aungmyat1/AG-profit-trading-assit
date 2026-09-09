"""Minimal evidence experiment generator (P10-P16). Exactly one function in this module
constructs an ExperimentProposal (`generate_experiment`) and it is the ONLY place in
this package that constructs one -- see models.ExperimentProposal.state, always
ExperimentState.PROPOSED.

Hard rules enforced HERE, architecturally, not just documented (P11/P12/P13):

  * `generate_experiment` returns None for FailureMode.UNKNOWN -- P5: do not invent a
    root cause, and by extension do not invent an experiment to test an unstated one.
  * Every template's `minimal_delta.type` is a read/inspection/attribution check, never
    a strategy rule or risk-parameter change -- STRATEGY_PARAMETER_EXPERIMENT is a
    listed ExperimentClass (models.py) for a future, separately authorized runner, but
    no template below ever selects it (P12: no automatic strategy optimization).
  * `requires_human_approval` is always True and `oos_contamination_risk` is computed by
    `_oos_contamination_risk`, never left False by default assumption; a proposal whose
    scope would touch a protected OOS set while also prescribing a non-NONE change is
    rejected outright (raises OOSContaminationError) rather than silently downgraded
    (P13).
  * No experiment chains to another experiment (P12) -- this module has no notion of a
    "next" proposal; each call is independent and produces at most one artifact.
"""
from __future__ import annotations

from typing import Optional

from validation_diagnostics.models import (
    DiagnosticTrace,
    ExperimentClass,
    ExperimentProposal,
    ExperimentState,
    FailureEvent,
    FailureMode,
)


class OOSContaminationError(Exception):
    """Raised instead of returning a proposal whose minimal_delta would touch a
    protected out-of-sample set with an actual (non-NONE) change (P13)."""


def _oos_contamination_risk(dataset: str, delta_type: str, proposed_change: str) -> bool:
    touches_oos = "oos" in dataset.lower() or "out_of_sample" in dataset.lower() or "out-of-sample" in dataset.lower()
    is_real_change = proposed_change.strip().upper() != "NONE"
    return touches_oos and is_real_change


def _base_kwargs(event: FailureEvent, trace: DiagnosticTrace) -> dict:
    return dict(
        experiment_id=f"EXP-{event.event_id}",
        strategy_id=event.strategy_id,
        strategy_version=event.strategy_version,
        source_event_id=event.event_id,
        failed_gate=event.gate_id,
        diagnostic_basis={
            "failure_mode": trace.primary_failure_mode.value,
            "secondary_failure_modes": [m.value for m in trace.secondary_failure_modes],
            "evidence_refs": list(trace.evidence_refs),
            "confidence": trace.confidence,
        },
        protected_constants={
            "strategy_rules_unchanged": True,
            "risk_rules_unchanged": True,
            "execution_authority_unchanged": True,
        },
        oos_contamination_risk=False,
        state=ExperimentState.PROPOSED,
        requires_human_approval=True,
    )


def _build(event, trace, experiment_class, hypothesis, minimal_delta, scope, expected_evidence,
           action_if_supported, action_if_rejected) -> ExperimentProposal:
    dataset = str(scope.get("dataset", ""))
    delta_type = str(minimal_delta.get("type", ""))
    proposed_change = str(minimal_delta.get("proposed_change", "NONE"))
    if _oos_contamination_risk(dataset, delta_type, proposed_change):
        raise OOSContaminationError(
            f"{event.event_id}: proposed experiment scope ({dataset!r}) touches a protected "
            f"OOS set with a non-NONE change ({proposed_change!r}); rejected per P13."
        )
    kwargs = _base_kwargs(event, trace)
    kwargs.update(
        experiment_class=experiment_class,
        hypothesis=hypothesis,
        minimal_delta=minimal_delta,
        scope=scope,
        expected_evidence=expected_evidence,
        action_if_supported=action_if_supported,
        action_if_rejected=action_if_rejected,
        oos_contamination_risk=False,
    )
    return ExperimentProposal(**kwargs)


def _template_missing_cost_model(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.COST_ATTRIBUTION_CHECK,
        hypothesis=(
            "Observed economic weakness (or lack of confirmed positive net economics) is "
            "attributable primarily to the absence of a cost/friction model, not to the "
            "strategy's gross signal economics."
        ),
        minimal_delta={
            "type": "COST_ATTRIBUTION_CHECK", "target": event.gate_id,
            "proposed_change": "NONE",
            "baseline": "existing resolved outcome records, no cost model applied (as-is)",
        },
        scope={"dataset": "existing resolved sample only (development, not OOS)", "period": "all resolved records to date", "folds": None, "trades": "all resolved", "symbols": "all instruments with resolved records"},
        expected_evidence={
            "metrics": ["gross_expectancy_R", "resolved_record_count"],
            "evidence_artifact": "artifacts/outcome_resolution/records/ (existing, unmodified)",
            "pass_interpretation": "Gross expectancy is already negative before any cost is applied -- friction is not the primary open question; classify NEGATIVE_EXPECTANCY.",
            "fail_interpretation": "Gross expectancy is positive/unknown-sign with too few records -- a governed cost model is the correct next evidence gap to close, not a strategy change.",
        },
        action_if_supported="Record NEGATIVE_EXPECTANCY as the primary open question; do not build a cost model as the next step.",
        action_if_rejected="Prioritize defining and signing a governed FX cost/friction model as the next evidence gap.",
    )


def _template_negative_expectancy(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.SAMPLE_SIZE_DIAGNOSTIC,
        hypothesis="The observed negative gross expectancy reflects the strategy's genuine current edge state rather than a small-sample artifact.",
        minimal_delta={"type": "SAMPLE_SIZE_DIAGNOSTIC", "target": event.gate_id, "proposed_change": "NONE", "baseline": "current resolved sample count and per-symbol/per-cycle breakdown"},
        scope={"dataset": "existing resolved sample only", "period": "all resolved records to date", "folds": None, "trades": "all resolved", "symbols": "all instruments with resolved records"},
        expected_evidence={
            "metrics": ["resolved_record_count", "gross_expectancy_R", "per_symbol_expectancy_R"],
            "evidence_artifact": "artifacts/outcome_resolution/records/ (existing, unmodified)",
            "pass_interpretation": "Sample is large enough (per repository-governed sample-size norms) and consistently negative across symbols/cycles -- treat as genuine weak/no edge, do not modify the strategy to force a pass.",
            "fail_interpretation": "Sample is still small or concentrated in one symbol/cycle -- classify INSUFFICIENT_SAMPLE and wait for more natural resolved trades before drawing an edge conclusion.",
        },
        action_if_supported="Report to owner: current evidence suggests the edge itself is weak; do not modify the strategy to chase a pass.",
        action_if_rejected="Continue accruing resolved trades before drawing a conclusion; re-run this diagnostic later.",
    )


def _template_friction_sensitivity(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.COST_ATTRIBUTION_CHECK,
        hypothesis="Partial cost coverage across resolved records is masking whether net economics are positive or negative.",
        minimal_delta={"type": "COST_ATTRIBUTION_CHECK", "target": event.gate_id, "proposed_change": "NONE", "baseline": "existing resolved records split by cost_status"},
        scope={"dataset": "existing resolved sample only", "period": "all resolved records to date", "folds": None, "trades": "all resolved", "symbols": "all instruments with resolved records"},
        expected_evidence={
            "metrics": ["net_expectancy_R_costed_subset", "gross_expectancy_R_uncosted_subset"],
            "evidence_artifact": "artifacts/outcome_resolution/records/ (existing, unmodified)",
            "pass_interpretation": "Costed and uncosted subsets show consistent sign/magnitude -- friction is not materially changing the conclusion.",
            "fail_interpretation": "Costed subset flips sign or materially shrinks the edge vs the uncosted subset -- classify FRICTION_SENSITIVITY as confirmed and prioritize completing cost coverage.",
        },
        action_if_supported="No further cost-model work required for a directional read; proceed with existing evidence.",
        action_if_rejected="Prioritize completing cost-status coverage across all resolved records.",
    )


def _template_missing_oos_authority(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.DATA_INTEGRITY_CHECK,
        hypothesis="The existing resolved/development sample is large and continuous enough to support defining a future OOS split boundary, without touching any OOS data (none currently exists).",
        minimal_delta={"type": "DATA_INTEGRITY_CHECK", "target": event.gate_id, "proposed_change": "NONE", "baseline": "existing resolved records, chronological continuity and count only"},
        scope={"dataset": "development sample only (no OOS set exists yet for this strategy)", "period": "all resolved records to date", "folds": None, "trades": "all resolved", "symbols": "all instruments with resolved records"},
        expected_evidence={
            "metrics": ["resolved_record_count", "date_range_covered", "gap_count"],
            "evidence_artifact": "artifacts/outcome_resolution/records/ (existing, unmodified)",
            "pass_interpretation": "Continuous, sufficient development history exists to responsibly define a future OOS boundary.",
            "fail_interpretation": "History is too sparse/discontinuous yet -- OOS boundary definition should wait for more accrual.",
        },
        action_if_supported="Owner may define a governed OOS split boundary as a separate, explicit decision; this experiment does not propose one itself.",
        action_if_rejected="Continue accruing development-sample evidence before any OOS split is defined.",
    )


def _template_data_quality_failure(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.DATA_INTEGRITY_CHECK,
        hypothesis="The elevated invalid/error rate traces to a specific, identifiable data or classification defect rather than the underlying strategy signal.",
        minimal_delta={"type": "DATA_INTEGRITY_CHECK", "target": event.gate_id, "proposed_change": "NONE", "baseline": "existing classified days/records, itemized by invalid/error reason"},
        scope={"dataset": "existing classified sample only", "period": "all classified days to date", "folds": None, "trades": None, "symbols": "all"},
        expected_evidence={
            "metrics": ["invalid_reason_breakdown", "data_error_reason_breakdown"],
            "evidence_artifact": "existing dated status/classification documents (unmodified)",
            "pass_interpretation": "Invalid/error days share one identifiable, fixable cause (e.g. one data source outage) -- fixing that cause is a data-pipeline task, not a strategy change.",
            "fail_interpretation": "Invalid/error days are heterogeneous with no common cause -- keep classifying, do not assume a fixable defect.",
        },
        action_if_supported="Route the identified data/classification defect to whoever owns that pipeline; no strategy change implied.",
        action_if_rejected="Continue accruing classified days; re-run this diagnostic once more data exists.",
    )


def _template_time_dependent_accrual(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.SHADOW_CLASSIFICATION_CHECK,
        hypothesis="The shortfall against target valid days is explained by calendar-time accrual alone, not a defect in the classification pipeline.",
        minimal_delta={"type": "SHADOW_CLASSIFICATION_CHECK", "target": event.gate_id, "proposed_change": "NONE", "baseline": "existing classified days vs. calendar days elapsed since series start"},
        scope={"dataset": "existing classified sample only", "period": "series start to date", "folds": None, "trades": None, "symbols": "all"},
        expected_evidence={
            "metrics": ["classified_days", "calendar_days_elapsed", "target_valid_days"],
            "evidence_artifact": "existing dated status/classification documents (unmodified)",
            "pass_interpretation": "Classified-day count tracks calendar days elapsed at a plausible rate -- no action needed, this is a natural time-dependent gate; do not treat as a software defect.",
            "fail_interpretation": "Classified-day count lags calendar days elapsed by an implausible margin -- investigate the classification pipeline itself for a stall.",
        },
        action_if_supported="No action; allow the series to continue accruing naturally.",
        action_if_rejected="Investigate the shadow-day classification pipeline for a stall or scheduling gap.",
    )


def _template_campaign_accrual_failure(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.CAMPAIGN_PIPELINE_CHECK,
        hypothesis="Missed/ineligible campaign days trace to a specific pipeline gap (e.g. a data-source or uptime failure), not to a lack of qualifying market structure.",
        minimal_delta={"type": "CAMPAIGN_PIPELINE_CHECK", "target": event.gate_id, "proposed_change": "NONE", "baseline": "existing campaign observation records, itemized by missed/data-error reason"},
        scope={"dataset": "existing campaign archive only", "period": "campaign activation date to date", "folds": None, "trades": None, "symbols": "BTCUSDT"},
        expected_evidence={
            "metrics": ["missed_days", "data_error_days", "missed_dates"],
            "evidence_artifact": "existing campaign archive records (unmodified)",
            "pass_interpretation": "Missed days cluster around an identifiable pipeline/uptime cause -- a pipeline fix, not a strategy or schedule change, is the correct next step.",
            "fail_interpretation": "Missed days are sparse/scattered with no common cause -- continue the campaign as-is.",
        },
        action_if_supported="Route the identified pipeline/uptime defect to whoever owns the campaign runner; this proposal does not itself change scheduling.",
        action_if_rejected="Continue the campaign unchanged; the shortfall is ordinary accrual.",
    )


def _template_governance_definition_gap(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.DATA_INTEGRITY_CHECK,
        hypothesis="The remaining blockers are enumerable, already-real governance/evidence gaps (e.g. a missing cost model or an open market-data dependency), not a strategy-logic defect.",
        minimal_delta={"type": "DATA_INTEGRITY_CHECK", "target": event.gate_id, "proposed_change": "NONE", "baseline": "existing itemized preflight sub-checks"},
        scope={"dataset": "existing preflight evidence only", "period": "as of latest evaluation", "folds": None, "trades": None, "symbols": "n/a"},
        expected_evidence={
            "metrics": ["preflight_subcheck_breakdown"],
            "evidence_artifact": "validation_framework adapter gate details (existing, unmodified)",
            "pass_interpretation": "Every remaining sub-check gap is already itemized and owned elsewhere -- no new diagnostic action needed, only owner prioritization of the existing gaps.",
            "fail_interpretation": "A sub-check gap is not yet itemized anywhere -- file it as a new, explicit governance item before further diagnosis.",
        },
        action_if_supported="Present the existing itemized gap list to the owner for prioritization; no automatic change.",
        action_if_rejected="File the newly identified gap as an explicit governance item.",
    )


def _template_insufficient_sample(event, trace) -> ExperimentProposal:
    return _build(
        event, trace,
        experiment_class=ExperimentClass.SAMPLE_SIZE_DIAGNOSTIC,
        hypothesis="Current evidence is too sparse to distinguish a real defect from ordinary accrual; more natural evidence, not a strategy change, is the correct next step.",
        minimal_delta={"type": "SAMPLE_SIZE_DIAGNOSTIC", "target": event.gate_id, "proposed_change": "NONE", "baseline": "current observed sample count"},
        scope={"dataset": "existing sample only", "period": "as of latest evaluation", "folds": None, "trades": "all resolved/observed", "symbols": "all"},
        expected_evidence={
            "metrics": ["observed_sample_count"],
            "evidence_artifact": "existing evidence artifacts (unmodified)",
            "pass_interpretation": "Sample remains below a reasonable diagnostic threshold -- wait for more natural accrual.",
            "fail_interpretation": "Sample is already large enough to support a more specific diagnosis -- re-run classification.",
        },
        action_if_supported="No action; continue natural evidence accrual and re-run diagnosis later.",
        action_if_rejected="Re-run diagnosis now with the larger sample available.",
    )


def _template_unsupported(event, trace) -> ExperimentProposal:
    """Safe, minimal fallback for any FailureMode this module has not yet been given a
    specific template for (never a strategy-parameter change, always advisory-only)."""
    return _build(
        event, trace,
        experiment_class=ExperimentClass.DATA_INTEGRITY_CHECK,
        hypothesis=f"Current evidence is insufficient to propose a more specific experiment for failure mode {trace.primary_failure_mode.value}.",
        minimal_delta={"type": "DATA_INTEGRITY_CHECK", "target": event.gate_id, "proposed_change": "NONE", "baseline": "existing gate evidence"},
        scope={"dataset": "existing evidence only", "period": "as of latest evaluation", "folds": None, "trades": None, "symbols": "n/a"},
        expected_evidence={
            "metrics": [],
            "evidence_artifact": "existing gate evidence_refs (unmodified)",
            "pass_interpretation": "n/a -- generic fallback, human review required to define a sharper experiment.",
            "fail_interpretation": "n/a -- generic fallback, human review required to define a sharper experiment.",
        },
        action_if_supported="Owner defines a sharper follow-up diagnostic manually.",
        action_if_rejected="Owner defines a sharper follow-up diagnostic manually.",
    )


_TEMPLATES = {
    FailureMode.MISSING_COST_MODEL: _template_missing_cost_model,
    FailureMode.NEGATIVE_EXPECTANCY: _template_negative_expectancy,
    FailureMode.FRICTION_SENSITIVITY: _template_friction_sensitivity,
    FailureMode.MISSING_OOS_AUTHORITY: _template_missing_oos_authority,
    FailureMode.DATA_QUALITY_FAILURE: _template_data_quality_failure,
    FailureMode.TIME_DEPENDENT_ACCRUAL: _template_time_dependent_accrual,
    FailureMode.CAMPAIGN_ACCRUAL_FAILURE: _template_campaign_accrual_failure,
    FailureMode.GOVERNANCE_DEFINITION_GAP: _template_governance_definition_gap,
    FailureMode.INSUFFICIENT_SAMPLE: _template_insufficient_sample,
}


def generate_experiment(event: FailureEvent, trace: DiagnosticTrace) -> Optional[ExperimentProposal]:
    """At most one proposal per call (P10) -- returns None for FailureMode.UNKNOWN (P5:
    never invent a root cause to test) or when the produced proposal would create
    OOS_CONTAMINATION_RISK (P13, raised by _build as OOSContaminationError and caught
    here so 'no experiment' is the safe default rather than a raised exception
    propagating to callers that only expect Optional[ExperimentProposal])."""
    if trace.primary_failure_mode == FailureMode.UNKNOWN:
        return None
    template = _TEMPLATES.get(trace.primary_failure_mode, _template_unsupported)
    try:
        return template(event, trace)
    except OOSContaminationError:
        return None
