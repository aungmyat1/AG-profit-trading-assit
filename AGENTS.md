# AG Profit Trading — Agent Instructions

## Purpose

AG Profit Trading is an MT5-connected trading assistant: deterministic strategy engine
+ execution engine + broker adapter, with AI as an advisory/explanatory layer on top.
See `PROJECT_STATUS.md` for current implementation state.

## Authority order

```
Strategy YAML -> Strategy Engine -> Execution Engine -> MT5
Agent skills  -> ADVISORY ONLY
```

1. `strategy_engine/` decides trade signals. Deterministic; not up for reinterpretation.
2. `execution/risk.py` decides allowed risk/sizing.
3. `execution/` controls MT5 orders (via `mt5/`). Entry-side OPEN is implemented
   (`execution/mt5_gateway.py`, `executor.py`) as of the 2026-08-28 Execution authority
   restructure (see `PROJECT_STATUS.md`) — reachable ONLY through
   `assistant.commands.execute_command()`, and only with a separate, non-defaulted
   `user_confirmed=True` derived from an explicit user instruction that turn. Never call
   `execution.executor`/`execution.mt5_gateway`/order_check/order_send directly or with
   `user_confirmed=True` unless the user's own message this turn was an explicit
   execution command ("execute it", "sell EURUSD 0.31 lots...", "close this position") —
   analysis or a proposal being generated is never sufficient on its own.
4. Agent skills (`.claude/skills/`, `.agents/skills/`) read and explain; they have no
   *independent* execution authority and never call `execution.executor`,
   `execution.mt5_gateway`, or any order_check/order_send path themselves, and never
   override a strategy engine result. Actual execution is always routed through point 3.
5. `trade_management/` (Phase 6, manual-entry only) is a separate, independently-gated
   pathway: it manages a position the user already opened by hand and explicitly
   claimed by ticket (`scripts/manage_trade.py claim <ticket>`). It never opens a
   position. Its only write surface is `mt5.management_gateway` (modify SL / partial
   close / close), gated by `config/trading.yaml`'s `trade_management:` block —
   independent of `execution/`'s gates in point 3. `.claude/skills/trade_management/*`
   and `.agents/skills/trade_management/*` are advisory wrappers around
   `trade_management.rules`, same as any other skill in point 4 — they don't call the
   gateway directly either; `trade_management.manager` does, after
   `trade_management.validator.validate()`.

## Default safety

- LIVE trading is disabled unless a human explicitly enables it (`config/trading.yaml`
  `account.allow_live_trading`, independent of the `mode` gate — see `PROJECT_STATUS.md`).
- Never override a deterministic strategy rule or a `NO_TRADE` result because market
  context "looks" favorable.
- Never modify files unrelated to the current task.
- Prefer the smallest correct implementation over a general one.

## Minimum-context principle

For every task:

1. Identify the smallest authoritative source for the answer (a specific strategy YAML,
   a specific module, a specific test) rather than reading broadly by default.
2. Use deterministic code (`strategy_engine.evaluate()`) for calculations — don't
   hand-compute session highs/lows/ER/sizing from raw candles when the engine can do it.
3. Load only the skill(s) relevant to the current question.
4. Run the narrowest test file that covers the change; run the full suite at milestones,
   not after every edit.
5. Report changes, evidence, and blockers — skip narrating routine reads/searches.

## Skill grouping (conceptual — both dirs stay flat, this is about which to load)

**Runtime** (load for "analyze EURUSD", "what's today's box", "why didn't this fire"):
`market-data`, `market-structure-analysis`, `supply-demand-analysis`,
`liquidity-analysis`, `entry-confirmation-analysis`, `trade-management-analysis`, plus
`session-box-drawing`, `trend-range-classification`, `sweep-detection-range-v2`,
`risk-position-sizing` underneath them as needed.

**Manual-entry trade management** (load for "claim this ticket", "is this position
eligible for a partial", "should breakeven have fired", "check on my open manual
trade"): `trade_management/position-monitor`, `trade_management/risk-manager`,
`trade_management/partial-profit-manager`, `trade_management/breakeven-manager`,
`trade_management/exit-manager`. These delegate to actual code in `trade_management/`
and `mt5.management_gateway` (via `trade_management.manager`) — see Authority order
point 5. Distinct from `trade-management-analysis` above, which only reports strategy
config-defined milestones and has no execution path at all.

**Research** (load only when the task is explicitly about spec-writing, backtesting, or
validation, not day-to-day analysis): `strategy-specification`, `backtest-engineering`,
`market-data-quality`, `robustness-validation`, `performance-analysis`,
`multi-asset-conventions`.

## Workflow

inspect → implement → targeted tests → concise report. Stop when the requested
acceptance criteria pass; don't expand scope into an unrequested audit or rewrite.
