"""Performance attribution + incremental expectancy foundation.

Reuses the existing strategy-neutral performance framework
(src/performance/calculator.py compute_trade_metrics + models.ResolvedTradeSample/
TradeMetrics) rather than inventing a parallel metrics engine -- see module docstring
in performance/calculator.py for the NOT_EVALUATED convention this inherits.

INSUFFICIENT_EVIDENCE: below `min_sample_size` (config performance_attribution.
min_sample_size, default 10) this module explicitly reports the classification
INSUFFICIENT_EVIDENCE instead of returning/implying any win-rate or profitability
number, even though compute_trade_metrics() itself will happily compute a (statistically
meaningless) metric from e.g. n=1. That refusal-to-infer is enforced here, one layer
above the raw calculator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from performance.calculator import compute_trade_metrics
from performance.models import NOT_EVALUATED, ResolvedTradeSample, TradeMetrics

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class AttributionSlice:
    dimension: str          # e.g. "setup_model", "session_pair", "symbol", "combined"
    key: str                # e.g. "S1_SWEEP_REVERSAL", "ASIAN_LONDON", "EURUSD", "COMBINED"
    sample_size: int
    classification: str     # INSUFFICIENT_EVIDENCE or "EVALUATED"
    metrics: Optional[TradeMetrics]


def _slice_metrics(samples: Sequence[ResolvedTradeSample], min_sample_size: int, dimension: str, key: str) -> AttributionSlice:
    n = len(samples)
    if n < min_sample_size:
        return AttributionSlice(dimension, key, n, INSUFFICIENT_EVIDENCE, None)
    return AttributionSlice(dimension, key, n, "EVALUATED", compute_trade_metrics(samples))


def attribute_by_setup_model(samples: Sequence[ResolvedTradeSample], setup_model_by_id: Dict[str, str], min_sample_size: int) -> List[AttributionSlice]:
    groups: Dict[str, List[ResolvedTradeSample]] = {}
    for s in samples:
        model = setup_model_by_id.get(s.source_record_id, "UNKNOWN")
        groups.setdefault(model, []).append(s)
    return [_slice_metrics(v, min_sample_size, "setup_model", k) for k, v in sorted(groups.items())]


def attribute_by_session_pair(samples: Sequence[ResolvedTradeSample], min_sample_size: int) -> List[AttributionSlice]:
    groups: Dict[str, List[ResolvedTradeSample]] = {}
    for s in samples:
        groups.setdefault(s.cycle or "UNKNOWN", []).append(s)
    return [_slice_metrics(v, min_sample_size, "session_pair", k) for k, v in sorted(groups.items())]


def attribute_by_symbol(samples: Sequence[ResolvedTradeSample], min_sample_size: int) -> List[AttributionSlice]:
    groups: Dict[str, List[ResolvedTradeSample]] = {}
    for s in samples:
        groups.setdefault(s.symbol, []).append(s)
    return [_slice_metrics(v, min_sample_size, "symbol", k) for k, v in sorted(groups.items())]


def attribute_combined(samples: Sequence[ResolvedTradeSample], min_sample_size: int) -> AttributionSlice:
    return _slice_metrics(samples, min_sample_size, "combined", "CAMPAIGN")


@dataclass(frozen=True)
class IncrementalExpectancyResult:
    label: str  # e.g. "S1_ONLY", "S1_PLUS_1_CONT", "S1_PLUS_2_CONT"
    sample_size: int
    net_R: object          # float or NOT_EVALUATED
    expectancy_R: object   # float or NOT_EVALUATED
    max_drawdown_R: object


@dataclass(frozen=True)
class IncrementalComparison:
    base_label: str
    variant_label: str
    incremental_net_R: object
    incremental_expectancy_R: object
    incremental_drawdown_effect: object


def _to_result(label: str, samples: Sequence[ResolvedTradeSample]) -> IncrementalExpectancyResult:
    if not samples:
        return IncrementalExpectancyResult(label, 0, NOT_EVALUATED, NOT_EVALUATED, NOT_EVALUATED)
    m = compute_trade_metrics(samples)
    return IncrementalExpectancyResult(label, m.sample_size, m.gross_total_R, m.gross_expectancy_R, m.max_drawdown_R)


def _diff(a, b):
    if a in (NOT_EVALUATED,) or b in (NOT_EVALUATED,):
        return NOT_EVALUATED
    return b - a


def incremental_expectancy_foundation(
    s1_only: Sequence[ResolvedTradeSample],
    s1_plus_1cont: Sequence[ResolvedTradeSample],
    s1_plus_2cont: Sequence[ResolvedTradeSample],
    s2_only: Sequence[ResolvedTradeSample],
    s2_plus_1cont: Sequence[ResolvedTradeSample],
    s2_plus_2cont: Sequence[ResolvedTradeSample],
) -> Dict[str, object]:
    """Foundation only: computes the six cumulative-sequence metrics and their pairwise
    incremental deltas. Real, non-synthetic campaign sequences from a live historical
    replay run are required to make these numerically meaningful -- see
    replay.py/tests for the synthetic fixtures this milestone actually exercises, and
    KNOWN_GAPS in the final report for what is not yet backed by real market data."""
    labels = {
        "S1_ONLY": s1_only, "S1_PLUS_1_CONT": s1_plus_1cont, "S1_PLUS_2_CONT": s1_plus_2cont,
        "S2_ONLY": s2_only, "S2_PLUS_1_CONT": s2_plus_1cont, "S2_PLUS_2_CONT": s2_plus_2cont,
    }
    results = {label: _to_result(label, samples) for label, samples in labels.items()}

    comparisons = []
    for base, variant in (
        ("S1_ONLY", "S1_PLUS_1_CONT"), ("S1_PLUS_1_CONT", "S1_PLUS_2_CONT"),
        ("S2_ONLY", "S2_PLUS_1_CONT"), ("S2_PLUS_1_CONT", "S2_PLUS_2_CONT"),
    ):
        a, b = results[base], results[variant]
        comparisons.append(IncrementalComparison(
            base_label=base, variant_label=variant,
            incremental_net_R=_diff(a.net_R, b.net_R),
            incremental_expectancy_R=_diff(a.expectancy_R, b.expectancy_R),
            incremental_drawdown_effect=_diff(a.max_drawdown_R, b.max_drawdown_R),
        ))

    return {"results": results, "comparisons": comparisons}
