# AG Edge + AI Runtime V1 — Implementation Plan

Status: PLANNED / NOT AUTHORIZED FOR EXECUTION CHANGES  
Planning branch: `plan/edge-ai-runtime-v1`  
Planning baseline: `1a8e7c5d922ba48423dca1b7858f8895afe0d66f`  
Baseline tree: `53b54053283f58fe7f34a898808212275c725768`

## 1. Objective

Restructure AG Profit Trading so the owner PC is a lightweight trusted trading edge:

```text
MT5 indicators -> Owner Edge Agent -> deterministic strategy/funnel -> Control API
                                                        |
                                                ChatGPT / Claude
                                                        |
                                                      Owner
                                                        |
                                               explicit confirmation
                                                        |
                                            Owner Edge Agent -> MT5
```

The migration is architectural, not a rewrite. Existing proposal, owner-decision, risk, execution containment, account guards, idempotency, reconciliation, and authorization behavior remain authoritative until a replacement component proves deterministic parity and receives independent review.

## 2. Non-negotiable invariants

- AI has zero broker execution authority.
- Only the local Owner Edge Agent may ultimately reach MT5 `order_check` / `order_send` for new orders.
- Indicators emit market facts only; never `BUY`, `SELL`, volume, risk approval, or execution commands.
- Opportunity and Proposal remain separate funnel states.
- No automatic execution.
- No live authorization expansion.
- No Demo authorization expansion as part of restructuring.
- No strategy semantic change disguised as architecture work.
- No risk-policy change disguised as architecture work.
- Historical replay, backtests, optimization, and Virtual Demo are not production-runtime dependencies.
- Existing runtime is not deleted until replacement parity and rollback evidence exist.
- One writer per branch/worktree; immutable baselines; bounded work packages; independent audit at security-sensitive gates.

## 3. Target repository architecture

```text
apps/
  control-api/
  owner-edge/
  web/                    # optional operational/debug UI

packages/
  contracts/
  strategy-core/
  risk-engine/
  execution-core/

mt5/
  indicators/
  expert/
  include/

research/
  backtests/
  replay/
  virtual_demo/
  optimization/
  experiments/
  reports/

strategies/
config/
governance/
tests/
docs/
```

The existing `src/`, `scripts/`, and `web/` runtime remain intact during the foundation phases. Migration is adapter-first, then parity-proven replacement.

## 4. Canonical contracts

Freeze these before moving implementation:

```text
MarketState
  -> Opportunity
  -> ProposalEligibilityDecision
  -> Proposal
  -> OwnerDecision
  -> ExecutionRequest
  -> ExecutionResult
```

Supporting contract: `AccountState`.

Every applicable contract must carry stable identity/provenance fields such as:

- `schema_version`
- `event_id`
- `created_at`
- `symbol`
- `source`
- `correlation_id`
- `semantic_hash`

Contracts must be deterministic, serializable, versioned, fail-closed on malformed/non-finite values, and independently testable.

## 5. Runtime authority matrix

| Component | Read market/account | Evaluate strategy | Evaluate risk | Record owner decision | Broker mutation |
|---|---:|---:|---:|---:|---:|
| MT5 indicators | YES | NO | NO | NO | NO |
| Owner Edge Agent | YES | NO* | final safety revalidation only | consume/verify | YES, gated |
| Strategy Core | facts only | YES | NO | NO | NO |
| Risk Engine | account/proposal | NO | YES | NO | NO |
| Control API | persisted state | NO | NO | YES | NO |
| ChatGPT / Claude | authorized API views | advisory only | advisory explanation only | proxy explicit owner action only | NO |
| Research | historical/replay data | YES | research only | NO | NO |

`*` Edge may verify frozen decision identity/contract invariants but must not invent a new strategy decision.

## 6. Phase sequence

### P0 — Migration baseline freeze

Do not assume this planning branch is the final implementation baseline. Before implementation, reconcile the latest accepted Gate-2 state and explicitly select the migration base SHA.

Record:
- base commit and tree hash;
- baseline tests and known failures;
- environment-only failures;
- strategy registry state;
- Demo/Live authorization state;
- known broker mutation surfaces;
- owner-decision and execution route identities.

Exit: `ARCH_BASELINE_FROZEN = PASS`.

### P1 — Contracts V1

Create `packages/contracts/` with versioned schemas for MarketState, Opportunity, ProposalEligibilityDecision, Proposal, OwnerDecision, ExecutionRequest, ExecutionResult, AccountState, and semantic errors.

Required tests:
- serialization round-trip;
- deterministic semantic hash;
- non-finite rejection;
- symbol/source mismatch rejection where relevant;
- immutable identity fields;
- schema-version rejection/compatibility behavior;
- timestamp/freshness primitives.

Exit: `CONTRACTS_V1_FROZEN = PASS`.

### P2 — Architecture shell

Create the target directory shell without moving/deleting the existing runtime. Add import/dependency boundary tests so broker libraries cannot leak into AI/control/strategy packages.

Exit:
- `NEW_ARCH_SHELL_READY = PASS`
- `OLD_RUNTIME_UNCHANGED = PASS`
- `BROKER_CALL_DELTA = 0`
- `AUTHORIZATION_DELTA = 0`

### P3 — MT5 MarketState pilot

Scope: EURUSD only; closed-bar facts; one selected strategy's minimum feature set.

Implement incrementally:
- `AG_SessionLevels.mq5`
- `AG_MarketStructure.mq5`
- `AG_Liquidity.mq5`
- `AG_SweepDetector.mq5`
- `AG_MarketState.mq5`

Optional FVG component only when required by the frozen vertical-slice strategy.

Indicators emit facts only. No order functions, risk sizing, strategy authorization, or trade direction commands.

Exit: `MT5_MARKET_STATE_EURUSD_READY = PASS`.

### P4 — Python/MQL5 deterministic parity

Feed identical closed candle blocks to the canonical Python implementation and MQL5 implementation. Compare session levels, structure, sweep/liquidity facts, timestamps, and required strategy features.

Test boundaries:
- session edges;
- DST;
- weekend gaps;
- missing bars;
- reconnect/restart;
- current/partial bar exclusion;
- symbol metadata/suffix handling;
- stale data.

Fail closed on semantic differences. Python remains canonical until parity is frozen.

Exit: `MARKET_STATE_PARITY = PASS`.

### P5 — Read-only Owner Edge Agent

Create `apps/owner-edge/` and migrate/adapt existing MT5 connection/account/symbol/deal/time capabilities behind a narrow interface. Initial mode is read-only.

Target submodules:
- `mt5_bridge/`
- `market_state/`
- `execution/`
- `safety/`
- `transport/`

No order submission is enabled in P5.

Exit: `EDGE_AGENT_READ_ONLY_READY = PASS`.

### P6 — Strategy Core extraction

Extract/adapt one strategy only into deterministic `packages/strategy-core/` + a self-contained strategy package. Input is MarketState; output is Opportunity/NoOpportunity with reason codes. No broker/account mutation access.

Exit: `ONE_STRATEGY_MARKETSTATE_PARITY = PASS`.

### P7 — Funnel preservation

Preserve:

```text
MarketState -> Strategy -> Opportunity -> ProposalEligibilityDecision -> Proposal
```

A blocked setup remains an Opportunity plus a rejected eligibility decision; it is not an executable Proposal.

Exit: `FUNNEL_SEMANTIC_PARITY = PASS`.

### P8 — Risk Engine extraction

Centralize stop geometry, finite-value validation, pilot risk policy, aggregate open-risk policy, volume calculation, broker metadata consistency, and risk reason codes.

Inputs include ProposalCandidate/Opportunity context, AccountState, StrategyPolicy, PilotPolicy, and BrokerMetadata. Output is deterministic RiskDecision / eligibility evidence.

Exit: `RISK_ENGINE_PARITY = PASS`.

### P9 — Lightweight Control API

Implement state coordination only. Start local-first; SQLite is sufficient unless measured requirements prove otherwise.

Minimum surfaces:
- `GET /v1/market-state`
- `GET /v1/opportunities`
- `GET /v1/proposals`
- `GET /v1/account`
- `POST /v1/proposals/{id}/owner-decision`
- `GET /v1/executions/{id}`
- `GET /v1/strategies/{id}`

The API cannot call MT5 directly.

Exit: `CONTROL_API_READY = PASS`.

### P10 — ChatGPT / Claude interface

Expose narrow analytical tools for market state, opportunities, proposals, account state, strategy evidence, and execution results. An owner-decision action may only record/proxy an explicit owner action under the existing authentication model.

Never expose arbitrary order submission, risk-policy mutation, authorization mutation, or raw broker credentials.

Exit: `AI_INTERFACE_CONTAINED = PASS`.

### P11 — Owner-confirmed Demo E2E

Only after P0-P10 pass:

```text
Proposal -> AI/UI presentation -> explicit owner confirm -> OwnerDecision
-> ExecutionRequest -> Edge final guards -> MT5 Demo -> ExecutionResult -> reconciliation
```

Edge final guards must include proposal identity/freshness, explicit owner authorization, account identity/Demo classification, symbol metadata, finite entry/SL, stop geometry, strategy/pilot risk, aggregate risk, volume, idempotency/duplicate state, and execution authorization.

No Live execution.

Exit: `EDGE_DEMO_E2E = PASS`.

### P12 — Research separation

Move/reclassify replay, backtests, Virtual Demo, experiments, optimization, and heavy datasets as research-only dependencies. Do not alter their evidence semantics during the move.

Exit: `RESEARCH_NOT_RUNTIME_DEPENDENCY = PASS`.

### P13 — Event-driven runtime

Replace aggressive polling only where parity is proven. Prefer closed-bar MarketState events and account/order/position change events. Preserve restart safety, exactly-once/idempotent behavior, and reconciliation.

Exit: `EVENT_RUNTIME_PARITY = PASS` plus measured resource comparison.

### P14 — Frontend optionalization

Make local Vite/React an optional debug/administration surface, not a required trading runtime dependency. Preserve a deterministic non-AI operational path for emergency/debug use.

Exit: `FRONTEND_OPTIONAL = PASS`.

### P15 — Production PC profile

Target normal trading-hours footprint:
1. MetaTrader 5 terminal;
2. AG Owner Edge Agent;
3. browser only when the owner wants ChatGPT/Claude/UI interaction.

Record CPU, RAM, process count, restart behavior, and offline behavior against the pre-migration baseline.

Exit: `LIGHTWEIGHT_OWNER_PC_PROFILE = PASS`.

### P16 — Multi-symbol expansion

Sequence: EURUSD -> GBPUSD -> USDJPY -> XAUUSD. Each symbol requires MarketState parity, broker metadata tests, and strategy/risk compatibility before enabling the next.

### P17 — Multi-strategy expansion

Add strategies one at a time against the normalized MarketState contract. Do not allow strategy-specific market-data polling to re-enter production runtime without explicit architecture review.

### P18 — Cloud deployment

Cloud is last, not a prerequisite. Move Control API/state coordination only after local E2E is stable. Edge remains the trusted broker boundary. On connectivity loss, remote execution requests fail closed; local broker/account reconciliation remains safe; buffered non-mutating state may reconcile after reconnect.

## 7. Parallel workstreams

After P0/P1 contract freeze:

- Lane A — MT5/MQL5: P3 -> P4.
- Lane B — Platform: P2 -> P5 and preparatory package work that does not depend on unproven MT5 semantics.
- Lane C — Independent audit: contract review, parity review, safety-boundary audit, regression classification.

Integration occurs only at explicit frozen SHAs. One writer per worktree/branch.

## 8. Bounded PR plan

1. PR-A0 — Migration baseline + architecture ADR
2. PR-A1 — Contracts V1
3. PR-A2 — Repository shell + dependency boundaries
4. PR-M1 — SessionLevels
5. PR-M2 — Structure/Liquidity/Sweep facts
6. PR-M3 — MarketState aggregator
7. PR-M4 — Python/MQL parity harness
8. PR-E1 — Read-only Edge Agent
9. PR-S1 — Strategy-core vertical slice
10. PR-F1 — Opportunity/Proposal funnel adapter
11. PR-R1 — Risk-engine extraction
12. PR-E2 — Edge execution guard pipeline
13. PR-C1 — Control API
14. PR-AI1 — AI analytical interface
15. PR-X1 — Owner-confirmed Demo E2E
16. PR-RS1 — Research separation
17. PR-RT1 — Event-driven runtime
18. PR-UI1 — Frontend optionalization
19. PR-P1 — Production runtime profile

Every PR must be independently reversible and must state: frozen base SHA, allowed files, prohibited changes, focused tests, regression evidence, authorization delta, broker-call delta, and rollback instructions.

## 9. Immediate implementation mission

The first implementation mission is P0 + P1 + P2 only. Do not implement MQL5 indicators or alter execution behavior in this mission.

Required deliverables:
1. select/freeze the accepted migration baseline after reconciling current Gate-2 work;
2. architecture ADR;
3. runtime authority matrix;
4. canonical Contracts V1;
5. contract validation tests;
6. architecture shell;
7. dependency/boundary tests;
8. proof existing runtime behavior/authorization is unchanged;
9. migration status document;
10. independent audit handoff.

Stop after P0/P1/P2 for independent audit.

## 10. Definition of architectural success

The migration is complete only when normal trading requires no local research/development stack and the owner PC can operate with MT5 + Owner Edge Agent, while ChatGPT/Claude remain optional analytical/control interfaces. Broker execution remains deterministic, local, owner-confirmed, account-guarded, risk-guarded, idempotent, auditable, and fail-closed.
