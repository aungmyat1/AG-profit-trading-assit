"""Strategy-neutral funnel vocabulary (AG V2, P3).

Stage answers "how far through the opportunity funnel is this candidate"; outcome
answers "what is its current disposition". The two are independent -- a candidate
can sit at stage=TRIGGER_ARMED with outcome=WAIT without inventing a new stage.

Portfolio risk is explicitly NOT a stage here (no RISK_FEASIBLE). Risk sits
downstream of a candidate, in ProposalEligibilityDecision and the existing
CanonicalProposal / risk authority -- see contracts.py.
"""
from __future__ import annotations

STAGE_MARKET_ELIGIBLE = "MARKET_ELIGIBLE"
STAGE_CONTEXT_VALID = "CONTEXT_VALID"
STAGE_LOCATION_VALID = "LOCATION_VALID"
STAGE_SETUP_DETECTED = "SETUP_DETECTED"
STAGE_TRIGGER_ARMED = "TRIGGER_ARMED"
STAGE_ENTRY_CONFIRMED = "ENTRY_CONFIRMED"
STAGE_OPPORTUNITY_READY = "OPPORTUNITY_READY"

FUNNEL_STAGES = (
    STAGE_MARKET_ELIGIBLE,
    STAGE_CONTEXT_VALID,
    STAGE_LOCATION_VALID,
    STAGE_SETUP_DETECTED,
    STAGE_TRIGGER_ARMED,
    STAGE_ENTRY_CONFIRMED,
    STAGE_OPPORTUNITY_READY,
)
VALID_FUNNEL_STAGES = frozenset(FUNNEL_STAGES)

OUTCOME_ACTIVE = "ACTIVE"
OUTCOME_WAIT = "WAIT"
OUTCOME_REJECT = "REJECT"
OUTCOME_INVALIDATED = "INVALIDATED"
OUTCOME_EXPIRED = "EXPIRED"
OUTCOME_ERROR = "ERROR"

FUNNEL_OUTCOMES = (
    OUTCOME_ACTIVE,
    OUTCOME_WAIT,
    OUTCOME_REJECT,
    OUTCOME_INVALIDATED,
    OUTCOME_EXPIRED,
    OUTCOME_ERROR,
)
VALID_FUNNEL_OUTCOMES = frozenset(FUNNEL_OUTCOMES)


def validate_stage(stage: str) -> None:
    if stage not in VALID_FUNNEL_STAGES:
        raise ValueError(f"stage must be one of {FUNNEL_STAGES}, got {stage!r}")


def validate_outcome(outcome: str) -> None:
    if outcome not in VALID_FUNNEL_OUTCOMES:
        raise ValueError(f"outcome must be one of {FUNNEL_OUTCOMES}, got {outcome!r}")
