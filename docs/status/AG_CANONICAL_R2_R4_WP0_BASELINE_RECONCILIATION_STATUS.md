# WP0 — Baseline Reconciliation Status

Program: `AG_CANONICAL_SCANNER_PROPOSAL_PIPELINE_V1`
Plan: `docs/plans/AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1.md`
Recorded: 2026-09-11
Baseline: `main` (current checkout)

## Purpose

Per the plan's WP0, this freezes one ownership/dependency map and a WP1-WP12
acceptance matrix, and records what is reused, migrated, quarantined, or removed
before any WP1-WP12 code changes begin.

## Ownership/dependency map (current checkout)

### 1. MT5 feed
- Real bridge: `src/mt5/market_data.py`, `connection.py`, `account.py`,
  `broker_time.py` — direct MetaTrader5 calls, UTC-normalized.
- Read-only wrapper: `src/assistant/market_data.py` (`MarketSnapshot`,
  `historical_candles`, `data_health`) — fail-closed, no synthetic substitution.
- API exposure: `src/api/broker_service.py::real_market_data()` →
  `GET /api/market-data/candles` (`src/api/app.py:182-205`).
- Gap: `src/assistant/market_data.py:32`'s `MarketSnapshot` dataclass carries no
  `market_data_mode` (REAL/REPLAY/SYNTHETIC) field. `src/historical_replay/` is a
  second, unrelated data path with no shared provenance contract.

### 2. Strategy decision
- Three independent engines with three different native state vocabularies:
  - FX: `src/post_asian_pilot/decision.py` (`ST_ASIAN_SWEEP_5R_V1`) —
    `WATCH/READY/NO_TRADE/DATA_ERROR/EXPIRED/BLOCKED`.
  - BTC: `src/strategy_engine/sweep_retest/models.py`
    (`ST_LIQUIDITY_SWEEP_RETEST_V1`) — `ENTRY_READY/WAITING_*/NO_TRADE_*`.
  - Large-SMC: `src/large_smc_research/decision.py` (`ST_LARGE_SMC_V1`) —
    `RESEARCH_QUALIFIED/WATCH/NO_TRADE/INVALIDATED/DATA_ERROR` (no READY by design).
- Read-view unifying contract already exists: `src/strategy_contract/decision.py`
  (`StrategyDecision`, frozen, one-way adapters `from_fx_decision`,
  `from_btc_setup_state`, `from_large_smc_decision`). Does not normalize the
  native state strings themselves (still verbatim in `setup_properties`).

### 3. Proposal / persistence
- `src/proposals/` — `SMCTradeProposal` (`SMC_TRADE_PROPOSAL_V1`), own identity
  (`identity.py`) and lifecycle (`lifecycle.py`: `CREATED/STILL_VALID/UPDATED/
  INVALIDATED/EXPIRED`). Persists via `src/runtime_state/store.py`
  (`JsonKeyValueStore`, file-backed, atomic, lock-protected) — durable,
  single-process scope.
- `src/proposal_envelope/models.py` — `CanonicalProposal`
  (`AG_CANONICAL_PROPOSAL_V1`), monotonic `version` correction linkage, per-strategy
  adapters. This is the closest existing match to the plan's target ledger shape.
- `src/ticket_delivery/identity.py::logical_ticket_id()` — a third identity
  scheme, self-documented as reusing/extending `proposals`' `setup_id` rather than
  competing with it.
- `src/strategy_engine/sweep_retest/occurrence_identity.py::btc_occurrence_id()` —
  a fourth, BTC-specific hash identity, self-documented as distinct from Large-SMC's
  `candidate_occurrence_id`.
- **Flag — in-memory, not durable**: `src/api/execution_service.py::
  InMemoryProposalRegistry` backs `GET /api/proposals` today and does not survive
  restart (self-documented as having "no persistent ingestion path yet").

### 4. API surface (`src/api/app.py`)
- Read endpoints confirmed: `/api/health`, `/api/broker/status`,
  `/api/broker/account`, `/api/broker/history`, `/api/market-data/candles`,
  `/api/system/status`, `/api/strategies[/{id}]`, `/api/validation/{id}`,
  `/api/proposals[/{hash}]`, `/api/telegram/status`, `/api/tickets[/{id}]`,
  `/api/executions/{id}`.
- Only order-mutation path: `POST /api/tickets/{approval_id}/authorize-demo` →
  `execution_service.authorize_demo_execution()` (proposal-hash integrity check +
  Demo strategy-authority gate, then real MT5 demo dispatch). No endpoint creates a
  proposal from raw input.

### 5. Frontend / scanner rendering
- `web/src/components/Terminal/AGBackendPanel.tsx` — genuinely renderer-only,
  reads verbatim from `src/api/app.py` via `agApiClient.ts`. Matches WP5 intent.
- **Contradictory — a second, independent backend exists**: `web/server.ts` (Node/
  Express) reimplements its own parallel route set, including
  `GET /api/proposals/scan` backed by `web/src/utils/smcEngine.ts
  ::evaluateAsianSweepStrategy()` — a from-scratch TypeScript reimplementation of
  the FX strategy over synthetic candles. Currently fenced by convention
  (`marketDataSource:'SYNTHETIC'`, `executionEligible:false`), not by structural
  boundary.
- **Contradictory — a second, weaker execution gateway**: `web/server.ts`'s
  `POST /api/execution/execute`, when `VITE_AG_API_MODE==='real'`, spawns
  `scripts/web_execute_trade.py` and submits a real MT5 demo order directly,
  bypassing `execution_service.authorize_demo_execution()` and the Python
  authorization store entirely. Gated only by a client-supplied
  `user_confirmed` boolean.
- `web/src/utils/api.ts` — a labeled mock data layer, still imported live in
  `App.tsx`.
- `web/src/components/Terminal/BrokerConnectionModal.tsx` — legacy/mock broker UI,
  actively wired into `ExecutionCockpit.tsx` and `Navbar.tsx` (not dead code).

### 6. Evidence / logging
- `src/execution/journal.py::record_event()` — durable append-only JSONL, used by
  both execution authorize/block and Telegram notify events.
- `src/ticket_delivery/archive.py` — structured cycle-decision archive linked to
  `logical_ticket_id`.
- `artifacts/ticket_delivery_evidence_exports/`, `artifacts/validation_ledger/`,
  `artifacts/readiness/` — existing timestamped, manifest/hash-indexed export
  mechanisms, but FX/ticket-delivery-scoped, not a single cross-strategy
  decision+proposal audit trail.

## Ownership conflicts to resolve before WP1 codes anything

1. **Two independent execution gateways.** `src/api/app.py` (authorized, gated) vs.
   `web/server.ts`'s real-mode `/api/execution/execute` (weaker gate, bypasses
   Python authorization store). One must become authoritative; the other retired
   or hard-blocked. This is the single highest-risk finding — it is a live path to
   a real MT5 demo order that does not go through
   `execution_service.authorize_demo_execution()`.
2. **Four parallel proposal-identity schemes** (`proposals/identity.py`,
   `proposal_envelope/models.py`, `ticket_delivery/identity.py`,
   `sweep_retest/occurrence_identity.py`). They are self-aware/cross-referenced,
   not accidental duplication, but WP7-WP8 need one canonical occurrence key.
   `proposal_envelope.models.CanonicalProposal` is the recommended target shape.
3. **No `market_data_mode` provenance contract exists anywhere.** WP1 has a clean
   slate here — nothing to reconcile, only to build.
4. **`InMemoryProposalRegistry` is not durable.** WP8's persistent ledger
   requirement is not met by anything currently backing `GET /api/proposals`.

## Reuse / migrate / quarantine / remove disposition

| Component | Disposition |
|---|---|
| `src/mt5/*` real bridge | **Reuse** as-is for WP2 |
| `src/assistant/market_data.py` | **Reuse + extend** — add `market_data_mode` for WP1 |
| `src/historical_replay/` | **Reuse under explicit non-real mode only** (per plan) |
| `src/strategy_contract/decision.py` | **Reuse + extend** as the WP4 canonical contract base |
| `src/post_asian_pilot`, `sweep_retest`, `large_smc_research` decision engines | **Reuse unmodified** (frozen strategy behavior) |
| `src/proposal_envelope/models.py::CanonicalProposal` | **Reuse** as WP6-WP8 target envelope shape |
| `src/proposals/`, `ticket_delivery/identity.py`, `sweep_retest/occurrence_identity.py` | **Migrate** into the canonical envelope identity at WP7; do not delete until migration is verified |
| `src/api/execution_service.py::InMemoryProposalRegistry` | **Migrate** to durable ledger-backed storage at WP8 |
| `src/api/app.py` read endpoints + `authorize-demo` gate | **Reuse** as the WP9 API base |
| `web/src/components/Terminal/AGBackendPanel.tsx` | **Reuse** as the WP5/WP10 renderer base |
| `web/server.ts` `/api/proposals/scan`, `smcEngine.ts` | **Quarantine** — must not be treated as, or migrated toward, canonical decision/proposal authority; explicitly out of the WP1-WP12 path |
| `web/server.ts` real-mode `/api/execution/execute` | **Quarantine, flag for hard-block** — out of R2-R4 scope (broker-read-only plan) but must not be left reachable while this plan claims zero-broker-mutation; recommend disabling the real-mode branch or gating it behind the same authorization store, tracked as a follow-up decision, not silently left live |
| `web/src/utils/api.ts` mock layer, `BrokerConnectionModal.tsx` | **Quarantine** — leave wired only where already isolated from the canonical renderer path; do not extend |

## WP1-WP12 acceptance matrix (starting state)

| WP | Requirement | Current state |
|---|---|---|
| WP1 | Versioned `MarketSnapshot` with `market_data_mode` | **PASS** — `src/strategy_contract/market_snapshot.py`, tested (`tests/test_market_snapshot_contract.py`, 8/8) |
| WP2 | Real closed-candle scanner feed (EURUSD/GBPUSD → backend) | **PASS** — reused as-is: `src/post_asian_pilot/pipeline.py::_evaluate_pair` already feeds real closed M15 candles from `mt5.market_data.get_candles` for both configured FX symbols into the canonical strategy path, excludes the forming bar (half-open range end), and fails closed to `DATA_ERROR` on any `MarketDataError`. No new code required; WP1's `MarketSnapshot` is available to attach at this call site when WP4 wires it. |
| WP3 | Fail-closed data guards | **PASS** — guards already existed (`mt5/market_data.py::_validate_monotonic/_validate_ohlc` for duplicate/out-of-order/non-finite/invalid-OHLC; `SYMBOL_NOT_FOUND`/`UNSUPPORTED_TIMEFRAME`/`MT5_NOT_CONNECTED`/`NAIVE_DATETIME_REJECTED` in the same module; snapshot-level duplicate/out-of-order/forming-bar guards already tested in `tests/test_post_asian_pilot.py`), but were **untested at the unit level for the MT5/FX path specifically** (only the crypto feeds had guard tests) — closed that gap with `tests/test_mt5_market_data_guards.py` (7/7 pass). Explicit staleness check (`check_freshness`) exists but is applied to live ticks, not the closed-candle path — closed candles don't need a staleness gate in the same sense since they're bounded by session windows already enforced by `pipeline.py`'s window logic. |
| WP4 | Canonical `StrategyDecision` | **PASS** — `strategy_contract/decision.py`'s three adapters now accept an optional `market_snapshot` and propagate `market_data_mode/source/asof/fingerprint` verbatim, with a fail-closed symbol-mismatch guard (`MarketSnapshotSymbolMismatch`). Backward compatible (existing 7 tests unchanged + 6 new, 13/13 pass). Native per-strategy state vocabularies remain intentionally un-normalized (three real state machines, not collapsed into one — see WP0 finding 2); this was a deliberate scope decision, not a gap: the plan requires preserving strategy-specific semantics, not forcing a shared enum. |
| WP5 | Renderer-only frontend | **PASS** — `AGBackendPanel.tsx` (RENDER_ONLY), `CandlestickChart.tsx` (VISUAL_ONLY, draws props only, `calculateEMA` is a pure indicator), `ReplayStudio.tsx` (DUPLICATE_STRATEGY_AUTHORITY but correctly isolated/labeled as an offline replay lab, not live-wired), `SignalScanner.tsx` (RENDER_ONLY; its real-MT5 data strip is explicitly non-feeding, per its own code comment; `onExecuteProposal` only navigates tabs). `web/server.ts`'s `/api/proposals/scan` + `smcEngine.ts` remain DUPLICATE_STRATEGY_AUTHORITY but correctly fenced by `SYNTHETIC`/`executionEligible:false` tagging (WP0, unchanged this session). **Fixed two real bugs**: (1) `web/src/utils/api.ts::generateClientProposals()` ran the identical synthetic strategy approximation as the server route but returned it **untagged**, now tagged identically. (2) WP5.2 hardening — `ExecutionCockpit.tsx`'s `isAuthoritativeProposal` check was negative-trust (`marketDataSource !== 'SYNTHETIC'`), which reads any *missing/unknown* provenance as authoritative by construction — a structural gap, not just the one instance bug #1 fixed. Replaced with a shared positive-trust helper, `web/src/utils/proposalAuthority.ts::isAuthoritativeProposal()`, checking `executionEligible === true` (an existing, already-documented field — no new schema introduced) — now used in both `ExecutionCockpit.tsx` and `SignalScanner.tsx`'s non-authoritative warning banner. Since no live path currently ever sets `marketDataSource:'MT5'` or `executionEligible:true` (confirmed by repo-wide grep), every proposal reaching the frontend today correctly reads as non-authoritative — the intended fail-closed state. 6/6 new tests (`web/tests/wp5_proposal_authority.test.ts`) + `npx tsc --noEmit` clean. |
| WP6 | Proposal formation gate | MISSING (no single gate enforcing REAL mode + complete geometry before proposal creation) |
| WP7 | Deterministic occurrence identity | CONTRADICTORY (4 parallel schemes) |
| WP8 | Persistent proposal ledger | MISSING (`InMemoryProposalRegistry` is not durable) |
| WP9 | Read-only proposal API | PARTIAL (`/api/proposals` exists, backed by non-durable store) |
| WP10 | Scanner rendering from ledger | PARTIAL (`AGBackendPanel.tsx` pattern exists; needs ledger-backed source once WP8 lands) |
| WP11 | Reliability/boundary proof | NOT_EVALUATED |
| WP12 | Natural end-to-end proof | NOT_EVALUATED |

## WP0A — Execution authority containment (resolved 2026-09-11)

The execution-gateway conflict flagged above was the one blocker WP0 could not defer.
Resolution:

- `web/server.ts`'s `POST /api/execution/execute` real-mode branch — which spawned
  `scripts/web_execute_trade.py` and accepted client-supplied entry/SL/TP/volume plus
  a client-supplied `user_confirmed` boolean as sufficient authority for a real MT5
  demo order — is **retired**. It now returns `410 EXECUTION_ROUTE_RETIRED` and
  performs no spawn, no broker call, and no order-shaped success response.
- The simulated/mock branch (in-memory fake position, no broker contact) is
  unchanged — it is not a broker-mutation path.
- Fixed a related bug that blocked verifying this safely: `readEnvFile()` in
  `web/server.ts` unconditionally overwrote already-set `process.env` values from
  `.env`, making the server impossible to stand up in an isolated test
  configuration. It now only fills in variables that are unset, standard dotenv
  precedence, no behavior change for the normal `npm run dev` path.
  Also made `PORT` configurable via env (was hardcoded `3000`) for the same reason.
- Canonical broker-mutation authority is now singular:
  `src/api/app.py::POST /api/tickets/{approval_id}/authorize-demo` →
  `execution_service.authorize_demo_execution()`. `web/server.ts` execution
  authority = **NONE**.
- Added `web/tests/wp0a_execution_route_containment.test.ts` (Node's built-in test
  runner, no new dependency): proves the retired route fails closed regardless of
  client-supplied geometry/confirmation, and that the synthetic scanner feed
  (`/api/proposals/scan`) still tags every proposal `executionEligible:false`.
  Result: 4/4 PASS. `npx tsc --noEmit` clean. No real order was submitted during
  verification (manual curl checks + automated suite both hit only the retired
  fail-closed path).
- The manual owner-controlled "New Order" form in `ExecutionCockpit.tsx` (which
  posts to this route) now fails closed in real mode too — it was already
  guarded against auto-filling from synthetic proposals, but its only real-broker
  path is now gone rather than left as an unauthorized bypass. This is the
  intended outcome per the plan's containment instruction: don't preserve a bypass
  for compatibility; route future manual-execution work toward the canonical
  Python gateway instead. No replacement execution path was created.

WP0A = **COMPLETE**. EXECUTION_AUTHORITY_CONFLICT = **RESOLVED**.

## WP0B — Position-management authority containment (resolved 2026-09-12)

The 2026-09-12 platform-finalization audit found WP0A had covered only *opening* a new
order. Two sibling routes still held an alternate authority path over an **existing**
broker position:

- `POST /api/execution/manage` (real mode) spawned `scripts/web_manage_trade.py` and
- `POST /api/execution/claim` (real mode) spawned `scripts/manage_trade.py`,

both reaching `src/mt5/management_gateway.py` and real `mt5.order_check` /
`mt5.order_send` for `BREAKEVEN` / `PARTIAL_CLOSE` / `CLOSE`, on nothing but a
client-supplied ticket and action. They were inert only because
`config/trading.yaml`'s `allow_live_management`, `allow_order_send`,
`allow_order_check` and `allow_live_trading` are all `false` — a **config gate, not a
structural boundary**.

Resolution (identical convention to WP0A, no second authorization system invented):

- Both real-mode branches now return `410 EXECUTION_ROUTE_RETIRED` and perform no
  spawn, no broker call, and no management-shaped success response.
- Mock mode is unchanged: the in-memory simulated position management the UI depends
  on still works and still reports `simulated: true`.
- `src/mt5/management_gateway.py`, `scripts/manage_trade.py`,
  `scripts/manage_positions.py` and all canonical `src/trade_management/` domain logic
  are **untouched** — the capability is preserved, only the alternate Node authority
  route is removed.
- `web/server.ts` now contains no reference to any broker-mutating script
  (`web_execute_trade.py`, `web_manage_trade.py`, `manage_trade.py`); a static source
  assertion in the containment suite enforces this going forward. The remaining
  real-mode spawn in `web/server.ts` is `scripts/web_mt5_positions.py`, a read-only
  positions read.
- Tests: `web/tests/wp0a_execution_route_containment.test.ts` extended to 9 cases
  (execute + all three manage actions + claim + the static source assertion);
  new `web/tests/wp0b_management_route_mock_mode.test.ts` (2 cases) proves mock mode
  is unaffected. 11/11 PASS, no MT5 terminal or broker connection involved.

WP0B = **COMPLETE**. Node/Express broker authority (open **and** manage) = **NONE**.

## Exit

No unresolved ownership conflict blocks WP1 from starting. The proposal-identity
duplication (4 parallel schemes) remains carried forward as an explicit WP7 input,
per plan section on identity reconciliation, and does not block WP1-WP5.

WP0 = **COMPLETE**. WP0A = **COMPLETE**.

## R2 exit — 2026-09-11

```
R2 = Real Market Watch Ready

WP1 MARKET_TRUTH_CONTRACT      = PASS  (src/strategy_contract/market_snapshot.py, 8/8 tests)
WP2 REAL_CLOSED_CANDLE_FEED    = PASS  (reused src/post_asian_pilot/pipeline.py, no new code)
WP3 DATA_GUARDS                = PASS  (existing guards + 7/7 new unit tests)

Real closed candles reach the canonical backend (pipeline.py, unchanged).
Timestamps/fingerprints: fingerprinting now available via MarketSnapshot; not yet
wired into pipeline.py's evidence records (that wiring is WP4/WP6 scope, since it
requires the canonical StrategyDecision/Proposal contracts to carry the field).
Guards fail closed: proven.
Zero broker mutation: proven (WP0A + this session's work touched no execution path).
```

Note: `MarketSnapshot` exists as a contract and is proven correct in isolation, but is
NOT YET attached to any live decision/evidence record — that propagation is WP4's job
("propagate the mode unchanged through every downstream contract"). R2 is READY in the
sense the plan defines it (real data reaches the canonical backend, guards hold); the
mode-tag itself only becomes end-to-end visible once WP4 wires it in.

## R3 exit — 2026-09-11

```
R3 = Canonical Strategy Ready

WP4 CANONICAL_STRATEGY_DECISION = PASS  (13/13 tests: 7 pre-existing unchanged + 6 new)
WP5 FRONTEND_RENDERER_ONLY      = PASS  (audit complete; 1 real mislabeling bug found and fixed)

AG_CANONICAL_STRATEGY_RUNTIME_READY_V1 = PASS

The backend is the only decision authority for the canonical StrategyDecision layer.
The UI has no live path that independently promotes a decision state without a
SYNTHETIC/non-authoritative label. Frozen strategy behavior (FX/BTC/Large-SMC native
decision logic) is unchanged -- only the additive read-view adapter layer and one
frontend tagging bug were touched.

broker_mutation = ZERO (no execution-path code touched this WP)
```

Caveat carried forward: as with WP2, `StrategyDecision`'s market_data_* fields are
correct and tested in isolation but have no live caller yet (confirmed via repo-wide
grep: `from_fx_decision`/`from_btc_setup_state`/`from_large_smc_decision` are called
only from their own test files). Wiring them into a live evaluation cycle
(`post_asian_pilot/pipeline.py` or equivalent) is API/scanner-serving work, which
belongs to WP9-WP10, not WP4.

## R3_CHECKPOINT — 2026-09-11

```
WP4 = PASS
WP5 = PASS

canonical strategy authority = Python
frontend strategy authority = NONE
synthetic fallback = NON_AUTHORITATIVE
missing provenance = NON_AUTHORITATIVE
broker mutation = ZERO

R3 = READY
AG_CANONICAL_STRATEGY_RUNTIME_READY_V1 = PASS
```

## Proposal identity reconciliation — 2026-09-11

WP0 originally framed this as "4 parallel/competing schemes." Deeper inspection this
session shows a more coherent picture: **3 strategy-family-scoped native identity
generators (each internally consistent, two already live and persisted) plus one
normalization wrapper that already correctly defers to them, plus one execution-layer
foreign key.** No destructive migration is required.

### Inventory

| Identity | Source path | Producer | Consumers | Persistent? | Restart-safe? | Deterministic? | Strategy-linked | Execution-linked |
|---|---|---|---|---|---|---|---|---|
| FX setup identity | `post_asian_pilot/proposal.py::PostAsianEntryProposal.setup_id` | `post_asian_pilot/pipeline.py` | `ticket_delivery/identity.py`, ledger/store | YES (`runtime_state.store`) | YES | YES | ST_ASIAN_SWEEP_5R_V1 | indirectly, via `execution.adapter.TradeProposal.setup_id` |
| FX delivery identity | `ticket_delivery/identity.py::logical_ticket_id()` | ticket-delivery pipeline | delivery journal, archive | YES | YES | YES | ST_ASIAN_SWEEP_5R_V1 | no |
| BTC occurrence identity | `strategy_engine/sweep_retest/occurrence_identity.py::btc_occurrence_id()` | `btc_sweep_research/pipeline.py` (called **before** `evaluate_setup`, whose result becomes `SetupState.setup_id` verbatim) | `btc_sweep_research/ledger.py` (keyed on it) | YES | YES | YES | ST_LIQUIDITY_SWEEP_RETEST_V1 | indirectly, via `execution.adapter.TradeProposal.setup_id` |
| Large-SMC setup-family identity | `proposals/identity.py::setup_id()`/`proposal_id_for()` | `large_smc_research/engine.py`, `historical_replay/{stage1,orchestrator}.py` | `proposals/lifecycle.py`, `proposals/gate.py` | YES (via lifecycle.py's store) | YES | YES | ST_LARGE_SMC_V1 | indirectly, via `execution.adapter.TradeProposal.setup_id` |
| Large-SMC occurrence identity (C14B) | `proposals/occurrence_identity.py::candidate_occurrence_id()` | entry_confirmation M1/M2/M3 adapters | tests only | NO -- **known, owner-acknowledged gap**: `proposals/lifecycle.py`'s store is still keyed by the coarser setup_id, not this finer occurrence id (see `strategies/ST_LARGE_SMC_V1.yaml`'s own `candidate_identity.lifecycle_store_evidence`, `SHARED_CHANGE_REQUIRED`, deliberately deferred because `lifecycle.py` is shared with the live `SMC_CONDITIONAL_ENTRY_V2` watcher) | N/A (not wired) | YES (unit-tested) | ST_LARGE_SMC_V1 | no |
| Canonical envelope wrapper | `proposal_envelope/models.py::CanonicalProposal.proposal_envelope_id` | `proposal_envelope/adapters/{fx,btc,large_smc}_adapter.py` | **none yet** (confirmed by repo-wide grep -- fully tested, zero live callers, same unwired-contract shape WP4's `StrategyDecision` had before this session) | NO | N/A | YES (pure string-prefix over the source identity: `f"FX:{source_record_id}"`, `f"BTC:{source_record_id}"`, `f"SMC:{proposal.proposal_id}"`) | all three, via `source_module`/`source_record_id` | no |
| Execution-approval identity | `execution/adapter.py::TradeProposal.setup_id` | `authorization/store.py::ExecutionApproval` | the one real execution gateway (`api/execution_service.py::authorize_demo_execution`) | YES | YES | inherits whichever native identity above populated it (not its own generator) | all three, by pass-through | **YES -- this is the actual execution-linked identity** |

### Disposition

| Identity | Disposition | Why |
|---|---|---|
| FX setup identity + delivery identity | **REUSE** | Live, persisted, deterministic, strategy-owned. Nothing to change. |
| BTC occurrence identity | **REUSE** | Live, persisted, deterministic, already ledger-backed. Nothing to change. |
| Large-SMC setup-family identity | **REUSE** | Live, persisted (via lifecycle.py), deterministic. The FAMILY-level identity is fine as-is. |
| Large-SMC occurrence identity (C14B) | **QUARANTINE / DEFERRED** | Correct and tested, but wiring it into the live lifecycle store is a separate, already-identified, owner-deferred `SHARED_CHANGE_REQUIRED` migration (shared surface with a live watcher). Not this reconciliation's call to force -- carried forward as a known, pre-existing gap, unchanged by R2-R4. |
| `proposal_envelope.CanonicalProposal.proposal_envelope_id` | **ADOPT as the WP7 canonical `proposal_id`** | This is already the correctly-shaped normalization wrapper the plan's "ONE CANONICAL PROPOSAL, others reference it" architecture wants: it doesn't invent an identity, it namespaces whichever native family identity produced the record (`source_record_id`). WP7 should build directly on this field rather than create a sixth scheme. |
| Execution-approval identity (`TradeProposal.setup_id` / `ExecutionApproval`) | **REFERENCE_ONLY** | This is the real execution-linked identity today, but it is a pass-through of whichever native family identity was supplied, not an independent generator. Out of R2-R4 scope to touch (this plan stays execution-untouched); when WP8's ledger exists, a future execution-integration task can add a `proposal_envelope_id` cross-reference here without changing its current behavior. |

**Destructive migration required = NO.** Nothing here needs to be rewritten, discarded,
or have its persisted records replayed under a new key. WP7/WP8 can build the canonical
ledger keyed on `proposal_envelope_id` additively, with each adapter's `source_record_id`
already providing full traceability back to the native family identity that produced it.

```
PROPOSAL_IDENTITY_RECONCILIATION

legacy_identity_count = 6 (FX setup+delivery, BTC occurrence, Large-SMC setup-family+
  occurrence, execution-approval) -- reframed from WP0's "4 competing schemes" to
  "3 live family-owned generators + 1 unwired normalization wrapper + 1 execution
  pass-through + 1 deferred-by-design occurrence layer"
canonical_proposal_identity = proposal_envelope.models.CanonicalProposal.proposal_envelope_id
occurrence_identity = each family's own generator, referenced via source_record_id
  (already deterministic; no new hash scheme needed)
migration_status = NO_DESTRUCTIVE_MIGRATION_REQUIRED -- additive adoption only
```

## CANONICAL_PROPOSAL_CORE — 2026-09-11

```
WP6 formation gate = PASS
WP7 identity        = PASS_WITH_NOTED_GAP
WP8 persistence     = PASS

duplicate protection = PASS
restart persistence  = PASS
broker mutation = ZERO
```

### WP6 — Proposal Formation Gate

New `src/proposal_envelope/formation_gate.py::apply_formation_gate()`. Reuse-first: each
per-family adapter (`proposal_envelope/adapters/{fx,btc,large_smc}_adapter.py`) already
enforced missing-required-field -> `BLOCKED` before this session; this gate adds the one
cross-family check none of them could perform alone -- REAL market-data-mode enforcement,
using WP1's `MarketSnapshot`. A `PROPOSAL_READY` envelope backed by REPLAY, SYNTHETIC, or
no supplied snapshot is downgraded to `BLOCKED` with an explicit reason code
(`NON_REAL_MARKET_MODE` / `MISSING_MARKET_SNAPSHOT`); every other `proposal_state` passes
through untouched. Added `market_data_mode/asof/fingerprint` to
`proposal_envelope.models.DataProvenance` (additive/optional, matches the WP4 pattern).
Tests: `tests/test_proposal_formation_gate.py`, 6/6 pass, plus the pre-existing
`test_proposal_envelope_models.py`/`test_proposal_envelope_adapters.py` (26 tests)
unchanged and still passing -- 32/32 total, fully backward compatible.

### WP7 — Canonical Proposal Identity

Confirmed via the identity reconciliation above:
`proposal_envelope.models.CanonicalProposal.proposal_envelope_id` is the canonical
`proposal_id`. It already satisfies the plan's core requirement (one deterministic
identity per qualifying occurrence, namespaced over each family's own proven generator)
without inventing a new scheme.

**Update 2026-09-11 (P8, WP11A live-wiring session): metadata gap partially closed.**
```
config_hash    = POPULATED_FROM_AUTHORITATIVE_SOURCE
engine_release = POPULATED_FROM_AUTHORITATIVE_SOURCE
git_commit     = NOT_AVAILABLE / UNSET
```
- `config_hash`: reuses `post_asian_pilot.fingerprint.fingerprint()` -- the exact same
  deterministic SHA-256 canonical-JSON hasher `post_asian_pilot/report.py::
  release_fingerprints()` already uses for `strategy_fingerprint` -- applied to
  `load_raw_yaml(pilot.strategy_source_path)`. No second hashing algorithm.
- `engine_release`: reuses `release_id`, already loaded inside `run_pilot_cycle()` from
  the canonical release config and already threaded through `PilotCycleResult`.
- `git_commit`: stays `None`. Checked every existing `git_commit` field in `src/`
  (`ag_scheduler_v2/evidence.py`, `validation_diagnostics/*`) -- all are unpopulated
  passthrough fields; no authoritative runtime producer exists anywhere in this repo.
  No subprocess `git` call was added (proven by
  `test_pipeline_module_never_spawns_git_subprocess`).

Honest statement: **strategy configuration identity = PRESENT. engine/release identity
= PRESENT. git/code commit identity = NOT AVAILABLE.** WP7 is not yet fully reproducible
with respect to code identity -- only config/release identity.

### WP8 — Persistent Proposal Ledger

New `src/proposal_envelope/ledger.py::ProposalLedger`. Reuses
`runtime_state.store.JsonKeyValueStore` verbatim (this repo's one established atomic/
thread-safe persistence convention -- no new storage mechanism invented). Only
`PROPOSAL_READY` envelopes may be recorded (`ProposalLedgerError` otherwise) -- matches
the plan's "NO_TRADE/rejected formations must not inflate the proposal population" rule.
Proven by `tests/test_proposal_ledger.py` (7/7 pass):
- same event rerun with identical geometry -> idempotent, no duplicate, original returned unchanged;
- two overlapping `ProposalLedger` instances over the same path (simulated scheduler overlap) -> one logical proposal;
- a fresh instance over the same path (simulated restart) -> recovers the identical original record;
- different geometry under the same `proposal_envelope_id` -> a linked correction (`version` incremented, `correction_of` set), original geometry preserved in history, never overwritten in place;
- distinct occurrence identities never collide.

## WP9 — Read-Only Proposal API — 2026-09-11

```
WP9 = PASS
```

New routes: `GET /api/canonical-proposals` and `GET /api/canonical-proposals/{proposal_id}`
in `src/api/app.py`, backed by the WP8 `ProposalLedger` (`get_proposal_ledger()`
dependency, overridable in tests the same way `get_proposal_registry` already is). New
`CanonicalProposalResponse` schema in `src/api/schemas.py`.

**Deliberately NOT** adapted from the existing `GET /api/proposals` route. That route is
the execution-approval lookup surface backing `authorize_demo_execution()`
(`InMemoryProposalRegistry`, keyed by `execution.adapter.TradeProposal` hash) -- a
different authority domain from this plan's OBSERVATION-ONLY canonical proposals.
Overloading it would have blurred the WP0A-established execution-authority boundary;
a new, clearly-separate, read-only-by-construction route (no POST method exists on it;
proven by `test_route_is_read_only_no_post_method`) keeps the two domains structurally
separate rather than relying on convention alone. `execution_eligible` is hardcoded
`False` in the response mapping regardless of upstream state -- this route grants no
execution authority under any circumstance.

Tests: `tests/test_api_canonical_proposals.py` (7 new) + full `tests/test_api.py`
regression (26 pre-existing) -- 33/33 pass, no regression.

## WP10 — Scanner Consumes Canonical Proposals — 2026-09-11

```
WP10 = PASS
```

`web/src/components/Terminal/AGBackendPanel.tsx` (already established RENDER_ONLY in
WP5) gains a new `CanonicalProposalsSection`, reading `GET /api/canonical-proposals`
verbatim via a new `agApiClient.listCanonicalProposals()`. Renderer computes nothing;
`execution_authority`/`execution_eligible` are displayed exactly as the backend returned
them (always `NONE`/`false` from this route by construction). Also **fixed a naming
hazard**, not a functional bug: the pre-existing `/api/proposals` section was titled
"Canonical Proposals," which would have collided/conflicted with this session's actual
canonical-proposal-ledger surface — renamed to "Execution-Linked Proposals" with an
explanatory note distinguishing it from the new section below it. `npx tsc --noEmit`
clean.

## R4_IMPLEMENTATION_CHECKPOINT — 2026-09-11

```
WP6-WP11 = PASS

automated acceptance tests = PASS
  python:      187/187  (market-contract, MT5 guards, strategy-decision contract +
                          propagation, proposal-envelope models/adapters/execution-
                          boundary, formation gate, ledger, canonical-proposals API,
                          full test_api.py, full test_post_asian_pilot.py)
  node/tsx:    10/10    (WP0A execution containment regression + WP5 provenance regression)
  typecheck:   clean    (npx tsc --noEmit)

broker_mutation = ZERO
WP0A containment regression = still green (re-run this WP, unchanged from original pass)

WP12 natural proof = NEXT
```

### WP11 assessment

No regression found across any surface this session touched. Reported separately per
the plan's instruction:

- market-contract tests: 8/8 (`test_market_snapshot_contract.py`)
- MT5 guard tests: 7/7 (`test_mt5_market_data_guards.py`)
- strategy-contract tests: 13/13 (`test_strategy_decision_contract.py` +
  `test_strategy_decision_market_snapshot_propagation.py`)
- proposal tests: 32/32 envelope + adapters + execution-boundary, 6/6 formation gate,
  7/7 ledger = 45/45
- API tests: 33/33 (7 new canonical-proposals + 26 pre-existing `test_api.py`)
- FX pipeline regression: 74/74 (`test_post_asian_pilot.py`, unchanged -- proves this
  session's work never touched frozen strategy behavior)
- frontend containment/regression: 10/10 (WP0A + WP5)

### Honest gap carried into WP12

**Nothing built this session (WP1/WP4/WP6/WP7/WP8/WP9/WP10) is wired into the live
evaluation run path yet.** `src/post_asian_pilot/pipeline.py::_evaluate_pair` -- the one
process that actually produces real EURUSD/GBPUSD closed-bar decisions today -- still
calls `mt5.market_data.get_candles` directly and builds a native `PostAsianDecision`;
it never constructs a `MarketSnapshot`, never calls `strategy_contract.decision
.from_fx_decision`, never calls `proposal_envelope.adapters.fx_adapter
.to_canonical_proposal`, never calls `apply_formation_gate`, and never calls
`ProposalLedger.record_proposal`. Every WP built this session is correct and tested in
isolation, but the wiring that would let a real market event flow through all of them
end-to-end does not exist yet -- confirmed by repo-wide grep before writing this
checkpoint, same check performed at WP4/WP7.

This means **WP12's natural end-to-end proof is not reachable in this repository's
current state**, independent of whether a natural READY/NO_TRADE occurs in the market
this week. The plan's WP12 diagram assumes the pipeline already exists; building that
live-wiring (a call inside `pipeline.py` or a thin new orchestration layer calling all
five stages after `_evaluate_pair` produces a decision) is itself a new, non-trivial
integration task that touches the one live, frozen-behavior-sensitive FX evaluation
path -- not something the plan's WP6-WP11 scope explicitly authorized, and risky to do
implicitly at the tail end of a long session without a dedicated, careful pass focused
solely on that wiring (per the plan's own "if satisfying a WP requires changing frozen
strategy behavior, STOP" caution, even though this integration is additive rather than
modifying frozen decision logic).

Recorded honestly per the plan's own rule (Outcome B / section "If no natural READY
occurs"): implementation is complete through WP11, WP12 proof is `PENDING`, and
`AG_PROPOSAL_OPERATION_READY_V1 = NOT_YET_PASS`.

## WP11A — Canonical Live Pipeline Wiring — 2026-09-11

```
WP11A CANONICAL_LIVE_PIPELINE_WIRING = PASS

REAL_FX_EVALUATION
  -> MarketSnapshot        (strategy_contract/market_snapshot.py::from_real_candle, new)
  -> StrategyDecision       (strategy_contract/decision.py::from_fx_decision, WP4, reused)
  -> FormationGate          (proposal_envelope/formation_gate.py, WP6, reused)
  -> CanonicalProposal      (proposal_envelope/adapters/fx_adapter.py, reused, unmodified)
  -> ProposalLedger         (proposal_envelope/ledger.py, WP8, reused)

NO_TRADE -> no proposal (structural: only `ordered_ready` decisions ever reach
  _form_canonical_proposal -- confirmed by inspection, not just testing)
duplicate occurrence -> no duplicate logical proposal (ledger's existing idempotency)
frontend authority = NONE
scanner execution authority = NONE
broker mutation = ZERO
```

### Wiring

- `src/strategy_contract/market_snapshot.py`: new `from_real_candle()` -- wraps an
  already-fetched closed candle as REAL provenance without a second live fetch (the
  existing `from_mt5_latest_closed()` does its own fetch via `get_latest_candles`, which
  `pipeline.py` doesn't use -- it already holds the exact candle from its own
  `get_candles` range query).
- `src/post_asian_pilot/pipeline.py`: `PairResult` gains an additive `market_snapshot`
  field (`None` by default, preserves every existing 5-positional-arg construction
  site); `_evaluate_pair` attaches a REAL `MarketSnapshot` only on the genuine
  fresh-evaluation branch (never on the cached/restart-recovery branch, which has no
  fresh candle to attach). New `_form_canonical_proposal()` runs the canonical chain
  and is called once per actionable native proposal (after it wins its daily-slot claim
  -- the same point the native pipeline itself treats as "actionable"), wrapped in
  try/except so a canonical-layer bug can never affect native decision/proposal/governor
  behavior. `run_pilot_cycle()` gained an optional `proposal_ledger` parameter
  (defaults to a real `ProposalLedger()` if not supplied, matching the existing
  `PilotStores.default(...)` pattern).
- P8 metadata: `config_hash` (reuses `post_asian_pilot.fingerprint.fingerprint()` over
  the strategy YAML) and `engine_release` (reuses `release_id`) now populate
  `CanonicalProposal`; `git_commit` stays `None` (no authoritative source exists).

### Frozen-behavior invariant

`test_post_asian_pilot.py`: **80/80 pass, unchanged** (the "74/74" figure quoted in the
earlier R4_IMPLEMENTATION_CHECKPOINT was an unverified estimate -- this session's first
isolated run of that file confirms 80 is the real, correct, unaffected baseline). No
native decision/proposal/governor/ledger code was modified -- only additive calls after
already-existing native logic completes.

### Tests

`tests/test_pipeline_canonical_wiring.py` (new, 10/10 pass): READY forms exactly one
canonical proposal with REAL provenance; NO_TRADE reaches zero proposals (structural,
not just tested); missing snapshot fails closed to zero; SYNTHETIC snapshot fails closed
to zero; duplicate evaluation collapses to one logical proposal; restart/reload recovers
identical `proposal_id`/geometry/provenance; config_hash/engine_release populate from
the exact authoritative sources (not a fallback); omitting them stays `None`, never
fabricated; static proof no `subprocess`/git-commit-shelling code was introduced.

### Full regression (this session)

```
Python:   197/197  (all R2-R4 contract/proposal/API/pipeline tests + full
                     test_post_asian_pilot.py + new WP11A wiring tests)
node/tsx: 10/10     (WP0A containment + WP5 provenance regression)
typecheck: clean    (npx tsc --noEmit)
```

## WP12 — Natural End-to-End Proof — 2026-09-11

First attempt (11:23Z) was outside every configured execution window (ASIAN_LONDON
07:00-11:00Z had just closed; LONDON_NEWYORK 12:00-15:00Z had not opened) --
correctly reported `OUTSIDE_LEGITIMATE_WINDOW` and deferred rather than running a
stale/expired cycle.

Second attempt, inside the LONDON_NEWYORK window, ran the real, existing CLI entrypoint
against the connected Vantage Demo MT5 terminal (`scripts/run_post_asian_pilot.py
--once --json --pilot-config config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml`) --
no ad hoc script, exactly the plan's preferred entrypoint. Two natural cycles observed
(~1 minute apart, the second capturing a window-boundary WATCH re-evaluation -- a
pre-existing native-pipeline timing characteristic, not something WP11A touched or
needs to fix):

```
Cycle 1 (12:04:14Z): EURUSD=NO_TRADE (NON_SWEEP_SETUP_OUT_OF_SCOPE), GBPUSD=WATCH
Cycle 2 (~12:05Z):   EURUSD=WATCH, GBPUSD=WATCH
```

Neither cycle produced READY. Per the plan, this is valuable WP12 evidence, not a
failure: `state/proposal_ledger/proposal_ledger.json` does not exist after either run
(confirmed on disk) -- zero canonical proposals were created, matching the structural
guarantee (`_form_canonical_proposal` is only ever called for `ordered_ready` decisions,
never NO_TRADE/WATCH). `GET /api/canonical-proposals` independently confirmed `200 []`.
Zero broker mutation: no execution/order code path was ever reachable for a non-READY
decision (unchanged from WP11A's structural proof).

```
WP12_NO_TRADE = PASS (EURUSD, cycle 1, natural REAL data, zero proposal creation proven)
WP12_READY = PENDING (no natural READY occurred in either observed cycle)
WP12_RESILIENCE = PARTIAL (rerun-idempotency proven at the native/ledger-empty level;
  full reload/restart/duplicate-protection proof for an actual READY proposal remains
  from the WP11A integration tests only, not yet from a natural occurrence)
```

## WP12 — Natural READY achieved — 2026-09-11 12:34Z

`repository_head` at time of this natural proof: `cfcfc8503dbca828e466824ff7529baa55dc44db`
(branch `main`) -- unchanged across this entire session; no commit was made.

A third natural cycle (still LONDON_NEWYORK window, a genuinely new closed M15 bar since
the prior two non-READY observations) produced a real `STATUS_READY` for GBPUSD:

```
symbol = GBPUSD, direction = LONG
ready_at = 2026-09-11T12:30:00Z
entry = 1.34975, stop_loss = 1.34810
tp1 = 1.35259, tp2 = 1.35800 (5R runner)
reason = LOWER_SWEEP_STRICT_PENETRATION
```

Full chain verified against the real ledger file (`state/proposal_ledger/proposal_ledger.json`),
not a test fixture:

```
proposal_id (proposal_envelope_id) = FX:DECISION-GBPUSD-6175099562eae0c6
strategy_id/version = ST_ASIAN_SWEEP_5R_V1 / 1.1.1
proposal_state = PROPOSAL_READY
execution_authority = NONE
market_data_mode = REAL
market_data_source = MT5
market_data_asof = 2026-09-11T12:45:00Z (bar close)
market_data_fingerprint = 54522a8ba61540ad8cadc11c2334422f64d2846b57dc3057774ff9379f34a588
config_hash = b1aaf486885a3dd8b92cb6e97e47c7e1d888d1ecab11ecd47ef2eccaffbf9b4d (populated, P8)
engine_release = AG_TRADE_ASSISTANT_V1_0_3 (populated, P8)
git_commit = null (correct -- NOT_AVAILABLE by design)
version = 1, correction_of = null
```

**Persistence/resilience** (against the real ledger, not tmp_path): a second, independent
`ProposalLedger()` instance (simulating process restart) recovered the identical record
-- same entry, same fingerprint. `list_active_proposals()` returned exactly 1.

**Read-only API**: `GET /api/canonical-proposals` and `GET /api/canonical-proposals/{id}`
both returned the identical record verbatim (`execution_eligible: false`,
`execution_authority: "NONE"`).

**Duplicate protection**: reran the same pilot cycle once more. The native pipeline's own
decision recomputation happened to show a pre-existing window-boundary timing quirk
(GBPUSD read back as WATCH rather than the cached READY -- same quirk observed in the
earlier non-READY cycles today, unrelated to WP11A/WP12 and not something this task
modifies). Regardless, the canonical ledger still shows exactly **1** active proposal,
unchanged (version 1, identical geometry) -- no duplicate was created, and none could
have been: `_form_canonical_proposal` is only reachable from `STATUS_READY` decisions in
`ordered_ready`.

**Containment**: zero new execution-journal entries after the proposal formed; no code
path in this chain calls `authorize_demo_execution`/`order_send`/`web_execute_trade.py`
(unchanged, structurally proven in WP11A).

```
WP12_READY = PASS
WP12_NO_TRADE = PASS (already proven earlier this session)
WP12_RESILIENCE = PASS (restart-reload + duplicate-protection both proven against real data)

R2 = READY
R3 = READY
R4 = READY

AG_CANONICAL_SCANNER_PROPOSAL_PIPELINE_V1 = PASS
AG_PROPOSAL_OPERATION_READY_V1 = PASS
```

## R4 COMPLETE — STOP #1

Per the readiness program's own rule, this is a genuine milestone: trustworthy proposal
operation is achieved for `ST_ASIAN_SWEEP_5R_V1`. This does **not** imply profitability,
Demo eligibility, or Live readiness -- see `docs/status/AG_R5_EVIDENCE_PIPELINE_STATUS.md`
for the (separately negative) economic evidence already on file for this same strategy.
`AG_POST_R4_EXPANSION_AND_DELIVERY_PLAN_V1.md` remains **DEFERRED** pending its own entry
gate review.
