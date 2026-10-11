"""Typed shapes for the manual-entry trade management pipeline:

MT5 position -> NormalizedPosition -> Claim -> (state.py) -> rules.py -> ManagementIntent
-> validator.py -> mt5.management_gateway -> journal.py

Authority chain (frozen, see PROJECT_STATUS.md 'Phase 6'):
  SKILL / rules.py     = decides what management action should occur
  mt5.management_gateway = the only component allowed to modify/partial-close/close a
                            position
Nothing in this package calls order_send/order_check directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

from mt5.symbol_resolver import SymbolMeta

# ManagementIntent actions -- do not add more without an explicit project rule.
ACTION_HOLD = "HOLD"
ACTION_PARTIAL_CLOSE = "PARTIAL_CLOSE"
ACTION_MOVE_SL = "MOVE_SL"
ACTION_CLOSE = "CLOSE"

# Management state machine (spec section 21).
STATE_UNCLAIMED = "UNCLAIMED"
STATE_MANAGED_OPEN = "MANAGED_OPEN"
STATE_TP1_PENDING = "TP1_PENDING"
STATE_TP1_PARTIAL_DONE = "TP1_PARTIAL_DONE"
STATE_BREAKEVEN_DONE = "BREAKEVEN_DONE"
STATE_RUNNER_ACTIVE = "RUNNER_ACTIVE"
STATE_CLOSED = "CLOSED"
STATE_MANAGEMENT_BLOCKED = "MANAGEMENT_BLOCKED"
STATE_BROKER_REJECTED = "BROKER_REJECTED"
STATE_STATE_RECONCILIATION_REQUIRED = "STATE_RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class NormalizedPosition:
    """Broker position data, read-only, normalized. Produced by
    trade_management.position_monitor (mirrors mt5.account.positions() raw rows) --
    never constructed from assumptions."""

    ticket: int
    symbol: str
    direction: str  # "BUY" / "SELL"
    volume_initial: float
    volume_current: float
    entry_price: float
    current_bid: float
    current_ask: float
    current_price: float
    sl: Optional[float]
    tp: Optional[float]
    profit: float
    swap: float
    commission: Optional[float]
    magic: int
    comment: str
    open_time: datetime
    account_login: int
    account_server: str


@dataclass(frozen=True)
class Claim:
    """Immutable initial snapshot captured when a manual position is first claimed
    (spec section 8). initial_r_distance is frozen here and never recomputed from a
    later-moved SL (spec section 12)."""

    ticket: int
    symbol: str
    direction: str  # "BUY" / "SELL"
    entry_price: float
    initial_sl: float
    initial_volume: float
    initial_r_distance: float
    tp1: Optional[float]
    final_r_multiple: float
    strategy: Optional[str]
    setup: Optional[str]
    claimed_at: datetime


@dataclass(frozen=True)
class ManagementIntent:
    intent_id: str
    position_ticket: int
    symbol: str
    action: str  # ACTION_HOLD / ACTION_PARTIAL_CLOSE / ACTION_MOVE_SL / ACTION_CLOSE
    reason_code: str
    requested_volume: Optional[float] = None
    new_sl: Optional[float] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason_code: str


def make_intent_id(ticket: int, action: str, milestone: str) -> str:
    """Deterministic id so re-running the manager never double-fires the same
    milestone action (spec section 15)."""
    return f"{ticket}:{action}:{milestone}"


# --------------------------------------------------------------------------------------
# TRADE_MANAGEMENT_V1 (pre-trade geometry / sizing / RR), added 2026-08-28.
# Independent of the Claim/NormalizedPosition/ManagementIntent shapes above -- those
# belong to Phase 6's manual-entry, already-open, broker-claimed position workflow
# (frozen 75/25 partial+breakeven policy, see rules.py). This section covers a proposed
# trade BEFORE any position exists, generic across strategy or manual use -- see
# docs/specs/TRADE_MANAGEMENT_V1_SPEC.md.

GEOMETRY_VALID = "VALID"
GEOMETRY_INVALID_DIRECTION = "INVALID_DIRECTION"
GEOMETRY_INVALID_LONG_STOP = "INVALID_LONG_STOP"
GEOMETRY_INVALID_LONG_TARGET = "INVALID_LONG_TARGET"
GEOMETRY_INVALID_SHORT_STOP = "INVALID_SHORT_STOP"
GEOMETRY_INVALID_SHORT_TARGET = "INVALID_SHORT_TARGET"
GEOMETRY_ZERO_STOP_DISTANCE = "ZERO_STOP_DISTANCE"
GEOMETRY_INVALID_PRICE = "INVALID_PRICE"

# Mirrors execution/validator.py's reason-code vocabulary where the same question is
# being asked (account/config/symbol-metadata sanity) -- see sizing.py's docstring.
SIZING_READY = "READY"
SIZING_NOT_REQUESTED = "NOT_REQUESTED"
SIZING_ACCOUNT_DATA_MISSING = "ACCOUNT_DATA_MISSING"
SIZING_INVALID_RISK_CONFIG = "INVALID_RISK_CONFIG"
SIZING_SYMBOL_METADATA_MISSING = "SYMBOL_METADATA_MISSING"
SIZING_RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
SIZING_VOLUME_BELOW_MIN = "VOLUME_BELOW_MIN"
SIZING_VOLUME_ABOVE_MAX = "VOLUME_ABOVE_MAX"
SIZING_SIZE_UNAVAILABLE = "SIZE_UNAVAILABLE"

OVERALL_READY = "READY"
OVERALL_BLOCKED = "BLOCKED"
OVERALL_PARTIAL = "PARTIAL"
OVERALL_INDETERMINATE = "INDETERMINATE"

ADVISORY_NOT_REQUESTED = "NOT_REQUESTED"
ADVISORY_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
ADVISORY_HOLD = "HOLD"
ADVISORY_BREAKEVEN_ELIGIBLE = "BREAKEVEN_ELIGIBLE"
ADVISORY_TARGET_REACHED = "TARGET_REACHED"


@dataclass(frozen=True)
class ManagementPolicy:
    """Caller-supplied (strategy or user) policy. Every field is optional and only
    evaluated when supplied -- Trade Management never substitutes a default policy of
    its own. See docs/specs/TRADE_MANAGEMENT_V1_SPEC.md 'Strategy-specific policy handling'."""

    max_risk_percent: Optional[float] = None  # signed ceiling; None = no ceiling enforced here
    breakeven_trigger_r: Optional[float] = None
    policy_source: Optional[str] = None  # e.g. "SESSION_TRADE_V1", "MANUAL"
    strategy_id: Optional[str] = None
    strategy_version: Optional[str] = None


@dataclass(frozen=True)
class TradeManagementRequest:
    symbol: str
    direction: str  # "LONG" / "SHORT" -- matches strategy_engine.TradeSignal's own convention
    entry_price: float
    stop_loss: float
    take_profit: Optional[float] = None

    risk_percent: Optional[float] = None  # 0 < x <= 100
    risk_amount: Optional[float] = None   # explicit currency amount, takes priority if both given

    equity: Optional[float] = None
    symbol_meta: Optional[SymbolMeta] = None

    current_price: Optional[float] = None  # for position_state advisory only

    management_policy: Optional[ManagementPolicy] = None


@dataclass(frozen=True)
class TradeGeometry:
    status: str
    direction: str
    entry: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    stop_distance_price: Optional[float] = None
    stop_distance_points: Optional[float] = None
    reward_distance_price: Optional[float] = None
    rr_multiple: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class PositionSizing:
    status: str
    requested_risk_percent: Optional[float] = None
    requested_risk_amount: Optional[float] = None
    risk_budget: Optional[float] = None
    loss_per_lot: Optional[float] = None
    raw_volume: Optional[float] = None
    normalized_volume: Optional[float] = None
    actual_risk_amount: Optional[float] = None
    actual_risk_percent: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class PositionStateAdvisory:
    status: str
    current_r: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class TradeManagementResult:
    symbol: str
    direction: str
    overall_status: str
    geometry: TradeGeometry
    sizing: PositionSizing
    position_state: PositionStateAdvisory
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    contract_version: str = "TRADE_MANAGEMENT_V1"
