"""Entry & Confirmation capability (Phase 5, ENTRY_CONFIRMATION_V1): answers "what
confirmation evidence exists for a proposed direction?" -- never "should I buy or sell?"

Advisory only: this package reports deterministic confirmation facts (displacement and
rejection/reversal candle measurements, structure-shift alignment, liquidity-reclaim
alignment). It has no execution authority, never calls execution/order_check/
order_send, and never decides a trade -- see PROJECT_STATUS.md 'Authority order' and
entry_confirmation/contract.py.

Reuses market_structure.StructureResult and liquidity.LiquidityResult verbatim (never
re-detects swings/BOS/CHoCH/sweeps/reclaims) and never independently fetches market
data -- callers supply an already-fetched Candle and already-computed upstream results.
See engine.py's module docstring for the full data flow and the `overall_state`
aggregation contract.

Where no owner-signed generic threshold exists (displacement/rejection qualification),
this package reports the objective measurement and an explicit
`ConfirmationState.UNSIGNED_RULE` rather than inventing one -- see contract.py's
ENTRY_CONFIRMATION_CONTRACT_GAPS.
"""
from .contract import CONTRACT_VERSION, ENTRY_CONFIRMATION_CONTRACT_GAPS, EntryConfirmationContractGap
from .engine import evaluate_entry_confirmation
from .models import (
    ALL_CONFIRMATIONS,
    DISPLACEMENT,
    LIQUIDITY_RECLAIM,
    REJECTION,
    STRUCTURE_SHIFT,
    CandidateDirection,
    ConfirmationState,
    DisplacementEvidence,
    EntryConfirmationRequest,
    EntryConfirmationResult,
    LiquidityAlignment,
    OverallState,
    RejectionEvidence,
    StructureAlignment,
)

__all__ = [
    "evaluate_entry_confirmation",
    "EntryConfirmationRequest", "EntryConfirmationResult",
    "CandidateDirection", "ConfirmationState", "OverallState",
    "DisplacementEvidence", "RejectionEvidence", "StructureAlignment", "LiquidityAlignment",
    "ALL_CONFIRMATIONS", "DISPLACEMENT", "STRUCTURE_SHIFT", "LIQUIDITY_RECLAIM", "REJECTION",
    "CONTRACT_VERSION", "ENTRY_CONFIRMATION_CONTRACT_GAPS", "EntryConfirmationContractGap",
]
