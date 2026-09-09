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

ABSTRACT MILESTONE GATES vs. CONCRETE STRATEGY-FAMILY GATES
(AG_EGSVF_V1_STRATEGY_STAGE_CONTRACT_RECONCILIATION). A lifecycle MILESTONE is common to
every strategy family; the EVIDENCE that satisfies it is not. `OPERATIONAL_SHADOW`'s
entry prerequisite was originally hardcoded as the literal gate name
`NATURAL_CAMPAIGN_ACCRUAL` -- correct for BTC's forward-observation campaign, but wrong
as a universal requirement: FX has no campaign named that, and forcing FX to prove it
would either fabricate evidence or wrongly block FX forever on a gate that doesn't apply
to its lifecycle. `STAGE_PREREQUISITES` may therefore name an ABSTRACT gate (currently
only `SHADOW_ENTRY_EVIDENCE`, listed in `ABSTRACT_MILESTONE_GATES`); `MILESTONE_GATE_MAP`
resolves it, per `strategy_id`, to that strategy's own concrete, evidence-backed gate
name. This substitution mechanism is deliberately narrow: `_resolve_gate_name` only ever
looks up a name that is a member of `ABSTRACT_MILESTONE_GATES` -- a FOUNDATIONAL_INVARIANT
name (or any other concrete gate name) is never a valid abstract-gate key, and
`validate_family_gate_map` (run at import time against `MILESTONE_GATE_MAP`, and callable
directly by tests against any other mapping) raises if one is ever configured, so
"foundational gates are never family-substitutable" is an enforced fact, not a
convention. A strategy with no entry in `MILESTONE_GATE_MAP` for a needed abstract gate
resolves to an intentionally-unsatisfiable placeholder name
(`f"{abstract_name}_UNRESOLVED_FOR_STRATEGY"`) rather than silently borrowing another
strategy's concrete gate or being treated as PASS -- no adapter emits a GateResult under
that placeholder name, so it always surfaces as a real MISSING_GATE blocker.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Mapping, Optional, Tuple

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
#
# OPERATIONAL_SHADOW's prerequisite is the ABSTRACT milestone gate SHADOW_ENTRY_EVIDENCE
# (see module docstring), resolved per-strategy by MILESTONE_GATE_MAP -- it is NOT a
# concrete gate name in its own right and no adapter should ever emit a GateResult
# literally named "SHADOW_ENTRY_EVIDENCE".
STAGE_PREREQUISITES: Dict[LifecycleStage, Tuple[str, ...]] = {
    LifecycleStage.OFFLINE_RESEARCH: (),
    LifecycleStage.FORWARD_RESEARCH: FOUNDATIONAL_INVARIANTS,
    LifecycleStage.OPERATIONAL_SHADOW: ("SHADOW_ENTRY_EVIDENCE",),
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

# The ONLY gate names that may ever be resolved through MILESTONE_GATE_MAP. Adding a
# name here is a deliberate governance decision that a lifecycle milestone's evidence is
# strategy-family-specific; FOUNDATIONAL_INVARIANTS must never appear in this set (see
# validate_family_gate_map, which enforces this at import time and is also directly
# testable against any other mapping).
ABSTRACT_MILESTONE_GATES: FrozenSet[str] = frozenset({"SHADOW_ENTRY_EVIDENCE"})

# Per-strategy resolution of each abstract milestone gate to that strategy's own
# concrete, evidence-backed gate name. A strategy_id absent from this map (or missing an
# entry for a specific abstract gate it needs) is NOT silently satisfied and does NOT
# fall back to another strategy's gate -- see _resolve_gate_name.
#
# ST_ASIAN_SWEEP_5R_V1: FX_SHADOW_ENTRY_PREFLIGHT_PASS is sourced from
#   docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md
#   (`shadow_entry_ready = YES`, classification `PREFLIGHT_PASS_SHADOW_READY`) -- the
#   actual, dated governance event that made FX's shadow-validation series eligible to
#   begin. Series 001's own evidence is NOT used as this gate's source: Series 001's Day
#   1 was EXCLUDED_DAY and Day 2 PENDING_RECONCILIATION (see PROJECT_STATUS.md), i.e.
#   pre-remediation, non-counting evidence -- using it here would manufacture a PASS from
#   a source the project itself never treated as qualifying.
# ST_LIQUIDITY_SWEEP_RETEST_V1: NATURAL_CAMPAIGN_ACCRUAL is BTC's own forward-observation
#   campaign gate, unchanged from the pre-reconciliation universal default -- reconciled
#   here as a per-strategy concrete mapping instead of a global one.
# ST_LARGE_SMC_V1: LARGE_SMC_SHADOW_ENTRY_PREFLIGHT (large_smc_adapter.py,
#   AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 P2). Large-SMC's own itemized entry
#   preflight -- strategy/version validity, E/M-model reachability, C10 stop
#   availability, market-data completeness, cost/spread metadata, zero execution
#   authority. Currently PARTIAL (real mechanism proof, no natural occurrence evidence
#   yet, no cost model yet) -- this still fails closed and blocks OPERATIONAL_SHADOW, but
#   as a real, inspectable gate rather than the unresolved placeholder.
MILESTONE_GATE_MAP: Dict[str, Dict[str, str]] = {
    "ST_ASIAN_SWEEP_5R_V1": {"SHADOW_ENTRY_EVIDENCE": "FX_SHADOW_ENTRY_PREFLIGHT_PASS"},
    "ST_LIQUIDITY_SWEEP_RETEST_V1": {"SHADOW_ENTRY_EVIDENCE": "NATURAL_CAMPAIGN_ACCRUAL"},
    "ST_LARGE_SMC_V1": {"SHADOW_ENTRY_EVIDENCE": "LARGE_SMC_SHADOW_ENTRY_PREFLIGHT"},
}


def validate_family_gate_map(mapping: Mapping[str, Mapping[str, str]]) -> None:
    """Raises ValueError if `mapping` targets anything other than a declared abstract
    milestone gate. This is what makes 'foundational invariants (and any other concrete
    gate) can never be family-substituted' an enforced fact: a mapping entry for
    DETERMINISM, SPEC_FIDELITY, or any name outside ABSTRACT_MILESTONE_GATES is rejected,
    never silently applied. Run at import time against MILESTONE_GATE_MAP; also exposed
    for tests to exercise directly against a deliberately malformed fixture."""
    for strategy_id, family_map in mapping.items():
        for abstract_name in family_map:
            if abstract_name not in ABSTRACT_MILESTONE_GATES:
                raise ValueError(
                    f"{strategy_id}: {abstract_name!r} is not a declared abstract "
                    f"milestone gate (ABSTRACT_MILESTONE_GATES={sorted(ABSTRACT_MILESTONE_GATES)}) "
                    "-- only an abstract milestone gate may be resolved to a "
                    "strategy-specific concrete gate; a foundational invariant or any "
                    "other concrete gate can never be targeted by a family mapping."
                )


validate_family_gate_map(MILESTONE_GATE_MAP)


def _resolve_gate_name(gate_name: str, strategy_id: Optional[str]) -> str:
    """Pass-through for every concrete gate name (including every FOUNDATIONAL_INVARIANT
    -- they are never members of ABSTRACT_MILESTONE_GATES, so this function never
    touches them). Only a name in ABSTRACT_MILESTONE_GATES is looked up in
    MILESTONE_GATE_MAP; an unmapped strategy (or no strategy_id at all) fails closed to
    an intentionally-unsatisfiable placeholder rather than PASS or another strategy's
    gate."""
    if gate_name not in ABSTRACT_MILESTONE_GATES:
        return gate_name
    concrete = MILESTONE_GATE_MAP.get(strategy_id or "", {}).get(gate_name)
    if concrete is None:
        return f"{gate_name}_UNRESOLVED_FOR_STRATEGY"
    return concrete

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


def get_cumulative_required_gates(
    target_stage: LifecycleStage, strategy_id: Optional[str] = None
) -> Tuple[str, ...]:
    """Every gate required to have legitimately reached `target_stage`, walking
    STAGE_PREREQUISITES from FORWARD_RESEARCH through target_stage inclusive (AGENT
    PROMPT section 11). This is NOT "every gate in the entire lifecycle" -- a target of
    FORWARD_RESEARCH yields only FOUNDATIONAL_INVARIANTS, never a later stage's gates
    (section 24: future gates must not block an earlier transition). Order is
    deterministic: earliest stage's gates first, target stage's own gates last;
    duplicates (none expected today, but a future stage could legitimately reuse a name)
    are removed while preserving first-seen order.

    Any abstract milestone gate encountered (see ABSTRACT_MILESTONE_GATES) is resolved
    to `strategy_id`'s concrete gate via _resolve_gate_name before being added -- so the
    tuple this returns is always a list of concrete gate names an adapter could actually
    have emitted a GateResult for, never a bare abstract placeholder like
    "SHADOW_ENTRY_EVIDENCE" itself. Omitting `strategy_id` (or naming an unmapped
    strategy) resolves to the fail-closed `_UNRESOLVED_FOR_STRATEGY` placeholder, not to
    any other strategy's gate."""
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
            resolved = _resolve_gate_name(name, strategy_id)
            if resolved not in seen:
                seen.append(resolved)
    return tuple(seen)


def required_gates_for(
    source: LifecycleStage,
    target: LifecycleStage,
    strategy_overrides: Mapping[Tuple[LifecycleStage, LifecycleStage], Tuple[str, ...]] = None,
    strategy_id: Optional[str] = None,
) -> Tuple[str, ...]:
    """Cumulative stage-entry requirements through `target` (see
    get_cumulative_required_gates, which resolves any abstract milestone gate to
    `strategy_id`'s concrete gate), extended -- never weakened -- by any strategy-
    specific stricter requirement registered for this exact (source, target) transition.
    A strategy override may only ADD gate names to the specific transition being
    evaluated; it can never remove a cumulative gate (AGENT PROMPT section 12: "Never
    weaken a global requirement just because one strategy is not ready for it"), and it
    never applies to any transition other than the exact pair it is registered under.
    `strategy_id` is keyword-only in practice (appended last) so existing positional
    call sites are unaffected."""
    base = get_cumulative_required_gates(target, strategy_id=strategy_id)
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
    strategy_id: Optional[str] = None,
) -> PromotionEvaluation:
    """Pure function. `gates` must already be computed GateResult objects (typically
    from an adapter reading real evidence) -- this function never computes a gate
    itself, never touches a filesystem, network, or broker, and never mutates
    authorization state.

    `strategy_id` resolves any abstract milestone gate in the cumulative requirement set
    (see ABSTRACT_MILESTONE_GATES/MILESTONE_GATE_MAP) to that strategy's own concrete
    gate name -- omitting it (or naming a strategy with no mapping for a needed abstract
    gate) fails closed rather than defaulting to any concrete gate name.
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

    required = required_gates_for(source_stage, target_stage, strategy_overrides, strategy_id=strategy_id)
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
