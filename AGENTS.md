# AG Profit Trading — Agent Instructions

## Purpose

AG Profit Trading is a deterministic FX and crypto trading assistant whose target
decision products are post-Asian and post-London Session Trade tickets, preset-time
BTC/ETH tickets, and persistent Large-SMC funnel status with entry-confirmation alerts.
The assistant also supports owner-led top-down chart analysis: relevant agent skills
organize structure, supply/demand, liquidity, and cross-timeframe confirmation evidence,
then resolve and invoke a compatible registered strategy when one exists. Skills remain
advisory; only the strategy engine may produce a `TradeSignal`, and no registered match
must be reported explicitly rather than filled with borrowed rules.
The immediate roadmap publishes informational tickets from current frozen strategy
outputs; strategy validation and candidate promotion are the next stage. The
guaranteed output is an explicit decision state, not a forced trade, and a ticket is
not a broker order. The current operational implementation is FX/MT5-first; crypto
remains proposal/interface-only until a real venue integration is implemented and
validated. AI remains an advisory/explanatory layer. See `PROJECT_STATUS.md` and
`docs/PROJECT_ROADMAP.md` for current state and delivery order.

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
4. Agent skills (`.agents/skills/` canonical, `.claude/skills/` a runtime-discovery
   mirror — see `docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md` "Universal skill
   contract") read and explain; they have no
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

## Frozen strategy version preservation

Do not modify a frozen production or current-authority strategy version in place. A
behavior-changing correction must be implemented in a new candidate strategy version and
may replace the current authority only after explicit validation and promotion. Newer
code, a higher version number, or passing tests do not by themselves make a candidate
production/current authority. Historical evidence remains permanently attributed to the
exact application version and strategy version that generated it and must never be
silently rewritten or reattributed.

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

## Token-efficiency rules

Treat tokens, tool output, and repeated validation as finite project resources:

1. **Do not rediscover settled facts.** Reuse the latest authoritative status/evidence
   record unless the underlying commit, date gate, environment, or external dependency
   has materially changed.
2. **Fail fast at ordered gates.** Check date/time/authorization before baseline, data,
   network, or runtime work. When an earlier gate fails, stop and mark later checks
   `NOT_EVALUATED`; do not run them for reassurance.
3. **Avoid duplicate waiting-state reports.** If nothing material changed, report only
   the unchanged state, the trigger required to resume, and the next checkpoint.
4. **Do not repeat external probes without a reason.** Retry MT5/exchange/Telegram calls
   only after a relevant environment change, scheduled checkpoint, backoff interval, or
   explicit user request. Preserve the prior HTTP/error evidence otherwise.
5. **Bound every read and command output.** Prefer targeted `rg`, specific files/line
   ranges, narrow JSON fields, and focused test summaries. Do not dump full logs,
   registries, status histories, candles, or diffs when a small excerpt answers the task.
6. **Read each authoritative source once per task.** Keep and reuse the result; do not
   reopen the same large document unless new evidence creates a concrete ambiguity.
7. **Use progressive testing.** Run the smallest relevant tests after each edit, the
   affected suite at completion, and the full suite only for a real milestone or broad
   shared-surface change. Do not rerun an unchanged passing suite.
8. **Prefer concise structured results.** Report classification, changed paths, exact
   test command/result, blockers, and next action. Do not reproduce long prompts or
   historical narratives already stored in the repository.
9. **Stop at acceptance.** Once requested criteria pass, do not expand into speculative
   features, unrelated audits, extra documentation, or repeated confirmation work.

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
Load `multi-timeframe-market-context` only when the question is explicitly cross-
timeframe (top-down / HTF-to-LTF alignment) — it orchestrates the skills above across a
caller-supplied timeframe profile and introduces no new detection logic or strategy
wiring; see `docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md` workflow F.

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

## AGENT BOOTSTRAP — MANDATORY

At task start, read this file once, classify the mission, read `config/agent_context.json`, resolve the relevant workstream, and load only the authoritative files and skills named there. Prefer named files and symbols before repository search; search only for unresolved dependencies, expand context progressively, and stop discovery once enough evidence exists.

Mission classes: `runtime`, `strategy`, `trade_proposal`, `validation_research`, `execution`, `trade_management`, `scheduler`, `frontend_api`, and `documentation_status`.

### Default context budget

Discovery defaults are at most 5 initial authoritative project files, 2 initial skills, 1 focused repository search, and 10 inspected search results. Avoid large full-file reads and load historical status/evidence only when current authority or explicit lineage requires it. Exceed a default only for a concrete missing authority, cross-module dependency, failing test, ambiguity, shared-surface change, or explicit audit. Begin testing with the narrowest relevant test.

### Workstream routing

Use the manifest for the initial route. Minimum reads are: strategy (registry, named contract, engine, focused test); validation/research (contract, current validation profile/status, runner, focused test); trade proposal (registry, current contract, proposal/strategy engine, authorized market-data source); execution (`config/trading.yaml`, canonical execution and risk authority, focused tests); trade management (relevant management module/gateway, named skill, focused tests); scheduler (canonical config, runner/state machine, focused tests); frontend/API (named module, client/boundary, endpoint, focused tests); documentation/status (current implementation/evidence, latest status, and `LIVE_STATUS_MAINTENANCE.md` when applicable).

Historical evidence, holdout/OOS data, and unrelated strategy histories are opt-in. The manifest routes discovery only; strategy, configuration, code, and status authorities remain authoritative. A HEAD mismatch alone does not invalidate the manifest; refresh an entry only when its routing authority materially changed.
