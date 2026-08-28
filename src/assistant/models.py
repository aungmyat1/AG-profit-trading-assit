"""Runtime-level contracts for ASSISTANT_RUNTIME_V1: MarketContext (strategy-neutral
runtime inputs), StrategyResult (normalized strategy output, whatever the underlying
strategy's own native result shape is), and AssistantDecision (the assistant's complete
decision record for one evaluate() call -- distinct from a strategy's own TradeIntent,
which stays owned by the strategy/its adapter).

Nothing here decides Trend/Range/Sweep/entry/SL/TP -- those values only ever get COPIED
in from a strategy's own result by strategy_manager/manager.py. See
strategy_manager/session_trade_adapter.py for SESSION_TRADE_V1's own mapping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Tuple

# MarketContext status
CONTEXT_READY = "CONTEXT_READY"
CONTEXT_FAILED = "CONTEXT_FAILED"

# StrategyResult status
STATUS_NO_SETUP = "NO_SETUP"
STATUS_TRADE_CANDIDATE = "TRADE_CANDIDATE"
STATUS_TRADE_READY = "TRADE_READY"
STATUS_BLOCKED = "BLOCKED"
STATUS_INVALID_CONTEXT = "INVALID_CONTEXT"

# AssistantDecision status
DECISION_CONTEXT_FAILED = "CONTEXT_FAILED"
DECISION_NO_SETUP = "NO_SETUP"
DECISION_TRADE_READY = "TRADE_READY"
DECISION_UNSIGNED_STRATEGY = "UNSIGNED_STRATEGY"
DECISION_UNSIGNED_CYCLE = "UNSIGNED_CYCLE"
DECISION_EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
DECISION_DUPLICATE_SIGNAL = "DUPLICATE_SIGNAL"
DECISION_RISK_REJECTED = "RISK_REJECTED"
DECISION_VALIDATION_REJECTED = "VALIDATION_REJECTED"
DECISION_ORDER_CHECK_REJECTED = "ORDER_CHECK_REJECTED"
DECISION_SHADOW_CHECKED = "SHADOW_CHECKED"
DECISION_EXECUTED = "EXECUTED"
DECISION_EXECUTION_FAILED = "EXECUTION_FAILED"
DECISION_STRATEGY_REGISTRY_CONFLICT = "STRATEGY_REGISTRY_CONFLICT"

# Runtime modes
MODE_ANALYZE_ONLY = "ANALYZE_ONLY"
MODE_SHADOW_DEMO = "SHADOW_DEMO"
MODE_DEMO_EXECUTION = "DEMO_EXECUTION"
MODE_LIVE = "LIVE"
ALL_MODES = (MODE_ANALYZE_ONLY, MODE_SHADOW_DEMO, MODE_DEMO_EXECUTION, MODE_LIVE)


@dataclass(frozen=True)
class MarketContext:
    """Strategy-neutral runtime inputs -- built once per evaluate() call by
    strategy_manager/context_builder.py and handed unchanged to whichever adapter the
    Strategy Manager dispatches to. Fields are deliberately generic (not
    SESSION_TRADE_V1-specific) so a future strategy's adapter can reuse the same
    context."""

    symbol: str
    broker_resolved_symbol: str
    timestamp_utc: datetime
    session_date: date
    account_login: int
    account_server: str
    account_is_demo: bool
    current_bid: float
    current_ask: float
    tick_time_utc: datetime
    status: str = CONTEXT_READY
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StrategyResult:
    """Normalized strategy output -- whatever SESSION_TRADE_V1 (or any future strategy)
    natively returns gets mapped into this shape by its own adapter. The Strategy
    Manager/TradeAssistant only ever read these fields; they never re-derive setup/
    direction/entry/SL/TP themselves (spec section 13)."""

    strategy_id: str
    strategy_version: str
    symbol: str
    cycle: str
    session_date: date
    status: str  # STATUS_* above
    setup: Optional[str] = None
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    risk_percent: Optional[float] = None
    signal_id: Optional[str] = None
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    metadata: dict = field(default_factory=dict)  # raw native fields for reporting (e.g. asian_high/low)


@dataclass(frozen=True)
class AssistantDecision:
    """The assistant's complete decision record for one evaluate() call. Distinct from
    StrategyResult (the strategy's own answer) and from any native TradeIntent (an
    executable request the strategy's own adapter/execution stack owns)."""

    run_id: str
    strategy_id: str
    strategy_version: Optional[str]
    symbol: str
    cycle: str
    timestamp_utc: datetime
    execution_mode: str  # MODE_* above
    status: str  # DECISION_* above
    context_status: str
    strategy_status: Optional[str] = None
    setup: Optional[str] = None
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    signal_id: Optional[str] = None
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    execution_report: Optional[dict] = None  # raw adapter execution outcome (order_check/order_send detail)
