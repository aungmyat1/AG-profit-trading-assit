# AG Two-System Architecture & Open-Source Reuse Ledger

Discovery + logical-classification pass only. No file was physically moved, no
strategy/application version changed, no execution authority changed. This document
normalizes AG's existing capabilities (already inventoried in
`docs/architecture/AG_MULTI_MARKET_OS_REUSE_LEDGER.md`) into exactly two top-level
logical domains and records the STRATEGY-vs-EXECUTION reuse classification the prior
pass did not attempt.

Baseline at time of this ledger: `main` @ `218ed1ab02175370245d2f1ed8aac429fbe1f40c`.
`ST_ASIAN_SWEEP_5R_V1` v1.1.1 (FX, `OPERATIONAL_PROPOSAL_SHADOW_AUTHORITY`),
`ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0 (BTC, `OPERATIONALLY_READY_FOR_FORWARD_RESEARCH`,
broker execution disabled), `ST_LARGE_SMC_V1` v1.0.6 (`RESEARCH_RUNTIME_READY_WITH_
GOVERNANCE_BLOCKS`, C10 UNSIGNED, C14 PARTIALLY_RESOLVED, broker execution disabled).
Re-verified against `strategies/registry.yaml` in this pass: unchanged, no
discrepancy found.

## Two-system architecture

```
STRATEGY SYSTEM                                   EXECUTION SYSTEM
----------------                                  -----------------
Market Data/Context                                Proposal Intake
  -> Strategy Engines (FX/BTC/Large-SMC/future Gold)  -> Portfolio/Account Risk
  -> Evidence/Versioning                              -> Authority/Approval
  -> Research/Validation                               -> Position Sizing
  -> Opportunity Ranking                               -> Telegram/API/UI (control only)
  -> TradeProposal/ResearchTicket                       -> ExecutionCommand
                                                          -> Execution Gateway
        [ IMMUTABLE CONTRACT / TRUST BOUNDARY ]          -> Broker Adapters (MT5/Bybit/Binance)
                                                          -> Orders/Fills/Positions
                                                          -> Reconciliation/Execution Journal
```

**Fundamental rule**: Strategy decides WHAT trade should exist (qualification,
direction, entry, stop/target geometry, expected R, strategy version, historical
attribution). Execution decides WHETHER/HOW MUCH/HOW a proposal safely reaches a
broker (authority, account risk budget, position sizing, portfolio exposure, daily
loss limits, margin, broker order lifecycle). Strategy never calls a broker API,
reads execution credentials, mutates a position, or bypasses authority. Execution
never changes setup qualification, direction, entry, SL/TP, session rules, strategy
version, or historical attribution, and never promotes research authority to
operational authority.

**Risk split** (verified against actual AG code, not assumed):
- STRATEGY RISK (stop/target geometry, expected R, invalidation semantics) lives in
  `src/strategy_engine/sweep_retest/{models,targets}.py`, `src/btc_sweep_research/
  costs.py`, `src/large_smc_research/engine.py` — e.g. the SESSION_RANGE_25 candidate
  SL-as-% research (`tests/test_large_smc_execution_boundary.py` territory) is
  strategy-side geometry, not account risk.
- EXECUTION RISK (account risk budget, position sizing, portfolio exposure, daily
  loss limits, margin, broker-volume normalization) lives in `src/execution/risk.py`
  (`size_position()`), `src/execution/daily_loss_guard.py::DailyLossGuard`,
  `src/execution/position_guard.py::OpenPositionGuard`.

## Trust-boundary verification against actual imports (not assumed)

A grep of every `strategy_engine`/`btc_sweep_research`/`post_asian_pilot`/
`large_smc_research` module against `execution*` imports, and every `execution*`
module against strategy-package imports, found:

**Strategy -> Execution (found, real, by design):**
- `src/strategy_engine/sweep_retest/engine.py` imports `execution.daily_loss_guard`,
  `execution.position_guard`, `execution.risk.size_position`.
- `src/btc_sweep_research/pipeline.py` imports `execution.daily_loss_guard`,
  `execution.position_guard`, `execution_runtime.binance_usdtm_feed`,
  `execution_runtime.crypto_feed`.
- `src/post_asian_pilot/{governor,pipeline,preflight,proposal,store}.py` import
  `execution.daily_loss_guard`, `execution.position_guard`, `execution.coordinator`,
  `execution.adapter.TradeProposal`, `execution.intent_builder`, `execution.models`,
  `execution.validator`, `execution.bar_tracker`, `execution_runtime.data_provider`.

**Execution -> Strategy (found, real, by design):**
- `src/execution/adapter.py`, `src/execution/coordinator.py` import
  `strategy_engine.sweep_retest.{models,profile}` (`SetupState`, `STATE_ENTRY_READY`,
  profile constants) — the strategy engine's own terminal-state contract, the closest
  thing AG has today to a "public strategy contract" surface.
- `src/execution/intent_builder.py`, `src/execution/validator.py` import
  `strategy_engine.models.{StrategyConfig, TradeSignal}`.
- `src/execution/crypto_models.py` imports `btc_sweep_research.proposal`.
- `src/execution_runtime/*` import `strategy_engine.session.Candle` and several
  `strategy_engine.sweep_retest.*` config/engine/state-store symbols.

**Finding**: the import graph is **not** one-directional today. This is a genuine,
intentional pre-existing pattern, not an oversight: strategy-side modules
pre-flight-check execution-owned guards (`DailyLossGuard`, `OpenPositionGuard`) before
emitting a proposal (avoids generating a signal that would be immediately blocked),
and execution consumes the strategy engine's terminal `SetupState`/`TradeSignal`
contract types (not internal detector/indicator logic). No import crosses into a
broker call, no import bypasses authority, no import lets execution rewrite strategy
economics. This is a **boundary ambiguity to document**, not a stop condition: the
logical Strategy-decides-WHAT / Execution-decides-WHETHER separation still holds at
the semantic level (no evidence any strategy module submits an order, reads a broker
credential, or mutates a position; no evidence any execution module changes a
strategy's direction/entry/SL/TP/version). It does mean a literal "strategy packages
must not import execution internals" regression test would fail immediately against
current, working, by-design code — see "Boundary hardening" below for why that test
was not added this pass.

## STRATEGY SYSTEM

| CAPABILITY | CURRENT_AG_PATH | LOCAL_RESOURCE | OPEN_SOURCE_RESOURCE | LICENSE | REUSE_CLASSIFICATION | TARGET_PATH | RATIONALE |
|---|---|---|---|---|---|---|---|
| Strategy contract | `strategies/registry.yaml`, `strategies/*.yaml`, `STRATEGY_LEDGER.md` | none needed | n/a | n/a | EXACT_REUSE | unchanged | Complete, signed source of truth for FX/BTC/Large-SMC; nothing external adds value |
| Decision/proposal model | `assistant/models.py::StrategyResult`/`AssistantDecision` (partial normalization, `SESSION_TRADE_V1` only); `post_asian_pilot/proposal.py::PostAsianEntryProposal`; `btc_sweep_research/proposal.py::BTCSweepResearchProposal`; `large_smc_research/engine.py` occurrence/outcome records | none | Jesse `Strategy`/order-intent shape (unverified license); LEAN `Insight`/`PortfolioTarget` (Apache-2.0, C#) | Jesse: unverified; LEAN: Apache-2.0/C# | ADAPTED_REUSE (deferred — see Phase-1 note in prior ledger) | `assistant/models.py` (additive fields only) if pursued | Three independently-signed shapes exist; a normalized `StrategyDecision` is an additive field-mapping exercise, not a rebuild; external frameworks offer shape-level inspiration only (Jesse license unverified, LEAN is C#) |
| Evidence | id-reference pattern (`evidence_snapshot_id`/`session_snapshot_id`) already consistent across FX/BTC/Large-SMC | `smc-lss-platform` provenance convention (reference only) | Jesse backtest result objects (unverified license) | unverified | LOCAL_REUSE (pattern only) | unchanged | AG's own id-linking pattern already satisfies the "evidence lineage without a shared mutable object" requirement |
| Version attribution | `strategy_id`/`strategy_version` fields threaded through every proposal/result object already | none | n/a | n/a | EXACT_REUSE | unchanged | Already present everywhere it's needed; immutable per existing historical-attribution rule |
| Campaign tracking | BTC `src/btc_sweep_research/pipeline.py::ResearchCycleResult/Report`; FX `DailyTradeSlot` | none | n/a | n/a | EXACT_REUSE | unchanged | Per-strategy campaign tracking already exists and is strategy-owned |
| Research/backtest | `src/backtest*` tooling, `historical_replay/` (Large-SMC), BTC `daily_report.py` | `smc-lss-platform` (research reference only, no license) | Jesse backtesting engine (unverified license); LEAN Algorithm/Research (Apache-2.0/C#) | Jesse unverified; LEAN Apache-2.0 | REFERENCE_ONLY (external) / EXACT_REUSE (AG's own) | unchanged | AG's own replay/backtest tooling is strategy-specific and already in use; external engines would require adopting their whole runtime for no proven gain |
| Statistics | advisory skills (`performance-analysis`, `robustness-validation`) already used as-is per prior ledger | none | Jesse statistics/analytics module (unverified license) | unverified | REFERENCE_ONLY (external) | n/a | Jesse's stats/reporting ergonomics are a plausible future reference only if its license is verified; not pursued this pass |
| Opportunity ranking | none exists (no cross-market ranking layer) | `smc-lss-platform/providers/common/registry.py` (conceptual data-provider registry shape only) | LEAN `Portfolio` allocation model (Apache-2.0, C#); Freqtrade has ranking-adjacent logic (GPL-3.0) | LEAN Apache-2.0/C#; Freqtrade GPL-3.0 | NEW_REQUIRED | n/a (not built) | No AG, local, or license-clean external candidate solves cross-strategy ranking; Freqtrade is copyleft (not adopted), LEAN is a C# conceptual port at best; deterministic, no external ML, V1 scope only if ever built |

## EXECUTION SYSTEM

| CAPABILITY | CURRENT_AG_PATH | LOCAL_RESOURCE | OPEN_SOURCE_RESOURCE | LICENSE | REUSE_CLASSIFICATION | TARGET_PATH | RATIONALE |
|---|---|---|---|---|---|---|---|
| Execution command | `src/execution/executor.py`, `execution/coordinator.py::ExecutionCoordinator/CoordinatorResult` | none | Hummingbot `ScriptStrategyBase`/executor pattern (Apache-2.0, no local clone to verify a commit) | Apache-2.0 (unverified commit) | EXACT_REUSE (AG) / REFERENCE_ONLY (Hummingbot) | unchanged | Already an asset-independent execution-command abstraction; no external code inspected or needed |
| Order model | `execution/adapter.py::TradeProposal`, `execution/models.py` | none | LEAN `Order`/`OrderTicket` (Apache-2.0, C#); Hummingbot `InFlightOrder` (Apache-2.0) | Apache-2.0 | EXACT_REUSE (AG) / CONCEPTUAL_PORT (LEAN, if ever needed) | unchanged | AG's `TradeProposal` already covers the asset-independent shape; LEAN's richer order-state-machine is a conceptual reference only, not needed at current scale |
| Order state / lifecycle | `execution/lifecycle.py` (confirmed-fill registration, restart idempotency) | none | Hummingbot order-tracking/state-machine (Apache-2.0, no local clone) | Apache-2.0 (unverified commit) | EXACT_REUSE (AG) / REFERENCE_ONLY (Hummingbot) | unchanged | AG already has restart-safe idempotent lifecycle tracking; Hummingbot's tracker is a future reference only if a new connector's order lifecycle needs richer states |
| Fill event | `execution/lifecycle.py::register_confirmed_fill` | none | LEAN `OrderEvent`/`Fill` (Apache-2.0, C#) | Apache-2.0 | EXACT_REUSE (AG) | unchanged | Already implemented and persisted; no gap |
| Position model | `src/mt5/deals.py`; crypto side via `execution/crypto_reconciliation.py` | none | Hummingbot `Position`; LEAN `SecurityHolding` | Apache-2.0 | EXACT_REUSE (AG) | unchanged | AG's position/deal tracking is broker-specific and already working; no external gap identified |
| Account risk (EXECUTION RISK) | `execution/daily_loss_guard.py::DailyLossGuard` | none | Freqtrade `protections`/stoploss-guard (GPL-3.0, reference only) | GPL-3.0 | EXACT_REUSE (AG) | unchanged | Proven, tested; GPL source excluded by default per license policy |
| Position sizing (EXECUTION RISK) | `execution/risk.py::size_position()` (tick_size/tick_value based, conformance-tested against `trade_management/sizing.py`) | none | Hummingbot position-sizing helpers (Apache-2.0, connector-scoped, no local clone) | Apache-2.0 (unverified commit) | EXACT_REUSE (AG) | unchanged | AG's sizing is broker-realistic and already conformance-tested; nothing external to gain without inspecting an actual commit |
| Portfolio exposure (EXECUTION RISK) | per-strategy risk primitives only; no shared cross-strategy exposure budget | none | LEAN `Portfolio.MarginRemaining` (Apache-2.0, C#) | Apache-2.0 | NEW_REQUIRED if unified budget is ever needed | n/a (not built) | No shared cross-market exposure object exists; building one is an owner-authorized semantic change, out of scope this pass |
| Authority/approval | `strategies/*.yaml` `authority`/`demo_authorized`/`live_authorized` fields; paused `src/authorization/strategy_authority.py` (branch `feature/telegram-demo-execution-gateway-v1`, not on `main`) | none | n/a | n/a | EXACT_REUSE (when owner lifts pause) | unchanged | Already-built, owner-paused; strongest existing asset for this capability, not resumed or modified this pass |
| Idempotency | `execution/bar_tracker.py::LastClosedBarStore`, restart-safe claim/lifecycle logic in `execution/lifecycle.py` and the paused `authorization/store.py::ExecutionApprovalStore.claim()` | none | Hummingbot client-order-id dedup pattern (Apache-2.0, reference only) | Apache-2.0 | EXACT_REUSE (AG) | unchanged | Duplicate-open/close protection and atomic claims already implemented and tested |
| Broker interface | `execution/adapter.py::ExecutionAdapter` (ABC) | none | Hummingbot `ConnectorBase` (Apache-2.0, no local clone); LEAN `IBrokerage` (Apache-2.0, C#) | Apache-2.0 | EXACT_REUSE (AG) | unchanged | Already broker-agnostic; adopting an external ABC would be a rewrite, not a reuse |
| MT5 | `src/mt5/` (`management_gateway`, `broker_time`, `deals`, `symbol_resolver`) | none | none (no MT5 connector in any candidate framework) | n/a | EXACT_REUSE (AG) | unchanged | Only MT5 connector available anywhere in scope |
| Bybit | `execution_runtime/bybit_linear_perp_feed.py` (read-only market data) | `ai-trade-systemD` (Bybit client tests, personal/unlicensed) | Hummingbot Bybit perpetual connector (Apache-2.0, no local clone) | Apache-2.0 (unverified commit) / none (local) | EXACT_REUSE (feed) / REFERENCE_ONLY (order routing, not built) | unchanged | Order-routing Bybit adapter is not built and not required while BTC broker execution stays disabled |
| Binance | `execution_runtime/binance_usdtm_feed.py` (env-blocked, read-only) | `01Binance futures trading setup07` (personal Docker/VPS bot, unlicensed) | Hummingbot Binance USDT-M connector (Apache-2.0, no local clone) | Apache-2.0 (unverified commit) / none (local) | EXACT_REUSE (feed) / REFERENCE_ONLY (order routing, not built) | unchanged | Same posture as Bybit; no order-routing code exists or is needed |
| Telegram | Complete, paused module on `feature/telegram-demo-execution-gateway-v1` (`src/authorization/{config,integrity,models,proposal_source,store,strategy_authority,telegram_gateway}.py`, Phases A/B/C/D1, 8 tests) | none found | Freqtrade Telegram bot (GPL-3.0, reference only) | GPL-3.0 (external) / n/a (AG's own) | EXACT_REUSE (AG, when unpaused) | unchanged | Inspected this pass for boundary properties (see below); by far the strongest asset; not merged/resumed/modified |
| Reconciliation | `execution/crypto_reconciliation.py::ReconciledCommandState` (BTC-wired, asset-generic shape) | none | LEAN `IOrderProcessor`/portfolio sync (Apache-2.0, C#) | Apache-2.0 | EXACT_REUSE (AG) | unchanged | Extend the existing shape to FX/MT5 only if ever required; do not invent a second model |
| Journal | BTC/crypto lifecycle journal entries under `execution/lifecycle.py`; FX equivalents under `post_asian_pilot/store.py` | none | Freqtrade trade DB (GPL-3.0, reference only) | GPL-3.0 (external) | EXACT_REUSE (AG) | unchanged | Already implemented per market; no external gap that justifies copyleft exposure |

## STRATEGY_SYSTEM_REUSE_MATRIX

| Capability | AG | Local | Jesse | LEAN | Freqtrade | Decision |
|---|---|---|---|---|---|---|
| Strategy contract | Complete (`strategies/registry.yaml`, per-strategy YAML) | n/a | n/a | n/a | n/a | EXACT_REUSE |
| Decision model | Partial (`assistant.models.StrategyResult`, SESSION_TRADE_V1 only) | n/a | Strategy/order-intent shape (license unverified) | `Insight` (Apache-2.0, C#) | Strategy interface (GPL-3.0) | ADAPTED_REUSE (deferred) |
| Proposal/ticket | 3 independent signed shapes (FX/BTC/Large-SMC) | n/a | unverified | `PortfolioTarget` (Apache-2.0, C#) | entry/exit signal (GPL-3.0) | ADAPTED_REUSE (deferred) |
| Evidence | id-reference pattern, consistent across all 3 markets | provenance convention (`smc-lss-platform`, reference only) | unverified | n/a | n/a | LOCAL_REUSE (pattern) |
| Version attribution | Complete, immutable, threaded everywhere | n/a | n/a | n/a | n/a | EXACT_REUSE |
| Campaign tracking | Per-strategy (BTC `ResearchCycleReport`, FX `DailyTradeSlot`) | n/a | n/a | n/a | n/a | EXACT_REUSE |
| Research/backtest | AG's own replay/backtest tooling per strategy | `smc-lss-platform` (reference only) | Backtest engine (unverified license) | Algorithm/Research (Apache-2.0, C#) | Backtesting engine (GPL-3.0) | EXACT_REUSE (AG) / REFERENCE_ONLY (external) |
| Statistics | Advisory skills reused as-is (no code duplicated) | n/a | Stats module (unverified license) | `Statistics` report generator (Apache-2.0, C#) | Backtest report (GPL-3.0) | REFERENCE_ONLY (external, unverified/copyleft) |
| Opportunity ranking | None exists | Provider-registry shape only (conceptual) | unverified | `Portfolio` allocation (Apache-2.0, C#) | Ranking-adjacent logic (GPL-3.0) | NEW_REQUIRED |

## EXECUTION_SYSTEM_REUSE_MATRIX

| Capability | AG | Local | Hummingbot | LEAN | Freqtrade | Decision |
|---|---|---|---|---|---|---|
| Execution command | `execution/executor.py`, `coordinator.py` | none | Executor/Scripts pattern (Apache-2.0, no local clone) | `IExecutionModel` (Apache-2.0, C#) | Order pipeline (GPL-3.0) | EXACT_REUSE (AG) |
| Order model | `execution/adapter.py::TradeProposal`, `models.py` | none | `InFlightOrder` (Apache-2.0) | `Order`/`OrderTicket` (Apache-2.0, C#) | Order dataclasses (GPL-3.0) | EXACT_REUSE (AG) |
| Order state | `execution/lifecycle.py` | none | Order tracker/state machine (Apache-2.0) | `OrderEvent` lifecycle (Apache-2.0, C#) | Trade state machine (GPL-3.0) | EXACT_REUSE (AG) |
| Fill event | `execution/lifecycle.py::register_confirmed_fill` | none | Trade-fill events (Apache-2.0) | `OrderEvent`/`Fill` (Apache-2.0, C#) | Fill handling (GPL-3.0) | EXACT_REUSE (AG) |
| Position model | `src/mt5/deals.py`, `execution/crypto_reconciliation.py` | none | `Position` (Apache-2.0) | `SecurityHolding` (Apache-2.0, C#) | Wallet/position state (GPL-3.0) | EXACT_REUSE (AG) |
| Account risk | `execution/daily_loss_guard.py::DailyLossGuard` | none | n/a (connector-scoped only) | `Portfolio` risk (Apache-2.0, C#) | Protections/stoploss-guard (GPL-3.0) | EXACT_REUSE (AG) |
| Position sizing | `execution/risk.py::size_position()` | none | Sizing helpers (Apache-2.0, connector-scoped) | Position sizer (Apache-2.0, C#) | Stake-amount logic (GPL-3.0) | EXACT_REUSE (AG) |
| Portfolio exposure | Per-strategy only, no shared budget | none | n/a | `Portfolio.MarginRemaining` (Apache-2.0, C#) | Wallet exposure (GPL-3.0) | NEW_REQUIRED (if unified budget ever needed) |
| Authority | `strategies/*.yaml` fields + paused `authorization/strategy_authority.py` | none | n/a | n/a | n/a | EXACT_REUSE (paused, unresumed) |
| Idempotency | `execution/bar_tracker.py`, `lifecycle.py`, paused `authorization/store.py::claim()` | none | Client-order-id dedup (Apache-2.0) | n/a | n/a | EXACT_REUSE (AG) |
| Broker interface | `execution/adapter.py::ExecutionAdapter` (ABC) | none | `ConnectorBase` (Apache-2.0, no local clone) | `IBrokerage` (Apache-2.0, C#) | Exchange wrapper (GPL-3.0) | EXACT_REUSE (AG) |
| MT5 | `src/mt5/` | none | none | none | none | EXACT_REUSE (AG) |
| Bybit | `execution_runtime/bybit_linear_perp_feed.py` (feed only) | `ai-trade-systemD` (unlicensed) | Bybit perp connector (Apache-2.0, no local clone) | none | Bybit support (GPL-3.0) | EXACT_REUSE (feed) / REFERENCE_ONLY (order routing) |
| Binance | `execution_runtime/binance_usdtm_feed.py` (feed only, env-blocked) | `01Binance futures trading setup07` (unlicensed) | Binance USDT-M connector (Apache-2.0, no local clone) | none | Binance support (GPL-3.0) | EXACT_REUSE (feed) / REFERENCE_ONLY (order routing) |
| Telegram | Complete, paused `src/authorization/telegram_gateway.py` et al. | none | n/a | n/a | Telegram bot (GPL-3.0) | EXACT_REUSE (paused, unresumed) |
| Reconciliation | `execution/crypto_reconciliation.py::ReconciledCommandState` | none | Order/trade-state tracker (Apache-2.0) | `IOrderProcessor` (Apache-2.0, C#) | Reconciliation logic (GPL-3.0) | EXACT_REUSE (AG) |
| Journal | `execution/lifecycle.py`, `post_asian_pilot/store.py` | none | n/a | n/a | Trade DB (GPL-3.0) | EXACT_REUSE (AG) |

## Telegram gateway boundary inspection (this pass)

Inspected `src/authorization/telegram_gateway.py` and `strategy_authority.py` on the
paused worktree (`.claude/worktrees/telegram-execution-gateway-v1/`, commit `740512b`,
not merged/modified). Confirmed boundary properties, verified by reading the actual
code (not assumed):

1. `TelegramExecutionGateway` never imports a broker/exchange client — the only
   "execution" it can reach is a caller-injected `ExecutionHandler` callable. In the
   committed state that handler is always `fake_execution_handler` (Phase C, always
   succeeds, no broker call) or `phase_d1_broker_disabled_handler` (Phase D1, always
   fails closed) — never `execution.coordinator`/`execution.executor`.
2. It never reconstructs a `TradeProposal` from Telegram data — it only resolves an
   already-persisted, immutable one via a caller-injected `proposal_lookup`, matching
   the spec's bridge-contract rule ("Telegram must never directly invoke broker
   APIs").
3. `strategy_authority.check_strategy_demo_authorized()` re-reads
   `strategies/registry.yaml` live, at click time, every time — no cached/independent
   copy of `demo_authorized` is kept Telegram-side, so an owner edit to the registry
   takes effect on the next click without a restart. The strategy-authorization check
   runs and can block **before** `mark_executing()` and before the execution handler
   is ever invoked.
4. This matches the required flow exactly: Strategy -> TradeProposal -> Execution
   authority -> Telegram renderer/controller, and Telegram callback -> Execution
   service -> Authority validation -> Idempotency (`store.claim()`) -> ExecutionCommand
   (would-be) -> Execution Gateway (not wired). Buttons/keyboards are rendered from
   backend approval/authority state (`keyboard_for_state`), not from strategy names.

**Conclusion**: the paused module already satisfies the two-system Telegram
requirement (control-plane-only, no direct broker access, live authority recheck) —
it is EXACT_REUSE material for the future EXECUTION SYSTEM once the owner lifts the
pause. Nothing about it needed correction or hardening; nothing was changed.

## Boundary hardening — evaluated, not implemented this pass

Section 28 of the task spec asks for a regression guard test asserting "strategy
packages must not import execution internals" and "execution may consume only public
strategy contracts" **only if it can be added with low false-positive risk**. Having
inspected the actual import graph (see "Trust-boundary verification" above), a
literal version of that invariant would fail immediately against multiple current,
intentional, working imports (`post_asian_pilot`/`btc_sweep_research`/
`strategy_engine.sweep_retest.engine` importing `execution.daily_loss_guard`/
`position_guard`/`risk`/`coordinator`/`adapter`/`intent_builder`/`validator`/
`bar_tracker`). Adding a broad test now would either (a) immediately fail on
pre-existing, correct code, or (b) require an allow-list so large it would provide no
real regression protection. Per the task's own instruction to prefer
discovery-only completion over a risky test, **no boundary test was added this
pass**. Recommendation for a future task (owner-scoped, not done here): narrow the
invariant to "execution must never import a strategy module's private
detector/indicator internals (only its terminal `SetupState`/`TradeSignal`/
`StrategyConfig` contract types)" — that narrower rule already holds today and could
be tested safely, whereas "strategy must never import execution" does not hold today
by design and should not be forced without an owner decision on whether `DailyLossGuard`/
`OpenPositionGuard` pre-flight checks belong in strategy or should be moved
behind a public execution-facing query function.

## Local project inventory and external OSS license findings

Unchanged from `docs/architecture/AG_MULTI_MARKET_OS_REUSE_LEDGER.md` (re-verified,
not re-crawled): no local clone of Hummingbot/LEAN/Freqtrade/Jesse exists on this
machine; all external rows above are license-category-level guidance from public
knowledge of each project's license, not evidence of an inspected commit. Hummingbot
= Apache-2.0 (permissive, but no local source inspected so all entries above stay
REFERENCE_ONLY/CONCEPTUAL, never ADAPTED_REUSE, until an actual file/commit can be
verified). LEAN = Apache-2.0 but C# (CONCEPTUAL_PORT ceiling per task default).
Freqtrade = GPL-3.0 (REFERENCE_ONLY by default; copyleft, not adopted). Jesse =
license unverified this pass (excluded from any reuse claim). No external code was
copied or adapted; `docs/provenance/open_source_reuse.yaml` was not created because
there is nothing to record provenance for.

## Stop conditions checked (none triggered)

Baseline unchanged and re-verified. No strategy economics copied from anywhere
external. No execution enabled. No strategy/app version changed. FX runtime not
touched. No BTC/FX forward evidence manufactured or advanced. No physical
reorganization performed. No new infrastructure (Kafka/Redis/k8s/etc.) added. No
credentials read, copied, or exposed. The one genuine ambiguity found (bidirectional
Strategy<->Execution imports around risk-guard pre-flight checks) does not itself
violate authority, safety, or economics, and is documented above rather than forced
into either a false "already clean" claim or an unwarranted reconciliation-blocking
finding.
