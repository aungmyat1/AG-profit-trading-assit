from performance.models import ResolvedTradeSample
from session_sweep_continuation.performance_attribution import (
    INSUFFICIENT_EVIDENCE,
    attribute_by_session_pair,
    attribute_by_symbol,
    attribute_combined,
    incremental_expectancy_foundation,
)


def _sample(i, symbol="EURUSD", cycle="ASIAN_LONDON", r=1.0):
    return ResolvedTradeSample(
        source_record_id=f"rec_{i}", source_path="synthetic", strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
        strategy_version="1.0.0", symbol=symbol, cycle=cycle, resolved_at=f"2026-09-{10+i:02d}T00:00:00Z",
        gross_R=r, net_R=r, cost_status="MODELED", outcome="WIN" if r > 0 else "LOSS",
    )


def test_insufficient_evidence_below_min_sample_size():
    samples = [_sample(i) for i in range(3)]
    slice_ = attribute_combined(samples, min_sample_size=10)
    assert slice_.classification == INSUFFICIENT_EVIDENCE
    assert slice_.metrics is None


def test_evaluated_when_sample_size_meets_threshold():
    samples = [_sample(i, r=1.0 if i % 2 == 0 else -1.0) for i in range(12)]
    slice_ = attribute_combined(samples, min_sample_size=10)
    assert slice_.classification == "EVALUATED"
    assert slice_.metrics is not None
    assert slice_.metrics.sample_size == 12


def test_attribution_by_symbol_and_session_pair_groups_correctly():
    samples = [_sample(i, symbol="EURUSD" if i % 2 == 0 else "GBPUSD") for i in range(20)]
    by_symbol = attribute_by_symbol(samples, min_sample_size=5)
    keys = {s.key for s in by_symbol}
    assert keys == {"EURUSD", "GBPUSD"}
    by_session = attribute_by_session_pair(samples, min_sample_size=5)
    assert by_session[0].key == "ASIAN_LONDON"


def test_incremental_expectancy_foundation_computes_pairwise_deltas():
    s1_only = [_sample(i, r=1.0) for i in range(5)]
    s1_plus_1 = [_sample(i, r=1.5) for i in range(5)]
    s1_plus_2 = [_sample(i, r=2.0) for i in range(5)]
    s2_only = [_sample(i, r=0.5) for i in range(5)]
    s2_plus_1 = [_sample(i, r=1.0) for i in range(5)]
    s2_plus_2 = [_sample(i, r=1.2) for i in range(5)]

    out = incremental_expectancy_foundation(s1_only, s1_plus_1, s1_plus_2, s2_only, s2_plus_1, s2_plus_2)
    assert "results" in out and "comparisons" in out
    comparison_labels = {(c.base_label, c.variant_label) for c in out["comparisons"]}
    assert ("S1_ONLY", "S1_PLUS_1_CONT") in comparison_labels
    first = next(c for c in out["comparisons"] if c.base_label == "S1_ONLY")
    assert first.incremental_net_R == 2.5  # (1.5*5) - (1.0*5)
