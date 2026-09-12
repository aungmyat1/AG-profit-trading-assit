"""TEST_ONLY SYNTHETIC evidence -- exercises src/external_candidate/walk_forward.py
only. Confirms the SAME frozen candidate is evaluated per window (no
re-optimization) and that aggregation invents no R6 threshold.
"""
from __future__ import annotations

from performance.models import NOT_EVALUATED, ResolvedTradeSample

from _fixtures_external_candidate import make_dataset

from external_candidate.models import DatasetRole
from external_candidate.walk_forward import aggregate_walk_forward, evaluate_window


def _sample(record_id: str, gross_R: float) -> ResolvedTradeSample:
    return ResolvedTradeSample(
        source_record_id=record_id, source_path="TEST_ONLY", strategy_id="ST_SYNTHETIC_TEST_ONLY_V1",
        strategy_version="1.0.0", symbol="EURUSD", cycle=record_id, resolved_at="2026-09-01T00:00:00+00:00",
        gross_R=gross_R, net_R=gross_R, cost_status="NOT_INCLUDED", outcome="TEST_ONLY",
    )


def test_windows_aggregate_positive_and_negative_counts():
    window1 = evaluate_window(
        "W1", make_dataset(DatasetRole.VALIDATION, "W1", "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"),
        [_sample("a", 1.0), _sample("b", 1.0)],
    )
    window2 = evaluate_window(
        "W2", make_dataset(DatasetRole.VALIDATION, "W2", "2026-02-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00"),
        [_sample("c", -1.0), _sample("d", -1.0)],
    )
    evidence = aggregate_walk_forward([window1, window2])
    assert evidence.positive_windows == 1
    assert evidence.negative_windows == 1
    assert evidence.worst_expectancy_R == -1.0
    assert evidence.median_expectancy_R == 0.0


def test_empty_windows_never_evaluated():
    window_empty = evaluate_window(
        "W1", make_dataset(DatasetRole.VALIDATION, "W1", "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"), [],
    )
    evidence = aggregate_walk_forward([window_empty])
    assert evidence.median_expectancy_R == NOT_EVALUATED
    assert evidence.worst_expectancy_R == NOT_EVALUATED
    assert evidence.positive_windows == 0
    assert evidence.negative_windows == 0
