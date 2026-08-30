"""State machine shapes for ST_SESSION_SWEEP_RETEST_V1.

Deliberately a flat, explicit state enum (strings, not a python Enum) matching the
project's existing convention of string-typed status/reason_code fields on frozen
dataclasses (see strategy_engine.session.setups.SetupDecision, execution.models.*).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

STATE_WAITING_REFERENCE = "WAITING_REFERENCE"
STATE_WAITING_WINDOW = "WAITING_WINDOW"
STATE_WAITING_SWEEP = "WAITING_SWEEP"
STATE_SWEEP_DETECTED = "SWEEP_DETECTED"
STATE_WAITING_MSS = "WAITING_MSS"
STATE_MSS_CONFIRMED = "MSS_CONFIRMED"
STATE_WAITING_RETEST = "WAITING_RETEST"
STATE_ENTRY_READY = "ENTRY_READY"
STATE_ORDER_SUBMITTED = "ORDER_SUBMITTED"
STATE_POSITION_OPEN = "POSITION_OPEN"
STATE_TP1_HIT = "TP1_HIT"
STATE_RUNNER_ACTIVE = "RUNNER_ACTIVE"

# Terminal states.
STATE_TP2_HIT = "TP2_HIT"
STATE_STOPPED = "STOPPED"
STATE_SETUP_EXPIRED = "SETUP_EXPIRED"
STATE_SESSION_EXPIRED = "SESSION_EXPIRED"
STATE_NO_TRADE_DIRECTION = "NO_TRADE_DIRECTION"
STATE_NO_TRADE_TARGET_GEOMETRY = "NO_TRADE_TARGET_GEOMETRY"
STATE_BLOCKED_DAILY_LOSS = "BLOCKED_DAILY_LOSS"
STATE_BLOCKED_OPEN_POSITION = "BLOCKED_OPEN_POSITION"

TERMINAL_STATES = frozenset({
    STATE_TP2_HIT, STATE_STOPPED, STATE_SETUP_EXPIRED, STATE_SESSION_EXPIRED,
    STATE_NO_TRADE_DIRECTION, STATE_NO_TRADE_TARGET_GEOMETRY,
    STATE_BLOCKED_DAILY_LOSS, STATE_BLOCKED_OPEN_POSITION,
})


@dataclass(frozen=True)
class SetupState:
    """One evaluation of a setup_id's current position in the state machine.
    Immutable -- a new SetupState is produced on every re-evaluation, never mutated in
    place, so persistence (state_store.py) is a plain snapshot write."""

    setup_id: str
    strategy_id: str
    symbol: str
    state: str
    reason_code: str
    evaluated_at: Optional[datetime] = None

    direction: Optional[str] = None  # "LONG" / "SHORT"
    asian_high: Optional[float] = None
    asian_low: Optional[float] = None
    asian_mid: Optional[float] = None

    sweep_level: Optional[float] = None
    sweep_extreme: Optional[float] = None
    sweep_time: Optional[datetime] = None

    broken_swing_price: Optional[float] = None
    mss_time: Optional[datetime] = None

    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    risk_distance: Optional[float] = None
    tp2_r_multiple: Optional[float] = None

    volume: Optional[float] = None
    risk_amount: Optional[float] = None

    evidence: dict = field(default_factory=dict)
