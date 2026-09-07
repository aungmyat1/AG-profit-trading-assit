# Trade Assistant Architecture

> Current authority and operational gates are summarized in
> [`../../PROJECT_STATUS.md`](../../PROJECT_STATUS.md). Dated implementation notes in
> this document explain design evolution and do not replace the executable safety gates.

## Project objective

```
AG PROFIT TRADING ASSISTANT
```

is the project. Reusable market-intelligence and execution capabilities are the product.
Individual trading strategies (`SESSION_TRADE_V1`, `ST_ASIAN_SWEEP_5R_V1`, and any future
strategy) are *managed by* the assistant, not the root of it. This document exists because that
distinction was at risk of being lost after several passes of strategy-specific work
(`SESSION_TRADE_V1` / `ASIAN_SESSION_V1`) in a separate repository, `D:\ddev\Session Trade
Codex`. Nothing in this pass changed that other repository's own architecture; it has its own
equivalent status doc (`SESSION_PAIR_STABILIZATION_STATUS.md`).

## Capability pyramid (this repo)

```
                    AG PROFIT TRADING ASSISTANT
                              |
        +----------+----------+----------+----------+
        |          |          |          |          |
   Market Data  Structure  Supply/    Liquidity   Entry &
                            Demand                Confirmation
        |          |          |          |          |
        +----------+----------+----------+----------+
                              |
                       Trade Management
                              |
                    +---------+---------+---------------------+
                    |                   |                      |
             Strategy Registry     Execution          trade_management/
             (strategies/)         (execution/, OPEN-side  (manual-entry only,
                    |                ACTIVE 2026-08-28)     BUILT 2026-08-27)
        +-----------+-----------+
        |                       |
  ST_ASIAN_SWEEP_5R_V1   SESSION_TRADE_V1 (by reference,
  (this repo)             see strategies/session_trade/)
```

`trade_management/` (Phase 6) is a sibling of `execution/`, not a resumption of it: it
only manages a position a human already opened manually and explicitly claimed by
ticket, never opens one, and is gated independently
(`config/trading.yaml`'s `trade_management:` block vs. `execution/`'s own `mode`/
`allow_order_send`/`allow_live_trading`). See `PROJECT_STATUS.md`'s "PHASE 6" section.

| Layer | Package | Status (verified 2026-08-28, `pytest tests/`: 396 passed, 0 failed, live MT5 terminal connected) |
|---|---|---|
| Market Data | `mt5/` | READY -- connection, candles, tick, account, symbol resolution |
| Market Structure | `market_structure/` | READY -- swings, BOS/CHoCH, `STRUCTURE_STATE_UNDEFINED` (Phase 2, frozen) |
| Supply & Demand | `supply_demand/` | READY -- Order Blocks (`AG_ORDER_BLOCK_V1`, frozen), FVG, PDH/PDL, premium/discount (Phase 3, frozen) |
| Liquidity | `liquidity/` | READY -- sweep/reclaim state machine, equal levels (Phase 4, built/paused, not broken) |
| Entry & Confirmation | `entry_confirmation/` | PARTIAL (Phase 5, `ENTRY_CONFIRMATION_V1`, 2026-08-27) -- `structure_shift`/`liquidity_reclaim` alignment fully signed (consume `market_structure`/`liquidity` verbatim); `displacement`/`rejection` measurement implemented but qualification is `UNSIGNED_RULE` pending an owner-signed generic threshold. See `docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md`. |
| Trade Management (pre-trade) | `trade_management/` (`geometry.py`/`sizing.py`/`position_state.py`/`pretrade_engine.py`) | READY (Phase 5 continuation, `TRADE_MANAGEMENT_V1`, 2026-08-28) -- deterministic geometry validation, broker-realistic tick_size/tick_value position sizing (never a hardcoded pip formula, never an unsafe round-up), R/reward geometry, and a lightweight non-broker-coupled position-state advisory. See `docs/specs/TRADE_MANAGEMENT_V1_SPEC.md`. |
| Trade Management (entry-side execution) | `execution/` | READY (OPEN), PARTIAL (strategy-signal path) -- **Execution authority restructure, 2026-08-28**: `execution/mt5_gateway.py`/`executor.py` implement OPEN for a new position (`USER_EXPLICIT_ORDER` and `ASSISTANT_PROPOSAL` sources), gated by `config/trading.yaml`'s `mode`/`execution.allow_order_send`/`account.allow_live_trading` AND a separate, non-defaulted `user_confirmed=True` per call -- reachable only via `assistant.commands.execute_command()`. Default config (`mode: ANALYSIS`, both `allow_*: false`) still blocks every `order_send`; DEMO execution requires an explicit config change plus an explicit user command. `execution/intent_builder.py`/`risk.py`/`validator.py` (the strategy-signal path) are unchanged. CLOSE delegates to the existing `mt5.management_gateway.close_position()` -- no second MT5 gateway. TRADE_MANAGEMENT_V1's `sizing.py` still reimplements (does not import) the same tick_size/tick_value formula as `execution/risk.py::size_position()`, now conformance-tested against it -- see `sizing.py`'s docstring. |
| Trade Management (manual-entry, open position) | `trade_management/`, `mt5.management_gateway` | BUILT (Phase 6, 2026-08-27) -- manages an already-open, manually-claimed position: 75% partial at TP1, breakeven once confirmed, 25% runner to 5R. Independent gate (`config/trading.yaml trade_management:`), default DRY_RUN. Live DEMO validation deferred, needs an explicit follow-up request. Unchanged by the TRADE_MANAGEMENT_V1 pass -- see `trade_management/__init__.py`'s docstring for how the two products share the package. |
| Strategy Manager | -- | PARTIAL -- see below |
| Strategy Registry | `strategies/registry.yaml`, `strategies/STRATEGY_LEDGER.md` | READY (data-level); see `docs/status/STRATEGY_REGISTRY_STATUS.md` |

## Generic Trade Assistant runtime — FIVE_SKILL_ASSISTANT_RUNTIME_V1 (2026-08-28)

The five-skill capability pyramid above now has an integrated, strategy-independent
runtime: `assistant.analyze_market(AssistantAnalysisRequest(...))` ->
`FiveSkillAnalysisResult` -> `assistant.build_assistant_assessment(...)` ->
human-readable report. Full contract: `docs/specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md`;
evidence: `docs/status/FIVE_SKILL_ASSISTANT_RUNTIME_STATUS.md`. This is a **second**, separate
public entry point in `assistant/` alongside the pre-existing
`assistant.runtime.evaluate()` (the `ASSISTANT_RUNTIME_V1` strategy-execution path,
unchanged) -- `analyze_market()` never requires a `strategy_id` and never touches
`strategy_manager`/`execution`. `Analyze EURUSD M15` works without loading any
registered strategy; a `TradeCandidate` lets a manual (or future strategy-supplied)
proposed trade flow through Structure/Supply-Demand/Liquidity/Entry-Confirmation/Trade-
Management with no execution performed.

## Strategy vs. capability boundary

A capability layer (Market Structure, Supply/Demand, Liquidity, Entry/Confirmation) reports
objective facts: "structure is BULLISH," "Asian High was swept and reclaimed," "an order block
is VALID." **It never decides a trade.** A strategy contract consumes those facts and applies its
own signed rules to reach `SIGNAL` / `NO_TRADE`. Execution then takes only a `TradeIntent` (or,
as of the 2026-08-28 restructure, a `TradeCommand`) -- it does not know what a sweep, CHoCH, or
order block is. This boundary holds in this repo's code (`PROJECT_STATUS.md`'s "Authority
order": capabilities are `ADVISORY ONLY` with no *independent* execution authority, never call
`execution.executor`/`execution.mt5_gateway` directly, never override `strategy_engine.evaluate()`)
and is unchanged by the execution-authority restructure -- that pass added a gated path from
explicit user command to `order_send`, routed only through `assistant/commands.py` ->
`execution/executor.py`, never through a capability skill.

## Strategy Manager -- ASSISTANT_RUNTIME_V1 (2026-08-27): READY for SESSION_TRADE_V1/ASIAN_LONDON

`strategy_manager/` now exists (`manager.py`, `context_builder.py`,
`session_trade_adapter.py`) plus `assistant/runtime.py`/`models.py`/`journal.py`/
`report.py` and `scripts/trade_assistant.py`. It is a thin orchestrator, not a second
execution engine: `SESSION_TRADE_V1`'s own execution stack (risk, duplicate protection,
governance, MT5 gateway) stays entirely in Session Trade Codex, invoked via subprocess
and normalized into this repo's `StrategyResult`/`AssistantDecision`. See
`docs/status/ASSISTANT_RUNTIME_V1.md` for the architecture and `docs/status/ASSISTANT_RUNTIME_V1_STATUS.md` for
live evidence. Only `SESSION_TRADE_V1` has an adapter; `ST_ASIAN_SWEEP_5R_V1` is still
invoked directly via `scripts/run_strategy.py` (unchanged) -- promote it to a Strategy
Manager adapter only when execution/'s own pause lifts.

## Agent skill boundary

Skills (`.agents/skills/`, `.claude/skills/`) are capability *instructions* -- they tell the
assistant how to invoke `market_structure.analyze_structure()`, `liquidity.liquidity_result()`,
etc., and how to report the result. They must never hardcode a strategy's decision rule (e.g. a
skill deciding "sweep => short" on its own). See `docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md` for the audit
of current skills against this rule.

## Session-box capability vs. strategy execution authority

The assistant can compute/report Asian, London, and New York session boxes for any symbol
(`assistant.market_data.session_snapshot()`, `config/canonical_sessions.yaml`) independent of
whether any registered strategy is authorized to trade off them. `SESSION_TRADE_V1`'s
`LONDON_NEWYORK` cycle being `UNSIGNED` for execution does not mean the assistant can't report
London/New York session statistics -- those are two different questions. See
`docs/specs/SESSION_TRADE_V1_SPEC.md` and `strategies/session_trade/contract.yaml`.

## Current registered strategies

See `strategies/registry.yaml` for the machine-readable list and `docs/status/STRATEGY_REGISTRY_STATUS.md`
for the narrative status. Summary: `ST_ASIAN_SWEEP_5R_V1` (this repo, research/incubation,
no execution authority anywhere yet), `SESSION_TRADE_V1` (registered here by reference,
implemented in `D:\ddev\Session Trade Codex`, demo-authorized for one of its two cycles),
`SMC_3R_V1` and `R8_OBM_V1` (both in the other repo, research/inactive, independence preserved,
not merged).

## Assistant skill taxonomy

Skill-optimization pass, 2026-08-27. Full audit/evidence: `docs/status/SKILL_OPTIMIZATION_STATUS.md`.
This section is the authoritative logical grouping of the agent-facing skills
(`.claude/skills/`, `.agents/skills/`, kept identical) into nine families. It is a
*logical* taxonomy, not a mandate to physically rename or move files -- see
`.claude/skills/SKILL_REGISTRY.yaml` for the reference-based mapping of every existing
skill directory to the family it belongs to.

```
CORE (five-layer pyramid, primary trading intelligence)
  1. market-structure       <- market-structure-analysis skill, market_structure/ package
  2. supply-demand          <- supply-demand-analysis skill, supply_demand/ package (AG_ORDER_BLOCK_V1 frozen)
  3. liquidity               <- liquidity-analysis skill, liquidity/ package
  4. entry-confirmation      <- entry-confirmation-analysis skill, entry_confirmation/ package
                                 (ENTRY_CONFIRMATION_V1, PARTIAL -- displacement/rejection
                                 qualification UNSIGNED, see docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md)
  5. trade-management        <- trade-management-analysis + risk-position-sizing skills,
                                 trade_management/{breakeven-manager,exit-manager,
                                 partial-profit-manager,position-monitor,risk-manager} skills,
                                 trade_management/ package (Phase 6 manual-entry, READY;
                                 TRADE_MANAGEMENT_V1 pre-trade geometry/sizing/RR, READY,
                                 added 2026-08-28 -- see docs/specs/TRADE_MANAGEMENT_V1_SPEC.md)

FOUNDATION
  6. market-context          <- market-data, market-data-quality, multi-asset-conventions,
                                 session-box-drawing skills; mt5/ package

STRATEGY TOOLING (assistant use case, not core intelligence)
  7. strategy-development    <- strategy-specification skill
  8. strategy-validation     <- performance-analysis, backtest-engineering,
                                 robustness-validation skills
  9. strategy-management     <- strategy-management skill (new this pass, documentation
                                 only), strategy_manager/ package, scripts/trade_assistant.py
```

Dependency diagram (not every request runs every box -- see "Skill invocation model" below):

```
                         MARKET CONTEXT
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
     STRUCTURE          SUPPLY & DEMAND       LIQUIDITY
          |                   |                   |
          +-------------------+-------------------+
                              v
                     ENTRY & CONFIRMATION
                              |
                              v
                       TRADE MANAGEMENT
                              |
                              v
                    ASSISTANT ASSESSMENT
```

Strategy diagram -- `strategy-management` is a use case hanging off the assistant, not
above it:

```
TRADE ASSISTANT
       |
       +-- five core skills + market-context (works with no strategy loaded)
       |
       +-- Strategy Management
                  |
             Strategy Registry (strategies/registry.yaml)
                  |
        +---------+-----------------+
        |         |                 |
 ST_ASIAN_SWEEP  SESSION_TRADE_V1   (future strategies)
   _5R_V1         (by reference)
```

### Skill invocation model

Not every request runs the whole pyramid. "Show me EURUSD structure" needs only
`market-context` -> `market-structure`. "Analyze EURUSD using full SMC context" runs
all five core skills. A registered strategy declares which capabilities it actually
needs (see each strategy's `contract.yaml`/`*.yaml`); `strategy-management` runs only
those, never the full pyramid by default.

### Strategy-specific skill ownership (not universal core skills)

Two existing top-level skill directories implement rules signed for one specific
strategy, not a generic Trade Assistant capability. Verified against
`strategy_engine/session/` and `strategies/registry.yaml` (not assumed):

| Skill directory | Algorithm | Owner strategy | Generic equivalent |
|---|---|---|---|
| `trend-range-classification` | `ER_ONLY_V2` (`strategy_engine/session/classifier.py`) | `ST_ASIAN_SWEEP_5R_V1` | none -- `market-structure` reports structural direction, a different question (see `docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md`) |
| `sweep-detection-range-v2` | `SESSION_FLOW_V2_SIMPLE` / `entry_2_sweep` (`strategy_engine/session/setups.py`) | `ST_ASIAN_SWEEP_5R_V1` | `liquidity` reports generic sweep/reclaim facts |

Note this corrects an initial assumption that both belonged to `SESSION_TRADE_V1`:
`SESSION_TRADE_V1` has its own, separately-signed `classify_session()` and
`detect_sweep()` in `Session Trade Codex`, distinct from `ER_ONLY_V2` and
`entry_2_sweep`. Both pairs coexist by design (`docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md`:
`STRATEGY_RULE_CONFLICTS = 0`) -- neither was altered by this pass. Both skill files
now carry an ownership note stating this explicitly.

## Future extensibility

Adding a strategy means: (1) an entry in `strategies/registry.yaml`, (2) a contract file
declaring `required_capabilities` and `supported_cycles`/execution authority explicitly, (3) its
own classifier/setup/risk logic, owned by the strategy, never duplicated into a capability
layer or a skill. Nothing about `SESSION_TRADE_V1` being registered here requires porting its
Python implementation into this repo.
