"""SessionTradeProposal (spec section 9): a typed projection over the existing
daytrading.decision.DaytradingSetupDecision + strategy_engine.session.ReferenceBox +
SetupDecision -- flattens their already-computed fields for the SESSION_TRADE workflow's
output contract, never recomputes them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Tuple

PROPOSAL_VALID = "VALID_PROPOSAL"
PROPOSAL_WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
PROPOSAL_NO_SETUP = "NO_SETUP"
PROPOSAL_CONFLICT = "CONFLICT"
PROPOSAL_INDETERMINATE = "INDETERMINATE"

PROPOSAL_STATUS_VALUES = (
    PROPOSAL_VALID,
    PROPOSAL_WAITING_CONFIRMATION,
    PROPOSAL_NO_SETUP,
    PROPOSAL_CONFLICT,
    PROPOSAL_INDETERMINATE,
)


@dataclass(frozen=True)
class SessionTradeProposal:
    strategy_id: str
    symbol: str
    trading_date: date

    reference_session: str
    reference_start: Optional[datetime]
    reference_end: Optional[datetime]

    market_bias: str

    reference_high: Optional[float]
    reference_low: Optional[float]
    reference_mid: Optional[float]
    reference_open: Optional[float]
    reference_close: Optional[float]

    efficiency_ratio: Optional[float]
    regime: Optional[str]

    sweep_detected: bool
    sweep_side: Optional[str]

    setup_type: str
    direction: Optional[str]

    entry_reference: Optional[float]
    stop_reference: Optional[float]
    target_reference: Optional[float]

    entry_confirmation_state: Optional[str]

    proposal_status: str

    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    created_at: Optional[datetime] = None

    # AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1 M4 (P15/P16): traces this proposal
    # back to the exact canonical MarketBiasResult that produced its `market_bias`
    # string above -- None only when the upstream MarketBias never carried
    # canonical_provenance (a hand-built MarketBias fixture, never a real evaluation
    # path). Never fabricated after the fact; always copied verbatim from
    # decision.market_bias.canonical_provenance by session_workflow.py.
    bias_decision_cycle_id: Optional[str] = None
    bias_model_version: Optional[str] = None
    bias_decision_time: Optional[datetime] = None
    bias_input_fingerprint: Optional[str] = None
    bias_reason_codes: Tuple[str, ...] = field(default_factory=tuple)
