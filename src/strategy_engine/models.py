"""Typed shapes for a loaded strategy config and for the engine's output signal.

Deliberately thin: fields mirror strategies/*.yaml structurally (see loader.py) rather
than reinterpreting it. Values the session-box code treats as fixed/validated contracts
(e.g. the ER_ONLY_V2 0.40 classifier threshold) are NOT duplicated here as configurable
knobs -- see strategy_engine/session/classifier.py for why.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Sequence


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start_time_gmt: str
    end_time_gmt: str


@dataclass(frozen=True)
class SessionPair:
    pair_id: str
    reference_session: SessionWindow
    trade_session: SessionWindow
    max_entries_per_session: int


@dataclass(frozen=True)
class RiskConfig:
    risk_mode: str
    stop_loss_mode: str
    stop_loss_range_pct: float
    max_spread_allowed_pips: float
    slippage_limit_points: int


@dataclass(frozen=True)
class TargetLeg:
    leg_id: int
    volume_pct: float
    target_type: str
    action_on_fill: Optional[str] = None
    fixed_r_multiple: Optional[float] = None
    trailing_rule: Optional[str] = None


@dataclass(frozen=True)
class StrategyConfig:
    strategy_id: str
    strategy_name: str
    strategy_family: str
    version: str
    status: str
    instruments: Sequence[str]
    timeframe: str
    magic_number: int
    session_pairs: Sequence[SessionPair]
    risk: RiskConfig
    entry_order_type: str
    total_target_r: float
    legs: Sequence[TargetLeg]
    max_range_pips_eurusd: float
    time_invalidation: str
    structural_invalidation: str
    source_path: str


@dataclass(frozen=True)
class TradeSignal:
    """Engine output. This is a candidate signal, not execution authority -- see
    strategy_engine/session/setups.py's SetupDecision.contract_status, which this wraps."""
    signal_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    pair_id: str
    reference_session: str
    session_date: date
    box_high: float
    box_low: float
    box_mid: float
    regime: str
    setup: str
    status: str  # "SIGNAL" or "NO_TRADE"
    reason_code: str
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_distance: Optional[float] = None
    # Additive, backward-compatible (default None): the CLOSED candle whose completion
    # produced this decision (strategy_engine.session.setups.SetupDecision.signal_timestamp,
    # verbatim -- entry_1_trend has none, box-based; entry_2_sweep/entry_3_range set it to
    # the qualifying candle's own open time). Callers needing a deterministic "ready at"
    # ordering key (not wall-clock evaluation/polling time) should use this field, never
    # invent one from when evaluate() happened to be called.
    signal_timestamp: Optional[datetime] = None
