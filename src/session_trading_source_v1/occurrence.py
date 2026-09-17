"""Occurrence generation pipeline. NEW_SOURCE_IMPLEMENTATION.

Ties together asian_range / sweep / stop_target / partial_be, and classifies
every generated occurrence as SOURCE_DETERMINISTIC or
SOURCE_RULE_DEPENDENT_UNRESOLVED per P9 -- never suppresses a structurally valid
signal because a source rule is missing; never invents a max-entries cap.
"""
from __future__ import annotations

from datetime import time
from typing import List, Sequence

from . import uncertainty
from .asian_range import build_asian_range
from .models import Candle, Occurrence
from .partial_be import resolve_occurrence
from .stop_target import compute_initial_risk, compute_stop, compute_tp2, opposite_boundary_target
from .sweep import detect_sweeps
from .models import SweepStatus

MANAGEMENT_END_UTC = time(uncertainty._MANAGEMENT_END_HOUR, 0)  # STRONGLY_SUPPORTED, ES-S1R P7/P11
_DISPUTED_CUTOFF_START_UTC = time(uncertainty._DISPUTED_ENTRY_CUTOFF_EARLIEST_HOUR, 0)


def _classify_entry_cutoff(signal_time) -> List[str]:
    """Entry-cutoff uncertainty per P9's own worked example: a signal clearly
    before the earliest disputed candidate cutoff is clean; a signal in the
    disputed zone between the earliest candidate cutoff and the STRONGLY_SUPPORTED
    management-end boundary is SOURCE_RULE_DEPENDENT_UNRESOLVED."""
    t = signal_time.time()
    if t >= _DISPUTED_CUTOFF_START_UTC:
        return ["NEW_ENTRY_CUTOFF_AMBIGUOUS"]
    return []


def _classify_tight_range(asian_range_pips: float) -> List[str]:
    """TIGHT_RANGE_FILTER_THRESHOLD is SOURCE_MISSING. Neither disputed candidate
    value found in source evidence is accepted as the real threshold (both were
    OUTCOME_DERIVED_INTERPRETATION, excluded in ES-S1R). A range at or above the
    HIGHER disputed candidate (15 pips) would not be filtered under either value
    ever seen in the source, so it is left clean; a range below it is flagged as
    uncertain, never excluded/suppressed."""
    if asian_range_pips < uncertainty._DISPUTED_TIGHT_RANGE_HIGHEST_CANDIDATE_PIPS:
        return ["TIGHT_RANGE_FILTER_THRESHOLD_MISSING"]
    return []


def generate_occurrences(
    asian_session_candles: Sequence[Candle], post_session_candles: Sequence[Candle], pip_size: float,
) -> List[Occurrence]:
    """`asian_session_candles`: the day's 00:00-07:00 UTC M15 candles.
    `post_session_candles`: every M15 candle from 07:00 UTC through the
    STRONGLY_SUPPORTED management-end boundary (22:00 UTC) for the same day,
    ascending, already closed. `pip_size`: the symbol's own pip size (e.g. 0.0001
    for EURUSD), used only to express the Asian range in pips for the tight-range
    uncertainty check -- never used to alter stop/target geometry. Returns one
    Occurrence per qualifying sweep event
    (VALID only -- AMBIGUOUS_DUAL_SIDE events produce no occurrence, matching the
    verified entry semantic). Multiple occurrences per day are preserved
    deliberately -- MAX_ENTRIES_PER_SESSION/DAY is SOURCE_MISSING and must not be
    silently enforced."""
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

        range_pips = asian_range.range / pip_size
        reasons = _classify_entry_cutoff(event.time) + _classify_tight_range(range_pips)
        classification = "SOURCE_RULE_DEPENDENT_UNRESOLVED" if reasons else "SOURCE_DETERMINISTIC"

        occurrences.append(Occurrence(
            signal_time=event.time, direction=event.direction, entry_price=entry, asian_range=asian_range,
            initial_risk=initial_risk, stop_price=stop, leg_a_target=leg_a_target, tp2_target=tp2,
            resolution=resolution, occurrence_classification=classification, uncertainty_reasons=reasons,
        ))

    return occurrences
