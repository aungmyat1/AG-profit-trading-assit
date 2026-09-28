"""Read-only FX Opportunity vertical slice (AG_FX_OPPORTUNITY_FOUNDATION_V1).

canonical M15 candles -> reference-session snapshot -> strategy_engine.evaluate()
-> PostAsianDecision -> AsianSweepFunnelAdapter -> OpportunityCandidate
-> ProposalEligibility (existing, unchanged) -> STOP.

No proposal formation, no ticket, no execution. See runner.py.
"""
from .runner import (
    CYCLES,
    PROPOSAL_NO_AUTHORITY,
    PROPOSAL_FORMATION_NOT_WIRED,
    SLICE_SYMBOLS,
    TRADE_TICKET_NOT_CREATED,
    FxOpportunityResult,
    evaluate_fx_opportunity,
)

__all__ = [
    "CYCLES",
    "PROPOSAL_NO_AUTHORITY",
    "PROPOSAL_FORMATION_NOT_WIRED",
    "SLICE_SYMBOLS",
    "TRADE_TICKET_NOT_CREATED",
    "FxOpportunityResult",
    "evaluate_fx_opportunity",
]
