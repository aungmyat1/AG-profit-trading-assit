"""Diagnostic adapter for ST_ASIAN_SWEEP_5R_V1 (P7).

Reads validation_framework.adapters.fx_adapter's own gate `details` first (already
evidence-backed, never re-derived differently here) and, only where that alone cannot
distinguish a failure mode, re-reads the SAME primary evidence fx_adapter.py reads --
the outcome_resolution records directory -- to compute one additional, purely
gross-evidence metric (mean realized_R across resolved trades). That computation uses
no cost/friction model of any kind (there being no governed one yet -- see
FRICTION_STRESS_TEST handling below), so it cannot itself be accused of assuming the
answer to the question it is trying to help distinguish.

Heuristic sample-size thresholds below (_MIN_RESOLVED_SAMPLE, _MIN_CLASSIFIED_SHADOW_DAYS)
are diagnostic-only judgment calls for secondary-mode flagging, not a new governance gate
threshold -- they never affect any GateStatus, PromotionEvaluation, or lifecycle stage.
"""
from __future__ import annotations

import json
import os
from typing import List, Tuple

from validation_diagnostics.adapters import RawDiagnosis
from validation_diagnostics.models import FailureMode
from validation_framework.models import StrategyValidationRecord

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
SEMANTIC_VERSION = "1.1.1"

SUPPORTED_GATES = frozenset({
    "FRICTION_STRESS_TEST",
    "OOS_VALIDATION",
    "SHADOW_SERIES_COMPLETION",
})

_OUTCOME_RECORDS_DIR = os.path.join("artifacts", "outcome_resolution", "records")

# Advisory-only diagnostic heuristics (see module docstring) -- not governance
# thresholds.
_MIN_RESOLVED_SAMPLE = 20
_MIN_CLASSIFIED_SHADOW_DAYS = 5
_HIGH_INVALID_RATIO = 0.5


def _read_resolved_records(repo_root: str) -> Tuple[List[dict], Tuple[str, ...]]:
    directory = os.path.join(repo_root, _OUTCOME_RECORDS_DIR)
    records: List[dict] = []
    refs: List[str] = []
    if not os.path.isdir(directory):
        return records, ()
    for name in sorted(os.listdir(directory)):
        if not name.startswith(STRATEGY_ID) or not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        with open(path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        if record.get("strategy_version") != SEMANTIC_VERSION:
            continue
        records.append(record)
        refs.append(os.path.join(_OUTCOME_RECORDS_DIR, name).replace("\\", "/"))
    return records, tuple(refs)


def _diagnose_friction(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    records, refs = _read_resolved_records(repo_root)
    total = len(records)

    if total == 0:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.INSUFFICIENT_SAMPLE,
            secondary_failure_modes=(),
            confidence="HIGH",
            evidence_refs=refs,
            rationale="No resolved outcome_resolution records exist for this strategy/version yet -- friction cannot be assessed without a resolved sample.",
            observed_metrics={"resolved_record_count": 0},
        )

    not_included = sum(1 for r in records if r.get("cost_status") == "NOT_INCLUDED")
    realized_R = [r.get("realized_R") for r in records if isinstance(r.get("realized_R"), (int, float))]
    gross_expectancy_R = (sum(realized_R) / len(realized_R)) if realized_R else None
    small_sample = total < _MIN_RESOLVED_SAMPLE
    metrics = {
        "resolved_record_count": total,
        "cost_status_not_included_count": not_included,
        "gross_expectancy_R": gross_expectancy_R,
    }

    if not_included == total:
        # No cost model has ever been applied to any resolved record -- the gate's own
        # NOT_VERIFIED status reflects exactly this. Gross expectancy (no cost model
        # involved in its computation) is real, deterministic evidence we already have:
        # if it is already negative before any friction is even considered, friction
        # cannot be the primary cause -- the weakness is at minimum partly intrinsic.
        if gross_expectancy_R is not None and gross_expectancy_R < 0:
            secondary = (FailureMode.MISSING_COST_MODEL,)
            if small_sample:
                secondary = secondary + (FailureMode.INSUFFICIENT_SAMPLE,)
            return RawDiagnosis(
                primary_failure_mode=FailureMode.NEGATIVE_EXPECTANCY,
                secondary_failure_modes=secondary,
                confidence="MEDIUM" if not small_sample else "LOW",
                evidence_refs=refs,
                rationale=(
                    f"Gross expectancy across {total} resolved trades is {gross_expectancy_R:.3f}R "
                    "BEFORE any transaction cost is applied (every record's cost_status is "
                    "NOT_INCLUDED). A negative gross result cannot be explained by friction, "
                    "which can only make it worse -- classified as NEGATIVE_EXPECTANCY with "
                    "MISSING_COST_MODEL as a secondary, still-open gap."
                ),
                observed_metrics=metrics,
            )

        secondary = (FailureMode.INSUFFICIENT_SAMPLE,) if small_sample else ()
        return RawDiagnosis(
            primary_failure_mode=FailureMode.MISSING_COST_MODEL,
            secondary_failure_modes=secondary,
            confidence="HIGH",
            evidence_refs=refs,
            rationale=(
                f"Gross expectancy across {total} resolved trades is "
                f"{'unavailable' if gross_expectancy_R is None else f'{gross_expectancy_R:.3f}R'} "
                "and non-negative before any transaction cost is applied, but no cost/friction "
                "model has ever been applied to any resolved record -- net economics cannot be "
                "determined from current evidence."
            ),
            observed_metrics=metrics,
        )

    if 0 < not_included < total:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.FRICTION_SENSITIVITY,
            secondary_failure_modes=(FailureMode.MISSING_COST_MODEL,),
            confidence="LOW",
            evidence_refs=refs,
            rationale=(
                f"{not_included}/{total} resolved records still carry cost_status=NOT_INCLUDED "
                "-- cost coverage is partial, so gate status is PARTIAL rather than a clean "
                "PASS/FAIL; the mixed cost coverage itself is the observed evidence."
            ),
            observed_metrics=metrics,
        )

    # not_included == 0: every record already carries a real cost figure but the gate
    # was still routed to this adapter (i.e. not PASS) -- current evidence cannot
    # explain why without inspecting the specific non-passing detail on the gate.
    return RawDiagnosis(
        primary_failure_mode=FailureMode.UNKNOWN,
        secondary_failure_modes=(),
        confidence="LOW",
        evidence_refs=refs,
        rationale="Every resolved record carries a cost figure but FRICTION_STRESS_TEST is not PASS; current adapter evidence cannot distinguish the cause.",
        observed_metrics=metrics,
    )


def _diagnose_oos(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("OOS_VALIDATION")
    refs = tuple(gate.evidence_refs) if gate else ()
    if not refs:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.MISSING_OOS_AUTHORITY,
            secondary_failure_modes=(),
            confidence="HIGH",
            evidence_refs=(),
            rationale="No FX-scoped out-of-sample/walk-forward artifact or test exists anywhere in the repository -- there is no OOS evidence to be degraded or insufficient, the authority itself does not yet exist.",
            observed_metrics={"oos_evidence_refs_found": 0},
        )
    return RawDiagnosis(
        primary_failure_mode=FailureMode.UNKNOWN,
        secondary_failure_modes=(),
        confidence="LOW",
        evidence_refs=refs,
        rationale="OOS_VALIDATION gate carries evidence refs but is not PASS; current adapter has no rule distinguishing INSUFFICIENT_OOS_SAMPLE/OOS_DEGRADATION/REGIME_DEPENDENCE from those refs alone.",
        observed_metrics={"oos_evidence_refs_found": len(refs)},
    )


def _diagnose_shadow_series(record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    gate = record.gates.get("SHADOW_SERIES_COMPLETION")
    details = dict(gate.details) if gate else {}
    valid = details.get("valid_days", 0) or 0
    invalid = details.get("invalid_days", 0) or 0
    excluded = details.get("excluded_days", 0) or 0
    pending = details.get("pending_days", 0) or 0
    target = details.get("target_valid_days")
    total_classified = valid + invalid + excluded
    metrics = {
        "valid_days": valid, "invalid_days": invalid, "excluded_days": excluded,
        "pending_days": pending, "target_valid_days": target,
        "total_classified_days": total_classified,
    }
    refs = tuple(gate.evidence_refs) if gate else ()

    if total_classified < _MIN_CLASSIFIED_SHADOW_DAYS:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.INSUFFICIENT_SAMPLE,
            secondary_failure_modes=(FailureMode.TIME_DEPENDENT_ACCRUAL,),
            confidence="LOW",
            evidence_refs=refs,
            rationale=(
                f"Only {total_classified} shadow day(s) classified so far against a target of "
                f"{target} valid days -- too few classified days to distinguish a data-quality "
                "problem from ordinary calendar-time accrual of a series that has just started."
            ),
            observed_metrics=metrics,
        )

    invalid_ratio = invalid / total_classified if total_classified else 0.0
    metrics["invalid_ratio"] = invalid_ratio
    if invalid_ratio > _HIGH_INVALID_RATIO:
        return RawDiagnosis(
            primary_failure_mode=FailureMode.DATA_QUALITY_FAILURE,
            secondary_failure_modes=(FailureMode.SHADOW_EVIDENCE_INCOMPLETE,),
            confidence="MEDIUM",
            evidence_refs=refs,
            rationale=(
                f"{invalid}/{total_classified} classified shadow days are INVALID "
                f"({invalid_ratio:.0%}) -- an elevated invalid rate over a large-enough sample "
                "points to a recurring data/classification problem rather than simple time accrual."
            ),
            observed_metrics=metrics,
        )

    return RawDiagnosis(
        primary_failure_mode=FailureMode.TIME_DEPENDENT_ACCRUAL,
        secondary_failure_modes=(FailureMode.SHADOW_EVIDENCE_INCOMPLETE,),
        confidence="MEDIUM",
        evidence_refs=refs,
        rationale=(
            f"{valid}/{target} valid shadow days classified with a low invalid rate "
            f"({invalid_ratio:.0%}) -- the shortfall against target reads as normal calendar-time "
            "accrual of an in-progress series, not a defect."
        ),
        observed_metrics=metrics,
    )


_DISPATCH = {
    "FRICTION_STRESS_TEST": _diagnose_friction,
    "OOS_VALIDATION": _diagnose_oos,
    "SHADOW_SERIES_COMPLETION": _diagnose_shadow_series,
}


def diagnose_gate(gate_name: str, record: StrategyValidationRecord, repo_root: str) -> RawDiagnosis:
    if gate_name not in SUPPORTED_GATES:
        raise ValueError(f"session_trade adapter does not support gate {gate_name!r}")
    return _DISPATCH[gate_name](record, repo_root)
