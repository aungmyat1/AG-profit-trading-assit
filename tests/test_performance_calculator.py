"""Tests for performance.calculator: gross/net separation, profit-factor edge cases,
drawdown, zero-denominator funnel ratios, and the FX 13-record regression baseline.
"""
from __future__ import annotations

import os

import pytest

from performance.adapters.fx_adapter import load_fx_resolved_samples
from performance.calculator import compute_funnel_counts, compute_trade_metrics, funnel_ratio
from performance.models import NOT_EVALUATED, ResolvedTradeSample


def _sample(gross_R, net_R=None, source_record_id="s", resolved_at=None, cost_status="NOT_INCLUDED"):
    return ResolvedTradeSample(
        source_record_id=source_record_id, source_path="fixture", strategy_id="X", strategy_version="1.0.0",
        symbol="EURUSD", cycle="ASIAN_LONDON", resolved_at=resolved_at, gross_R=gross_R, net_R=net_R,
        cost_status=cost_status, outcome="RESOLVED",
    )


def test_empty_sample_reports_not_evaluated_everywhere_except_counts():
    metrics = compute_trade_metrics([])
    assert metrics.sample_size == 0
    assert metrics.gross_total_R == 0.0
    assert metrics.gross_expectancy_R == NOT_EVALUATED
    assert metrics.net_expectancy_R == NOT_EVALUATED
    assert metrics.profit_factor == NOT_EVALUATED


def test_net_expectancy_is_not_evaluated_unless_every_sample_has_net_r():
    samples = [_sample(-1.0, net_R=-1.2), _sample(2.0, net_R=None)]
    metrics = compute_trade_metrics(samples)
    assert metrics.gross_expectancy_R == 0.5
    assert metrics.net_expectancy_R == NOT_EVALUATED  # must never fall back to gross


def test_net_expectancy_computed_when_all_samples_have_net_r():
    samples = [_sample(-1.0, net_R=-1.2), _sample(2.0, net_R=1.7)]
    metrics = compute_trade_metrics(samples)
    assert metrics.net_total_R == pytest.approx(0.5)
    assert metrics.net_expectancy_R == pytest.approx(0.25)


def test_profit_factor_undefined_no_losses():
    metrics = compute_trade_metrics([_sample(1.0), _sample(2.0)])
    assert metrics.profit_factor == "UNDEFINED_NO_LOSSES"


def test_profit_factor_undefined_no_wins():
    metrics = compute_trade_metrics([_sample(-1.0), _sample(-2.0)])
    assert metrics.profit_factor == "UNDEFINED_NO_WINS"


def test_profit_factor_normal_case():
    metrics = compute_trade_metrics([_sample(2.0), _sample(-1.0)])
    assert metrics.profit_factor == pytest.approx(2.0)


def test_max_drawdown_and_consecutive_losses_are_deterministic():
    samples = [
        _sample(1.0, source_record_id="a", resolved_at="2026-01-01T00:00:00Z"),
        _sample(-1.0, source_record_id="b", resolved_at="2026-01-02T00:00:00Z"),
        _sample(-1.0, source_record_id="c", resolved_at="2026-01-03T00:00:00Z"),
        _sample(0.5, source_record_id="d", resolved_at="2026-01-04T00:00:00Z"),
    ]
    metrics = compute_trade_metrics(samples)
    # cum sequence: 1.0, 0.0, -1.0, -0.5 -- peak 1.0 at t0, trough -1.0 at t2 -> DD 2.0
    assert metrics.max_drawdown_R == pytest.approx(2.0)
    assert metrics.max_consecutive_losses == 2


def test_drawdown_baseline_starts_at_zero_not_at_first_sample():
    """AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1 Phase 1 item 1: a lone first
    resolved trade that is a loss must itself register as drawdown -- the equity curve's
    peak starts at the zero baseline that exists before any trade, not at whatever the
    first sample's own cumulative value happens to be."""
    metrics = compute_trade_metrics([_sample(-1.0, resolved_at="2026-01-01T00:00:00Z")])
    assert metrics.max_drawdown_R == pytest.approx(1.0)


def test_drawdown_baseline_zero_does_not_affect_a_winning_first_trade():
    """A first trade that's a win must not retroactively create drawdown either --
    zero-baseline peak only matters when equity ever dips below its starting point."""
    metrics = compute_trade_metrics([_sample(2.0, resolved_at="2026-01-01T00:00:00Z")])
    assert metrics.max_drawdown_R == pytest.approx(0.0)


def test_missing_timestamps_sort_last_by_source_record_id():
    """AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1 Phase 1 item 3: timestamped
    records first (chronological), missing-timestamp records last, ordered by their
    immutable source_record_id -- never silently dropped, never sorted as if earliest."""
    from performance.calculator import _ordered

    samples = [
        _sample(1.0, source_record_id="missing_b", resolved_at=None),
        _sample(1.0, source_record_id="timed_2", resolved_at="2026-01-02T00:00:00Z"),
        _sample(1.0, source_record_id="missing_a", resolved_at=None),
        _sample(1.0, source_record_id="timed_1", resolved_at="2026-01-01T00:00:00Z"),
    ]
    ordered_ids = [s.source_record_id for s in _ordered(samples)]
    assert ordered_ids == ["timed_1", "timed_2", "missing_a", "missing_b"]


def test_ordering_is_stable_and_independent_of_input_order():
    ordered_input = [
        _sample(1.0, source_record_id="a", resolved_at="2026-01-01T00:00:00Z"),
        _sample(-2.0, source_record_id="b", resolved_at="2026-01-02T00:00:00Z"),
    ]
    reversed_input = list(reversed(ordered_input))
    m1 = compute_trade_metrics(ordered_input)
    m2 = compute_trade_metrics(reversed_input)
    assert m1.max_drawdown_R == m2.max_drawdown_R


def test_funnel_ratio_zero_denominator_is_not_evaluated():
    assert funnel_ratio(0, 0) == NOT_EVALUATED


def test_funnel_ratio_normal_case():
    assert funnel_ratio(3, 12) == pytest.approx(0.25)


def test_compute_funnel_counts_never_reports_zero_percent_for_missing_denominator():
    counts = compute_funnel_counts([])
    assert counts.total_rows == 0
    assert funnel_ratio(counts.m_engaged, counts.e_qualified) == NOT_EVALUATED


REAL_CSV = r"D:\EURUSD_M5_202504211715_202607310000.csv"


@pytest.mark.skipif(
    not os.path.exists("artifacts/outcome_resolution/records"),
    reason="FX outcome-resolution evidence directory not present",
)
def test_fx_adapter_reproduces_the_13_record_negative_baseline():
    """This must FAIL loudly if the calculator's math disagrees with the already-known,
    already-verified aggregate (artifacts/outcome_resolution/AG_FORWARD_SHADOW_
    PERFORMANCE_SNAPSHOT_V1.json: 13 resolved, 0 wins, 13 losses, gross_total_R=-13.0,
    cost_status NOT_INCLUDED on every record) -- never adjusted to match a different
    calculator result."""
    samples = load_fx_resolved_samples(".")
    assert len(samples) == 13
    metrics = compute_trade_metrics(samples)
    assert metrics.sample_size == 13
    assert metrics.wins == 0
    assert metrics.losses == 13
    assert metrics.gross_total_R == pytest.approx(-13.0)
    assert metrics.gross_expectancy_R == pytest.approx(-1.0)
    assert metrics.net_expectancy_R == NOT_EVALUATED  # cost_status NOT_INCLUDED on all 13
    assert metrics.cost_status == "NOT_INCLUDED"
