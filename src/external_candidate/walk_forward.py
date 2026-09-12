"""Reusable deterministic VALIDATION walk-forward orchestration (mission sections
20-21).

Important distinction this module exists to enforce: this is validation
walk-forward, not optimization walk-forward. Every window evaluates the exact same
frozen candidate configuration against a different forward evidence slice --
nothing here re-fits, re-tunes, or searches parameters. If parameter
re-optimization per window is desired, that belongs to the external research
environment, entirely outside this repository (mission section 20).

No R6 threshold is referenced or invented here -- this module produces evidence
only; `validation_framework/economic_gate.py` (unmodified) decides pass/fail
against a signed contract.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Sequence, Tuple

from performance.calculator import compute_trade_metrics
from performance.models import NOT_EVALUATED, ResolvedTradeSample, TradeMetrics

from .models import DatasetPartition


@dataclass(frozen=True)
class WindowResult:
    window_id: str
    start: str
    end: str
    dataset_fingerprint: str
    metrics: TradeMetrics


@dataclass(frozen=True)
class WalkForwardEvidence:
    windows: Tuple[WindowResult, ...]
    positive_windows: int
    negative_windows: int
    median_expectancy_R: object  # float or NOT_EVALUATED
    worst_expectancy_R: object  # float or NOT_EVALUATED
    degradation_R: object  # float or NOT_EVALUATED -- best_window_expectancy - worst_window_expectancy


def evaluate_window(
    window_id: str, dataset: DatasetPartition, resolved_samples: Sequence[ResolvedTradeSample],
) -> WindowResult:
    metrics = compute_trade_metrics(resolved_samples)
    return WindowResult(
        window_id=window_id,
        start=dataset.utc_start,
        end=dataset.utc_end,
        dataset_fingerprint=dataset.dataset_fingerprint,
        metrics=metrics,
    )


def _expectancy(metrics: TradeMetrics):
    # Net expectancy is preferred (cost-inclusive); gross is used only when net was
    # never evaluated for that window -- never silently treated as equivalent.
    return metrics.net_expectancy_R if metrics.net_expectancy_R != NOT_EVALUATED else metrics.gross_expectancy_R


def aggregate_walk_forward(windows: Sequence[WindowResult]) -> WalkForwardEvidence:
    expectancies = []
    positive = 0
    negative = 0
    for w in windows:
        exp = _expectancy(w.metrics)
        if exp == NOT_EVALUATED or not isinstance(exp, (int, float)):
            continue
        expectancies.append(exp)
        if exp > 0:
            positive += 1
        elif exp < 0:
            negative += 1

    if not expectancies:
        return WalkForwardEvidence(
            windows=tuple(windows), positive_windows=0, negative_windows=0,
            median_expectancy_R=NOT_EVALUATED, worst_expectancy_R=NOT_EVALUATED, degradation_R=NOT_EVALUATED,
        )

    return WalkForwardEvidence(
        windows=tuple(windows),
        positive_windows=positive,
        negative_windows=negative,
        median_expectancy_R=statistics.median(expectancies),
        worst_expectancy_R=min(expectancies),
        degradation_R=max(expectancies) - min(expectancies),
    )
