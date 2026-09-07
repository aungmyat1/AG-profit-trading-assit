# AG Multi-Market Strategy OS — Reuse Ledger

Discovery-only pass. No strategy economics, versions, authority, or execution gates
changed by this document or by this task. Target architecture referenced:

```
Strategy Contracts -> Evidence/Version Layer -> Opportunity Ranking -> Risk/Portfolio
  -> Authority/Approval -> Telegram/API/UI -> Execution Gateway -> MT5/Bybit/Binance
```

Baseline at time of this ledger: `main` @ `218ed1ab02175370245d2f1ed8aac429fbe1f40c`.
`ST_ASIAN_SWEEP_5R_V1` v1.1.1 (FX), `ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0 (BTC,
broker execution disabled), `ST_LARGE_SMC_V1` v1.0.6 (C10 UNSIGNED, C14 PARTIALLY
RESOLVED, broker execution disabled). None of these fields were touched.

## Reuse precedence applied

```
1. This repo (AG profit trading) — actual code, not re-derived
2. Other local repos on this machine (D:\) — reference/pattern only, never economics
3. License-compatible external OSS (Hummingbot Apache-2.0, LEAN Apache-2.0/C#
   conceptual-port only, Freqtrade GPL-3.0 reference-only, Jesse license unverified
   in this pass -> reference-only)
4. Small adapters
5. New code (last resort)
```

## Capability-by-capability findings

### Strategy Contract
- **AG**: `strategies/registry.yaml`, `strategies/*.yaml`, `strategies/STRATEGY_LEDGER.md`.
  Three live contracts (FX/BTC/Large-SMC) already declare `strategy_id`,
  `strategy_version`, `required_capabilities`, authority fields. This is the existing,
  signed source of truth — nothing external is needed or considered.
- **Decision**: AG_REUSE (already complete, do not touch).

### Proposal Contract
- **AG**: three independently-signed, differently-shaped proposal dataclasses already
  exist and must stay independent:
  - FX: `src/post_asian_pilot/proposal.py::PostAsianEntryProposal` (wraps
    `execution.adapter.TradeProposal`, adds TP2/expiry/actionable-claim fields).
  - BTC: `src/btc_sweep_research/proposal.py::BTCSweepResearchProposal`.
  - Large-SMC: `src/large_smc_research/engine.py::LargeSMCResearchEngine` produces its
    own occurrence/outcome records (see `historical_replay/` for the replay/fill
    representation), not a `TradeProposal`.
  - Partial normalized layer already exists for the `SESSION_TRADE_V1`-style adapter
    pattern: `src/assistant/models.py::StrategyResult` / `AssistantDecision`
    (`strategy_id`, `strategy_version`, `symbol`, `cycle`, `status`, `direction`,
    `entry`, `stop_loss`, `target`, `reason_codes`, `metadata`) — this is the closest
    existing analogue to the spec's requested `StrategyDecision` shape, but it is
    single-target (no `targets` list), has no `market`/`authority`/`confidence`/
    `expected_r`/`evidence_ref`/`proposal_ref`/`blockers` fields, and is currently wired
    only for the Strategy-Manager/`SESSION_TRADE_V1` adapter path, not FX/BTC/Large-SMC.
- **Decision**: ADAPT (see Phase-1 assessment below) — not implemented this pass.

### Evidence
- **AG**: `evidence_snapshot_id`/`session_snapshot_id` fields already threaded through
  FX (`PostAsianEntryProposal`), BTC daily reports (`src/btc_sweep_research/pipeline.py`
  `ResearchCycleResult`/`ResearchCycleReport`), and Large-SMC replay artifacts under
  `artifacts/`. No generic "Evidence" object exists yet, but the id-reference pattern is
  already consistent across all three markets.
- **Decision**: AG_REUSE the id-reference pattern; NEW_REQUIRED only if a shared
  Evidence *object* (not just an id string) is ever needed — not justified by current
  scope.

### Ranking (Opportunity Ranking)
- **AG**: no cross-market ranking layer exists; each strategy's proposal pipeline is
  independent and does not compete for the same slot except FX's own
  `DailyTradeSlot`/tie-break claim inside `src/post_asian_pilot/`.
- **Local**: `smc-lss-platform/providers/common/registry.py` has a provider-registry
  pattern (config-driven adapter lookup) that is a reasonable *shape* reference for a
  future strategy/opportunity registry, but it ranks data providers, not trade
  opportunities — conceptual only.
- **External**: Hummingbot's strategy `market_making`/`order_book_tracker` scoring is
  connector-level, not cross-strategy opportunity ranking; not a fit. LEAN's
  `Portfolio.MarginRemaining`-driven allocation is conceptually closest but C#
  (CONCEPTUAL_PORT only).
- **Decision**: NEW_REQUIRED if/when built — no existing AG or local component solves
  "rank proposals across FX/BTC/Large-SMC," and no external license-clean, in-language
  candidate was found that isn't itself GPL (Freqtrade) or a C# port (LEAN).

### Portfolio / Risk
- **AG**: `src/execution/risk.py::size_position()` (tick_size/tick_value based, broker-
  realistic, already conformance-tested against `trade_management/sizing.py`),
  `src/execution/daily_loss_guard.py::DailyLossGuard`, FX's own `DailyTradeSlot` claim,
  BTC's own `src/btc_sweep_research/costs.py::CostEstimate`. Each strategy currently
  owns its own risk gate; there is no shared cross-strategy risk budget object.
- **Decision**: AG_REUSE the existing per-strategy primitives; a shared
  cross-strategy risk-budget layer is NEW_REQUIRED but out of scope (would need
  explicit owner sign-off since it changes how independent per-strategy risk gates
  interact — a "semantic change" stop condition).

### Authority / Approval
- **AG**: `src/authorization/strategy_authority.py` (on the paused
  `feature/telegram-demo-execution-gateway-v1` branch/worktree,
  `.claude/worktrees/telegram-execution-gateway-v1/`), plus each strategy's own
  `authority` field in `strategies/*.yaml` (`OPERATIONAL_PROPOSAL_SHADOW_AUTHORITY`,
  `OPERATIONALLY_READY_FOR_FORWARD_RESEARCH`, `RESEARCH_RUNTIME_READY_WITH_GOVERNANCE_
  BLOCKS`). This is the existing, owner-governed authority model — already generic
  enough to key by `strategy_id`.
- **Decision**: AG_REUSE. The already-built `src/authorization/` module (frozen on its
  own branch, Phases A/B/C/D1 committed, owner directive: PAUSE further Telegram work)
  is the natural authority/approval layer for a future OS — it is not on `main` and
  this task does not merge, resume, or modify it.

### Execution Command
- **AG**: `src/execution/executor.py`, `src/execution/coordinator.py`
  (`ExecutionCoordinator`, `CoordinatorResult`), `src/execution/adapter.py`
  (`ExecutionAdapter` ABC, `MT5ExecutionAdapter`, `CryptoExecutionAdapter`,
  `TradeProposal`, `AdapterSubmitResult`). This already IS an asset-independent
  execution-command abstraction (one ABC, two concrete adapters, one proposal type)
  spanning MT5 and crypto today.
- **Decision**: AG_REUSE — already the right shape for a broker-agnostic execution
  gateway; do not replace.

### Broker interface
- **AG**: `execution.adapter.ExecutionAdapter` (ABC) is already the broker-agnostic
  interface; `MT5ExecutionAdapter`/`CryptoExecutionAdapter` are its two concrete
  implementations.
- **External reference**: Hummingbot's `ConnectorBase`/`ExchangeBase` pattern
  (Apache-2.0) is a mature, multi-exchange analogue and is a reasonable structural
  reference if a third/fourth broker connector is ever added — but AG already has an
  ABC of its own; adopting Hummingbot's would be a rewrite, not a reuse.
- **Decision**: AG_REUSE (existing ABC); Hummingbot pattern noted as REFERENCE_ONLY for
  future connector additions, no code taken.

### MT5
- **AG**: `src/mt5/` — `management_gateway.py::ManagementGatewayError/GatewayResult`,
  `broker_time.py`, `deals.py`, `symbol_resolver.py`. Mature, in active use.
- **Decision**: AG_REUSE. No external candidate applies (MT5 is a proprietary
  broker terminal API; Hummingbot/LEAN/Freqtrade/Jesse have no MT5 connector).

### Bybit
- **AG**: `src/execution_runtime/bybit_linear_perp_feed.py::BybitLinearPerpFeed`
  (V5 linear perpetual, public/read-only, owner-approved
  `AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION` scope), implementing the shared
  `src/execution_runtime/crypto_feed.py::CryptoCandleFeed` Protocol.
- **External reference**: Hummingbot ships a Bybit perpetual connector
  (Apache-2.0) — order-placement/websocket-private-channel patterns could inform a
  future *trading* (not just market-data) Bybit adapter, but AG's current Bybit usage
  is read-only market data, and no order-routing Bybit code exists yet to replace.
- **Decision**: AG_REUSE current read-only feed; Hummingbot connector noted as
  REFERENCE_ONLY candidate for a future order-routing Bybit adapter (not built here —
  broker execution stays disabled).

### Binance
- **AG**: `src/execution_runtime/binance_usdtm_feed.py::BinanceUsdtmFeed` (same
  `CryptoCandleFeed` Protocol; environment-blocked HTTP 451, retained as an alternate
  implementation, not currently reachable from this network).
- **Local**: `D:\ddev\01Binance futures trading setup07` — a personal Docker/VPS
  Binance-Futures bot project (own, unlicensed, no `LICENSE` file found; treat as
  personal/proprietary, not OSS). Contains `.env`-driven testnet/live config and a
  `gateway`/`agents` structure. No credentials were read or copied. Its
  request-signing/order-lifecycle pattern is a plausible structural reference *if*
  AG ever adds Binance order routing, but it duplicates account-specific operational
  concerns (watchdog, Docker Compose, DB) that are out of scope and not needed while
  Binance execution stays disabled here.
  `D:\ddev\ai-trade-systemD` was also checked (has Bybit-client tests, K8s/systemd
  deployment scaffolding) — same conclusion: personal/unlicensed, structurally
  interesting only for a future live-execution buildout, not reused.
- **External**: Hummingbot ships a Binance USDT-M perpetual connector (Apache-2.0),
  the strongest license-clean external candidate for a future Binance order-routing
  adapter.
- **Decision**: AG_REUSE current read-only feed (blocked by environment, not by
  code); Hummingbot connector and the two local personal projects noted as
  REFERENCE_ONLY / CONCEPTUAL candidates only — nothing copied, no order-routing
  Binance adapter exists or was built.

### Telegram
- **AG (existing, not on `main`)**: a complete, previously-built Telegram
  approval/authority module already exists in this same repository, isolated on
  `feature/telegram-demo-execution-gateway-v1` (commit `740512b`,
  "AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_BROKER_UNREACHABLE_BASELINE"),
  checked out at `.claude/worktrees/telegram-execution-gateway-v1/src/authorization/`
  (`config.py`, `integrity.py`, `models.py`, `proposal_source.py`, `store.py`,
  `strategy_authority.py`, `telegram_gateway.py`). Phases A/B/C/D1 committed; Phase D1
  reads real FX (`post_asian_pilot`) proposal journals read-only. It is explicitly
  **paused by owner directive** (`PROJECT_STATUS.md`: "PAUSE further Telegram-related
  development") and not connected to `execution.executor` anywhere in its own file set.
  This is confirmed present on disk in this pass (branch verified via `git branch -a`,
  worktree directory listing verified) but **not merged, not resumed, not modified**.
- **Decision**: AG_REUSE is the answer *when the owner lifts the pause* — this is
  by far the strongest asset for this capability; building a new Telegram integration
  or importing an external bot framework would duplicate already-built, tested
  (8 focused tests per `PROJECT_STATUS.md`), owner-paused work. No action taken this
  pass beyond recording its existence and location.

### Reconciliation
- **AG**: `src/execution/crypto_reconciliation.py::ReconciledCommandState`,
  `tests/test_crypto_reconciliation.py`. BTC-specific today; the shape
  (`ReconciledCommandState`) is asset-generic in structure even though only wired for
  crypto.
- **Decision**: AG_REUSE — extend the existing reconciliation shape to FX/MT5 only
  if/when that becomes a real requirement; do not invent a second reconciliation model.

### Analytics
- **AG**: `docs/specs/`, `docs/status/*` narrative reporting; BTC daily report
  (`src/btc_sweep_research/daily_report.py`); no shared cross-market analytics/metrics
  aggregation layer exists yet.
- **Decision**: NEW_REQUIRED if/when a cross-market dashboard is wanted; existing
  advisory skills (`performance-analysis`, `robustness-validation`) already cover the
  analysis method for any one strategy's backtest output and were reused as-is
  (no code duplicated into this ledger).

## Local project inventory (D:\ddev, this pass)

| Project | License found | Relevant material | Classification |
|---|---|---|---|
| `smc-lss-platform` | none found (no `LICENSE*`) | ST-C1/SMC-LSS v3.6 rule research, `providers/common/{adapter,registry,normalization,validation}.py` (config-driven data-provider adapter pattern) | Research reference (per existing `STRATEGY_WORKFLOW_RESOURCE_MAP.md`); provider-registry *shape* is a conceptual reference for a future opportunity/strategy registry, not copied |
| `Session Trade Codex` | n/a (own prior AG-adjacent repo) | `SESSION_TRADE_V1`, `SMC_3R_V1`, `R8_OBM_V1` | Separate authority, already governed by existing docs; unchanged |
| `Session-SMC/session-smc-trading-bot` | none found | Strategy B SMC, SVOS, its own `execution`/`execution_gate.py`/`virtual_broker` | Locked session research per existing map; not used as Large-SMC authority; not inspected further this pass (out of current capability gaps) |
| `Integrated_Claude_Forex_PQTA_System_upgraded` | none found | SMC-LSS runbook/toolkit | Operational/historical reference per existing map; decommissioned auto-execution explicitly not restored |
| `01Binance futures trading setup07` | none found (`.zip` archives, no `LICENSE`) | Docker/VPS Binance-Futures bot (testnet/live config, `gateway`, `agents`) | Personal/unlicensed -> REFERENCE_ONLY / CONCEPTUAL candidate for a future Binance order-routing adapter; no code or config copied |
| `ai-trade-systemD` | none found | Bybit client tests, K8s/systemd/Docker deployment scaffolding, alembic migrations | Personal/unlicensed -> REFERENCE_ONLY; premature infra (K8s, Alembic/Postgres) for AG's current scale, not adopted |
| `Session trade hybrid Workflow` | not re-checked this pass | — | Excluded per existing map (no matching contract found) |

No new local repository was found this pass beyond what
`docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md` already documents, except the
two Binance/Bybit-oriented personal projects above (`01Binance futures trading
setup07`, `ai-trade-systemD`), which that document did not previously enumerate.

## External OSS candidates (per approved list)

| Project | License | Role considered | Verified how | Classification |
|---|---|---|---|---|
| Hummingbot | Apache-2.0 | Broker/connector patterns (Bybit perp, Binance USDT-M, `ConnectorBase`) | Known public license (Apache-2.0); no local clone found on this machine to inspect an exact file/commit in this pass | REFERENCE_ONLY / CONCEPTUAL — no file inspected, no commit hash available, so no ADAPTED_REUSE claim is made |
| LEAN (QuantConnect) | Apache-2.0, C# | Portfolio/margin allocation shape | Known public license; C# codebase | CONCEPTUAL_PORT only, per task's own default |
| Freqtrade | GPL-3.0 | (not pursued — copyleft) | Known public license | REFERENCE_ONLY by default (GPL-3.0 incompatible with adapting code into AG without triggering copyleft obligations) |
| Jesse | Unverified this pass | (not pursued) | No local clone, no license file inspected | Excluded — per the license-safety gate, do not claim any reuse tier without a verified license; treated as REFERENCE_ONLY at most, and not actually referenced |

No external repository was cloned, fetched, or inspected file-by-file in this pass
(no local clone of Hummingbot/LEAN/Freqtrade/Jesse was found on this machine, and no
network fetch of external source was performed). All external rows above are
license-category-level guidance from the task's own approved list, not evidence of
inspected code — this is why no `docs/provenance/open_source_reuse.yaml` entry is
created: nothing was actually copied or adapted from any external source.

## Phase-1 (normalized `StrategyDecision`) assessment — NOT IMPLEMENTED

Discovery shows three genuinely different, independently-signed proposal/result
shapes already in production use (FX `PostAsianEntryProposal`, BTC
`BTCSweepResearchProposal`, Large-SMC's own engine/replay records), plus a fourth,
partial normalization (`assistant.models.StrategyResult`/`AssistantDecision`) wired
only for the `SESSION_TRADE_V1` Strategy-Manager adapter path. A safe, additive,
"mostly reuse" thin adapter would need a field-by-field mapping decision for each of
the three strategies (in particular: FX's dual-target TP1/TP2 vs. a single `targets`
list; BTC's cost-model fields; Large-SMC's occurrence/outcome shape) plus explicit
confirmation that populating a new normalized view can never become a second
authority that competes with each strategy's own signed contract. That mapping work
and the associated risk of silently blessing one shape as "canonical" exceeds what
this discovery-first pass should decide unilaterally. Per the task's own instruction
("if in doubt, stop at discovery"), Phase-1 is deferred, not implemented. If pursued
later, the closest existing scaffold to extend is `assistant.models.StrategyResult`
adding `market`, `authority`, `confidence`, `expected_r`, `evidence_ref`,
`proposal_ref`, `blockers`, and a `targets: Tuple[float, ...]` in place of the single
`target` field — additively (new optional fields), never removing or renarrowing the
existing ones consumed by `SESSION_TRADE_V1`.

## REUSE_DISCOVERY_MATRIX

| Capability | AG | Local project | Hummingbot | LEAN | Freqtrade | Jesse | Decision |
|---|---|---|---|---|---|---|---|
| Strategy Contract | `strategies/registry.yaml`, `*.yaml`, `STRATEGY_LEDGER.md` (complete) | n/a | n/a | n/a | n/a | n/a | AG_REUSE |
| Proposal Contract | 3 distinct shapes (FX/BTC/Large-SMC) + partial `StrategyResult` | n/a | n/a | n/a | n/a | n/a | ADAPT (deferred, see Phase-1) |
| Evidence | id-reference pattern already consistent across all 3 markets | `smc-lss-platform` provenance-preservation convention (reference only) | n/a | n/a | n/a | n/a | AG_REUSE pattern |
| Ranking | none exists (no cross-market opportunity ranking) | `smc-lss-platform/providers/common/registry.py` (data-provider registry shape, conceptual only) | market-making scoring is connector-level, not a fit | `Portfolio` allocation model (C#) | ranking exists but GPL-3.0 | unverified license | NEW_REQUIRED |
| Portfolio/Risk | `execution/risk.py`, `daily_loss_guard.py`, per-strategy risk fields (no shared cross-market budget) | none found | position-sizing modules (Apache-2.0, connector-scoped) | `Portfolio` margin model (C#) | risk manager exists but GPL-3.0 | unverified license | AG_REUSE existing; NEW_REQUIRED if unified budget ever needed |
| Authority/Approval | `strategies/*.yaml` authority fields + paused `src/authorization/strategy_authority.py` (own branch) | none found | n/a | n/a | n/a | n/a | AG_REUSE |
| Execution Command | `execution/executor.py`, `coordinator.py`, `adapter.py` (`ExecutionAdapter` ABC, asset-agnostic) | none found | `StrategyBase`/order-tracking pattern (Apache-2.0, reference only) | `IExecutionModel` (C#) | order pipeline exists but GPL-3.0 | unverified license | AG_REUSE |
| Broker interface | `execution.adapter.ExecutionAdapter` (ABC), `MT5ExecutionAdapter`, `CryptoExecutionAdapter` | none found | `ConnectorBase`/`ExchangeBase` (Apache-2.0, reference only) | `IBrokerage` (C#) | exchange wrapper exists but GPL-3.0 | unverified license | AG_REUSE |
| MT5 | `src/mt5/` (`management_gateway`, `broker_time`, `deals`, `symbol_resolver`) | n/a (no MT5 connector in any candidate) | none | none | none | none | AG_REUSE |
| Bybit | `execution_runtime/bybit_linear_perp_feed.py` (read-only, `CryptoCandleFeed` Protocol) | `ai-trade-systemD` (Bybit client tests, personal/unlicensed) | Bybit perpetual connector (Apache-2.0, reference only for future order routing) | none | Bybit exchange support but GPL-3.0 | unverified license | AG_REUSE (feed); REFERENCE_ONLY (order routing, not built) |
| Binance | `execution_runtime/binance_usdtm_feed.py` (env-blocked HTTP 451, same Protocol) | `01Binance futures trading setup07` (Docker/VPS bot, personal/unlicensed) | Binance USDT-M connector (Apache-2.0, reference only for future order routing) | none | Binance exchange support but GPL-3.0 | unverified license | AG_REUSE (feed); REFERENCE_ONLY (order routing, not built) |
| Telegram | Complete, paused module on `feature/telegram-demo-execution-gateway-v1` (Phases A/B/C/D1 committed, owner-paused) | none found | n/a | n/a | n/a | Telegram notifier exists but GPL-3.0 | AG_REUSE (when owner lifts pause) |
| Reconciliation | `execution/crypto_reconciliation.py::ReconciledCommandState` (BTC-wired, asset-generic shape) | none found | order/trade-state tracker (Apache-2.0, reference only) | `IOrderProcessor` (C#) | reconciliation exists but GPL-3.0 | unverified license | AG_REUSE (extend shape, not rebuild) |
| Analytics | narrative status docs + BTC `daily_report.py`; no cross-market aggregation | none directly reused | performance/notebook tooling (Apache-2.0, reference only) | `Statistics`/report generators (C#) | backtesting report exists but GPL-3.0 | unverified license | NEW_REQUIRED if a cross-market dashboard is wanted |

## Stop conditions checked (none triggered)

License unclear (Jesse) -> excluded from any reuse claim, not a project stop.
No semantic change, execution-safety bypass, authorization weakening, credential
exposure, outdated/insecure external source use, "AG already has better impl"
override, unjustified dependency cost, unverifiable provenance, or baseline
contradiction was found or introduced.
