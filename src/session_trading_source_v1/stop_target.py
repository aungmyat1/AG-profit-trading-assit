"""Source stop/target geometry. NEW_SOURCE_IMPLEMENTATION -- independent of
`ST_ASIAN_SWEEP_5R_V1 v1.1.1`'s wick-based stop authority (never imported, never
consulted).

Frozen source contract (ST_SESSION_TRADING_SOURCE_V1_CANDIDATE_SPEC.md, P5/P6):
  A = AsianHigh - AsianLow
  LONG:  SL = Entry - 0.25*A         TP2 = Entry + 5*INITIAL_RISK = Entry + 1.25*A
  SHORT: SL = Entry + 0.25*A         TP2 = Entry - 5*INITIAL_RISK = Entry - 1.25*A
  INITIAL_RISK = abs(Entry - SL) = 0.25*A (by construction)
  Leg A (75%) target = opposite Asian boundary.
"""
from __future__ import annotations

from .models import AsianRange, Direction

STOP_RANGE_FRACTION = 0.25
TARGET_MULTIPLIER_R = 5.0


def compute_stop(direction: Direction, entry: float, asian_range: AsianRange) -> float:
    distance = STOP_RANGE_FRACTION * asian_range.range
    if direction == Direction.LONG:
        return entry - distance
    return entry + distance


def compute_initial_risk(entry: float, stop: float) -> float:
    return abs(entry - stop)


def compute_tp2(direction: Direction, entry: float, initial_risk: float) -> float:
    if direction == Direction.LONG:
        return entry + TARGET_MULTIPLIER_R * initial_risk
    return entry - TARGET_MULTIPLIER_R * initial_risk


def opposite_boundary_target(direction: Direction, asian_range: AsianRange) -> float:
    """Leg A (75%) target: the boundary OPPOSITE the one that was swept."""
    if direction == Direction.LONG:  # swept the low -> opposite is the high
        return asian_range.high
    return asian_range.low  # swept the high -> opposite is the low
