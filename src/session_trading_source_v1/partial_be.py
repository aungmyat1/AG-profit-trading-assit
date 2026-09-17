"""Partial/BE/runner resolution state machine. NEW_SOURCE_IMPLEMENTATION.

State machine (ST_SESSION_TRADING_SOURCE_V1_CANDIDATE_SPEC.md, P6/P9/P10):

    OPEN
      -> STOPPED_FULL_POSITION   (SL hit before any partial -- necessary terminal
                                   state not explicitly named in the mission's list
                                   of 6, but required for completeness; a plain,
                                   source-supported "the trade stops out" outcome,
                                   not an invented rule)
      -> PARTIAL_FILL_CONFIRMED  (Leg A / opposite-boundary target touched first)
      -> RUNNER_BE_ACTIVE        (Leg B armed at raw entry price, no cost adjustment
                                   -- BE_COST_ADJUSTMENT is SOURCE_UNADDRESSED)
      -> RUNNER_TP2              (5R runner target reached)
      -> RUNNER_BE_EXIT          (BE stop re-touched after partial)
      -> UNRESOLVED              (any same-candle collision where M15 OHLC cannot
                                   establish order -- never resolved to a guessed
                                   sequence)

Per P10: because the qualifying entry candle's own price action (pre-close) is not
a post-entry event, `subsequent_candles` passed in here must already exclude the
entry candle itself -- ENTRY_SL_SAME_BAR and ENTRY_TP_SAME_BAR are therefore
DETERMINISTIC by construction and never evaluated inside this module.
"""
from __future__ import annotations

from typing import Sequence

from .models import Candle, Direction, OccurrenceState, ResolvedOccurrence


def resolve_occurrence(
    direction: Direction, entry: float, stop: float, leg_a_target: float, tp2: float,
    subsequent_candles: Sequence[Candle],
) -> ResolvedOccurrence:
    """`subsequent_candles` = every M15 candle strictly after the entry candle,
    already bounded to the management window by the caller. Never looks beyond
    what it is given; never assumes STOP_FIRST or TARGET_FIRST."""
    is_long = direction == Direction.LONG

    if not subsequent_candles:
        return ResolvedOccurrence(state=OccurrenceState.OPEN, reason="NO_DATA_AFTER_ENTRY_BEFORE_WINDOW_END")

    partial_index = None
    for i, c in enumerate(subsequent_candles):
        sl_hit = (c.low <= stop) if is_long else (c.high >= stop)
        pt1_hit = (c.high >= leg_a_target) if is_long else (c.low <= leg_a_target)
        tp2_hit = (c.high >= tp2) if is_long else (c.low <= tp2)

        if sl_hit and (pt1_hit or tp2_hit):
            reason = "SL_TP2_SAME_BAR_INTRABAR_ORDER_UNRESOLVED" if tp2_hit else "SL_TP1_SAME_BAR_INTRABAR_ORDER_UNRESOLVED"
            return ResolvedOccurrence(
                state=OccurrenceState.UNRESOLVED, reason=reason,
                events=[{"time": str(c.time), "sl_hit": sl_hit, "pt1_hit": pt1_hit, "tp2_hit": tp2_hit}],
            )
        if sl_hit:
            return ResolvedOccurrence(
                state=OccurrenceState.STOPPED_FULL_POSITION, reason="INITIAL_STOP_HIT_BEFORE_PARTIAL",
                events=[{"time": str(c.time), "event": "SL"}],
            )
        if pt1_hit:
            partial_index = i
            break

    if partial_index is None:
        return ResolvedOccurrence(state=OccurrenceState.OPEN, reason="MANAGEMENT_WINDOW_NOT_YET_RESOLVED")

    partial_event = {"time": str(subsequent_candles[partial_index].time), "event": "PARTIAL_FILL_CONFIRMED",
                      "leg_a_target": leg_a_target}
    be_price = entry  # RAW_ENTRY_PRICE -- BE_COST_ADJUSTMENT is SOURCE_UNADDRESSED, never invented here

    for c in subsequent_candles[partial_index + 1:]:
        be_hit = (c.low <= be_price) if is_long else (c.high >= be_price)
        tp2_hit = (c.high >= tp2) if is_long else (c.low <= tp2)

        if be_hit and tp2_hit:
            return ResolvedOccurrence(
                state=OccurrenceState.UNRESOLVED, reason="BE_TP2_SAME_BAR_INTRABAR_ORDER_UNRESOLVED",
                events=[partial_event, {"time": str(c.time), "be_hit": be_hit, "tp2_hit": tp2_hit}],
            )
        if be_hit:
            return ResolvedOccurrence(
                state=OccurrenceState.RUNNER_BE_EXIT, reason="RUNNER_STOPPED_AT_BREAKEVEN",
                events=[partial_event, {"time": str(c.time), "event": "RUNNER_BE_STOP"}],
            )
        if tp2_hit:
            return ResolvedOccurrence(
                state=OccurrenceState.RUNNER_TP2, reason="RUNNER_TARGET_HIT",
                events=[partial_event, {"time": str(c.time), "event": "RUNNER_TP2"}],
            )

    return ResolvedOccurrence(state=OccurrenceState.RUNNER_BE_ACTIVE, reason="MANAGEMENT_WINDOW_NOT_YET_RESOLVED",
                               events=[partial_event])
