---
name: strategy-specification
description: Convert a trading hypothesis or indicator idea into an unambiguous, testable, causal strategy specification before coding. Use when defining universe, data, signals, timing, entries, exits, sizing, constraints, costs, benchmarks, parameters, or acceptance criteria for a backtest. Do not optimize or promise profitability.
---

# Strategy Specification

Turn prose into rules another researcher could independently implement and reproduce.

## Workflow

1. Write the economic or behavioral hypothesis in one paragraph. Separate it from the implementation.
2. Define the instrument universe using point-in-time eligibility rules.
3. Define every input field, source, frequency, timezone, adjustment, and availability timestamp.
4. Write each feature as an equation or pseudocode, including warm-up and missing-data behavior.
5. Define signal timing and execution timing separately.
6. Define entries, exits, rebalancing frequency, holding period, and conflict resolution.
7. Define simulated position sizing and portfolio constraints.
8. Define spread, slippage, commissions, funding, borrow, roll, and currency conversion assumptions.
9. Freeze parameter values or define the training-only selection procedure.
10. Select naive baselines and a benchmark.
11. Predeclare evaluation windows, metrics, and pass/fail criteria.
12. List falsification tests: observations that would weaken the hypothesis.

## Causality checklist

For each decision at time `t`, verify that every input was knowable before the assumed order submission. A bar's closing value cannot normally generate a fill at the same unqualified closing price. Fundamental or macro data becomes usable at its publication timestamp, not its reporting period end.

## Required specification

Return a numbered strategy contract with:

- objective and hypothesis;
- asset class and universe;
- data contract;
- feature definitions;
- signal rule;
- order/fill model;
- exit/rebalance rule;
- sizing and limits;
- cost model;
- parameter-selection policy;
- train/validation/test partition;
- benchmarks;
- metrics and acceptance criteria;
- known limitations.

## Guardrails

- Do not change rules after viewing final-test performance.
- Do not replace missing details with hidden assumptions; list assumptions prominently.
- Do not use future universe membership, revised fundamentals, or final contract-roll information.
- Keep research and live execution out of the same specification.
