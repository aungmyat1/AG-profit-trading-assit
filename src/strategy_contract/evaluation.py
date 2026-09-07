"""StrategyEvaluationRecord -- a normalized, cross-strategy research-metric summary
(AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_V1, Phase 3), inspired by Jesse's standardized
metrics without adopting Jesse's runtime.

Discovery finding: AG has no existing production module that computes
expectancy/win-rate/profit-factor/Sharpe/Sortino/max-drawdown/MAE/MFE for a strategy's
trade history (the only matches repo-wide were advisory-skill scripts under
.claude/skills/performance-analysis and .agents/skills/performance-analysis, which are
user-facing advisory tools, not production strategy evaluation infrastructure). This is
therefore new, additive code (NEW_MINIMAL_IMPLEMENTATION), not a duplicate of anything.

NON-GOALS: this module NEVER reads or replaces raw historical evidence (FX shadow
records, BTC ledger rows, Large-SMC candidate rows all remain exactly as they are,
wherever they are stored). It only ever consumes a caller-supplied sequence of
`TradeOutcomeSample` -- plain, already-resolved R-multiple/MAE/MFE numbers the caller
extracts from whatever raw evidence store it owns -- and returns a summary. It never
ranks, promotes, or grants authority to any strategy; sample_count/strategy_version/
evaluation window are always carried alongside the metrics so a low-sample research
strategy can never be silently presented as equivalent to a mature operational one.

CANONICAL FORMULAS (documented explicitly per the task's requirement -- do not add a
metric here without extending this list):

- sample_count: len(samples).
- expectancy_r: mean(r_multiple) across all samples. None if sample_count == 0.
- win_rate: count(r_multiple > 0) / sample_count. A trade with r_multiple == 0 (scratch)
  counts in the denominator but not as a win. None if sample_count == 0.
- profit_factor: sum(r_multiple for r_multiple > 0) / abs(sum(r_multiple for r_multiple < 0)).
  Zero-loss handling: if the loss sum is 0 (no losing trades), profit_factor is None
  rather than +inf or a fabricated cap -- an undefined ratio is reported as unknown, not
  invented. Empty-set handling: None if sample_count == 0.
- max_drawdown_r: largest peak-to-trough decline of the cumulative-R equity curve built
  by summing r_multiple values IN THE ORDER SUPPLIED BY THE CALLER (callers must supply
  samples in chronological order; this module does not re-sort, since "chronological" is
  evidence-store-specific). None if sample_count == 0.
- sharpe_r: mean(r_multiple) / population_stdev(r_multiple). This is a PER-TRADE
  (per-sample) ratio, deliberately NOT annualized -- AG strategies trade at very
  different, non-uniform cadences (FX: at most one signal per session; BTC: research-only
  daily report; Large-SMC: per-candidate), so no single trades-per-year assumption would
  be honest across all three. Risk-free rate is assumed 0 (R-multiples are already
  risk-normalized returns, not absolute account returns). None if sample_count < 2 or
  stdev == 0.
- sortino_r: mean(r_multiple) / downside_deviation, where downside_deviation =
  sqrt(mean(min(r_multiple, 0) ** 2)) over ALL samples (target return = 0, i.e. deviation
  below breakeven, not below the mean). Same non-annualization and risk-free-rate=0
  rules as sharpe_r. None if sample_count < 2 or downside_deviation == 0.
- mae_mean_r / mfe_mean_r: mean of the samples' mae_r / mfe_r fields, computed only over
  samples where that field is not None. None if no sample supplies that field (never
  defaults to 0).
- execution_drag_ratio: mean(realized_r) / mean(ideal_r) across samples that supply both
  `realized_r` and `ideal_r`. Provenance is explicit and separate: `ideal_r` is the
  strategy's own, un-adjusted result; `realized_r` is a broker/simulation-adjusted
  result. This ratio NEVER overwrites or replaces either series -- both remain on the
  sample if the caller wants them. None if no sample supplies both, or if mean(ideal_r) == 0.

All fields are Optional; a strategy with 0 or 1 samples predictably yields nearly all
None fields rather than a fabricated number -- this is intentional (per the task's
"None for insufficient-sample strategies" requirement) and falls out of the formulas
above, not from any separately invented minimum-sample threshold.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence


@dataclass(frozen=True)
class TradeOutcomeSample:
    """One already-resolved trade/setup outcome, as extracted by the caller from its own
    raw evidence store. This module never derives these values itself."""

    r_multiple: float
    mae_r: Optional[float] = None
    mfe_r: Optional[float] = None
    ideal_r: Optional[float] = None
    realized_r: Optional[float] = None


@dataclass(frozen=True)
class StrategyEvaluationRecord:
    strategy_id: str
    strategy_version: str
    evaluation_start: Optional[datetime]
    evaluation_end: Optional[datetime]
    sample_count: int
    expectancy_r: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    sharpe_r: Optional[float] = None
    sortino_r: Optional[float] = None
    max_drawdown_r: Optional[float] = None
    mae_mean_r: Optional[float] = None
    mfe_mean_r: Optional[float] = None
    execution_drag_ratio: Optional[float] = None


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _population_stdev(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _max_drawdown_r(r_multiples: Sequence[float]) -> Optional[float]:
    if not r_multiples:
        return None
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in r_multiples:
        cumulative += r
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def build_evaluation_record(
    strategy_id: str,
    strategy_version: str,
    samples: Sequence[TradeOutcomeSample],
    evaluation_start: Optional[datetime] = None,
    evaluation_end: Optional[datetime] = None,
) -> StrategyEvaluationRecord:
    """Pure function: samples in, one StrategyEvaluationRecord out. `samples` must be in
    chronological order for max_drawdown_r to be meaningful (see module docstring)."""
    r_multiples = [s.r_multiple for s in samples]
    n = len(r_multiples)

    expectancy_r = _mean(r_multiples)

    win_rate = (sum(1 for r in r_multiples if r > 0) / n) if n > 0 else None

    gains = sum(r for r in r_multiples if r > 0)
    losses = sum(r for r in r_multiples if r < 0)  # negative or 0
    if n == 0 or losses == 0:
        profit_factor = None
    else:
        profit_factor = gains / abs(losses)

    stdev = _population_stdev(r_multiples)
    sharpe_r = (expectancy_r / stdev) if (stdev is not None and stdev != 0) else None

    downside_sq = [min(r, 0.0) ** 2 for r in r_multiples]
    downside_dev = math.sqrt(_mean(downside_sq)) if n >= 2 else None
    sortino_r = (
        (expectancy_r / downside_dev) if (downside_dev is not None and downside_dev != 0) else None
    )

    max_drawdown_r = _max_drawdown_r(r_multiples)

    mae_values = [s.mae_r for s in samples if s.mae_r is not None]
    mfe_values = [s.mfe_r for s in samples if s.mfe_r is not None]
    mae_mean_r = _mean(mae_values)
    mfe_mean_r = _mean(mfe_values)

    drag_pairs = [(s.realized_r, s.ideal_r) for s in samples if s.realized_r is not None and s.ideal_r is not None]
    if drag_pairs:
        mean_ideal = _mean([p[1] for p in drag_pairs])
        mean_realized = _mean([p[0] for p in drag_pairs])
        execution_drag_ratio = (mean_realized / mean_ideal) if mean_ideal not in (None, 0) else None
    else:
        execution_drag_ratio = None

    return StrategyEvaluationRecord(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        sample_count=n,
        expectancy_r=expectancy_r,
        win_rate=win_rate,
        profit_factor=profit_factor,
        sharpe_r=sharpe_r,
        sortino_r=sortino_r,
        max_drawdown_r=max_drawdown_r,
        mae_mean_r=mae_mean_r,
        mfe_mean_r=mfe_mean_r,
        execution_drag_ratio=execution_drag_ratio,
    )
