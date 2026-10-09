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

**Logical instruments:** EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, ETHUSD. These canonical names are the objective's identities. Host-observed VT Markets broker symbols are recorded in [`status/evidence/host_symbol_info_2026-10-09.json`](../status/evidence/host_symbol_info_2026-10-09.json). That read-only capture (mission AGP-C1-HOST, `VTMarkets-Demo`, 2026-10-09T11:50:34Z) observed `EURUSD-VIP`, `GBPUSD-VIP`, `USDJPY-VIP` and `XAUUSD-VIP` at `trade_mode` FULL; unsuffixed `EURUSD`, `GBPUSD` and `USDJPY` at DISABLED; `XAUUSD.crp` hidden and DISABLED; and `BTCUSD` and `ETHUSD` at FULL. These host observations are evidence, not execution authorization. The separate versioned canonical-to-broker configuration is `config/broker_symbol_map/vt_markets_demo.yaml` (map version 1), proposed by AGP-C2-SYMMAP in [PR #109](https://github.com/aungmyat1/AG-profit-trading-assit/pull/109); evidence [`status/evidence/host_symbol_info_2026-10-09_symmap.json`](../status/evidence/host_symbol_info_2026-10-09_symmap.json), [`status/evidence/host_symbol_map_smoke_2026-10-09.txt`](../status/evidence/host_symbol_map_smoke_2026-10-09.txt).

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
   - Intended runtime strategy (owner decision D4, 2026-10-09): `ST_CRYPTO_CFD_SWEEP_RETEST_V1`. Admission requires Logic Gate L1–L6 evidence; it is **not admitted** today and the existing runtime binding is unchanged (see `strategies/registry.yaml`).

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

## Owner decisions D1–D6 (2026-10-09)

The owner approved these decisions with the ratification (register entry `OBJ-RATIFY-2026-10-09`). They are **not** the 2026-09-30 decisions D1–D8 in [`AG_V1_TWO_GOALS_OWNER_DECISIONS.md`](governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md), which share the D-numbers and remain the record of the current runtime bindings until a successor is admitted. None of the decisions below admits a strategy, changes a runtime binding or configuration, or authorizes execution.

| Decision | Content | Status / authority |
|---|---|---|
| D1 / D3 | `ST_ASIAN_SWEEP_5R_V1@1.1.2` is the intended successor for both ASIAN → LONDON and LONDON → NEW YORK. | Not admitted. The registry keeps 1.1.2 as `CANDIDATE_PENDING_OWNER_CONFIRM`, and the runtime still loads 1.1.1. Admission waits for ASW-RATIFY to pass its gates. |
| D2 | Risk 0.5% per trade. Cost warns at ≥0.10R and blocks at ≥0.25R (R = proposed entry-to-stop risk). | The only in-repo carrier is [`config/v1_tickets/crypto_cfd_ticket_policy.yaml`](../config/v1_tickets/crypto_cfd_ticket_policy.yaml), which is crypto-ticket scoped. This document changes no FX runtime risk configuration. |
| D4 | `ST_CRYPTO_CFD_SWEEP_RETEST_V1` is the intended VT Markets crypto runtime. Spread is a percent of the proposed entry-to-stop distance: below 10% OK, 10% to 20% inclusive WARN, above 20% BLOCKED. | Same policy file (`spread_ok_pct: 10`, `spread_block_pct: 20`). Admission is conditional on L1–L6 evidence; the strategy is not activated. |
| D5 | Demo authorization is per strategy and conditional on G1–G5. | G1–G5 are not yet defined in a repository record. Every `demo_authorized` stays `false`, and ratification is not execution authorization. |
| D6 | Asian Sweep `READY` tickets require D6 plus the G1/G3 prerequisites. | [`config/v1_tickets/ready_authority.yaml`](../config/v1_tickets/ready_authority.yaml) keeps `ST_ASIAN_SWEEP_5R_V1` `ready: OFF` (`READY_AUTHORITY_OFF_D6`). Re-enabling still needs explicit owner confirmation recorded in `docs/governance/`. |

The 2026-09-30 D2 ("Telegram is DEFERRED") stays subject to rescission row C1. Open rows stay in [`OWNER_DECISION_REGISTER.md`](governance/OWNER_DECISION_REGISTER.md) until the owner records them.

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
- Coverage includes each admitted strategy's applicable operating sessions (for example ASIAN → LONDON and LONDON → NEW YORK) and, for admitted crypto, applicable weekend operation.
- A cycle counts only if it meets every acceptance criterion: real market data, a canonical terminal outcome for every expected evaluation, no silent outcome, no invented context, the required Telegram delivery, restart-safe deduplication and zero broker mutations.
- No soak cycle is counted as complete in this document; completion requires dated evidence.
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

1. **#60 Telegram delivery** — **DONE**: merged to `main` at merge commit `4012d8f` (GitHub: merged 2026-10-08T13:47:14Z; verified 2026-10-09 with `git merge-base --is-ancestor 4012d8f origin/main`). Merged implementation is not host acceptance; live delivery proof remains in step 5.
2. **Asian Sweep Logic Gate reconciliation** — resolve L2 contract/engine divergences in a separately versioned successor; pass L1–L6 before actionable ticket admission. **OPEN**: D1/D3 name `ST_ASIAN_SWEEP_5R_V1@1.1.2` as the intended successor; ratification and admission (ASW-RATIFY) are not done.
3. **Crypto CFD contract + sizing** — define and validate BTCUSD/ETHUSD VT Markets CFD identity, data semantics, risk/sizing and strategy admission. **OPEN**: D4 names `ST_CRYPTO_CFD_SWEEP_RETEST_V1` (D2/D4 risk, cost and spread policy); L1–L6 admission is not done.
4. **Large-SMC verification on six instruments** — resolve unsigned/research-only contract fields, provide deterministic engine authority and pass the required Logic Gate before actionable ticketing.
5. **AGP-LIVE-01** — open-window real-market acceptance of the admitted pipeline, including first live Telegram delivery proof. Requires the canonical-to-broker symbol map (AGP-C2-SYMMAP, pending) and its host acceptance first.
6. **Scheduler integration** — invoke the accepted pipeline unchanged and prove restart/retry idempotency.
7. **Telegram Confirm/Reject path, execution flag OFF** — append-only owner decisions through the canonical execution boundary with zero broker mutation.
8. **≥10-cycle operational soak** — at least 10 clean scheduled cycles per admitted strategy across FX + admitted crypto + admitted Large-SMC scope (see Definition of Done → Soak); no silent cycles or duplicates; broker mutations remain zero.
9. **Owner demo-authorization decision** — separate post-soak governance decision. Authorization is not implied by successful tickets, logic verification, edge status, Telegram confirmation, or soak completion.

## Current-State Boundary

This document defines the **target product objective and Definition of Done**. It does not promote current research strategies, assert economic edge, enable demo/live execution, or claim that unaccepted crypto/LSMC runtime paths are already operational. Current implementation and validation truth remains in `PROJECT_STATUS.md`, `strategies/registry.yaml`, the strategy ledger, and dated `docs/status/` evidence.
