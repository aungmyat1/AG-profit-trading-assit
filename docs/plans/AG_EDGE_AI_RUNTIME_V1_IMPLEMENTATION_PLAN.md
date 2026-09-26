# AG Edge + AI Runtime V1 — Architecture & Implementation Roadmap

Status: ACTIVE ROADMAP — FOUNDATION REMEDIATION REQUIRED  
Planning branch: `plan/edge-ai-runtime-v1`  
Owner-selected migration baseline: `1a8e7c5d922ba48423dca1b7858f8895afe0d66f`  
Baseline tree: `53b54053283f58fe7f34a898808212275c725768`  
Foundation candidate: `59701c4be377ab7b4bba4d9ebcd0f58ca88deaaa` (local candidate; independent audit FAIL)  
Current gate: `P1-R1 CONTRACT INVARIANT REMEDIATION`

## 1. Objective

Restructure AG Profit Trading so the owner PC becomes a lightweight trusted trading edge while research, development, and AI analysis can run outside the broker-execution boundary.

```text
DEVELOPMENT / RESEARCH / AI
ChatGPT • Claude • Codex
          |
          | analysis / coding / audit
          v
     CONTROL API
market state / opportunities / proposals / audit
          |
          | narrow contracts/events
          v
+---------------- OWNER PC ----------------+
|                                          |
| MT5 + indicators <-> AG Owner Edge Agent |
|       |                    |             |
|  market facts         account safety     |
|                       reconciliation     |
|                       gated execution    |
+------------------------------------------+
          ^
          |
   EXPLICIT OWNER CONFIRM
```

This is an architectural migration, not a rewrite. Existing proposal, owner-decision, risk, containment, account guards, idempotency, reconciliation, and authorization behavior remain authoritative until replacement components prove parity and receive independent review.

## 2. Non-negotiable authority rules

- AI has zero broker execution authority.
- Only the local Owner Edge Agent may ultimately reach MT5 `order_check` / `order_send` for new orders.
- MT5 indicators emit deterministic market facts only; never BUY/SELL recommendations, approved volume, risk approval, owner approval, or execution commands.
- `Opportunity` and `Proposal` are different states.
- A rejected `ProposalEligibilityDecision` cannot produce an executable `Proposal`.
- No automatic execution.
- No Live authorization expansion.
- No Demo authorization expansion merely because of restructuring.
- No strategy semantic change disguised as architecture work.
- No risk-policy change disguised as architecture work.
- Research/backtest/replay/optimization workloads are not production-runtime dependencies.
- Existing runtime is not removed until replacement parity and rollback evidence exist.
- One writer per branch/worktree; immutable baselines; bounded work packages; independent audit at security-sensitive gates.

## 3. Target repository architecture

```text
apps/
  control-api/
  owner-edge/
  web/                    # optional operations/debug UI

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

During migration, existing `src/`, `scripts/`, and `web/` production runtime remain intact. Migration is adapter-first and parity-gated.

## 4. Canonical state pipeline

```text
MarketState
    -> Strategy
    -> Opportunity
    -> ProposalEligibilityDecision
         |-- REJECTED -> STOP / retain audit evidence
         `-- ACCEPTED -> Proposal
                           -> OwnerDecision
                           -> ExecutionRequest
                           -> ExecutionResult
```

Supporting contract: `AccountState`.

Every applicable contract carries stable identity/provenance such as `schema_version`, `event_id`, `created_at`, `symbol`, `source`, `correlation_id`, and `semantic_hash`.

### MarketState closed-schema rule

`MarketState` must use an explicit typed/allowlisted facts schema. Arbitrary key/value maps must not be able to encode action or approval semantics such as `recommendation=BUY`, `action=ENTER`, `risk_approved=true`, or equivalent variants.

### Proposal eligibility binding rule

A `Proposal` must be cryptographically/deterministically bound to the exact ACCEPTED eligibility decision for the same Opportunity. Rejected, mismatched, or tampered eligibility identity must make Proposal construction fail closed.

## 5. Runtime authority matrix

| Component | Read market/account | Strategy evaluation | Risk evaluation | Owner decision | Broker mutation |
|---|---:|---:|---:|---:|---:|
| MT5 indicators | YES | NO | NO | NO | NO |
| Owner Edge Agent | YES | verify only | final safety revalidation | consume/verify | YES, later gated |
| Strategy Core | facts only | YES | NO | NO | NO |
| Risk Engine | account/proposal context | NO | YES | NO | NO |
| Control API | persisted state | NO | NO | record explicit action | NO |
| ChatGPT / Claude | authorized views | advisory | advisory explanation | proxy explicit owner action only | NO |
| Research | historical/replay | research | research | NO | NO |

## 6. Current verified status

### P0 — Migration baseline freeze: PASS

Owner selected merged baseline `1a8e7c5d922ba48423dca1b7858f8895afe0d66f`. Gate-2 R3 remains a separate lineage.

### P1 — Contracts V1: REMEDIATION REQUIRED

Foundation candidate `59701c4...` passed serialization, hashing, immutability, schema, timezone, and finite-value inspection, but independent audit found two HIGH contract gaps:

- `F-01`: MarketState generic facts can encode action-like semantics (for example `recommendation=BUY`).
- `F-02`: Proposal can be constructed even when eligibility for the same Opportunity is rejected.

Therefore `CONTRACTS_V1_FROZEN = NO` until P1-R1 remediation passes independent re-audit.

### P2 — Architecture shell: PASS AS CANDIDATE

Independent audit found the candidate correctly based on the selected baseline, with protected runtime unchanged and no new broker/authorization path. This remains part of the candidate and becomes frozen only when the Foundation as a whole passes re-audit.

### Reproduced candidate validation

- 33 new tests passed.
- 58 focused regression tests passed.
- 247 broader owner-decision/execution tests passed.
- Broker-call delta: 0.
- New broker mutation surfaces: 0.
- Strategy semantic delta: 0.
- Risk-policy delta: 0.
- Authorization delta: 0.
- Demo authorization expansion: NO.
- Live authorization expansion: NO.
- AI-to-broker path introduced: NONE.
- Full backend suite: not required/run for this audit; known broad-suite/environment failures remain separate.

Current classification:

```text
P0 = PASS
P1 = REMEDIATION_R1
P2 = PASS_AS_CANDIDATE
FOUNDATION_FROZEN = NO
CURRENT_GATE = P1_R1_CONTRACT_INVARIANT_REMEDIATION
```

## 7. Immediate mission — P1-R1 Contract Invariant Remediation

Do not start P3 or P5 yet.

### F-01 remediation

Replace/constrain unrestricted MarketState generic facts with an explicit closed typed/allowlisted schema. Do not solve this with an ever-growing blacklist. Add adversarial negative tests for action, recommendation, signal, execution, order, owner approval, and risk approval semantics including nested/alternate representations where supported.

Exit requirements:

```text
MARKET_STATE_FACT_SCHEMA = CLOSED
MARKET_STATE_EXECUTION_AUTHORITY = NONE
```

### F-02 remediation

Bind Proposal creation to an immutable ACCEPTED `ProposalEligibilityDecision` for the same Opportunity. Proposal must preserve eligibility identity/hash through serialization and semantic hashing.

Required cases:

- ACCEPTED + matching Opportunity -> Proposal construction PASS.
- REJECTED -> Proposal construction FAIL.
- ACCEPTED for different Opportunity -> FAIL.
- tampered eligibility identity/hash -> FAIL.

Exit requirements:

```text
FUNNEL_SEPARATION = PASS
REJECTED_ELIGIBILITY_TO_PROPOSAL = IMPOSSIBLE
```

After local remediation commit, stop for `INDEPENDENT_FOUNDATION_R1_REAUDIT`.

## 8. Foundation freeze gate

Foundation may freeze only when the independent R1 re-audit verifies:

```text
P0_ARCH_BASELINE_FROZEN = PASS
P1_CONTRACTS_V1_FROZEN = PASS
P2_NEW_ARCH_SHELL_READY = PASS
OLD_RUNTIME_UNCHANGED = PASS
BROKER_CALL_DELTA = 0
NEW_BROKER_MUTATION_SURFACES = 0
STRATEGY_SEMANTIC_DELTA = 0
RISK_POLICY_DELTA = 0
AUTHORIZATION_DELTA = 0
DEMO_AUTHORIZATION_EXPANSION = NO
LIVE_AUTHORIZATION_EXPANSION = NO
MARKET_STATE_EXECUTION_AUTHORITY = NONE
FUNNEL_SEPARATION = PASS
```

## 9. P3 — MT5 MarketState pilot

Starts only after Foundation freeze.

Scope: EURUSD only; closed-bar facts; minimum feature set required by one frozen vertical-slice strategy.

Implement incrementally:

- `AG_SessionLevels.mq5`
- `AG_MarketStructure.mq5`
- `AG_Liquidity.mq5`
- `AG_SweepDetector.mq5`
- `AG_MarketState.mq5`

FVG is optional and added only if required by the selected strategy.

No order functions, risk sizing, strategy authorization, BUY/SELL recommendation, or trade execution semantics.

Exit: `MT5_MARKET_STATE_EURUSD_READY = PASS`.

## 10. P4 — Python/MQL5 deterministic parity

Feed identical closed candle blocks to canonical Python and MQL5 implementations and compare session levels, structure, liquidity/sweep facts, timestamps, and required features.

Boundary tests include session edges, DST, weekend gaps, missing bars, restart/reconnect, partial-bar exclusion, symbol suffix/metadata, and stale data.

Python remains canonical until parity is frozen.

Exit: `MARKET_STATE_PARITY = PASS`.

## 11. P5 — Read-only Owner Edge Agent

May begin in parallel with P3/P4 only after Foundation freeze.

Create/adapt `apps/owner-edge/` around narrow read-only MT5 interfaces for connection, account state, symbols, positions/deals, broker time, MarketState transport, and local safety state.

P5 MUST NOT enable new-order submission.

Exit: `EDGE_AGENT_READ_ONLY_READY = PASS`.

## 12. P6 — Strategy Core

Extract one strategy only. Input is normalized MarketState; output is Opportunity/NoOpportunity plus deterministic reason codes. Strategy Core has no broker/account mutation access.

Exit: `ONE_STRATEGY_MARKETSTATE_PARITY = PASS`.

## 13. P7 — Opportunity/Proposal funnel

Preserve:

```text
MarketState -> Strategy -> Opportunity -> ProposalEligibilityDecision
                                          | rejected -> STOP
                                          ` accepted -> Proposal
```

A rejected setup remains an Opportunity with rejection/audit evidence; it is not a Proposal.

Exit: `FUNNEL_SEMANTIC_PARITY = PASS`.

## 14. P8 — Risk Engine

Only after P6/P7 semantics are stable. Centralize stop geometry, finite values, pilot risk policy, aggregate open-risk policy, volume calculation, broker metadata consistency, and deterministic reason codes.

Exit: `RISK_ENGINE_PARITY = PASS`.

## 15. P9 — Lightweight Control API

Build state coordination only after contracts/funnel/Edge interfaces are stable. Start local-first; SQLite is sufficient until measured requirements prove otherwise.

Minimum surfaces:

- `GET /v1/market-state`
- `GET /v1/opportunities`
- `GET /v1/proposals`
- `GET /v1/account`
- `POST /v1/proposals/{id}/owner-decision`
- `GET /v1/executions/{id}`
- `GET /v1/strategies/{id}`

The Control API cannot call MT5 directly.

Exit: `CONTROL_API_READY = PASS`.

## 16. P10 — ChatGPT / Claude interface

Expose narrow analytical tools for market state, opportunities, proposals, account state, strategy evidence, and execution results. Owner-decision actions may only proxy an explicit authenticated owner action.

Never expose arbitrary order submission, risk-policy mutation, authorization mutation, or broker credentials.

Exit: `AI_INTERFACE_CONTAINED = PASS`.

## 17. P11 — Owner-confirmed Demo E2E

First major destination milestone:

```text
Proposal
 -> AI/UI explanation
 -> explicit Owner CONFIRM
 -> OwnerDecision
 -> ExecutionRequest
 -> Owner Edge final guards
 -> MT5 Demo order_check/order_send
 -> ExecutionResult
 -> reconciliation
```

Final Edge guards include proposal identity/freshness, explicit owner authorization, Demo account identity, symbol metadata, finite entry/SL, stop geometry, strategy/pilot risk, aggregate risk, volume, duplicate/idempotency state, and execution authorization.

No Live execution.

Exit: `FIRST_VERTICAL_SLICE_E2E = PASS` / `EDGE_DEMO_E2E = PASS`.

## 18. P12–P15 — Reduce owner-PC capacity requirements

### P12 — Research separation
Move/reclassify replay, backtests, Virtual Demo, experiments, optimization, and heavy datasets as research-only workloads. Exit: `RESEARCH_NOT_RUNTIME_DEPENDENCY = PASS`.

### P13 — Event-driven runtime
Replace aggressive polling where parity is proven. Prefer closed-bar MarketState events and account/order/position change events. Preserve restart safety, idempotency, and reconciliation. Exit: `EVENT_RUNTIME_PARITY = PASS` plus measured resource comparison.

### P14 — Frontend optionalization
Make local Vite/React an optional debug/admin surface, not a trading-runtime requirement. Preserve a deterministic non-AI fallback path. Exit: `FRONTEND_OPTIONAL = PASS`.

### P15 — Lightweight production PC profile
Target normal trading-hours footprint: MT5 + AG Owner Edge Agent; browser only on demand. Measure CPU, RAM, process count, startup/restart, reconnect, and offline behavior against the pre-migration baseline. Exit: `LIGHTWEIGHT_OWNER_PC_PROFILE = PASS`.

## 19. P16–P18 — Scale only after the vertical slice

### P16 — Multi-symbol
Sequence: EURUSD -> GBPUSD -> USDJPY -> XAUUSD. Each requires MarketState parity, broker metadata tests, and strategy/risk compatibility.

### P17 — Multi-strategy
Add strategies one at a time against normalized MarketState. Do not reintroduce strategy-specific production market-data polling without architecture review.

### P18 — Cloud deployment
Cloud is last. Move Control API/state coordination only after local E2E is stable. Owner Edge remains the trusted broker boundary. Connectivity loss must fail closed for remote execution while preserving local account/broker safety and later non-mutating state reconciliation.

## 20. Correct parallel execution model

After Foundation R1 independent re-audit PASS:

```text
                     FOUNDATION FROZEN
                            |
                +-----------+-----------+
                |                       |
                v                       v
          LANE A: P3 -> P4         LANE B: P5
          MT5 MarketState          Read-only Edge
          + parity                 preparation
                |                       |
                +-----------+-----------+
                            v
                           P6
                     Strategy Core
                            |
                           P7
                   Funnel integration
                            |
                           P8
                      Risk Engine
                            |
                           P9
                      Control API
                            |
                          P10
                    ChatGPT / Claude
                            |
                          P11
                   Owner Demo E2E
```

Do not start P8/P9 prematurely: P8 depends on stable P6/P7 semantics and P9 should consume stable contracts/Edge interfaces rather than create another reconciliation target.

Gate-2 R3 remains a separate lineage until independently accepted. Any later integration with the frozen Edge+AI foundation requires a bounded compatibility/diff audit; no automatic cherry-pick/merge is authorized by this roadmap.

## 21. Bounded PR/work-package sequence

1. PR-A0 — Migration baseline + architecture ADR
2. PR-A1 — Contracts V1
3. PR-A1-R1 — Contract invariant remediation (F-01/F-02) — CURRENT
4. PR-A2 — Repository shell + dependency boundaries
5. PR-M1 — SessionLevels
6. PR-M2 — Structure/Liquidity/Sweep facts
7. PR-M3 — MarketState aggregator
8. PR-M4 — Python/MQL parity harness
9. PR-E1 — Read-only Edge Agent
10. PR-S1 — Strategy-core vertical slice
11. PR-F1 — Opportunity/Proposal funnel adapter
12. PR-R1 — Risk-engine extraction
13. PR-C1 — Control API
14. PR-AI1 — AI analytical interface
15. PR-E2 — Edge execution guard pipeline
16. PR-X1 — Owner-confirmed Demo E2E
17. PR-RS1 — Research separation
18. PR-RT1 — Event-driven runtime
19. PR-UI1 — Frontend optionalization
20. PR-P1 — Production runtime profile

Every work package must state frozen base SHA, allowed files, prohibited changes, focused tests, regression evidence, authorization delta, broker-call delta, rollback instructions, and next audit gate.

## 22. Roadmap summary

```text
FOUNDATION
P0 Baseline Freeze                 PASS
P1 Contracts V1                    R1 REMEDIATION  <-- CURRENT
P2 Architecture Shell              PASS AS CANDIDATE
Independent Foundation Audit       FAIL (F-01/F-02)
Independent Foundation R1 Reaudit  NEXT

SENSING
P3 MT5 MarketState                 BLOCKED ON FOUNDATION FREEZE
P4 Python/MQL parity               BLOCKED ON P3

EDGE + TRADING BRAIN
P5 Read-only Owner Edge            BLOCKED ON FOUNDATION FREEZE
P6 Strategy Core                   BLOCKED ON P3/P4/P5 INTERFACES
P7 Opportunity/Proposal Funnel     BLOCKED ON P6
P8 Risk Engine                     BLOCKED ON P6/P7

CONTROL + AI + EXECUTION
P9 Control API                     BLOCKED ON STABLE CONTRACTS/EDGE
P10 ChatGPT / Claude               BLOCKED ON P9
P11 Owner-confirmed Demo E2E       BLOCKED ON P0-P10

OPTIMIZATION
P12 Research Separation            AFTER FIRST VERTICAL SLICE
P13 Event-driven Runtime           AFTER PARITY/E2E
P14 Optional Frontend              AFTER CONTROL PATH STABLE
P15 Lightweight PC Profile         AFTER P12-P14

SCALE
P16 Multi-symbol                   AFTER EURUSD VERTICAL SLICE
P17 Multi-strategy                 AFTER SINGLE STRATEGY PROVEN
P18 Cloud Deployment               LAST
```

## 23. Definition of architectural success

Normal trading should ultimately require only MT5 + Owner Edge Agent locally, with a browser/ChatGPT/Claude used on demand. Heavy research/development workloads stay outside the trading runtime. Broker execution remains deterministic, local, owner-confirmed, account-guarded, risk-guarded, idempotent, auditable, and fail-closed.
