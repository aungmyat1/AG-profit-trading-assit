"""AG_DAILY_ROUTINE_V1 data contracts -- D1 (direction) -> H1 (location) -> M5
(execution) -> risk-managed proposal. Additive, orchestration-only: every analytical
field here is populated by calling an existing skill (market_structure, liquidity,
supply_demand, entry_confirmation, trade_management), never by a new detector.

Concepts audited and confirmed ABSENT from the existing codebase (spec sections 5-6,
11) are represented as explicit GAP statuses, never fabricated:
    - Midnight Open: no contract anywhere in the repo.
    - Alert zone / breathing room: no proximity/tolerance contract anywhere.
    - Generic TP2: trade_management only models a single TP1 (+ breakeven runner);
      only one strategy-specific field (session_trade_adapter.py's own "tp2_5r") uses
      a "tp2" name, not a general contract.
    - Fundamental context: no deterministic fundamental-events engine exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# --------------------------------------------------------------------------- D1

DIRECTIONAL_PERMISSION_LONG_ONLY = "LONG_ONLY"
DIRECTIONAL_PERMISSION_SHORT_ONLY = "SHORT_ONLY"
DIRECTIONAL_PERMISSION_BOTH = "BOTH"
DIRECTIONAL_PERMISSION_NO_TRADE = "NO_TRADE"
DIRECTIONAL_PERMISSION_INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class FundamentalContext:
    """No deterministic fundamental-events engine exists in this project (spec section
    9) -- status is always UNAVAILABLE unless/until one is wired. Never populated with
    LLM-invented events."""
    status: str = "UNAVAILABLE"
    events: Tuple[str, ...] = field(default_factory=tuple)
    high_impact_event_present: Optional[bool] = None
    entry_restriction: Optional[str] = None
    source: Optional[str] = None
    as_of: Optional[datetime] = None


@dataclass(frozen=True)
class D1Context:
    symbol: str
    as_of: Optional[datetime]
    timeframe: str = "D1"
    market_data_freshness: str = "UNKNOWN"

    structure_direction: Optional[str] = None  # market_structure.models.STATE_BULLISH/BEARISH/UNDEFINED
    external_buy_side_liquidity: Optional[Any] = None  # liquidity.models.LiquidityLevel
    external_sell_side_liquidity: Optional[Any] = None
    internal_liquidity: Tuple[Any, ...] = field(default_factory=tuple)  # liquidity.models.LiquidityLevel, best-effort
    gap_liquidity: Tuple[Any, ...] = field(default_factory=tuple)  # supply_demand.models.ZoneResult (FVGs)

    fundamental_context: FundamentalContext = field(default_factory=FundamentalContext)
    directional_permission: str = DIRECTIONAL_PERMISSION_INDETERMINATE
    reasoning_codes: Tuple[str, ...] = field(default_factory=tuple)
    evidence: Dict[str, Any] = field(default_factory=dict)
    status: str = "UNAVAILABLE"  # READY / PARTIAL / UNAVAILABLE


# --------------------------------------------------------------------------- H1

H1_WAITING_CONTEXT = "WAITING_CONTEXT"
H1_WAITING_LOCATION = "WAITING_LOCATION"
H1_POI_IDENTIFIED = "POI_IDENTIFIED"
H1_POI_REACHED = "POI_REACHED"
H1_INVALIDATED = "INVALIDATED"
H1_INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class MidnightOpen:
    """GAP (spec section 5): no Midnight Open contract exists anywhere in this
    project. Always NOT_IMPLEMENTED -- never approximated with an invented UTC/broker
    convention."""
    status: str = "NOT_IMPLEMENTED"
    price: Optional[float] = None


@dataclass(frozen=True)
class AlertZone:
    """GAP (spec section 6): no breathing-room/proximity/tolerance contract exists
    anywhere in this project. `proximity_policy` stays UNDEFINED -- never assigned an
    invented pip/ATR threshold."""
    target_zone: Optional[Any] = None
    proximity_policy: str = "UNDEFINED"
    status: str = "POLICY_REQUIRED"


@dataclass(frozen=True)
class H1SetupContext:
    symbol: str
    as_of: Optional[datetime]
    timeframe: str = "H1"
    d1_directional_permission: str = DIRECTIONAL_PERMISSION_INDETERMINATE

    structure_direction: Optional[str] = None
    external_liquidity: Tuple[Any, ...] = field(default_factory=tuple)
    internal_liquidity: Tuple[Any, ...] = field(default_factory=tuple)
    asian_session_high: Optional[float] = None
    asian_session_low: Optional[float] = None

    poi_candidates: Tuple[Any, ...] = field(default_factory=tuple)  # supply_demand.models.ZoneResult/ValidatedOrderBlock
    selected_poi: Optional[Any] = None
    midnight_open: MidnightOpen = field(default_factory=MidnightOpen)
    current_location: Optional[str] = None  # "ABOVE_POI" / "BELOW_POI" / "INSIDE_POI" / None
    alert_zone: AlertZone = field(default_factory=AlertZone)

    reasoning_codes: Tuple[str, ...] = field(default_factory=tuple)
    evidence: Dict[str, Any] = field(default_factory=dict)
    status: str = H1_WAITING_CONTEXT


# --------------------------------------------------------------------------- M5

M5_WAITING_H1_LOCATION = "WAITING_H1_LOCATION"
M5_WAITING_SWEEP = "WAITING_SWEEP"
M5_WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
M5_RISK_REJECTED = "RISK_REJECTED"
M5_READY_FOR_PROPOSAL = "READY_FOR_PROPOSAL"
M5_NO_TRADE = "NO_TRADE"
M5_INDETERMINATE = "INDETERMINATE"

TP2_POLICY_REQUIRED = "TP2_POLICY_REQUIRED"  # spec section 11: never invent a universal TP2 formula


@dataclass(frozen=True)
class M5ExecutionContext:
    symbol: str
    as_of: Optional[datetime]
    timeframe: str = "M5"
    d1_permission: str = DIRECTIONAL_PERMISSION_INDETERMINATE
    h1_location: Optional[str] = None
    strategy_id: str = "SMC_CONDITIONAL_ENTRY_V2"  # the only strategy currently wired; see m5_execution.py

    session_liquidity_reference: Optional[Any] = None
    sweep_result: Optional[str] = None
    structure_shift_result: Optional[str] = None
    displacement_result: Optional[str] = None
    entry_array_result: Optional[Any] = None  # proposals.models.SMCTradeProposal
    confirmation_result: Optional[Any] = None  # entry_confirmation.SMCEntryCombinationResult

    risk_result: Optional[Any] = None  # trade_management.models.TradeManagementResult
    tp1: Optional[float] = None
    tp2: str = TP2_POLICY_REQUIRED

    reasoning_codes: Tuple[str, ...] = field(default_factory=tuple)
    evidence: Dict[str, Any] = field(default_factory=dict)
    status: str = M5_WAITING_H1_LOCATION


# --------------------------------------------------------------------------- routine result

@dataclass(frozen=True)
class DailyRoutineResult:
    symbol: str
    as_of: Optional[datetime]
    d1: D1Context
    h1: H1SetupContext
    m5: M5ExecutionContext
    overall_status: str  # WAITING / READY_FOR_PROPOSAL / NO_TRADE / INVALIDATED / RISK_REJECTED / INDETERMINATE / STALE_DATA
    next_action: str
    proposal_id: Optional[str] = None
    diagnostics: Tuple[str, ...] = field(default_factory=tuple)
