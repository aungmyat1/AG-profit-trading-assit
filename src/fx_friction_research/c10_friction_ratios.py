"""Descriptive-only C10 stop-buffer-vs-spread ratios (WP3A.1 WP8). Reads
strategies/ST_LARGE_SMC_V1.yaml's C10_STRUCTURAL_INVALIDATION_V1 min_buffer_pips as a
reference constant only -- this module never derives, recommends, or writes a stop
buffer, and never touches the strategy file. Output is research evidence
(C10_FRICTION_RESEARCH_STATUS), not a strategy change.
"""
from __future__ import annotations

from typing import Dict

# strategies/ST_LARGE_SMC_V1.yaml C10_STRUCTURAL_INVALIDATION_V1 min_buffer_pips=1.5 --
# read-only reference value, not owned or settable by this module.
C10_MIN_BUFFER_PIPS = 1.5

_RATIO_KEYS = ("median_pips", "p90_pips", "p95_pips", "p99_pips")


def friction_to_stop_ratios(spread_summary: Dict[str, float], min_buffer_pips: float = C10_MIN_BUFFER_PIPS) -> Dict[str, float]:
    """Pure descriptive ratios (spread percentile / min_buffer_pips) over whichever of
    median/p90/p95/p99 keys are present in spread_summary. Never optimizes, never
    changes C10; a caller wanting a stop-buffer decision must go to the owner, not here."""
    return {
        f"{key}_to_min_buffer_ratio": spread_summary[key] / min_buffer_pips
        for key in _RATIO_KEYS
        if key in spread_summary
    }
