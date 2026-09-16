"""AVO-WP1 state model + read-only status derivation.

This module answers exactly one question per registered strategy: "what does
canonical repository evidence say about this strategy's validation status right now?"
It never answers "should this strategy advance" and never writes to any registry,
lifecycle file, or evidence artifact.

Canonical evidence sources (reused, not re-derived):
  - strategies/registry.yaml            (registered/active/research/demo_authorized/
                                          live_authorized) via api.strategy_service
  - config/governance/strategy_lifecycle.yaml (lifecycle_stage/semantic_version) via
                                          api.strategy_service
  - the 4 existing validation_framework adapters (ST_ASIAN_SWEEP_5R_V1,
    ST_LIQUIDITY_SWEEP_RETEST_V1, ST_LARGE_SMC_V1, ST_SESSION_SWEEP_CONTINUATION_V1),
    reached only through api.strategy_service.get_validation_record() -- this module
    never imports validation_framework.adapters.* directly, so it can never drift from
    what the existing read-only API already exposes.

Every public function takes its collaborators (get_strategy / has_validation_adapter /
get_validation_record / list_strategies) as keyword-only, defaulted parameters. The
defaults are the real api.strategy_service functions, so production callers get
genuine canonical-evidence-derived behavior for free; tests inject fakes to exercise
fail-closed paths (missing/contradictory evidence, unknown strategy) without touching
real repository files.

Determinism: the only field that may legitimately differ between two calls against
unchanged evidence is `updated_at_utc` (a diagnostic timestamp). Every other field is
computed solely from the collaborator return values. StrategyValidationStatus.
semantic_tuple() excludes updated_at_utc for exactly this reason -- use it (not `==`
on the whole dataclass) when asserting repeated-evaluation determinism.

This module must never import a broker order-submission function, MetaTrader5, or
anything under src/execution/, src/mt5/, or src/authorization/. No execution
capability is reachable from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from api import strategy_service

AGENT_REQUIRED_NONE = "NONE"
"""AVO-WP1 implements no dispatch capability (deferred to AVO-WP7 per the parent
spec) -- agent_required is therefore always NONE, honestly reflecting that this
module cannot request an agent run."""

NOT_TRACKED = "NOT_TRACKED_BY_WP1"
"""Used for dataset_role_status / lineage_status / holdout_status and, for
no-adapter strategies, evidence_status. No canonical multi-strategy reader for
dataset-role/lineage/holdout state exists in the repository today (see inventory);
reporting a real value here would mean inventing state that no evidence supports.
Fail-closed means saying "not tracked", never guessing "clear" or "sealed"."""


class UnknownStrategyError(Exception):
    """Raised when a requested strategy_id has no entry in the canonical registry.
    Never silently substituted with a fabricated/default status."""

    def __init__(self, strategy_id: str) -> None:
        super().__init__(strategy_id)
        self.strategy_id = strategy_id


@dataclass(frozen=True)
class StrategyValidationStatus:
    """Strategy-neutral read-only status snapshot. Field set matches
    docs/validation/AG_AUTO_VALIDATION_ORCHESTRATOR_V1.md section 6 exactly."""

    strategy_id: str
    strategy_version: Optional[str]
    lifecycle_stage: Optional[str]
    current_gate: Optional[str]
    furthest_verified_gate: Optional[str]
    validation_state: str
    blocking_reasons: Tuple[str, ...]
    evidence_status: str
    dataset_role_status: str
    lineage_status: str
    holdout_status: str
    demo_authorized: bool
    live_authorized: bool
    next_safe_action: str
    agent_required: str
    updated_at_utc: str

    def semantic_tuple(self) -> tuple:
        """All fields except updated_at_utc -- the basis for determinism assertions."""
        return (
            self.strategy_id,
            self.strategy_version,
            self.lifecycle_stage,
            self.current_gate,
            self.furthest_verified_gate,
            self.validation_state,
            self.blocking_reasons,
            self.evidence_status,
            self.dataset_role_status,
            self.lineage_status,
            self.holdout_status,
            self.demo_authorized,
            self.live_authorized,
            self.next_safe_action,
            self.agent_required,
        )


_NEXT_SAFE_ACTION_BY_STATE: Mapping[str, str] = {
    "NO_VALIDATION_ADAPTER": "NONE_NO_ADAPTER_WIRED",
    "EVIDENCE_ERROR": "RESOLVE_EVIDENCE_ERROR",
    "GATE_FAILURE_PRESENT": "REVIEW_GATE_FAILURE_STOP_OR_OPEN_NEW_HYPOTHESIS",
    "EVIDENCE_INCOMPLETE": "CONTINUE_EVIDENCE_COLLECTION",
    "NO_GATES_REPORTED": "CONTINUE_EVIDENCE_COLLECTION",
    "GATES_ALL_PASS_BLOCKED": "RESOLVE_PROMOTION_BLOCKERS",
    "GATES_ALL_PASS_NO_BLOCKERS": "OWNER_REVIEW_FOR_NEXT_GATE",
}
_DEFAULT_NEXT_SAFE_ACTION = "OWNER_REVIEW_REQUIRED"


def _gate_analysis(
    gates: Sequence[Mapping[str, object]],
) -> Tuple[Optional[str], Optional[str], str]:
    """Derives (current_gate, furthest_verified_gate, evidence_status) from an
    adapter's own reported gate list, consumed strictly in the order the adapter
    returned it (the adapter's own evaluation order -- this function never reorders,
    renames, or invents a gate name). `current_gate` is the first non-PASS gate;
    `furthest_verified_gate` is the last gate in the unbroken PASS prefix from the
    start of the list."""
    if not gates:
        return None, None, "NO_GATES_REPORTED"

    current_gate: Optional[str] = None
    furthest_verified_gate: Optional[str] = None
    saw_fail = False
    for gate in gates:
        name = str(gate["gate_name"])
        status = str(gate["status"])
        if current_gate is None and status == "PASS":
            furthest_verified_gate = name
            continue
        if current_gate is None:
            current_gate = name
        if status == "FAIL":
            saw_fail = True

    if current_gate is None:
        return None, gates[-1]["gate_name"], "GATES_ALL_PASS"
    if saw_fail:
        return current_gate, furthest_verified_gate, "GATE_FAILURE_PRESENT"
    return current_gate, furthest_verified_gate, "EVIDENCE_INCOMPLETE"


def _validation_state(evidence_status: str, promotion_blockers: Sequence[str]) -> str:
    if evidence_status == "GATES_ALL_PASS":
        return "GATES_ALL_PASS_BLOCKED" if promotion_blockers else "GATES_ALL_PASS_NO_BLOCKERS"
    return evidence_status


def _blocking_reasons(
    gates: Sequence[Mapping[str, object]],
    promotion_blockers: Sequence[str],
) -> Tuple[str, ...]:
    reasons: List[str] = []
    for gate in gates:
        if str(gate["status"]) == "FAIL":
            reasons.append(f"{gate['gate_name']}:FAIL")
    for blocker in promotion_blockers:
        if blocker not in reasons:
            reasons.append(str(blocker))
    return tuple(reasons)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _adapter_backed_status(
    strategy_id: str,
    strategy_version: Optional[str],
    lifecycle_stage: Optional[str],
    demo_authorized: bool,
    live_authorized: bool,
    get_validation_record: Callable[[str], Optional[dict]],
) -> StrategyValidationStatus:
    try:
        record = get_validation_record(strategy_id)
    except Exception as exc:  # noqa: BLE001 -- any raised exception means evidence
        # could not be trusted (missing file, malformed registry, contradictory
        # semantic_version between strategy_lifecycle.yaml and the adapter's own
        # SEMANTIC_VERSION -- see lifecycle_registry.LifecycleRegistryError). Fail
        # closed rather than guessing a status.
        return StrategyValidationStatus(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            lifecycle_stage=lifecycle_stage,
            current_gate=None,
            furthest_verified_gate=None,
            validation_state="EVIDENCE_ERROR",
            blocking_reasons=(f"EVIDENCE_ERROR: {exc}",),
            evidence_status=NOT_TRACKED,
            dataset_role_status=NOT_TRACKED,
            lineage_status=NOT_TRACKED,
            holdout_status=NOT_TRACKED,
            demo_authorized=demo_authorized,
            live_authorized=live_authorized,
            next_safe_action=_NEXT_SAFE_ACTION_BY_STATE["EVIDENCE_ERROR"],
            agent_required=AGENT_REQUIRED_NONE,
            updated_at_utc=_now_utc_iso(),
        )

    if record is None:
        # has_validation_adapter said True but get_validation_record returned None --
        # contradictory canonical evidence. Fail closed rather than trusting either
        # signal alone.
        return StrategyValidationStatus(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            lifecycle_stage=lifecycle_stage,
            current_gate=None,
            furthest_verified_gate=None,
            validation_state="EVIDENCE_ERROR",
            blocking_reasons=(
                "EVIDENCE_ERROR: has_validation_adapter() reported True but "
                "get_validation_record() returned None",
            ),
            evidence_status=NOT_TRACKED,
            dataset_role_status=NOT_TRACKED,
            lineage_status=NOT_TRACKED,
            holdout_status=NOT_TRACKED,
            demo_authorized=demo_authorized,
            live_authorized=live_authorized,
            next_safe_action=_NEXT_SAFE_ACTION_BY_STATE["EVIDENCE_ERROR"],
            agent_required=AGENT_REQUIRED_NONE,
            updated_at_utc=_now_utc_iso(),
        )

    gates = record.get("gates") or []
    promotion_blockers = tuple(record.get("promotion_blockers") or ())
    current_gate, furthest_verified_gate, evidence_status = _gate_analysis(gates)
    validation_state = _validation_state(evidence_status, promotion_blockers)
    blocking_reasons = _blocking_reasons(gates, promotion_blockers)
    next_safe_action = _NEXT_SAFE_ACTION_BY_STATE.get(validation_state, _DEFAULT_NEXT_SAFE_ACTION)

    return StrategyValidationStatus(
        strategy_id=strategy_id,
        strategy_version=record.get("semantic_version", strategy_version),
        lifecycle_stage=record.get("lifecycle_stage", lifecycle_stage),
        current_gate=current_gate,
        furthest_verified_gate=furthest_verified_gate,
        validation_state=validation_state,
        blocking_reasons=blocking_reasons,
        evidence_status=evidence_status,
        dataset_role_status=NOT_TRACKED,
        lineage_status=NOT_TRACKED,
        holdout_status=NOT_TRACKED,
        demo_authorized=demo_authorized,
        live_authorized=live_authorized,
        next_safe_action=next_safe_action,
        agent_required=AGENT_REQUIRED_NONE,
        updated_at_utc=_now_utc_iso(),
    )


def _no_adapter_status(
    strategy_id: str,
    strategy_version: Optional[str],
    lifecycle_stage: Optional[str],
    demo_authorized: bool,
    live_authorized: bool,
) -> StrategyValidationStatus:
    return StrategyValidationStatus(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        lifecycle_stage=lifecycle_stage,
        current_gate=None,
        furthest_verified_gate=None,
        validation_state="NO_VALIDATION_ADAPTER",
        blocking_reasons=(
            "no validation_framework adapter is registered for this strategy_id "
            "(see api.strategy_service.has_validation_adapter)",
        ),
        evidence_status=NOT_TRACKED,
        dataset_role_status=NOT_TRACKED,
        lineage_status=NOT_TRACKED,
        holdout_status=NOT_TRACKED,
        demo_authorized=demo_authorized,
        live_authorized=live_authorized,
        next_safe_action=_NEXT_SAFE_ACTION_BY_STATE["NO_VALIDATION_ADAPTER"],
        agent_required=AGENT_REQUIRED_NONE,
        updated_at_utc=_now_utc_iso(),
    )


def derive_status(
    strategy_id: str,
    *,
    get_strategy: Callable[[str], Optional[dict]] = strategy_service.get_strategy,
    has_validation_adapter: Callable[[str], bool] = strategy_service.has_validation_adapter,
    get_validation_record: Callable[[str], Optional[dict]] = strategy_service.get_validation_record,
) -> StrategyValidationStatus:
    """Derives the current StrategyValidationStatus for one strategy_id.

    Raises UnknownStrategyError if strategy_id has no entry in the canonical registry
    -- never fabricates a status for an unregistered id."""
    entry = get_strategy(strategy_id)
    if entry is None:
        raise UnknownStrategyError(strategy_id)

    strategy_version = entry.get("semantic_version")
    lifecycle_stage = entry.get("lifecycle_stage")
    demo_authorized = bool(entry.get("demo_authorized"))
    live_authorized = bool(entry.get("live_authorized"))

    if has_validation_adapter(strategy_id):
        return _adapter_backed_status(
            strategy_id,
            strategy_version,
            lifecycle_stage,
            demo_authorized,
            live_authorized,
            get_validation_record,
        )
    return _no_adapter_status(strategy_id, strategy_version, lifecycle_stage, demo_authorized, live_authorized)


def derive_all_status(
    *,
    list_strategies: Callable[[], Sequence[Mapping[str, object]]] = strategy_service.list_strategies,
    has_validation_adapter: Callable[[str], bool] = strategy_service.has_validation_adapter,
    get_validation_record: Callable[[str], Optional[dict]] = strategy_service.get_validation_record,
) -> List[StrategyValidationStatus]:
    """Derives status for every strategy currently present in the canonical registry.
    Strategy discovery itself is delegated entirely to list_strategies() (real default:
    api.strategy_service.list_strategies(), which reads strategies/registry.yaml) --
    this module never hardcodes a strategy id list."""
    statuses: List[StrategyValidationStatus] = []
    for entry in list_strategies():
        strategy_id = str(entry["strategy_id"])
        strategy_version = entry.get("semantic_version")
        lifecycle_stage = entry.get("lifecycle_stage")
        demo_authorized = bool(entry.get("demo_authorized"))
        live_authorized = bool(entry.get("live_authorized"))

        if has_validation_adapter(strategy_id):
            status = _adapter_backed_status(
                strategy_id,
                strategy_version,
                lifecycle_stage,
                demo_authorized,
                live_authorized,
                get_validation_record,
            )
        else:
            status = _no_adapter_status(
                strategy_id, strategy_version, lifecycle_stage, demo_authorized, live_authorized
            )
        statuses.append(status)
    return statuses
