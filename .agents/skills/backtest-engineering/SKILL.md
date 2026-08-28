---
name: backtest-engineering
description: Design, implement, test, or review causal historical strategy backtests. Use for vectorized or event-driven backtesting, signal/order/fill alignment, transaction costs, portfolio accounting, baselines, reproducibility, unit tests, and look-ahead or survivorship-bias prevention. Research only; do not connect to brokers or place orders.
---

# Backtest Engineering

Implement the frozen strategy specification; do not redesign it to improve results during coding.

## Preconditions

- Read the strategy contract produced by `strategy-specification`.
- Read the data audit produced by `market-data-quality`.
- Apply `multi-asset-conventions` for the tested instruments.
- Stop if signal timestamps, executable prices, or P&L units are unresolved.

## Architecture choice

Use a vectorized test only when fills, holdings, and costs can be represented without path-dependent ambiguity. Use an event-driven loop for orders, partial fills, stops, limits, expiries, margin, multi-currency cash, or asynchronous instruments.

## Implementation workflow

1. Pin the runtime and dependency versions; seed stochastic code.
2. Separate immutable raw data, derived features, signals, orders, fills, positions, cash, and reports.
3. Compute features without accessing later rows.
4. Make the information lag explicit. Shift signals or schedule orders according to the strategy contract.
5. Apply participation, liquidity, leverage, and position constraints before fills.
6. Calculate gross P&L and every cost component separately.
7. Reconcile positions, cash, account-currency equity, and realized/unrealized P&L.
8. Run a simple baseline through the same engine and cost model.
9. Save configuration, data fingerprint, code version, outputs, and run timestamp.

## Minimum tests

Create automated tests for:

- no future observations entering a decision;
- exact signal-to-order-to-fill lag;
- one-hand-calculated trade and one losing trade;
- no-trade flat equity;
- fee, spread, slippage, funding/borrow, and roll signs;
- long/short P&L symmetry where appropriate;
- contract multiplier and FX conversion;
- missing bars and duplicate timestamps;
- warm-up behavior;
- position and leverage limits;
- delisting/expiry/end-of-sample behavior.

## Leakage challenges

- Perturb data after time `t`; decisions through `t` must not change.
- Truncate the dataset at several dates; earlier outputs must remain identical.
- Delay all signals by one extra period; investigate if results improve implausibly.
- Compare adjusted versus raw/executable prices where applicable.

## Required outputs

Return:

1. assumptions and architecture;
2. file/module map;
3. tests and their results;
4. trade ledger and daily/periodic equity series;
5. gross and net returns with itemized costs;
6. warnings and known simplifications;
7. exact reproduction command.

Do not call a backtest complete if accounting does not reconcile or causality tests fail.
