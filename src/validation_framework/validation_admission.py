"""VALIDATION_ADMISSION -- Portability WP2: a strategy-independent admission check that
runs BEFORE G0.

Deliberately NOT numbered "G-1" and does not touch `ag_validation_methodology.GATE_NAMES`
(G0-G10 numbering is frozen validation-core semantics -- see that module's docstring).
Admission answers a narrower, prior question: "has this strategy declared enough about
itself to even be EVALUATED by G0?" It is a completeness check over a
`StrategyValidationProfile`, not a correctness/quality judgment -- an admitted strategy
can still fail G0 on its merits.

`ADMISSION PASS DOES NOT IMPLY G0 PASS.` This module produces no GateResult and writes
nothing to any gate-evidence or lifecycle store.

Per-symbol: a profile may declare multiple `symbols`, but a strategy's canonical
instrument universe can differ from the symbol under admission review (e.g.
ST_LARGE_SMC_V1's `FROZEN_INSTRUMENT_UNIVERSE = ("EURUSD",)`) -- `run_validation_admission`
takes an explicit `symbol` argument so a per-instrument BLOCKED result never silently
becomes a strategy-wide judgment or vice versa.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from .svos_contracts import StrategyValidationProfile

REASON_MISSING_SPEC_REF = "MISSING_SPEC_REF"
REASON_MISSING_IMPLEMENTATION_REF = "MISSING_IMPLEMENTATION_REF"
REASON_MISSING_DATASET_ROLES = "MISSING_DATASET_ROLES"
REASON_SYMBOL_NOT_IN_CANONICAL_UNIVERSE = "SYMBOL_NOT_IN_CANONICAL_UNIVERSE"
REASON_MISSING_TIMEFRAMES = "MISSING_TIMEFRAMES"
REASON_MISSING_SESSION_TIMEZONE_CONTRACT = "MISSING_SESSION_TIMEZONE_CONTRACT"
REASON_MISSING_FRICTION_POLICY = "MISSING_FRICTION_POLICY"
REASON_MISSING_VALIDATION_POLICY = "MISSING_VALIDATION_POLICY"
REASON_MISSING_HYPOTHESIS_BASELINE_MODE = "MISSING_HYPOTHESIS_BASELINE_MODE"
REASON_MISSING_HOLDOUT_BOUNDARY = "MISSING_HOLDOUT_BOUNDARY"
REASON_EXECUTION_AUTHORITY_NOT_ISOLATED = "EXECUTION_AUTHORITY_NOT_ISOLATED"
REASON_DUPLICATE_STRATEGY_VERSION = "DUPLICATE_STRATEGY_VERSION"

# Reasons that represent an active safety violation (execution authority already
# granted before any gate ran) rather than an incomplete-but-fixable declaration gap.
# Any of these present -> FAIL, never BLOCKED.
_FAIL_REASONS = frozenset({REASON_EXECUTION_AUTHORITY_NOT_ISOLATED, REASON_DUPLICATE_STRATEGY_VERSION})


class AdmissionResult(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ValidationAdmissionResult:
    strategy_id: str
    strategy_version: str
    symbol: Optional[str]
    result: AdmissionResult
    reason_codes: Tuple[str, ...]


def run_validation_admission(
    profile: StrategyValidationProfile,
    symbol: Optional[str] = None,
    known_admitted_strategy_versions: Tuple[Tuple[str, str], ...] = (),
) -> ValidationAdmissionResult:
    """Pure, deterministic. `known_admitted_strategy_versions` is an optional caller-
    supplied set of (strategy_id, strategy_version) pairs already admitted elsewhere --
    used only for the uniqueness check; this function has no registry/filesystem access
    of its own and performs no I/O."""
    reasons = []

    if (profile.strategy_id, profile.strategy_version) in known_admitted_strategy_versions:
        reasons.append(REASON_DUPLICATE_STRATEGY_VERSION)
    if not profile.strategy_spec_ref:
        reasons.append(REASON_MISSING_SPEC_REF)
    if not profile.implementation_ref:
        reasons.append(REASON_MISSING_IMPLEMENTATION_REF)
    if not profile.dataset_roles:
        reasons.append(REASON_MISSING_DATASET_ROLES)
    if symbol is not None and symbol not in profile.symbols:
        reasons.append(REASON_SYMBOL_NOT_IN_CANONICAL_UNIVERSE)
    if not profile.timeframes:
        reasons.append(REASON_MISSING_TIMEFRAMES)
    if not profile.session_timezone_contract_ref:
        reasons.append(REASON_MISSING_SESSION_TIMEZONE_CONTRACT)
    if not profile.friction_policy_ref:
        reasons.append(REASON_MISSING_FRICTION_POLICY)
    if not profile.validation_policy_ref:
        reasons.append(REASON_MISSING_VALIDATION_POLICY)
    if not profile.hypothesis_state:
        reasons.append(REASON_MISSING_HYPOTHESIS_BASELINE_MODE)
    if profile.holdout_metadata is None:
        reasons.append(REASON_MISSING_HOLDOUT_BOUNDARY)
    exec_meta = profile.execution_authority_metadata or {}
    if any(exec_meta.get(key) for key in ("demo_authorized", "live_authorized", "proposal_generation_authorized")):
        reasons.append(REASON_EXECUTION_AUTHORITY_NOT_ISOLATED)

    if any(r in _FAIL_REASONS for r in reasons):
        result = AdmissionResult.FAIL
    elif reasons:
        result = AdmissionResult.BLOCKED
    else:
        result = AdmissionResult.PASS

    return ValidationAdmissionResult(
        strategy_id=profile.strategy_id, strategy_version=profile.strategy_version,
        symbol=symbol, result=result, reason_codes=tuple(reasons),
    )
