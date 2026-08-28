"""Execution-layer data shapes.

A TradeIntent is what execution/intent_builder.py produces from a strategy_engine
TradeSignal plus live account/symbol state: a fully-sized order request that has not
yet been sent to order_check or order_send. Kept separate from TradeSignal so the
strategy engine never has to know about lot sizes, account equity, or broker fields.

IntentResult is the outer, always-returned shape: status + reason_code, with `intent`
populated only when status == READY_FOR_ORDER_CHECK. Every rejection path returns a
result, never an exception -- a bad signal/config/data state is an expected outcome to
report, not a crash.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

STATUS_READY = "READY_FOR_ORDER_CHECK"


@dataclass(frozen=True)
class TradeIntent:
    signal_id: str
    strategy_id: str
    strategy_version: str
    pair_id: str
    symbol: str
    direction: str  # "LONG" / "SHORT"
    entry: float
    stop_loss: float
    take_profit: Optional[float]
    volume: float
    risk_amount: float
    risk_percent: float
    equity_at_sizing: float
    magic_number: int


@dataclass(frozen=True)
class IntentResult:
    status: str  # STATUS_READY or a rejection reason_code
    reason_code: str
    intent: Optional[TradeIntent] = None


# --- Execution Authority Restructure (2026-08-28) -------------------------------------
# See docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md / PROJECT_STATUS.md "Execution authority
# restructure". These shapes are additive -- TradeIntent/IntentResult above are
# unchanged and remain the strategy-signal path (execution/intent_builder.py).
#
# ExecutionSource is the mandatory distinction between the two ways a TradeCommand can
# arise: an assistant-generated TradeProposal the user then explicitly executes, vs. a
# fully user-specified order. Only USER_EXPLICIT_ORDER skips entry-confirmation/strategy
# requirements -- see execution/executor.py.


class ExecutionSource(str, Enum):
    ASSISTANT_PROPOSAL = "ASSISTANT_PROPOSAL"
    USER_EXPLICIT_ORDER = "USER_EXPLICIT_ORDER"


@dataclass(frozen=True)
class TradeCommand:
    """A caller-constructed request to open or close a position. Never executed by
    constructing one -- execution/executor.py::execute() additionally requires a
    separate, non-defaulted user_confirmed=True to reach order_send."""

    command_id: str
    action: str  # "OPEN" / "CLOSE"
    symbol: str
    source: ExecutionSource
    side: Optional[str] = None  # "BUY" / "SELL" -- required for OPEN
    order_type: str = "MARKET"  # "MARKET" / "LIMIT"
    volume: Optional[float] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    risk_percent: Optional[float] = None
    proposal_id: Optional[str] = None  # required when source == ASSISTANT_PROPOSAL
    position_ticket: Optional[int] = None  # required for CLOSE
    comment: str = ""
    magic_number: int = 0


@dataclass(frozen=True)
class OrderSendResult:
    """Deterministic outcome of one order_check/order_send attempt. status is never
    inferred -- EXECUTED requires the broker's own retcode == TRADE_RETCODE_DONE."""

    status: str  # "EXECUTED" / "REJECTED"
    reason_code: str
    symbol: str
    side: Optional[str] = None
    requested_volume: Optional[float] = None
    filled_volume: Optional[float] = None
    requested_price: Optional[float] = None
    fill_price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    ticket: Optional[int] = None
    deal_id: Optional[int] = None
    broker_retcode: Optional[int] = None
    broker_comment: Optional[str] = None
    timestamp: Optional[datetime] = None
    request: Optional[dict] = None  # the exact broker request dict, always populated


@dataclass(frozen=True)
class ExecutionReport:
    """Outer, always-returned shape from execution/executor.py::execute()."""

    command_id: str
    source: ExecutionSource
    status: str  # "EXECUTED" / "REJECTED"
    gate_reason_code: Optional[str] = None
    result: Optional[OrderSendResult] = None
    reasons: Tuple[str, ...] = field(default_factory=tuple)
