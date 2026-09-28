"""AG_EGSVF_V1 -- core data model.

This module defines the vocabulary the rest of the framework speaks: strategy identity,
gate status/result, lifecycle stage, the per-strategy validation record, and the
read-only promotion-evaluation result. Nothing here executes a strategy, calls a
broker, mutates evidence, or grants authorization -- see evaluator.py for the pure
eligibility function and adapters/ for how native AG evidence is translated into these
shapes.

Core invariant this module exists to encode (never collapse these into one boolean):

    STRATEGY LOGIC VALIDATION != EVIDENCE MATURITY != PROMOTION ELIGIBILITY
    != EXECUTION CAPABILITY != EXECUTION AUTHORITY
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple


class GateStatus(str, Enum):
    """Fail-closed by construction: unknown/missing evidence must never be reported as
    PASS. Only PASS satisfies a required gate unless a transition contract explicitly
    allows NOT_APPLICABLE to satisfy it (see evaluator.py)."""

    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNSIGNED = "UNSIGNED"
    NOT_VERIFIED = "NOT_VERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class LifecycleStage(str, Enum):
    """Candidate lifecycle model (see AGENT PROMPT section 15/20). Distinct from, and
    never a substitute for, execution_capability/execution_authority fields on
    StrategyValidationRecord -- a strategy can be LIVE_ELIGIBLE while its
    execution_authority remains RESEARCH_ONLY."""

    OFFLINE_RESEARCH = "OFFLINE_RESEARCH"
    FORWARD_RESEARCH = "FORWARD_RESEARCH"
    OPERATIONAL_SHADOW = "OPERATIONAL_SHADOW"
    DEMO_ELIGIBLE = "DEMO_ELIGIBLE"
    DEMO_AUTHORIZED = "DEMO_AUTHORIZED"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    LIVE_AUTHORIZED = "LIVE_AUTHORIZED"


# Adjacent-transition-only default order. A transition is legal only between
# consecutive stages in this tuple unless a higher-authority AG contract explicitly
# permits a skip (none currently does -- see evaluator.ALLOWED_SKIP_TRANSITIONS, empty
# by default).
LIFECYCLE_ORDER: Tuple[LifecycleStage, ...] = (
    LifecycleStage.OFFLINE_RESEARCH,
    LifecycleStage.FORWARD_RESEARCH,
    LifecycleStage.OPERATIONAL_SHADOW,
    LifecycleStage.DEMO_ELIGIBLE,
    LifecycleStage.DEMO_AUTHORIZED,
    LifecycleStage.LIVE_ELIGIBLE,
    LifecycleStage.LIVE_AUTHORIZED,
)


@dataclass(frozen=True)
class StrategyIdentity:
    """Evidence belongs permanently to (strategy_id, semantic_version) and, only if a
    caller actually supplies one, (strategy_id, semantic_version, interface_version).
    AG has no separately versioned normalized interface today (see
    src/strategy_contract/ discovery notes), so interface_version defaults to None /
    NOT_USED -- it is not introduced speculatively."""

    strategy_id: str
    semantic_version: str
    interface_version: Optional[int] = None

    def key(self) -> Tuple[str, str, Optional[int]]:
        return (self.strategy_id, self.semantic_version, self.interface_version)


@dataclass(frozen=True)
class GateResult:
    """One gate's evaluated status, always tied to concrete evidence. `evidence_refs`
    must be precise enough that another operator/agent can independently inspect the
    cited source (a file path, a test node id, a JSON artifact path + field) --
    'file exists' alone is never sufficient justification for PASS (see AGENT PROMPT
    section 10)."""

    gate_name: str
    status: GateStatus
    evidence_refs: Tuple[str, ...]
    evaluated_at: datetime
    evaluator_version: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyValidationRecord:
    """The per-strategy governance snapshot AG-EGSVF produces. This is a DERIVED,
    read-only view over primary evidence -- it is never itself the authoritative source
    for strategy behavior, and building/holding one changes no strategy state."""

    identity: StrategyIdentity
    lifecycle_stage: LifecycleStage
    gates: Dict[str, GateResult]

    execution_capability: str
    execution_capability_evidence: Tuple[str, ...]
    execution_authority: str
    execution_authority_evidence: Tuple[str, ...]

    next_transition: Optional[LifecycleStage]
    promotion_eligible: bool
    promotion_blockers: Tuple[str, ...]

    last_updated: datetime
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionEvaluation:
    """Pure result of evaluator.evaluate_transition(). No side effects, no filesystem
    mutation, no broker calls -- see evaluator.py."""

    source_stage: LifecycleStage
    target_stage: LifecycleStage
    eligible: bool

    required_gates: Tuple[str, ...]
    passed_gates: Tuple[str, ...]
    blocking_gates: Tuple[str, ...]
    violations: Tuple[str, ...]
