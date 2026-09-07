"""Focused tests for src/strategy_contract/evaluation.py (Phase 3): formula correctness,
empty-set handling, zero-loss handling, and that insufficient samples yield None rather
than fabricated numbers.
"""
from __future__ import annotations

import math

from strategy_contract.evaluation import TradeOutcomeSample, build_evaluation_record


def test_empty_sample_set_yields_all_none_metrics():
    record = build_evaluation_record("ST_X", "1.0.0", samples=[])

    assert record.sample_count == 0
    assert record.expectancy_r is None
    assert record.win_rate is None
    assert record.profit_factor is None
    assert record.sharpe_r is None
    assert record.sortino_r is None
    assert record.max_drawdown_r is None
    assert record.mae_mean_r is None
    assert record.mfe_mean_r is None
    assert record.execution_drag_ratio is None


def test_single_sample_has_expectancy_but_no_dispersion_metrics():
    """One sample: expectancy/win_rate/profit_factor/drawdown are defined, but
    sharpe/sortino need at least two samples for a meaningful dispersion estimate."""
    record = build_evaluation_record("ST_X", "1.0.0", samples=[TradeOutcomeSample(r_multiple=2.0)])

    assert record.sample_count == 1
    assert record.expectancy_r == 2.0
    assert record.win_rate == 1.0
    assert record.profit_factor is None  # zero-loss handling: no losers -> undefined, not inf
    assert record.sharpe_r is None
    assert record.sortino_r is None
    assert record.max_drawdown_r == 0.0


def test_expectancy_win_rate_profit_factor_known_values():
    samples = [
        TradeOutcomeSample(r_multiple=2.0), TradeOutcomeSample(r_multiple=2.0),
        TradeOutcomeSample(r_multiple=-1.0), TradeOutcomeSample(r_multiple=-1.0),
    ]
    record = build_evaluation_record("ST_X", "1.0.0", samples=samples)

    assert record.expectancy_r == 0.5  # (2+2-1-1)/4
    assert record.win_rate == 0.5  # 2 of 4
    assert record.profit_factor == 2.0  # 4 / 2


def test_max_drawdown_r_on_known_equity_curve():
    # cumulative: 3, 1, 4, 0, 5 -> peaks/troughs -> max decline is 4->0 = 4
    samples = [TradeOutcomeSample(r_multiple=r) for r in (3.0, -2.0, 3.0, -4.0, 5.0)]
    record = build_evaluation_record("ST_X", "1.0.0", samples=samples)

    assert record.max_drawdown_r == 4.0


def test_sharpe_and_sortino_known_values():
    samples = [TradeOutcomeSample(r_multiple=r) for r in (1.0, -1.0, 1.0, -1.0)]
    record = build_evaluation_record("ST_X", "1.0.0", samples=samples)

    assert record.expectancy_r == 0.0
    # population stdev of [1,-1,1,-1] is 1.0 -> sharpe = 0/1 = 0.0 (defined, not None)
    assert record.sharpe_r == 0.0
    # downside deviation: mean(min(r,0)^2) over all 4 = (0+1+0+1)/4=0.5 -> sqrt=~0.707
    assert record.sortino_r == 0.0


def test_mae_mfe_only_averaged_over_samples_that_supply_them():
    samples = [
        TradeOutcomeSample(r_multiple=1.0, mae_r=-0.5, mfe_r=1.5),
        TradeOutcomeSample(r_multiple=1.0),  # no mae/mfe supplied
    ]
    record = build_evaluation_record("ST_X", "1.0.0", samples=samples)

    assert record.mae_mean_r == -0.5
    assert record.mfe_mean_r == 1.5


def test_execution_drag_ratio_provenance_and_none_when_missing():
    no_drag_samples = [TradeOutcomeSample(r_multiple=1.0)]
    assert build_evaluation_record("ST_X", "1.0.0", no_drag_samples).execution_drag_ratio is None

    drag_samples = [
        TradeOutcomeSample(r_multiple=1.0, ideal_r=2.0, realized_r=1.0),
        TradeOutcomeSample(r_multiple=1.0, ideal_r=2.0, realized_r=1.0),
    ]
    record = build_evaluation_record("ST_X", "1.0.0", drag_samples)
    assert record.execution_drag_ratio == 0.5  # realized 1.0 / ideal 2.0
