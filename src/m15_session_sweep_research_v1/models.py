"""Data models for ST_M15_SESSION_SWEEP_RESEARCH_V1.

`Candle` is imported unchanged (REUSE_UNCHANGED) -- a generic, strategy-neutral
immutable OHLC dataclass with no behavior attached, shared project-wide.

`Direction`, `AsianRange`, `SweepStatus`, `SweepEvent`, `OccurrenceState`,
`ResolvedOccurrence` are FORK_COPY_FROZEN, byte-identical to
session_trading_source_v1/models.py (ST_SESSION_TRADING_SOURCE_V1 v0.1.0,
research_parent) -- copied, not imported, so this lineage cannot drift if the
parent package changes.

`Occurrence` is a NEW_RESEARCH_COMPONENT adaptation: it drops the parent's
`occurrence_classification`/`uncertainty_reasons` fields, which existed only to
support the parent's source-replication comparison (SOURCE_DETERMINISTIC vs.
SOURCE_RULE_DEPENDENT_UNRESOLVED against the sealed benchmark). This lineage
makes no source-replication claim, so that distinction does not apply here --
see SEMANTIC_REUSE_MANIFEST.md for the full accounting.
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
    """Frozen 00:00-07:00 UTC reference range."""
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
    """One generated Sweep candidate plus its full deterministic geometry and
    (if resolvable at all from the data given) its resolution -- never a
    WIN/LOSS label; economic interpretation is out of scope for ES-R0."""
    signal_time: datetime
    direction: Direction
    entry_price: float
    asian_range: AsianRange
    initial_risk: float
    stop_price: float
    leg_a_target: float
    tp2_target: float
    resolution: ResolvedOccurrence
