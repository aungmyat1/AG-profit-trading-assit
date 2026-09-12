# AG Canonical R2-R4 Proposal Pipeline V1

Status: **CURRENT PRIORITY IMPLEMENTATION PLAN — PLANNING AUTHORITY ONLY**  
Recorded: **2026-09-11**  
Program: `AG_CANONICAL_SCANNER_PROPOSAL_PIPELINE_V1`  
Governing roadmap: `docs/PROJECT_ROADMAP.md`  
Objective: **Prove the real, canonical, proposal-first path before expansion**

## Outcome

Deliver the shortest authoritative path from the current observation/demo surface to
a read-only workflow in which real MT5 closed candles produce canonical backend
decisions, eligible `READY` decisions form durable proposals, and the API and scanner
render the same persisted truth.

Completion produces `AG_PROPOSAL_OPERATION_READY_V1` and then stops. It does not prove
economic edge or authorize Telegram, new symbols, crypto, Demo execution, or Live
execution.

## Authority and invariants

- The broker/feed owns market truth.
- The deterministic Python strategy engine owns decision truth.
- The proposal service and ledger own proposal identity and lifecycle.
- The frontend is a renderer and cannot derive, repair, or promote strategy output.
- AI and advisory skills may explain evidence; they cannot create `READY`, proposals,
  eligibility, or authorization.
- `market_data_mode` is explicit and immutable across snapshot, decision, proposal,
  evidence, API, and UI. Mixed-mode chains fail closed.
- All work in this plan is broker-read-only. Proposals carry
  `execution_eligible=false` and `execution_authority=NONE`.
- Frozen strategy behavior is not modified in place.

## Work method

At each work package, inspect the smallest authoritative code, contract, and tests;
classify the requirement as satisfied, partial, missing, or contradictory; reuse
compatible surfaces; implement only the gap; run focused tests; and update live-status
documentation when capability changes. If an earlier gate fails, mark dependent work
`NOT_EVALUATED` and stop.

## WP0 — Baseline reconciliation

- Map current MT5 feed, strategy decision, proposal-envelope, persistence, API,
  scanner, and evidence paths.
- Identify mock/frontend decision logic, in-memory-only state, and competing proposal
  identities.
- Freeze one ownership/dependency map and a WP1-WP12 acceptance matrix.
- Record what is reused, migrated, quarantined, or removed before coding.

Exit: no unresolved ownership conflict exists for market, decision, proposal,
evidence, or execution truth.

## R2 — Real Market Watch Ready

### WP1 — Market truth contract

Freeze a versioned `MarketSnapshot` contract containing source/venue, resolved symbol,
timeframe, closed-bar boundary, `market_data_asof`, retrieval time, fingerprint, and
`market_data_mode = REAL | REPLAY | SYNTHETIC`. Propagate the mode unchanged through
every downstream contract.

### WP2 — Real closed-candle scanner feed

- Reuse the configured Vantage Demo MT5 read-only bridge.
- Resolve and validate EURUSD and GBPUSD explicitly.
- Feed canonical closed M15 candles into the backend strategy path; add M1/context
  data only where the signed strategy requires it.
- Keep replay and synthetic fixtures available only under explicit non-real modes.

### WP3 — Fail-closed data guards

Cover stale, missing, duplicate, out-of-order, incomplete, future-dated,
timezone-ambiguous, wrong-symbol, wrong-timeframe, and disconnected-feed cases. Emit a
reason-coded data failure; never substitute synthetic data and report a real result.

R2 exit: real closed candles reach the canonical backend; timestamps and fingerprints
reproduce; guards fail closed; mode provenance is visible end to end; and zero broker
mutation occurs.

## R3 — Canonical Strategy Ready

### WP4 — Canonical `StrategyDecision`

Freeze or reconcile one versioned contract containing strategy identity, symbol,
timeframe/session, evaluation and market-data times, state, strategy-owned geometry,
reason/confirmation/invalidation, config hash, code identity, data fingerprint, and
data mode. Missing required geometry blocks proposal formation.

`READY` is exclusively a decision state. Non-ready and data-error states remain
durable evaluation evidence but do not become proposals.

### WP5 — Renderer-only frontend

- Remove or quarantine frontend/mock logic that independently qualifies setups,
  invents geometry, or promotes states.
- Render backend `READY`, `WATCHING`, `CANDIDATE`, `QUALIFYING`, `NO_TRADE`,
  `INVALIDATED`, and `DATA_ERROR` without reinterpretation.
- Label replay/synthetic output visibly and exclude it from real proposal formation.

R3 exit: the backend is the only decision authority; the UI faithfully renders real
and research modes; browser objects cannot become authoritative proposals; and frozen
strategy behavior is unchanged.

## R4 — Canonical Proposal Ready

### WP6 — Proposal Formation Gate

Require known strategy/version, `market_data_mode=REAL`, complete provenance and
fingerprint, fresh unexpired data, complete strategy-owned entry/stop/targets, and
valid risk geometry. Persist reason-coded formation-attempt evidence for rejection;
never guess missing values. This proves representability, not profitability.

### WP7 — Deterministic occurrence identity

Freeze normalization, encoding, hash algorithm, and schema version for the occurrence
key based on strategy/version, symbol, session, decision-bar close, and strategy-owned
setup identity. One occurrence retains one proposal ID across rerun, overlap, restart,
API retry, and later delivery retry.

### WP8 — Persistent proposal ledger

- Persist atomically before downstream display or delivery.
- Preserve immutable original geometry and provenance.
- Keep proposal lifecycle separate from freshness.
- Append linked corrections; never rewrite historical evidence.
- Recover safely from interruption and reject conflicting duplicate identity.

Only an accepted formation attempt creates a proposal. `NO_TRADE`, `WATCHING`, data
failures, and rejected formations remain evaluation evidence and must not inflate the
proposal population.

### WP9 — Read-only proposal API

Expose canonical list/detail endpoints backed by the ledger. Validate response schemas
and return reason-coded unavailable/error states. This plan adds no execution endpoint.

### WP10 — Scanner rendering

Render ledger-backed proposals as `OBSERVATION ONLY`, including proposal and strategy
identity, source/mode, as-of time, freshness, lifecycle, geometry, and explicit
execution authority. Reload reads backend truth rather than recreating state.

### WP11 — Reliability and boundary proof

Test restart, rerun, overlap, duplicate calls, interrupted persistence, conflicting
identity, stale transitions, malformed data, API reload, and UI refresh. Add structural
tests proving that R2-R4 cannot reach order submission.

### WP12 — Natural end-to-end proof

In the intended read-only Demo environment, capture:

- one natural EURUSD or GBPUSD closed-bar `READY` occurrence that forms exactly one
  persistent proposal, is returned by the API, and renders `OBSERVATION ONLY`;
- one natural `NO_TRADE` occurrence that renders correctly and creates no proposal;
- reload, rerun, overlap, and restart evidence preserving identity;
- source commit, strategy version, config hash, data fingerprint, proposal ID,
  timestamps, environment, and exact test results;
- proof that zero broker order was submitted.

Do not manufacture `READY`. Waiting for natural evidence is valid and does not permit
later plans to start early.

## Completion gate

Complete only when every R2-R4 gate passes automated acceptance and WP12 natural proof.
Publish the rolling-status update and dated evidence for
`AG_PROPOSAL_OPERATION_READY_V1`, then **STOP**.

The next eligible plan is `AG_POST_R4_EXPANSION_AND_DELIVERY_PLAN_V1.md`; it does not
start automatically and cannot waive an incomplete gate here.

## Explicitly out of scope

- Telegram activation or operational sends;
- USDJPY, XAUUSD, BTCUSDT, or ETHUSDT expansion;
- economic validation or strategy promotion;
- Demo or Live authorization and execution;
- unrelated UI redesign or advisory-analysis expansion.
