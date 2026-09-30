---
name: risk-position-sizing
description: Design and review simulated portfolio sizing and risk controls for backtests, including fixed fractional risk, volatility targeting, risk budgets, exposure, concentration, leverage, drawdown, liquidity, correlation, and stress limits. Use for research portfolios only, not personalized advice or live order sizing.
---

# Risk and Position Sizing

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

Sizing transforms signals into portfolio risk. Treat it as a separate, testable layer.

**Research/backtest scope only.** For a live/production sizing question (given account
equity, a proposed entry/SL, and broker symbol metadata, what is the deterministic
position size), use `trade_management.evaluate_sizing()` /
`evaluate_trade_management()` instead (`docs/specs/TRADE_MANAGEMENT_V1_SPEC.md`) — that path is
tick_size/tick_value-based and broker-normalized, not a portfolio backtest sizing model.

## Inputs

Require:

- account/base currency and simulated capital;
- instrument P&L conventions;
- signal scale and rebalance timing;
- volatility/covariance estimator and its observation lag;
- liquidity measure and participation limit;
- gross, net, per-name, sector, asset-class, and leverage limits;
- cost and margin assumptions.

## Workflow

1. Start with a transparent baseline such as equal notional or equal risk.
2. If volatility targeting is used, define lookback, estimator, floor, cap, annualization, and lag.
3. Convert target risk to units using the correct multiplier and currency conversion.
4. Round to valid lot/contract sizes, then recompute actual risk.
5. Apply constraints in a documented order.
6. Model cash, collateral, financing, and margin conservatively.
7. Cap size by realistic liquidity/participation.
8. Stress volatility spikes, correlation convergence, gaps, funding changes, and reduced liquidity.
9. Attribute performance changes to signal quality versus sizing.

## Guardrails

- Avoid martingale, loss-doubling, or uncapped averaging-down rules.
- Do not infer safety from low historical volatility alone.
- Use lagged, point-in-time estimates.
- Treat drawdown stops as strategy changes requiring separate validation.
- Never hide leverage created by derivatives or cross-currency exposure.

## Output

Produce:

- sizing equation and all units;
- estimator definitions and lags;
- ordered constraint pipeline;
- before/after exposures and risk contributions;
- turnover and cost impact;
- stress scenarios;
- cases where no position should be taken due to missing or unreliable inputs.
