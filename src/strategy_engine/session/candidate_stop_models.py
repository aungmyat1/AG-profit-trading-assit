"""RESEARCH_CANDIDATE stop-loss models for ST_ASIAN_SWEEP_5R_V1.

Status: RESEARCH_CANDIDATE, authority=NONE. Nothing in this module is wired into the
live signal path (`strategy_engine.engine.evaluate` / `session.setups.entry_2_sweep`
remain untouched -- v1.1.1's frozen stop_reference = sweep-candle wick behavior is
preserved exactly as-is). This module exists only to let candidate 1.1.2-RC1 stop
geometry be computed and tested in isolation, per
AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION.

MODEL_A = SESSION_RANGE_25: the strategy's already-declared, already-parsed, but never
consumed contract (`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`'s
`risk_and_money_management.stop_loss_range_pct: 0.25`, loaded into
`StrategyConfig.risk.stop_loss_range_pct` by `strategy_engine/loader.py` but never read
by any calculation site -- confirmed by repo-wide grep, 2026-09-06):

    SL distance = reference_session_range * stop_loss_range_pct
    reference_session_range = box_high - box_low (the same reference box entry_2_sweep
    already computes and passes to TradeSignal.box_high/box_low)

No ATR, spread multiplier, minimum-stop tuning, maximum-stop tuning, or hybrid
structural logic is added here -- see the governing prompt's Model A discipline.
"""
from __future__ import annotations

from dataclasses import dataclass

from .setups import Direction

CANDIDATE_MODEL_ID = "SESSION_RANGE_25"
CANDIDATE_VERSION = "1.1.2-RC1"


class CandidateStopModelError(ValueError):
    """Fail-closed: raised instead of returning a guessed/degraded stop distance."""


@dataclass(frozen=True)
class CandidateStopResult:
    model: str
    candidate_version: str
    direction: Direction
    entry: float
    box_high: float
    box_low: float
    stop_loss_range_pct: float
    reference_session_range: float
    stop_distance: float
    stop_loss: float


def session_range_25_stop(
    direction: Direction,
    entry: float,
    box_high: float,
    box_low: float,
    stop_loss_range_pct: float,
) -> CandidateStopResult:
    """MODEL_A: SL distance = (box_high - box_low) * stop_loss_range_pct.

    Fails closed (raises CandidateStopModelError) rather than guessing on:
      - non-finite / non-positive stop_loss_range_pct
      - box_high <= box_low (non-positive or degenerate session range)
      - a resulting non-positive stop distance
      - an unrecognized direction
    """
    if stop_loss_range_pct is None or not (stop_loss_range_pct == stop_loss_range_pct):  # NaN check
        raise CandidateStopModelError("stop_loss_range_pct is missing or NaN")
    if stop_loss_range_pct <= 0:
        raise CandidateStopModelError(f"stop_loss_range_pct must be > 0, got {stop_loss_range_pct!r}")

    reference_session_range = box_high - box_low
    if reference_session_range <= 0:
        raise CandidateStopModelError(
            f"non-positive reference session range: box_high={box_high!r} box_low={box_low!r}"
        )

    stop_distance = reference_session_range * stop_loss_range_pct
    if stop_distance <= 0:
        raise CandidateStopModelError(f"computed non-positive stop distance: {stop_distance!r}")

    if direction == Direction.LONG:
        stop_loss = entry - stop_distance
    elif direction == Direction.SHORT:
        stop_loss = entry + stop_distance
    else:
        raise CandidateStopModelError(f"unrecognized direction: {direction!r}")

    return CandidateStopResult(
        model=CANDIDATE_MODEL_ID,
        candidate_version=CANDIDATE_VERSION,
        direction=direction,
        entry=entry,
        box_high=box_high,
        box_low=box_low,
        stop_loss_range_pct=stop_loss_range_pct,
        reference_session_range=reference_session_range,
        stop_distance=stop_distance,
        stop_loss=stop_loss,
    )
