"""Sanitized Pydantic response models. No field here may ever carry a credential --
see tests/test_api.py::test_no_response_model_field_named_like_a_secret for a static
guard against that regressing."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class BrokerStatusResponse(BaseModel):
    connected: bool
    broker: Optional[str] = None
    environment: Optional[str] = None
    server: Optional[str] = None
    account_redacted: Optional[str] = None
    trade_allowed_informational: Optional[bool] = None
    reason_code: Optional[str] = None


class BrokerAccountResponse(BaseModel):
    """Balance/equity summary only -- see mt5.account.Account for the full (still
    non-secret) field set this is drawn from. No currency/margin field is included:
    Account carries neither today, and this module never invents one."""

    connected: bool
    broker: Optional[str] = None
    environment: Optional[str] = None
    server: Optional[str] = None
    account_redacted: Optional[str] = None
    balance: Optional[float] = None
    equity: Optional[float] = None
    trade_allowed_informational: Optional[bool] = None
    reason_code: Optional[str] = None


class BrokerDealResponse(BaseModel):
    ticket: int
    position_id: int
    time: str
    symbol: str
    side: str
    volume: float
    price: float
    profit: float
    commission: float
    swap: float
    fee: float
    comment: str


class BrokerHistoryResponse(BaseModel):
    account_redacted: str
    server: str
    environment: str
    lookback_days: int
    total_closing_deals: int
    returned_deals: int
    realized_net: float
    deals: List[BrokerDealResponse]


class MT5StatusResponse(BaseModel):
    connected: bool


class MarketDataCandleResponse(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataCandlesResponse(BaseModel):
    """Roadmap R2 (AG_REAL_MARKET_WATCH_READY_V1): real, closed-bar-only MT5 candles.
    `source` is always the literal 'MT5' here -- this response model exists precisely
    so a caller can distinguish it from the frontend's SYNTHETIC scanner proposals,
    never the reverse."""

    source: str
    broker: Optional[str] = None
    environment: Optional[str] = None
    symbol: str
    timeframe: str
    bar_count: int
    last_closed_candle_at: str
    freshness: str
    candles: List[MarketDataCandleResponse]


class TelegramStatusResponse(BaseModel):
    configured: bool


class SystemStatusResponse(BaseModel):
    service: str
    status: str
    application_release: str
    execution_mode: str
    broker: BrokerStatusResponse
    mt5: MT5StatusResponse
    telegram: TelegramStatusResponse


class StrategyResponse(BaseModel):
    """Backend-authoritative registration/lifecycle summary -- see
    strategies/registry.yaml and config/governance/strategy_lifecycle.yaml, the
    canonical sources this is read from unchanged. demo_authorized/live_authorized are
    never inferred from lifecycle_stage or from proposal existence."""

    strategy_id: str
    registered: bool
    active: bool
    research: bool
    demo_authorized: bool
    live_authorized: bool
    lifecycle_stage: Optional[str] = None
    semantic_version: Optional[str] = None


class GateResultResponse(BaseModel):
    gate_name: str
    status: str
    evidence_refs: List[str]


class ValidationResponse(BaseModel):
    strategy_id: str
    semantic_version: str
    lifecycle_stage: str
    execution_capability: str
    execution_authority: str
    next_transition: Optional[str] = None
    promotion_eligible: bool
    promotion_blockers: List[str]
    gates: List[GateResultResponse]


class TelegramStatusDetailResponse(BaseModel):
    """Detailed status for GET /api/telegram/status -- distinct from the nested
    summary on SystemStatusResponse.telegram. No field here may ever carry a bot
    token or chat-bearing URL."""

    configured: bool
    bot_configured: bool
    chat_configured: bool
    reachable: bool
    reason_code: Optional[str] = None


class TelegramActionResponse(BaseModel):
    success: bool
    reason_code: Optional[str] = None
    message_id: Optional[str] = None


class ProposalResponse(BaseModel):
    proposal_hash: str
    setup_id: str
    strategy_id: str
    symbol: str
    direction: str
    entry: float
    stop_loss: float
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    volume: float
    risk_amount: float
    risk_percent: Optional[float] = None


class CanonicalProposalResponse(BaseModel):
    """WP9 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): read-only view of
    proposal_envelope.models.CanonicalProposal from the WP8 ProposalLedger. Always
    execution_authority='NONE' and execution_eligible=False -- this is an OBSERVATION
    ONLY surface; see api.app's canonical-proposals routes for the read-only boundary
    (no execution, no authorization, no geometry mutation)."""

    proposal_id: str  # proposal_envelope_id -- the WP7 canonical identity
    strategy_id: str
    strategy_version: str
    symbol: str
    market: str
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    targets: List[float] = []
    watcher_state: str
    proposal_state: str
    execution_authority: str
    execution_eligible: bool = False
    market_data_mode: Optional[str] = None
    market_data_source: Optional[str] = None
    market_data_asof: Optional[str] = None
    market_data_fingerprint: Optional[str] = None
    ready_at: Optional[str] = None
    expires_at: Optional[str] = None
    version: int
    correction_of: Optional[str] = None
    reasons: List[str] = []
    # V1.2 (AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2): additive governance
    # fields, mirrored verbatim from CanonicalProposal -- default values match this
    # surface's own pre-existing execution_eligible=False fail-closed posture, so every
    # response already served before this field set existed stays valid.
    economic_edge_established: bool = False
    demo_eligible: bool = False
    demo_authorized: bool = False
    live_authorized: bool = False
    proposal_only: bool = True
    broker_mutation_blocked: bool = True
    lifecycle_stage: Optional[str] = None


class TicketResponse(BaseModel):
    approval_id: str
    setup_id: str
    strategy_id: Optional[str] = None
    symbol: Optional[str] = None
    direction: Optional[str] = None
    environment: str
    state: str
    created_at: str
    expires_at: str


class AuthorizeDemoRequest(BaseModel):
    action: str = "EXECUTE_DEMO"


class AuthorizeDemoResponse(BaseModel):
    approval_id: str
    success: bool
    state: str
    reason_code: Optional[str] = None
    result_reference: Optional[str] = None


class ErrorResponse(BaseModel):
    reason_code: str
    message: str
