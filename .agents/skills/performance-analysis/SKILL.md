---
name: performance-analysis
description: Evaluate and communicate historical strategy performance using returns, volatility, drawdown, Sharpe/Sortino/Calmar, hit rate, payoff, turnover, exposure, capacity, attribution, benchmarks, and uncertainty. Use on completed backtests after costs. Do not present metrics as guaranteed future returns.
---

# Performance Analysis

Analyze the net, out-of-sample result first. Show gross results only to explain cost drag.

## Inputs

Require:

- periodic account-currency equity or returns;
- trade/fill ledger;
- benchmark under compatible dates and currency;
- declared periods per year and risk-free-rate convention;
- train/validation/test labels;
- exposure, turnover, and itemized costs.

## Workflow

1. Verify equity continuity and reconcile it with the ledger/accounting.
2. Label in-sample and out-of-sample periods visibly.
3. Calculate cumulative and annualized return, annualized volatility, maximum drawdown and duration.
4. Calculate risk-adjusted metrics with formulas and assumptions. Avoid annualizing very short samples without a warning.
5. Report hit rate together with average win, average loss, payoff ratio, trade count, and concentration.
6. Report gross/net exposure, leverage, turnover, holding time, and time in market.
7. Attribute P&L by instrument, side, period, regime, and cost component when available.
8. Compare with benchmarks using the same dates and account currency.
9. Quantify uncertainty with confidence intervals or resampling when the sample permits.
10. Highlight the worst periods and failed validation tests, not only headline metrics.

## Metric cautions

- Sharpe is sensitive to serial correlation, non-normal tails, annualization, and sample length.
- Maximum drawdown is one realized path, not a bound on future loss.
- Hit rate alone says little without payoff and costs.
- A high return from concentrated exposure is not diversified alpha.
- Overlapping positions or bars reduce the effective sample size.

## Output

Return:

1. executive summary with scope and test period;
2. metric table with formulas/assumptions;
3. benchmark comparison;
4. cost, exposure, and turnover analysis;
5. drawdown and concentration analysis;
6. uncertainty and robustness summary;
7. limitations and next falsification test.

For a simple periodic-return CSV, run `scripts/metrics.py` to make calculations reproducible, then supplement its output with exposure, ledger, benchmark, and uncertainty analysis.
