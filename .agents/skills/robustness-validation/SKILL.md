---
name: robustness-validation
description: Challenge a trading backtest with out-of-sample, walk-forward, parameter-sensitivity, regime, cost, delay, bootstrap, multiple-testing, and leakage checks. Use after a backtest appears promising or when comparing variants. Favor falsification over optimization and never tune on the final test set.
---

# Robustness Validation

## Token minimum usage policy (owner rule, applies to every task)
- Do only what the task asks; no extra features, refactors or docs.
- No polling, scheduled check-ins or PR subscriptions unless explicitly asked.
- Don't ask questions mid-task: make conservative choices, record them, continue.
- Read only files needed; prefer grep/targeted reads over full-file or repo-wide dumps.
- Don't re-run unchanged failing steps; report the blocker once and stop.
- Batch tool calls; avoid repeated verification of the same fact.
- Reports: concise — status, key results, blockers, next step. No restating the prompt,
  no long learning sections unless asked.
- Stop immediately when the task is done.

Assume an attractive backtest may be caused by leakage, overfitting, costs, regime luck, or data errors until challenged.

## Data partition policy

- Keep chronological train, validation, and untouched final-test periods.
- Use expanding or rolling walk-forward evaluation for time-varying refits.
- Fit scalers, thresholds, feature selection, and models only on each training window.
- Do not inspect the final test repeatedly.

## Validation battery

1. **Causality:** rerun truncation and future-perturbation tests.
2. **Baselines:** compare with buy-and-hold/cash and simple rules through the same engine.
3. **Parameter surface:** inspect neighboring values, not only the optimum. Prefer broad stability to a sharp peak.
4. **Time stability:** report by year and by declared market regime without selecting regimes after seeing results.
5. **Cross-section/venue stability:** test independent instruments or venues where the hypothesis should transfer.
6. **Cost stress:** multiply realistic fees, spread, slippage, funding, borrow, and roll costs.
7. **Execution stress:** delay fills and worsen prices without using future liquidity information.
8. **Subperiod and leave-one-out:** identify dependence on a few dates, trades, or symbols.
9. **Resampling:** bootstrap trades or return blocks while preserving dependence as reasonably as possible.
10. **Multiple testing:** disclose the number of tried ideas/parameters and use a correction or deflated metric when warranted.
11. **Data variants:** compare vendors, adjustments, roll methods, and bar boundaries where feasible.

## Failure interpretation

A failed robustness test is a research result. Do not repair it by silently adding filters. Any new rule creates a new strategy version that must restart the validation process.

## Output

Create a validation matrix with:

- test name and rationale;
- frozen inputs and changed variable;
- expected failure mode;
- result and uncertainty;
- pass/warn/fail threshold declared before execution;
- conclusion.

End with one classification:

- **Rejected** — evidence contradicts or cannot support the hypothesis;
- **Needs more evidence** — unresolved bias or insufficient independent data;
- **Research candidate** — survives stated tests but has no guarantee of future performance.

Never label a strategy safe, proven, or ready for live trading based only on historical validation.
