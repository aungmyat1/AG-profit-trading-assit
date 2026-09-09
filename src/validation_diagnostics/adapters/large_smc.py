"""Diagnostic adapter for ST_LARGE_SMC_V1 (P8).

Deliberately narrow: reads validation_framework.adapters.large_smc_adapter's own gate
`details` only. Per P8, this adapter must never propose "run more often / schedule a
watcher / generate synthetic setups" -- see experiment.py, which is the only place an
experiment is actually generated and which enforces this by never offering those
experiment classes for this strategy's failure modes.
"""
from __future__ import annotations

from validation_diagnostics.adapters import RawDiagnosis
from validation_diagnostics.models import FailureMode
from validation_framework.models import StrategyValidationRecord

STRATEGY_ID = "ST_LARGE_SMC_V1"

SUPPORTED_GATES = frozenset({
    "FRICTION_STRESS_TEST",
    "OOS_VALIDATION",
    "LARGE_SMC_SHADOW_ENTRY_PREFLIGHT",
})


def _diagnose_friction(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("FRICTION_STRESS_TEST")
    refs = tuple(gate.evidence_refs) if gate else ()
    return RawDiagnosis(
        primary_failure_mode=FailureMode.MISSING_COST_MODEL,
        secondary_failure_modes=(FailureMode.INSUFFICIENT_SAMPLE,),
        confidence="HIGH",
        evidence_refs=refs,
        rationale="No Large-SMC-specific cost/friction model or test exists anywhere in the repository, and no natural qualifying occurrence has been observed to cost yet -- both the model and the sample it would need are absent.",
        observed_metrics={"cost_model_found": False},
    )


def _diagnose_oos(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("OOS_VALIDATION")
    refs = tuple(gate.evidence_refs) if gate else ()
    return RawDiagnosis(
        primary_failure_mode=FailureMode.MISSING_OOS_AUTHORITY,
        secondary_failure_modes=(),
        confidence="HIGH",
        evidence_refs=refs,
        rationale="tests/test_smc_walkforward.py is scoped to shared advisory skills, not ST_LARGE_SMC_V1's own candidate economics -- no strategy-scoped OOS artifact exists for Large-SMC.",
        observed_metrics={"oos_evidence_refs_found": len(refs)},
    )


def _diagnose_shadow_preflight(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("LARGE_SMC_SHADOW_ENTRY_PREFLIGHT")
    details = dict(gate.details) if gate else {}
    refs = tuple(gate.evidence_refs) if gate else ()

    missing_natural_evidence = details.get("natural_occurrence_evidence", "").startswith("NOT_FOUND")
    missing_cost = details.get("cost_spread_metadata", "").startswith("NOT_VERIFIED")
    market_data_gap = "SHARED_CHANGE_REQUIRED" in str(details.get("market_data_completeness", ""))

    secondary = []
    if missing_cost:
        secondary.append(FailureMode.MISSING_COST_MODEL)
    if market_data_gap:
        secondary.append(FailureMode.GOVERNANCE_DEFINITION_GAP)

    if missing_natural_evidence:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.INSUFFICIENT_SAMPLE,
            secondary_failure_modes=tuple(secondary),
            confidence="HIGH",
            evidence_refs=refs,
            rationale="No real historical replay or live observation has ever reached RESEARCH_QUALIFIED for Large-SMC -- the mechanism is proven only against unit-test fixtures, so there is zero natural occurrence sample to evaluate.",
            observed_metrics=details,
        )

    return RawDiagnosis(
        primary_failure_mode=FailureMode.GOVERNANCE_DEFINITION_GAP,
        secondary_failure_modes=tuple(secondary),
        confidence="MEDIUM",
        evidence_refs=refs,
        rationale="LARGE_SMC_SHADOW_ENTRY_PREFLIGHT is PARTIAL with every sub-check real and none fabricated -- the remaining gap is an open governance item (market-data replay dependency and/or missing cost model), not a strategy-logic defect.",
        observed_metrics=details,
    )


_DISPATCH = {
    "FRICTION_STRESS_TEST": _diagnose_friction,
    "OOS_VALIDATION": _diagnose_oos,
    "LARGE_SMC_SHADOW_ENTRY_PREFLIGHT": _diagnose_shadow_preflight,
}


def diagnose_gate(gate_name: str, record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    if gate_name not in SUPPORTED_GATES:
        raise ValueError(f"large_smc adapter does not support gate {gate_name!r}")
    return _DISPATCH[gate_name](record, repo_root)
