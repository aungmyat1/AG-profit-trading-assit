"""AG Advisory Validation Diagnostic Agent V1 -- core data model.

This module defines the vocabulary the diagnostic agent speaks: a canonical, immutable
FailureEvent (P2), a deterministic DiagnosticTrace (P5), and an advisory-only
ExperimentProposal (P10). Nothing here mutates a strategy file, a lifecycle registry, a
gate, or authorization state -- this package only ever reads
validation_framework.evaluator/adapters output and writes files under
artifacts/validation_diagnostics/ (see service.py).

Authority boundary encoded structurally, not just in comments: no dataclass in this
module has any field or method that could promote a lifecycle stage, set
demo_authorized/live_authorized, or submit an order. ExperimentProposal.state is always
ExperimentState.PROPOSED at construction time -- this package has no function anywhere
that returns any other ExperimentState (see experiment.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class FailureMode(str, Enum):
    """Deterministic failure-mode categories (AGENT PROMPT P5). UNKNOWN is returned,
    never a guessed category, whenever deterministic evidence cannot distinguish a
    cause (P5: 'do not invent a root cause')."""

    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    NEGATIVE_EXPECTANCY = "NEGATIVE_EXPECTANCY"
    FRICTION_SENSITIVITY = "FRICTION_SENSITIVITY"
    OOS_DEGRADATION = "OOS_DEGRADATION"
    REGIME_DEPENDENCE = "REGIME_DEPENDENCE"
    DATA_QUALITY_FAILURE = "DATA_QUALITY_FAILURE"
    LOOKAHEAD_RISK = "LOOKAHEAD_RISK"
    EVIDENCE_IDENTITY_MISMATCH = "EVIDENCE_IDENTITY_MISMATCH"
    MISSING_COST_MODEL = "MISSING_COST_MODEL"
    MISSING_OOS_AUTHORITY = "MISSING_OOS_AUTHORITY"
    SHADOW_EVIDENCE_INCOMPLETE = "SHADOW_EVIDENCE_INCOMPLETE"
    CAMPAIGN_ACCRUAL_FAILURE = "CAMPAIGN_ACCRUAL_FAILURE"
    EXECUTION_METADATA_FAILURE = "EXECUTION_METADATA_FAILURE"
    GOVERNANCE_DEFINITION_GAP = "GOVERNANCE_DEFINITION_GAP"
    TIME_DEPENDENT_ACCRUAL = "TIME_DEPENDENT_ACCRUAL"
    MANUAL_CLASSIFICATION_DEPENDENCY = "MANUAL_CLASSIFICATION_DEPENDENCY"
    UNKNOWN = "UNKNOWN"


class ExperimentClass(str, Enum):
    """Controlled experiment types (P14). STRATEGY_PARAMETER_EXPERIMENT is the only
    class treated as higher-risk (P14) and is never emitted by experiment.py in V1 (see
    that module's docstring) -- listed here so the type exists for a future, separately
    authorized experiment runner, without this package ever selecting it itself."""

    DATA_INTEGRITY_CHECK = "DATA_INTEGRITY_CHECK"
    COST_ATTRIBUTION_CHECK = "COST_ATTRIBUTION_CHECK"
    REGIME_ATTRIBUTION_CHECK = "REGIME_ATTRIBUTION_CHECK"
    SAMPLE_SIZE_DIAGNOSTIC = "SAMPLE_SIZE_DIAGNOSTIC"
    EXECUTION_METADATA_CHECK = "EXECUTION_METADATA_CHECK"
    DETERMINISM_REPLAY = "DETERMINISM_REPLAY"
    OOS_REPRODUCTION = "OOS_REPRODUCTION"
    SHADOW_CLASSIFICATION_CHECK = "SHADOW_CLASSIFICATION_CHECK"
    CAMPAIGN_PIPELINE_CHECK = "CAMPAIGN_PIPELINE_CHECK"
    STRATEGY_PARAMETER_EXPERIMENT = "STRATEGY_PARAMETER_EXPERIMENT"


class ExperimentState(str, Enum):
    """Explicit human-arbiter state machine (P18). This package's diagnostic agent may
    only ever construct ExperimentState.PROPOSED -- APPROVED/EXECUTED/CLOSED etc. belong
    to a separate human/arbiter interface this package does not implement (P18/P19)."""

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    EVIDENCE_AVAILABLE = "EVIDENCE_AVAILABLE"
    CLOSED = "CLOSED"


# Fixed, never-varying authority declaration stamped onto every artifact this package
# writes (P17/P20). Not a per-instance field an adapter or service could accidentally
# override to something else -- there is exactly one authority string this package ever
# emits.
ADVISORY_AUTHORITY = "ADVISORY_ONLY"


@dataclass(frozen=True)
class FailureEvent:
    """Canonical, immutable diagnostic failure event (P2). Bound to strategy identity,
    application release, git commit, and evidence -- never a free-floating claim. Built
    only from an already-computed validation_framework GateResult (P3); this package
    never re-derives or reinterprets gate status itself."""

    event_id: str
    created_at: datetime
    strategy_id: str
    strategy_version: str
    application_release: str
    git_commit: str

    current_lifecycle_stage: str
    target_lifecycle_stage: Optional[str]

    gate_id: str
    gate_status: str

    observed_metrics: Mapping[str, Any]
    required_thresholds: Mapping[str, Any]
    threshold_authority: Mapping[str, Any]

    blocker_codes: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    artifact_hashes: Tuple[str, ...]

    diagnostic_input_complete: bool


@dataclass(frozen=True)
class DiagnosticTrace:
    """One deterministic root-cause trace for one FailureEvent (P5/P24 #4 -- exactly
    one trace per event). `confidence` is a descriptive label (HIGH/MEDIUM/LOW), never a
    formal probability -- this package has no governed scoring authority for that."""

    event_id: str
    diagnosed_at: datetime
    classifier_version: str

    primary_failure_mode: FailureMode
    secondary_failure_modes: Tuple[FailureMode, ...]
    confidence: str
    evidence_refs: Tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class ExperimentProposal:
    """Advisory-only minimal experiment proposal (P10/P11). `requires_human_approval`
    is always True and `state` is always ExperimentState.PROPOSED -- see
    experiment.py, the sole constructor of this dataclass in this package."""

    experiment_id: str
    strategy_id: str
    strategy_version: str
    source_event_id: str
    failed_gate: str

    experiment_class: ExperimentClass
    hypothesis: str

    diagnostic_basis: Mapping[str, Any]
    minimal_delta: Mapping[str, Any]
    scope: Mapping[str, Any]
    protected_constants: Mapping[str, Any]
    expected_evidence: Mapping[str, Any]

    action_if_supported: str
    action_if_rejected: str

    oos_contamination_risk: bool
    state: ExperimentState
    requires_human_approval: bool
    authority: str = ADVISORY_AUTHORITY
    promotion_authority: bool = False
    execution_authority: bool = False
