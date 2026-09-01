# ST_LARGE_SMC_V1 — Research Strategy Contract

Status: **RESEARCH_DRAFT / ADVISORY_ONLY**  
Version: **1.0.0**  
Authority: `strategies/ST_LARGE_SMC_V1.yaml`

This is a separate strategy family. It does not modify, extend, or operate as a mode
of `ST_ASIAN_SWEEP_5R_V1 v1.1.1`, whose authority remains Session Day Trading only.
Shared analysis capabilities may supply evidence to both strategies; they do not share
strategy authority or validation evidence.

## 1. Objective and hypothesis

The research hypothesis is that larger FX opportunities may arise when price reaches a
predeclared higher-timeframe SMC location and subsequently produces a causal,
lower-timeframe liquidity-event-to-structure-shift confirmation sequence. The exact
location qualification, entry array, lifecycle, and acceptance thresholds are not yet
signed; therefore this draft cannot emit an actionable proposal.

## 2. Asset class and universe

- Asset class: FX for the first research contract.
- Instrument universe and point-in-time eligibility: `UNSIGNED`.
- Crypto is outside this contract and requires a separate venue/data contract.

## 3. Data contract

- Source: MT5 research data through the existing fail-closed market-data boundary.
- Timezone: UTC; decisions use closed bars only.
- Context timeframes: D1, H4, H1.
- Candidate confirmation timeframe: M15; use of M5/M1 is `UNSIGNED`.
- Warm-up, gap tolerance, availability timestamps, and historical reconstruction rules
  remain `UNSIGNED` and block causal backtesting until frozen.

## 4. Feature definitions

Candidate inputs may include external/internal liquidity, premium/discount, order
blocks, fair-value gaps, supply/demand zones, and protected highs/lows. Existing shared
capabilities must provide these inputs without strategy-specific reinterpretation.
Exact formulas, precedence, invalidation, and conflict resolution are `UNSIGNED`.

## 5. Signal rule

The candidate sequence is location -> liquidity event -> MSS/CHoCH -> displacement ->
entry array. Exact direction rules, event ordering, bar limits, and entry-array
qualification are `UNSIGNED`. Until signed, the only valid output is research evidence
or a non-actionable state; `READY` is not authorized.

## 6. Order and fill model

Order type, decision-to-order latency, next-bar assumptions, spread, slippage,
commission, and partial-fill handling are `UNSIGNED`. No execution adapter is connected.

## 7. Exit and lifecycle

Initial stop placement, targets, partial-profit rules, breakeven behavior, invalidation,
maximum holding period, and overnight/weekend policy are `UNSIGNED`. Session-trade
lifecycle rules must not be inherited implicitly.

## 8. Sizing and limits

The shared `execution.risk` engine is the intended sizing authority. Risk percentage,
portfolio concurrency, aggregate exposure, correlation, and loss locks are `UNSIGNED`.
No account-wide default may silently sign these strategy parameters.

## 9. Cost model

Spread, slippage, commission, financing/swap, currency conversion, and market-impact
assumptions are `UNSIGNED`.

## 10. Parameter-selection policy

No optimization is authorized. Parameters must be predeclared using training data only,
then frozen before validation and final testing.

## 11. Validation partition

Training, validation, final-test, walk-forward, and live-observation windows are
`UNSIGNED`. Evidence from Session Day Trading or another SMC strategy does not transfer.

## 12. Benchmarks

Naive baselines and an appropriate market benchmark are `UNSIGNED`.

## 13. Metrics and acceptance criteria

Required metrics and pass/fail thresholds—including expectancy, drawdown, tail loss,
turnover, exposure, stability, and minimum sample size—are `UNSIGNED`. Profitability is
not presumed.

## 14. Falsification tests

Predeclared falsification tests are `UNSIGNED`. They must test whether location adds
information beyond the confirmation sequence, whether results survive costs and timing
delays, and whether performance is stable across instruments and regimes.

## 15. Public states and execution boundary

The intended vocabulary is `READY`, `WATCH`, `NO_TRADE`, `DATA_ERROR`, `EXPIRED`, and
`BLOCKED`. During `RESEARCH_DRAFT`, `READY` is not actionable. Execution is
`ADVISORY_ONLY`; automatic execution is disabled and demo/live authorization are false.

## 16. Promotion gates

Promotion requires an owner-approved frozen revision resolving every `UNSIGNED` field,
deterministic engine tests, causal replay, robustness validation, independent registry
authorization, and separately evidenced demo validation. Registration alone never
grants execution permission.

