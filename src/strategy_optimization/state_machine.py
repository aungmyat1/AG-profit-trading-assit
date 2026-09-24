"""Non-authorizing candidate research state machine.

This state machine is subordinate to `validation_framework.lifecycle_registry`, which
remains the only strategy-lifecycle authority. Terminal blocked/rejected states are
intentionally irreversible; remediation requires a new experiment ID, not a reset or
implicit parameter search.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence, Tuple


class CandidateState(str, Enum):
    DRAFT = "DRAFT"
    PREREGISTERED = "PREREGISTERED"
    DEVELOPMENT_TESTED = "DEVELOPMENT_TESTED"
    ROBUSTNESS_PASS = "ROBUSTNESS_PASS"
    CANDIDATE_FROZEN = "CANDIDATE_FROZEN"
    REPLICATION_PASS = "REPLICATION_PASS"
    OOS_PASS = "OOS_PASS"
    HOLDOUT_PASS = "HOLDOUT_PASS"
    PARITY_PASS = "PARITY_PASS"
    FORWARD_RESEARCH = "FORWARD_RESEARCH"
    OWNER_REVIEW = "OWNER_REVIEW"

    BLOCKED_REPRODUCIBILITY = "BLOCKED_REPRODUCIBILITY"
    BLOCKED_DATA = "BLOCKED_DATA"
    BLOCKED_SEMANTICS = "BLOCKED_SEMANTICS"
    BLOCKED_AUTHORITY = "BLOCKED_AUTHORITY"
    REJECTED_NEGATIVE = "REJECTED_NEGATIVE"
    REJECTED_UNSTABLE = "REJECTED_UNSTABLE"
    REJECTED_SAMPLE_INSUFFICIENT = "REJECTED_SAMPLE_INSUFFICIENT"
    REJECTED_OWNER_DECISION = "REJECTED_OWNER_DECISION"


TERMINAL_STATES = frozenset({
    CandidateState.BLOCKED_REPRODUCIBILITY,
    CandidateState.BLOCKED_DATA,
    CandidateState.BLOCKED_SEMANTICS,
    CandidateState.BLOCKED_AUTHORITY,
    CandidateState.REJECTED_NEGATIVE,
    CandidateState.REJECTED_UNSTABLE,
    CandidateState.REJECTED_SAMPLE_INSUFFICIENT,
    CandidateState.REJECTED_OWNER_DECISION,
})

_ALLOWED_FORWARD = {
    CandidateState.DRAFT: frozenset({CandidateState.PREREGISTERED}),
    CandidateState.PREREGISTERED: frozenset({CandidateState.DEVELOPMENT_TESTED}),
    CandidateState.DEVELOPMENT_TESTED: frozenset({CandidateState.ROBUSTNESS_PASS}),
    CandidateState.ROBUSTNESS_PASS: frozenset({CandidateState.CANDIDATE_FROZEN}),
    CandidateState.CANDIDATE_FROZEN: frozenset({CandidateState.REPLICATION_PASS}),
    CandidateState.REPLICATION_PASS: frozenset({CandidateState.OOS_PASS}),
    CandidateState.OOS_PASS: frozenset({CandidateState.HOLDOUT_PASS}),
    CandidateState.HOLDOUT_PASS: frozenset({CandidateState.PARITY_PASS}),
    CandidateState.PARITY_PASS: frozenset({CandidateState.FORWARD_RESEARCH}),
    CandidateState.FORWARD_RESEARCH: frozenset({CandidateState.OWNER_REVIEW}),
    CandidateState.OWNER_REVIEW: frozenset(),
}

_BLOCKED_FROM = frozenset(state for state in CandidateState if state not in TERMINAL_STATES)
_REJECTION_FROM = {
    CandidateState.REJECTED_NEGATIVE: frozenset({
        CandidateState.DEVELOPMENT_TESTED, CandidateState.ROBUSTNESS_PASS,
        CandidateState.CANDIDATE_FROZEN, CandidateState.REPLICATION_PASS,
        CandidateState.OOS_PASS, CandidateState.HOLDOUT_PASS,
    }),
    CandidateState.REJECTED_UNSTABLE: frozenset({
        CandidateState.ROBUSTNESS_PASS, CandidateState.CANDIDATE_FROZEN,
        CandidateState.REPLICATION_PASS, CandidateState.OOS_PASS,
    }),
    CandidateState.REJECTED_SAMPLE_INSUFFICIENT: frozenset({
        CandidateState.PREREGISTERED, CandidateState.DEVELOPMENT_TESTED,
        CandidateState.ROBUSTNESS_PASS, CandidateState.CANDIDATE_FROZEN,
        CandidateState.REPLICATION_PASS, CandidateState.OOS_PASS,
        CandidateState.HOLDOUT_PASS, CandidateState.PARITY_PASS,
        CandidateState.FORWARD_RESEARCH,
    }),
}

_REQUIRED_EVIDENCE = {
    CandidateState.PREREGISTERED: frozenset({
        "baseline_reproduction", "data_integrity", "semantic_integrity",
        "economic_diagnosis", "hypothesis_preregistration",
    }),
    CandidateState.DEVELOPMENT_TESTED: frozenset({"control_candidate_development_result"}),
    CandidateState.ROBUSTNESS_PASS: frozenset({"robustness_report"}),
    CandidateState.CANDIDATE_FROZEN: frozenset({"candidate_freeze"}),
    CandidateState.REPLICATION_PASS: frozenset({"independent_replication_result"}),
    CandidateState.OOS_PASS: frozenset({"oos_result"}),
    CandidateState.HOLDOUT_PASS: frozenset({"final_holdout_result"}),
    CandidateState.PARITY_PASS: frozenset({"paper_demo_parity_report"}),
    CandidateState.FORWARD_RESEARCH: frozenset({"canonical_lifecycle_evaluation", "owner_forward_authorization"}),
    CandidateState.OWNER_REVIEW: frozenset({"forward_summary", "owner_review_packet"}),
    CandidateState.BLOCKED_REPRODUCIBILITY: frozenset({"baseline_provenance_search"}),
    CandidateState.BLOCKED_DATA: frozenset({"data_blocker_evidence"}),
    CandidateState.BLOCKED_SEMANTICS: frozenset({"semantic_blocker_evidence"}),
    CandidateState.BLOCKED_AUTHORITY: frozenset({"authority_blocker_evidence"}),
    CandidateState.REJECTED_NEGATIVE: frozenset({"negative_result", "rejection_rationale"}),
    CandidateState.REJECTED_UNSTABLE: frozenset({"instability_result", "rejection_rationale"}),
    CandidateState.REJECTED_SAMPLE_INSUFFICIENT: frozenset({"sample_size_evidence", "rejection_rationale"}),
    CandidateState.REJECTED_OWNER_DECISION: frozenset({"owner_rejection_record"}),
}


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    current_state: CandidateState
    requested_state: CandidateState
    required_evidence: Tuple[str, ...] = ()
    missing_evidence: Tuple[str, ...] = ()
    blockers: Tuple[str, ...] = ()


def validate_transition(
    current: CandidateState,
    requested: CandidateState,
    evidence_refs: Mapping[str, Sequence[str]],
    *,
    optimization_admission_passed: bool = False,
) -> TransitionDecision:
    """Validate one explicit state transition; performs no mutation or stage advance."""
    required = _REQUIRED_EVIDENCE.get(requested, frozenset())
    present = {key for key, refs in evidence_refs.items() if tuple(refs)}
    missing = tuple(sorted(required - present))
    blockers = []

    if current in TERMINAL_STATES:
        blockers.append("TERMINAL_STATE_REQUIRES_NEW_EXPERIMENT_ID")
    elif requested is CandidateState.REJECTED_OWNER_DECISION:
        blockers.append("OWNER_DECISION_API_REQUIRED")
    elif requested in TERMINAL_STATES:
        if requested in {
            CandidateState.REJECTED_NEGATIVE,
            CandidateState.REJECTED_UNSTABLE,
            CandidateState.REJECTED_SAMPLE_INSUFFICIENT,
        }:
            if current not in _REJECTION_FROM.get(requested, frozenset()):
                blockers.append("REJECTION_NOT_VALID_FROM_CURRENT_STAGE")
        elif current not in _BLOCKED_FROM:
            blockers.append("BLOCKED_STATE_NOT_VALID_FROM_CURRENT_STAGE")
    elif requested not in _ALLOWED_FORWARD.get(current, frozenset()):
        blockers.append("NON_MONOTONIC_OR_UNSUPPORTED_TRANSITION")

    if missing:
        blockers.append("REQUIRED_EVIDENCE_MISSING")
    if requested is CandidateState.DEVELOPMENT_TESTED and not optimization_admission_passed:
        blockers.append("OPTIMIZATION_ADMISSION_NOT_PASSED")
    if requested is CandidateState.ROBUSTNESS_PASS and not optimization_admission_passed:
        blockers.append("OPTIMIZATION_ADMISSION_NOT_PASSED")

    return TransitionDecision(
        allowed=not blockers,
        current_state=current,
        requested_state=requested,
        required_evidence=tuple(sorted(required)),
        missing_evidence=missing,
        blockers=tuple(blockers),
    )


__all__ = ["CandidateState", "TERMINAL_STATES", "TransitionDecision", "validate_transition"]
