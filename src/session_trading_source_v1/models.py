"""Data models for ST_SESSION_TRADING_SOURCE_V1 / SWEEP.

`Candle` is imported unchanged (REUSE_UNCHANGED) -- a generic, strategy-neutral
immutable OHLC dataclass with no behavior attached. Every other model here is a
NEW_SOURCE_IMPLEMENTATION specific to this candidate's own, independently-derived
geometry (see the frozen candidate spec, not `ST_ASIAN_SWEEP_5R_V1`'s models).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from strategy_engine.session.candles import Candle  # REUSE_UNCHANGED -- generic, no behavior

__all__ = ["Candle", "Direction", "AsianRange", "SweepEvent", "OccurrenceState", "ResolvedOccurrence", "Occurrence"]


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class AsianRange:
    """Frozen 00:00-07:00 UTC reference range. NEW_SOURCE_IMPLEMENTATION -- not
    `strategy_engine.session.setups.ReferenceBox` (that type's default window and
    entanglement with entry_2_sweep's own stop/entry_reference fields is exactly
    what this candidate must avoid inheriting)."""
    high: float
    low: float
    high_time: datetime
    low_time: datetime

    @property
    def range(self) -> float:
        return self.high - self.low


class SweepStatus(Enum):
    VALID = "VALID"
    AMBIGUOUS_DUAL_SIDE = "AMBIGUOUS_DUAL_SIDE"


@dataclass(frozen=True)
class SweepEvent:
    status: SweepStatus
    time: datetime
    direction: Optional[Direction]
    entry_price: Optional[float]
    evidence: Dict[str, object] = field(default_factory=dict)


class OccurrenceState(Enum):
    OPEN = "OPEN"
    STOPPED_FULL_POSITION = "STOPPED_FULL_POSITION"
    PARTIAL_FILL_CONFIRMED = "PARTIAL_FILL_CONFIRMED"
    RUNNER_BE_ACTIVE = "RUNNER_BE_ACTIVE"
    RUNNER_TP2 = "RUNNER_TP2"
    RUNNER_BE_EXIT = "RUNNER_BE_EXIT"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class ResolvedOccurrence:
    state: OccurrenceState
    reason: str
    events: List[Dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class Occurrence:
    """One generated Sweep candidate plus its full source-faithful geometry and
    (if resolvable at all from the data given) its resolution -- never a WIN/LOSS
    label, since this candidate's R-unit/outcome semantics are research-only."""
    signal_time: datetime
    direction: Direction
    entry_price: float
    asian_range: AsianRange
    initial_risk: float
    stop_price: float
    leg_a_target: float
    tp2_target: float
    resolution: ResolvedOccurrence
    occurrence_classification: str  # SOURCE_DETERMINISTIC | SOURCE_RULE_DEPENDENT_UNRESOLVED
    uncertainty_reasons: List[str] = field(default_factory=list)
