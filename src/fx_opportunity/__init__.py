"""Read-only FX Opportunity platform (AG_FX_OPPORTUNITY_FOUNDATION_V1 -> PLATFORM_V2).

canonical M15 candles -> MarketState (strategy-neutral facts) -> reference-session
snapshot -> strategy_engine.evaluate() -> PostAsianDecision -> AsianSweepFunnelAdapter
-> OpportunityCandidate -> ProposalEligibility (existing, unchanged) -> STOP.

Symbols come from config/instruments/fx_opportunity_instruments.yaml (EURUSD, GBPUSD,
USDJPY); scanner.py returns one explicit state per symbol per cycle. No proposal
formation, no ticket, no execution. See runner.py / scanner.py.
"""
from .runner import (
    CYCLES,
    PROPOSAL_NO_AUTHORITY,
    PROPOSAL_FORMATION_NOT_WIRED,
    RESEARCH_STRATEGY,
    SLICE_SYMBOLS,
    TRADE_TICKET_NOT_CREATED,
    FxOpportunityResult,
    evaluate_fx_opportunity,
)

__all__ = [
    "CYCLES",
    "PROPOSAL_NO_AUTHORITY",
    "PROPOSAL_FORMATION_NOT_WIRED",
    "RESEARCH_STRATEGY",
    "SLICE_SYMBOLS",
    "TRADE_TICKET_NOT_CREATED",
    "FxOpportunityResult",
    "evaluate_fx_opportunity",
]
