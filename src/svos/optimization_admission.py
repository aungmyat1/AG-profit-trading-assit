"""Optimization-admission governance evaluator (WP12) -- fail-closed.

Optimization is `OPTIMIZATION_ELIGIBLE` only when EVERY required admission condition
passes and the governing contract is SIGNED. `economic_gate_result == FAIL` alone NEVER
authorizes optimization. This module performs no search, no replay, no economics and
touches no data -- it only evaluates a conditions mapping against the frozen contract
shape (see config/governance/optimization_admission_contract.yaml).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

OPTIMIZATION_ELIGIBLE = "OPTIMIZATION_ELIGIBLE"
OPTIMIZATION_BLOCKED = "OPTIMIZATION_BLOCKED"

REQUIRED_CONDITIONS: Tuple[str, ...] = (
    "economic_gate_result",
    "data_integrity",
    "semantic_integrity",
    "population_role",
    "failure_diagnosis_complete",
    "mechanism_identified",
    "hypothesis_preregistered",
    "search_budget_frozen",
    "protected_data_access_count",
    "optimization_population_authorized",
)

# Conditions whose VALUE must match exactly (case-insensitive).
_FIXED_VALUES = {
    "economic_gate_result": "FAIL",  # optimization is only justified after a legitimate G3 FAIL
    "data_integrity": "PASS",
    "semantic_integrity": "PASS",
    "population_role": "DEVELOPMENT",
}

# Conditions that must be boolean True.
_MUST_BE_TRUE = frozenset({
    "failure_diagnosis_complete",
    "mechanism_identified",
    "hypothesis_preregistered",
    "search_budget_frozen",
    "optimization_population_authorized",
})


@dataclass(frozen=True)
class OptimizationAdmissionResult:
    eligible: bool
    status: str
    blockers: Tuple[str, ...]


def evaluate_optimization_admission(conditions: Mapping[str, Any]) -> OptimizationAdmissionResult:
    """Pure condition check (no contract read). Fails closed on any missing/incorrect
    condition; an absent condition is never treated as satisfied."""
    blockers = []
    for cond in REQUIRED_CONDITIONS:
        if cond not in conditions:
            blockers.append(f"MISSING_{cond.upper()}")
            continue
        value = conditions[cond]
        if cond in _FIXED_VALUES:
            if str(value).upper() != _FIXED_VALUES[cond]:
                blockers.append(f"{cond.upper()}_MUST_BE_{_FIXED_VALUES[cond]} (got {value!r})")
        elif cond in _MUST_BE_TRUE:
            if bool(value) is not True:
                blockers.append(f"{cond.upper()}_MUST_BE_TRUE (got {value!r})")
        elif cond == "protected_data_access_count":
            if int(value) != 0:
                blockers.append(f"PROTECTED_DATA_ACCESS_COUNT_MUST_BE_ZERO (got {value!r})")

    eligible = not blockers
    return OptimizationAdmissionResult(
        eligible=eligible,
        status=OPTIMIZATION_ELIGIBLE if eligible else OPTIMIZATION_BLOCKED,
        blockers=tuple(blockers),
    )


def evaluate_under_contract(
    contract: Mapping[str, Any],
    conditions: Mapping[str, Any],
) -> OptimizationAdmissionResult:
    """Contract-gated evaluation. Fails closed (OPTIMIZATION_BLOCKED) unless the
    contract identity.status == SIGNED -- mirrors economic_gate.py's signed-contract
    discipline."""
    identity = contract.get("identity") or {}
    if identity.get("status") != "SIGNED":
        return OptimizationAdmissionResult(
            eligible=False, status=OPTIMIZATION_BLOCKED, blockers=("CONTRACT_NOT_SIGNED",),
        )
    return evaluate_optimization_admission(conditions)
