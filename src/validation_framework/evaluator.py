"""AG_EGSVF_V1 -- pure, deterministic promotion evaluator.

evaluate_transition() answers: "given these already-computed gate results, is THIS
specific adjacent lifecycle transition currently eligible?" It performs no filesystem
I/O, no network access, no broker call, no strategy execution/signal generation, and no
authorization mutation. It never grants DEMO_AUTHORIZED or LIVE_AUTHORIZED -- those
remain external, explicit, human-issued facts (see
models.StrategyValidationRecord.execution_authority, which this module never writes).

Only implements evaluate_transition(...) (read-only). There is deliberately no
promote_strategy(...) in V1 -- promotion evaluation and promotion action are different
capabilities, and this framework performs neither strategy mutation nor lifecycle-state
persistence.

CUMULATIVE PREREQUISITE INHERITANCE (AG_EGSVF_V1_PROMOTION_INVARIANT_HARDENING). The
required-gate set for a transition into `target_stage` is NOT just that stage's own
entry gates -- it is every stage's entry gates from FORWARD_RESEARCH through
target_stage, inclusive (see get_cumulative_required_gates). This exists because a
strategy's current `lifecycle_stage` label is not itself proof that the gates required
to reach that stage were ever evaluated: every one of AG's three real strategies was
assigned its current stage before AG-EGSVF existed (see
docs/architecture/AG_EGSVF_V1_LEDGER.md). Without cumulative inheritance, a strategy
already labeled OPERATIONAL_SHADOW could advance to DEMO_ELIGIBLE while its own
DETERMINISM/HISTORICAL_REPLAY gates sat at PARTIAL, because those foundational gates
are not literally "OPERATIONAL_SHADOW -> DEMO_ELIGIBLE's own" requirement -- they are
FORWARD_RESEARCH's. Cumulative inheritance closes that gap: FOUNDATIONAL_INVARIANTS are
required for every promotion at or beyond FORWARD_RESEARCH, permanently, regardless of
which adjacent step is currently being evaluated or which stage a strategy is currently
labeled at.
"""
from __future__ import annotations

from typing import Dict, Mapping, Tuple

from .models import GateResult, GateStatus, LIFECYCLE_ORDER, LifecycleStage, PromotionEvaluation

# Gates required for every promotion at or beyond FORWARD_RESEARCH (AGENT PROMPT
# section 7/2). These can never be dropped by a strategy override (see
# required_gates_for) and never satisfied by a strategy's current lifecycle label alone
# (see get_cumulative_required_gates / module docstring).
FOUNDATIONAL_INVARIANTS: Tuple[str, ...] = (
    "SPEC_FIDELITY",
    "DETERMINISM",
    "NO_LOOKAHEAD",
    "HISTORICAL_REPLAY",
)

# Per-stage ENTRY prerequisites: the gates that must PASS to have legitimately reached
# that stage (candidate default model, AGENT PROMPT section 10/20). OFFLINE_RESEARCH has
# none -- it is the starting point every strategy begins at. FORWARD_RESEARCH's entry
# prerequisite is exactly FOUNDATIONAL_INVARIANTS; every stage after it ADDS its own
# additional entry gate(s) on top (see get_cumulative_required_gates).
STAGE_PREREQUISITES: Dict[LifecycleStage, Tuple[str, ...]] = {
    LifecycleStage.OFFLINE_RESEARCH: (),
    LifecycleStage.FORWARD_RESEARCH: FOUNDATIONAL_INVARIANTS,
    LifecycleStage.OPERATIONAL_SHADOW: ("NATURAL_CAMPAIGN_ACCRUAL",),
    LifecycleStage.DEMO_ELIGIBLE: (
        "SHADOW_SERIES_COMPLETION",
        "FRICTION_STRESS_TEST",
        "OOS_VALIDATION",
    ),
    LifecycleStage.DEMO_AUTHORIZED: (
        "OWNER_PROMOTION_SIGNATURE",
        "RISK_INVARIANTS_AUDIT",
    ),
    LifecycleStage.LIVE_ELIGIBLE: (
        "DEMO_SLIPPAGE_VERIFICATION",
        "IDEMPOTENCY_CHECK",
    ),
    LifecycleStage.LIVE_AUTHORIZED: (
        "OWNER_LIVE_SIGNATURE",
    ),
}

# No skipped transition is currently permitted by any higher-authority AG contract
# discovered during this task. Kept as an explicit, empty, extensible set rather than a
# hardcoded "only adjacent" special case, so a future reconciled AG governance decision
# can be added here without changing evaluate_transition()'s logic.
ALLOWED_SKIP_TRANSITIONS: Tuple[Tuple[LifecycleStage, LifecycleStage], ...] = ()

# Statuses that satisfy a REQUIRED gate. Deliberately excludes NOT_APPLICABLE -- it only
# satisfies a requirement when the specific transition contract lists it in
# na_satisfies (per-transition, per-strategy override), never globally (AGENT PROMPT
# section 23).
_SATISFYING_BY_DEFAULT = frozenset({GateStatus.PASS})


def _is_adjacent(source: LifecycleStage, target: LifecycleStage) -> bool:
    try:
        return LIFECYCLE_ORDER.index(target) - LIFECYCLE_ORDER.index(source) == 1
    except ValueError:
        return False


def get_cumulative_required_gates(target_stage: LifecycleStage) -> Tuple[str, ...]:
    """Every gate required to have legitimately reached `target_stage`, walking
    STAGE_PREREQUISITES from FORWARD_RESEARCH through target_stage inclusive (AGENT
    PROMPT section 11). This is NOT "every gate in the entire lifecycle" -- a target of
    FORWARD_RESEARCH yields only FOUNDATIONAL_INVARIANTS, never a later stage's gates
    (section 24: future gates must not block an earlier transition). Order is
    deterministic: earliest stage's gates first, target stage's own gates last;
    duplicates (none expected today, but a future stage could legitimately reuse a name)
    are removed while preserving first-seen order."""
    if target_stage == LifecycleStage.OFFLINE_RESEARCH:
        return ()
    try:
        target_index = LIFECYCLE_ORDER.index(target_stage)
        start_index = LIFECYCLE_ORDER.index(LifecycleStage.FORWARD_RESEARCH)
    except ValueError:
        return ()
    if target_index < start_index:
        return ()

    seen = []
    for stage in LIFECYCLE_ORDER[start_index : target_index + 1]:
        for name in STAGE_PREREQUISITES.get(stage, ()):
            if name not in seen:
                seen.append(name)
    return tuple(seen)


def required_gates_for(
    source: LifecycleStage,
    target: LifecycleStage,
    strategy_overrides: Mapping[Tuple[LifecycleStage, LifecycleStage], Tuple[str, ...]] = None,
) -> Tuple[str, ...]:
    """Cumulative stage-entry requirements through `target` (see
    get_cumulative_required_gates), extended -- never weakened -- by any strategy-
    specific stricter requirement registered for this exact (source, target) transition.
    A strategy override may only ADD gate names to the specific transition being
    evaluated; it can never remove a cumulative gate (AGENT PROMPT section 12: "Never
    weaken a global requirement just because one strategy is not ready for it"), and it
    never applies to any transition other than the exact pair it is registered under."""
    base = get_cumulative_required_gates(target)
    extra = ()
    if strategy_overrides:
        extra = strategy_overrides.get((source, target), ())
    # Preserve order (foundational -> earlier stages -> target stage -> strategy-
    # specific additive, per AGENT PROMPT section 13), de-duplicate.
    seen = []
    for name in (*base, *extra):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def evaluate_transition(
    source_stage: LifecycleStage,
    target_stage: LifecycleStage,
    gates: Mapping[str, GateResult],
    strategy_overrides: Mapping[Tuple[LifecycleStage, LifecycleStage], Tuple[str, ...]] = None,
    na_satisfies: Mapping[Tuple[LifecycleStage, LifecycleStage], Tuple[str, ...]] = None,
) -> PromotionEvaluation:
    """Pure function. `gates` must already be computed GateResult objects (typically
    from an adapter reading real evidence) -- this function never computes a gate
    itself, never touches a filesystem, network, or broker, and never mutates
    authorization state.
    """
    violations: list = []

    if source_stage == target_stage:
        violations.append("SOURCE_EQUALS_TARGET")

    skip_allowed = (source_stage, target_stage) in ALLOWED_SKIP_TRANSITIONS
    if not _is_adjacent(source_stage, target_stage) and not skip_allowed:
        violations.append("NON_ADJACENT_TRANSITION_NOT_PERMITTED")
        return PromotionEvaluation(
            source_stage=source_stage,
            target_stage=target_stage,
            eligible=False,
            required_gates=(),
            passed_gates=(),
            blocking_gates=(),
            violations=tuple(violations),
        )

    required = required_gates_for(source_stage, target_stage, strategy_overrides)
    na_ok = set((na_satisfies or {}).get((source_stage, target_stage), ()))

    passed: list = []
    blocking: list = []
    for gate_name in required:
        result = gates.get(gate_name)
        if result is None:
            blocking.append(gate_name)
            violations.append(f"MISSING_GATE:{gate_name}")
            continue
        status = result.status
        if status in _SATISFYING_BY_DEFAULT:
            passed.append(gate_name)
        elif status == GateStatus.NOT_APPLICABLE and gate_name in na_ok:
            passed.append(gate_name)
        else:
            blocking.append(gate_name)

    eligible = len(blocking) == 0 and len(violations) == 0

    return PromotionEvaluation(
        source_stage=source_stage,
        target_stage=target_stage,
        eligible=eligible,
        required_gates=required,
        passed_gates=tuple(passed),
        blocking_gates=tuple(blocking),
        violations=tuple(violations),
    )
