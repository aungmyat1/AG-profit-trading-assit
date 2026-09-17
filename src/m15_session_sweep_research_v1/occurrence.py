"""Occurrence generation pipeline. NEW_RESEARCH_COMPONENT.

Ties together asian_range / sweep / stop_target / partial_be. Generates EVERY
structurally valid Sweep occurrence with NO eligibility filtering of any kind
-- no range/wick/cutoff/max-entries gate. This is a deliberate baseline
decision (AG_GOVERNANCE_CHOICE, ES-R0 P4): eligibility hypotheses belong to a
future, separately preregistered ES-R1+ mission, never silently reintroduced
here as a "default."
"""
from __future__ import annotations

from datetime import time
from typing import List, Sequence

from .asian_range import build_asian_range
from .models import Candle, Occurrence, SweepStatus
from .partial_be import resolve_occurrence
from .stop_target import compute_initial_risk, compute_stop, compute_tp2, opposite_boundary_target
from .sweep import detect_sweeps

MANAGEMENT_END_UTC = time(22, 0)  # AG_GOVERNANCE_CHOICE, matches provenance parent 1's own carried-forward
                                    # boundary (ES-S1R P7/P11, STRONGLY_SUPPORTED) -- not re-derived here


def generate_occurrences(
    asian_session_candles: Sequence[Candle], post_session_candles: Sequence[Candle],
) -> List[Occurrence]:
    """`asian_session_candles`: the day's 00:00-07:00 UTC M15 candles.
    `post_session_candles`: every M15 candle from 07:00 UTC through the
    management-end boundary for the same day, ascending, already closed.
    Returns one Occurrence per qualifying sweep event (VALID only --
    AMBIGUOUS_DUAL_SIDE events produce no occurrence). Multiple occurrences per
    day are preserved deliberately -- no max-entries cap exists in this
    baseline."""
    asian_range = build_asian_range(asian_session_candles)
    if asian_range is None:
        return []

    management_window = [c for c in post_session_candles if c.time.time() < MANAGEMENT_END_UTC]
    sweep_events = detect_sweeps(asian_range, management_window)

    occurrences: List[Occurrence] = []
    for event in sweep_events:
        if event.status != SweepStatus.VALID:
            continue

        entry = event.entry_price
        stop = compute_stop(event.direction, entry, asian_range)
        initial_risk = compute_initial_risk(entry, stop)
        leg_a_target = opposite_boundary_target(event.direction, asian_range)
        tp2 = compute_tp2(event.direction, entry, initial_risk)

        subsequent = [c for c in management_window if c.time > event.time]
        resolution = resolve_occurrence(event.direction, entry, stop, leg_a_target, tp2, subsequent)

        occurrences.append(Occurrence(
            signal_time=event.time, direction=event.direction, entry_price=entry, asian_range=asian_range,
            initial_risk=initial_risk, stop_price=stop, leg_a_target=leg_a_target, tp2_target=tp2,
            resolution=resolution,
        ))

    return occurrences
