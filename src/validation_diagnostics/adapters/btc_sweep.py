"""Diagnostic adapter for ST_LIQUIDITY_SWEEP_RETEST_V1 (P9).

Reads validation_framework.adapters.btc_adapter's own gate `details` -- in particular
NATURAL_CAMPAIGN_ACCRUAL's itemized counters (valid/data_error/excluded/missed days),
already computed by src/btc_sweep_research/campaign_calendar.py's evidence-qualified
counting (P9: DATA_ERROR/OUTSIDE_WINDOW/unauthorized CATCH_UP days are never counted as
successful campaign evidence there, and this adapter does not recompute or override that
-- it only reads the resulting counters).
"""
from __future__ import annotations

from validation_diagnostics.adapters import RawDiagnosis
from validation_diagnostics.models import FailureMode
from validation_framework.models import StrategyValidationRecord

STRATEGY_ID = "ST_LIQUIDITY_SWEEP_RETEST_V1"

SUPPORTED_GATES = frozenset({
    "OOS_VALIDATION",
    "HISTORICAL_REPLAY",
    "NATURAL_CAMPAIGN_ACCRUAL",
})


def _diagnose_oos(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("OOS_VALIDATION")
    refs = tuple(gate.evidence_refs) if gate else ()
    return RawDiagnosis(
        primary_failure_mode=FailureMode.MISSING_OOS_AUTHORITY,
        secondary_failure_modes=(),
        confidence="HIGH",
        evidence_refs=refs,
        rationale="No BTC-scoped out-of-sample/walk-forward artifact or test exists in the repository.",
        observed_metrics={"oos_evidence_refs_found": len(refs)},
    )


def _diagnose_historical_replay(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("HISTORICAL_REPLAY")
    refs = tuple(gate.evidence_refs) if gate else ()
    return RawDiagnosis(
        primary_failure_mode=FailureMode.INSUFFICIENT_SAMPLE,
        secondary_failure_modes=(FailureMode.MISSING_OOS_AUTHORITY,),
        confidence="HIGH",
        evidence_refs=refs,
        rationale="No BTC backtest/historical-replay artifact or test exists repository-wide -- BTC's evidence base is forward-observation only (NATURAL_CAMPAIGN_ACCRUAL), not historical replay.",
        observed_metrics={"historical_replay_evidence_refs_found": len(refs)},
    )


def _diagnose_campaign_accrual(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("NATURAL_CAMPAIGN_ACCRUAL")
    details = dict(gate.details) if gate else {}
    refs = tuple(gate.evidence_refs) if gate else ()

    valid = details.get("valid_campaign_days", 0) or 0
    target = details.get("target_count")
    data_error = details.get("data_error_days", 0) or 0
    missed = details.get("missed_days", 0) or 0
    total_records = details.get("total_observation_records", 0) or 0
    metrics = {
        "valid_campaign_days": valid, "target_count": target,
        "data_error_days": data_error, "missed_days": missed,
        "total_observation_records": total_records,
    }

    if total_records == 0:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.INSUFFICIENT_SAMPLE,
            secondary_failure_modes=(FailureMode.CAMPAIGN_ACCRUAL_FAILURE,),
            confidence="HIGH",
            evidence_refs=refs,
            rationale="Zero observation records exist for the BTC campaign yet -- nothing has accrued.",
            observed_metrics=metrics,
        )

    if data_error > 0 and data_error >= max(1, total_records // 4):
        return RawDiagnosis(
            primary_failure_mode=FailureMode.DATA_QUALITY_FAILURE,
            secondary_failure_modes=(FailureMode.CAMPAIGN_ACCRUAL_FAILURE,),
            confidence="MEDIUM",
            evidence_refs=refs,
            rationale=f"{data_error}/{total_records} observation records are DATA_ERROR -- a non-trivial share of the campaign's own records, not counted as valid evidence per the campaign's counting contract.",
            observed_metrics=metrics,
        )

    if missed > 0:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.CAMPAIGN_ACCRUAL_FAILURE,
            secondary_failure_modes=(FailureMode.INSUFFICIENT_SAMPLE,),
            confidence="MEDIUM",
            evidence_refs=refs,
            rationale=f"{missed} campaign day(s) are MISSED (no qualifying observation captured) against a target of {target} valid days -- this is an accrual/uptime gap, not evidence the strategy lacks edge.",
            observed_metrics=metrics,
        )

    return RawDiagnosis(
        primary_failure_mode=FailureMode.INSUFFICIENT_SAMPLE,
        secondary_failure_modes=(FailureMode.CAMPAIGN_ACCRUAL_FAILURE,),
        confidence="MEDIUM",
        evidence_refs=refs,
        rationale=f"{valid}/{target} valid campaign days accrued with no elevated data-error or missed-day rate -- shortfall against target reads as ordinary forward-observation time accrual.",
        observed_metrics=metrics,
    )


_DISPATCH = {
    "OOS_VALIDATION": _diagnose_oos,
    "HISTORICAL_REPLAY": _diagnose_historical_replay,
    "NATURAL_CAMPAIGN_ACCRUAL": _diagnose_campaign_accrual,
}


def diagnose_gate(gate_name: str, record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    if gate_name not in SUPPORTED_GATES:
        raise ValueError(f"btc_sweep adapter does not support gate {gate_name!r}")
    return _DISPATCH[gate_name](record, repo_root)
