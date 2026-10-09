---
class: authority
state: DESIGN
owner_reviewed: 2026-10-09
review_by: 2026-11-07
---
# AG Profit Trading — Project Objective (rev 2026-10-08)

**Repository:** `aungmyat1/AG-profit-trading-assit`  
**Target branch:** `main`  
**Venue:** VT Markets MT5 Demo  
**Product phase:** PRE-EDGE  
**Owner ratification:** RATIFIED 2026-10-09 by the owner — register entry `OBJ-RATIFY-2026-10-09` in [`docs/governance/OWNER_DECISION_REGISTER.md`](governance/OWNER_DECISION_REGISTER.md). Ratification is not execution authorization; demo and live execution stay disabled.

## Objective

Every trading day, AG Profit Trading reads real market data and evaluates **logically verified** strategies across the six target instruments. For each scheduled evaluation, it delivers to the owner on Telegram either an actionable informational trade/watch ticket or a deterministic terminal reason.

The owner decides every entry. A confirmed ticket may reach the canonical **demo execution boundary only after separately recorded owner demo authorization**. Until `demo_authorized=true` is explicitly established through the governed authorization path, Confirm/Reject is decision capture only and broker execution remains a no-op/blocked path. Live real-money execution is outside this objective.

`LOGIC_VERIFIED`, `ACTIONABLE`, `EDGE_VERIFIED`, `DEMO_AUTHORIZED`, and `LIVE_AUTHORIZED` are independent states. Ticket readiness or logical verification never implies economic edge or execution authority.

## Scope

**Logical instruments:** EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, ETHUSD. These canonical names are the objective's identities. Host-observed VT Markets broker symbols are recorded in [`status/evidence/host_symbol_info_2026-10-09.json`](../status/evidence/host_symbol_info_2026-10-09.json). The canonical-to-broker symbol map is **PENDING AGP-C2-SYMMAP**; it is neither implemented nor verified, and no broker symbol is implied here.

1. **Session tickets — FX + Gold**
   - EURUSD
   - GBPUSD
   - USDJPY
   - XAUUSD
   - ASIAN → LONDON and LONDON → NEW YORK.
   - Owner-defined session windows are authoritative.
   - Each scheduled instrument/session evaluation must end in an explicit canonical terminal outcome; no forced trade is required.

2. **Crypto tickets — VT Markets CFDs (target capability)**
   - BTCUSD
   - ETHUSD
   - Daily, including weekends, at strategy-defined times.
   - This is a target production capability, not a claim that the current crypto runtime is already accepted. Venue/contract identity, market-data semantics, sizing and strategy admission must be validated before operational acceptance.
   - Intended runtime strategy: `ST_CRYPTO_CFD_SWEEP_RETEST_V1`. Admission requires Logic Gate L1–L6 evidence; it is **not admitted** today (see `strategies/registry.yaml`).

3. **Large-SMC watch / alerts — all six instruments (target capability)**
   - Use a separately versioned `ST_LARGE_SMC` strategy only after its contract/engine passes the required Logic Gate and is admitted for ticketing.
   - Delivery freshness, remaining-R and send-time usability belong to the post-signal actionability layer and must not alter frozen strategy market logic.
   - Current research/draft status does not constitute logical verification or ticket authority.

4. **Telegram owner interface**
   - Canonical-ticket delivery.
   - Complete session summaries.
   - Persistent logical-ticket deduplication across restart/retry.
   - Owner Confirm/Reject is a governed decision-capture path.
   - Confirm/Reject appends an owner decision and may hand off only to the canonical execution boundary.
   - Demo execution remains disabled/no-op unless separately recorded owner authorization enables it.
   - No Telegram control may independently bypass execution/risk/authorization gates.

## Owner decisions D1–D6

The approved V1 decisions D1–D6 stay authoritative in their dated record, [`docs/governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md`](governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md); this objective references them and does not restate or amend them. Where this objective's target differs from a dated decision, the difference is not resolved here: D2 (Telegram DEFERRED) is subject to rescission row C1, and D4/D5 (crypto perp contract, Bybit/Binance data) differ from the VT Markets CFD target above. Open rows stay in [`OWNER_DECISION_REGISTER.md`](governance/OWNER_DECISION_REGISTER.md) until the owner records them.

## Definition of Done

### Strategy admission

- Every strategy allowed to emit an owner trade/watch ticket passes Logic Gate L1–L6 and records `logic_status=VERIFIED`.
- `EDGE_VERIFIED=FALSE` (or the canonical equivalent showing economic edge is not verified) is visible on every PRE-EDGE ticket.
- Strategies at `NOT_VERIFIED`, with unresolved contract fields, or with strategy/engine divergence may be observed and diagnosed but may not be promoted to actionable ticket authority.

### Live acceptance

Complete at least one open-window acceptance run for each scope item after that scope's market-data and strategy contracts are admitted.

For each acceptance:
- real venue data is used;
- all expected evaluations reach a deterministic terminal outcome;
- silent outcomes = 0;
- invented market context = 0;
- Telegram delivery = PASS;
- duplicate owner messages = 0;
- broker mutation remains 0 unless a later, separately authorized execution acceptance explicitly changes the mission.

A live acceptance run does **not** require a trade signal. `NO_TRADE`, `INFO_ONLY`, `EXPIRED`, `BLOCKED`, `INSUFFICIENT_DATA`, and other canonical fail-closed states are valid outcomes when produced truthfully. The existing canonical outcome taxonomy is unchanged; this objective adds no terminal state.

### Automation

- The scheduler invokes the accepted evaluation → actionability → canonical-ticket → delivery pipeline without reinterpreting strategy decisions.
- Restart/retry produces no duplicate cycles or duplicate messages.
- Missing/stale/invalid data cannot be silently converted into `NO_TRADE` or `WATCH_READY`.

### Soak

- At least 10 clean scheduled cycles across the admitted FX, crypto and Large-SMC scope.
- At least 10 clean scheduled cycles **per admitted strategy**.
- Coverage includes every applicable session (ASIAN → LONDON, LONDON → NEW YORK) and, for admitted crypto, weekend days.
- Expected evaluations equal terminal evaluations.
- Silent cycles = 0.
- Duplicate owner messages = 0.
- `broker_mutations = 0` throughout the PRE-EDGE/read-only soak.

### Owner Confirm/Reject path

- Confirm/Reject is tested end-to-end with execution disabled.
- Owner decisions are append-only/auditable and bound to canonical ticket identity.
- A Confirm event cannot enable execution by itself.
- Demo execution becomes reachable only after a separately recorded owner authorization enables the governed demo authority.
- Live real-money execution remains separately gated and out of scope.

## Invariants

- Fail closed.
- No invented market context.
- No silent scheduled sessions.
- No strategy tuning to force `READY` or `WATCH_READY`.
- `NO_TRADE` is a valid successful evaluation outcome.
- Read-only missions make zero broker mutations.
- Strategy validity and delivery actionability are separate layers.
- `LOGIC_VERIFIED != EDGE_VERIFIED`.
- `WATCH_READY != EDGE_VERIFIED`.
- `EDGE_VERIFIED != DEMO_AUTHORIZED`.
- `DEMO_AUTHORIZED != LIVE_AUTHORIZED`.
- Execution stays disabled unless the owner has separately authorized the relevant execution mode.
- Strategy → strategy engine → risk/execution authority → MT5 remains the execution authority chain.

## Out of Scope / Separate Tracks

- Economic edge validation and promotion in `ag-edgelab`.
- Strategy optimization for profitability.
- Live real-money execution.
- Full production UI.
- Full 16-stage research funnel.

These tracks may progress independently but must not be used to bypass this objective's strategy, actionability or execution gates.

## Critical Path

1. **#60 Telegram delivery** — **DONE**: merged to `main` at merge commit `4012d8f` (verified 2026-10-09: `git merge-base --is-ancestor 4012d8f origin/main`).
2. **Asian Sweep Logic Gate reconciliation** — resolve L2 contract/engine divergences in a separately versioned successor; pass L1–L6 before actionable ticket admission.
3. **Crypto CFD contract + sizing** — define and validate BTCUSD/ETHUSD VT Markets CFD identity, data semantics, risk/sizing and strategy admission.
4. **Large-SMC verification on six instruments** — resolve unsigned/research-only contract fields, provide deterministic engine authority and pass the required Logic Gate before actionable ticketing.
5. **AGP-LIVE-01** — open-window real-market acceptance of the admitted pipeline, including first live Telegram delivery proof.
6. **Scheduler integration** — invoke the accepted pipeline unchanged and prove restart/retry idempotency.
7. **Telegram Confirm/Reject path, execution flag OFF** — append-only owner decisions through the canonical execution boundary with zero broker mutation.
8. **≥10-cycle operational soak** — FX + admitted crypto + admitted Large-SMC scope; no silent cycles or duplicates; broker mutations remain zero.
9. **Owner demo-authorization decision** — separate post-soak governance decision. Authorization is not implied by successful tickets, logic verification, edge status, Telegram confirmation, or soak completion.

## Current-State Boundary

This document defines the **target product objective and Definition of Done**. It does not promote current research strategies, assert economic edge, enable demo/live execution, or claim that unaccepted crypto/LSMC runtime paths are already operational. Current implementation and validation truth remains in `PROJECT_STATUS.md`, `strategies/registry.yaml`, the strategy ledger, and dated `docs/status/` evidence.
