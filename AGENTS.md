# AG Profit Trading — Agent Instructions

## Purpose

AG Profit Trading is a deterministic FX and crypto trading assistant whose target
decision products are daily Session Trade proposals and selective higher-timeframe
Large-SMC Trade proposals. The guaranteed output is an explicit decision state, not a
forced trade. The current operational implementation is FX/MT5-first; crypto remains
proposal/interface-only until a real venue integration is implemented and validated.
AI remains an advisory/explanatory layer. See `PROJECT_STATUS.md` for current state.

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

**Strategy authority and dispatch** (load when a registered strategy is named):
`strategy-management`. Read `strategies/registry.yaml` and the named contract first.
Registration, advisory analysis, proposal authority, demo authorization, and live
authorization are separate states. Never use a generic analysis skill to fill an
`UNSIGNED` strategy rule.

**Session Day Trading runtime** (`ST_ASIAN_SWEEP_5R_V1` and independently registered
session strategies): `market-data` -> `session-box-drawing` -> deterministic strategy
engine. Load `trend-range-classification` and `sweep-detection-range-v2` only when the
named contract requires them. `risk-position-sizing` applies only after the engine has
produced an eligible signal; advisory structure/zone reads never promote a signal.

**Large SMC research/advisory** (`ST_LARGE_SMC_V1`, currently `RESEARCH_DRAFT`):
`market-data` -> `market-structure-analysis` -> `supply-demand-analysis` ->
`liquidity-analysis` -> `entry-confirmation-analysis` -> `trade-management-analysis`.
Use these to collect and explain evidence only. Until the Large-SMC contract resolves
its `UNSIGNED` fields and gains an engine, this chain cannot emit an actionable `READY`
proposal and must not borrow rules from another D-drive repository implicitly.

**Generic market analysis** (no strategy named): load only the smallest necessary
subset of `market-data`, `market-structure-analysis`, `supply-demand-analysis`,
`liquidity-analysis`, `entry-confirmation-analysis`, and
`trade-management-analysis`. These remain advisory and do not require strategy dispatch.

**Manual-entry trade management** (load for "claim this ticket", "is this position
eligible for a partial", "should breakeven have fired", "check on my open manual
trade"): `trade_management/position-monitor`, `trade_management/risk-manager`,
`trade_management/partial-profit-manager`, `trade_management/breakeven-manager`,
`trade_management/exit-manager`. These delegate to actual code in `trade_management/`
and `mt5.management_gateway` (via `trade_management.manager`) — see Authority order
point 5. Distinct from `trade-management-analysis` above, which only reports strategy
config-defined milestones and has no execution path at all.

**Research and promotion** (load only for explicit research work, in this order):
`strategy-specification` -> `multi-asset-conventions` -> `market-data-quality` ->
`backtest-engineering` -> `robustness-validation` -> `performance-analysis`. A later
stage must not silently repair or reinterpret an earlier contract. Research evidence
never authorizes demo/live execution; promotion is recorded separately in the registry
and strategy ledger.

See `docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md` for the D-drive source map,
adoption rules, and the complete skill-to-workflow matrix.

## Workflow

inspect → implement → targeted tests → concise report. Stop when the requested
acceptance criteria pass; don't expand scope into an unrequested audit or rewrite.

## Live-status documentation maintenance

Any change that affects implemented capability, runtime reachability, execution
authority, safety gates, strategy authorization, live/demo validation, known gaps, or
the regression baseline must follow `docs/status/LIVE_STATUS_MAINTENANCE.md` in the same
change set.

At minimum:

1. Update the rolling snapshot at the top of `PROJECT_STATUS.md`.
2. Update `README.md` when the user-visible capability or quick-start surface changed.
3. Update `strategies/registry.yaml` and `strategies/STRATEGY_LEDGER.md` together when
   strategy registration or authorization changed; never infer authorization from code
   availability.
4. Add or update a dated `docs/status/` evidence document for a completed milestone or
   live validation. Preserve old dated results as historical evidence.
5. Update `docs/README.md` when a document is added, moved, superseded, or changes its
   role in the authority hierarchy.
6. Record the exact test command, result, date, environment, and any skipped or deferred
   live checks. Never label a unit-tested path as live-verified.

Documentation-only edits do not authorize trading and must not change safety gates.
