"""Enumerates EVERY qualifying sweep candidate within a completed execution window,
rather than only the first (engine.evaluate_setup's own single-occurrence contract is
UNCHANGED and still exactly what Forex/single-occurrence callers use -- see its
sweep_search_after parameter's docstring).

Remediation Gap 1: the BTC research pipeline previously used one setup_id per
symbol/day, so once that setup_id reached a terminal state (EXPIRED/NO_TRADE/BLOCKED),
SweepRetestRuntime's own terminal-state caching (by design, for restart-safety) meant a
genuinely later, independent sweep the same day was never (re-)evaluated. This module is
the fix's enumeration half: it repeatedly calls the SAME find_qualified_sweep (sweep.py)
against a shrinking candle pool -- never a second sweep-qualification rule -- to produce
the full, chronological list of sweep candidates in one window. The pipeline then gives
each candidate its OWN occurrence-scoped setup_id (see btc_sweep_research.pipeline), so
each one gets independently tracked, restart-safe, terminal-state progress through
evaluate_setup/SweepRetestRuntime.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from strategy_engine.session import Candle

from .engine import in_execution_windows
from .sweep import SweepEvent, find_qualified_sweep


def enumerate_sweep_candidates(
    m5_candles: Sequence[Candle],
    execution_windows: Sequence[tuple],
    ref_high: float,
    ref_low: float,
    required_direction: Optional[str] = None,
) -> List[SweepEvent]:
    """All qualified sweeps, chronologically, among the execution-window-filtered subset
    of m5_candles -- the exact same window filter and the exact same find_qualified_sweep
    evaluate_setup itself uses (see engine.py), just called repeatedly: each match narrows
    the remaining pool to candles strictly after that match's own candle_time before
    searching again, so the same candle is never counted as a sweep for two candidates."""
    window_candles = [c for c in m5_candles if in_execution_windows(c.time, execution_windows)]
    candidates: List[SweepEvent] = []
    pool = window_candles
    while True:
        sweep = find_qualified_sweep(pool, ref_high, ref_low, required_direction)
        if sweep is None:
            break
        candidates.append(sweep)
        pool = [c for c in pool if c.time > sweep.candle_time]
    return candidates
