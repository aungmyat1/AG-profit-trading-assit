---
class: authority
state: DESIGN
owner_reviewed: 2026-10-12
review_by: 2026-11-07
---
# AG Profit Trading — Project Objective (rev 2026-10-12)

**Repository:** `aungmyat1/AG-profit-trading-assit`  
**Target branch:** `main`  
**Venue:** VT Markets MT5 Demo  
**Product phase:** PRE-EDGE  
**Owner ratification:** Original objective RATIFIED 2026-10-09 by the owner — register entry `OBJ-RATIFY-2026-10-09`. C14 sequencing amendment RATIFIED 2026-10-11 — register entry `C14` and [owner decision](governance/AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md). FX/Gold session coverage and crypto entry ceiling OWNER_APPROVED 2026-10-12 — register entry `AGP-OD1012-SESSION-CRYPTO` and [owner decision](governance/AGP_OD1012_SESSION_CRYPTO_OWNER_DECISION_2026-10-12.md). Policy ratification is not strategy-specific execution authorization; `demo_authorized=false`, `live_authorized=false`, and READY remains OFF.


## C14 demo sequencing (ratified 2026-10-11)

After a strategy passes L1–L6 for its exact frozen identity and completes runtime binding, READY, host acceptance, execution-safety and broker gates, it may become eligible for automatic **DEMO-only** orders after separate, valid, revocable, strategy-specific standing owner authorization. Each order must independently pass current account, signal, freshness, geometry, spread/cost, sizing, duplicate, broker `order_check`, reconciliation and emergency-stop checks. No per-order owner Confirm is required within that authorized scope. Economic qualification (`EDGE_VERIFIED`) and a 10-cycle scheduled zero-order shadow soak are optional; neither is a DEMO prerequisite. G1–G4 remain required, G5 is optional observation, and G6 is the independently gated demo round trip. Live trading remains disabled and out of scope. See [C14 owner decision](governance/AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md).

The [AGP-C6 amendment](governance/AGP_C6_AUTO_DEMO_OBJECTIVE_AMENDMENT_2026-10-10.md) remains available as historical proposal evidence. Its mandatory soak and post-soak/per-order requirements were superseded by C14 and are not current policy.

## Ticket lanes & execution routing (2026-10-12)

**Status:** owner-directed amendment, DESIGN. Documentation and configuration schema only. It enables no code path, flips no scope to `PASSED`, changes no READY flag, and leaves `demo_authorized=false`, `live_authorized=false` and all execution flags OFF. Schema: [`config/governance/ticket_verification_routing.yaml`](../config/governance/ticket_verification_routing.yaml).

**Intent.** During logical verification the system produces trade tickets from **all three strategy families** — Asian Sweep session FX/gold (`ST_ASIAN_SWEEP_5R_V1`), Crypto CFD sweep-retest (`ST_CRYPTO_CFD_SWEEP_RETEST_V1`) and Large-SMC (`ST_LARGE_SMC_V1`) — for every relevant pair. Each ticket is stamped with the current verification status of its **strategy scope**:

- Scope status `PASSED` → ticket is routed `DEMO_ORDER`: a VT Markets DEMO order is placed and a Telegram report is sent.
- Scope status other than `PASSED` → ticket is routed `REPORT_ONLY`: Telegram report only, labelled `REPORT-ONLY: <status>`.
- On a scope's transition to `PASSED`, subsequent tickets for that scope may auto-place DEMO orders. **No backfill:** tickets generated before the transition are never placed retroactively.

**Scope.** A verification scope is the tuple **strategy × pair × session/branch** (for example `ST_ASIAN_SWEEP_5R_V1@1.1.2` × GBPUSD × ASIAN_LONDON × SWEEP). A passing scope verifies no other branch, symbol, session or venue (AGP-C15).

### PASSED (scope-level definition)

`PASSED` is a scope-level state meaning **every** existing per-strategy gate is green for that exact scope:

1. **Logic L1–L6** recorded as passing, as required for ticket authority under Strategy admission (the owner's shorthand "L1–L5" is not used because L6 is already mandatory in this objective) with frozen identity, causality and deterministic replay (`LOGIC_VERIFICATION_REPORT`).
2. **Data:** VT MT5 `symbol_info` evidence for the traded broker symbol (G2).
3. **Cost:** required risk and cost keys present and threshold tests passing (G3).
4. **Host acceptance:** read-only open-window acceptance and published heartbeat for the scope (G4).
5. **Shadow soak:** at least **10 clean cycles** for the scope, each meeting every acceptance criterion in the Optional operational soak section (zero broker mutations).

**Logic-only is not PASSED.** `LOGIC_VERIFIED` alone never yields `PASSED`, and `PASSED` does not by itself confer DEMO authority (see Routing rules).

> **OWNER DECISION REQUIRED — conflict with ratified C14.** Requirement 5 makes a 10-cycle shadow soak a DEMO-routing prerequisite. Ratified C14 (2026-10-11) and OD1009-D5 state that the mandatory 10-cycle zero-order soak is **not** a DEMO prerequisite. This amendment keeps the soak in the `PASSED` definition as directed for the routing registry; this applies only to DEMO routing and does not reinstate it as a general authorization gate. The owner must confirm which applies before any scope is set to `PASSED`. Until confirmed, no scope may be set to `PASSED`.

### Per-ticket guards (apply even when PASSED)

A ticket for a `PASSED` scope is still blocked, and is then routed `REPORT_ONLY` with the block reason recorded, if any of these hold:

| Guard | Rule |
|---|---|
| Risk | `risk_pct` = 0.5 (owner ticket config; no fallback to strategy or `trading.yaml` risk). |
| Cost | Spread + commission ≥ **0.25R** blocks (`cost_block_R`, OD1009-D2). |
| Crypto spread | Crypto CFD spread > **20%** of the stop/risk distance blocks. *Owner instruction 2026-10-12; no recorded config key exists yet, so until one is recorded this guard fails closed.* |
| Large-SMC reward | `lsmc_min_remaining_reward_fraction` = 0.5 (at least 50% of entry-to-target distance remaining). |

Any guard failure, missing execution-critical input, stale or expired ticket, or unknown status produces `execution_route=REPORT_ONLY` with a populated `route_reason`.

### Ticket schema additions

| Field | Type | Values / rule |
|---|---|---|
| `verification_status` | enum | `UNVERIFIED` \| `IN_VERIFICATION` \| `LOGIC_VERIFIED` \| `PASSED` \| `STALE_IDENTITY`. Read from the routing registry for the ticket's scope; never inferred from the ticket itself. |
| `execution_route` | enum | `DEMO_ORDER` \| `REPORT_ONLY`. Default and fail-closed value is `REPORT_ONLY`. |
| `route_reason` | string | Required whenever `execution_route=REPORT_ONLY`: the status (for example `REPORT-ONLY: LOGIC_VERIFIED`) or the first failing guard/block reason. Required and non-empty. |

`LOGIC_VERIFIED`, `ACTIONABLE`, `EDGE_VERIFIED`, `DEMO_AUTHORIZED` and `LIVE_AUTHORIZED` remain independent states. `verification_status=PASSED` is not `DEMO_AUTHORIZED`.

### Routing rules

1. `DEMO_ORDER` requires **all** of: scope `verification_status=PASSED` in the routing registry; every per-ticket guard passing; and a **separate, valid, revocable, strategy-specific standing DEMO authorization** covering the exact strategy version and scope (C14 gate 5). Without that authorization, a `PASSED` scope routes `REPORT_ONLY` with reason `DEMO_AUTHORIZATION_ABSENT`.
2. Every other case routes `REPORT_ONLY`.
3. Routing reads a **single per-scope status registry** (`config/governance/ticket_verification_routing.yaml`). Missing, unknown or malformed status fails closed to `REPORT_ONLY`. Live accounts are never routable.
4. The crypto daily ceiling of two combined entries (AGP-OD1012-SESSION-CRYPTO) and the existing risk ceilings (1 open position per instrument, 5 trades per strategy per day, 1% daily loss per strategy, 2% account-wide) still bind at the execution boundary and are not relaxed by `PASSED`.

### Execution path and Telegram controls

- Every automatic order passes the canonical execution/risk authority (`assistant.commands.execute_command()` boundary where implemented), with `order_check`, duplicate prevention, reconciliation and emergency stop. No ticket generator, Telegram message or callback may place an order directly.
- The owner may **edit or close** demo orders from Telegram. Such actions are broker mutations and must pass through the same canonical executor, with an append-only audit record. They may not bypass routing, guards, authorization or the Live exclusion.

### Supersession of the 2026-10-09 owner-approval order flow

The 2026-10-09 flow in which an owner Confirm places an order (Issue #47 V5 per-order confirmation, OD1009-D5) is **superseded for `PASSED` scopes**. Per-order Confirm is no longer the placement trigger for those scopes. Owner Confirm/Reject remains decision capture for other scopes and never grants or extends authorization.

**Activation caveat (not changed by this amendment):** the per-order `user_confirmed` gate in `AGENTS.md` stays in force until the reviewed executor change and matching `AGENTS.md` update have landed together (see `docs/agents/INVARIANTS.md`). Until then, no `PASSED` scope can route `DEMO_ORDER` in practice.

### Current state

No scope is `PASSED`. The routing registry is empty, so every ticket is `REPORT_ONLY` with reason `REGISTRY_ENTRY_MISSING`. Strategy admission, READY, runtime binding and host acceptance are unchanged. This section sets target policy only and is not evidence that any gate has passed.

## Objective

Every trading day, AG Profit Trading reads real market data and evaluates **logically verified** strategies across the six target instruments. For each scheduled evaluation, it delivers to the owner on Telegram either an actionable informational trade/watch ticket or a deterministic terminal reason.

On each applicable FX trading day, EURUSD, GBPUSD, USDJPY and XAUUSD are each evaluated once for ASIAN_LONDON and once for LONDON_NEWYORK: eight scheduled instrument-session evaluations, each with a deterministic auditable terminal outcome. A scheduled evaluation is not a trade quota. BTCUSD and ETHUSD are scanned dynamically, only qualified current opportunities are ranked, and at most two combined crypto entries are taken per defined trading day; zero or one is acceptable (AGP-OD1012-SESSION-CRYPTO).

Under ratified C14, a strategy with separate, valid, scoped standing DEMO authorization may submit eligible orders automatically after every runtime, READY, host, risk and broker gate passes; no per-order owner confirmation is required for that authorized scope. Confirm/Reject remains optional decision capture and cannot grant or extend authorization. Until `demo_authorized=true` is explicitly established through the governed authorization path, broker execution remains blocked. Live real-money execution is outside this objective.

`LOGIC_VERIFIED`, `ACTIONABLE`, `EDGE_VERIFIED`, `DEMO_AUTHORIZED`, and `LIVE_AUTHORIZED` are independent states. Ticket readiness or logical verification never implies economic edge or execution authority.

## Scope

**Logical instruments:** EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, ETHUSD. These canonical names are the objective's identities. Host-observed VT Markets broker symbols are recorded in [`status/evidence/host_symbol_info_2026-10-09.json`](../status/evidence/host_symbol_info_2026-10-09.json). That read-only capture (mission AGP-C1-HOST, `VTMarkets-Demo`, 2026-10-09T11:50:34Z) observed `EURUSD-VIP`, `GBPUSD-VIP`, `USDJPY-VIP` and `XAUUSD-VIP` at `trade_mode` FULL; unsuffixed `EURUSD`, `GBPUSD` and `USDJPY` at DISABLED; `XAUUSD.crp` hidden and DISABLED; and `BTCUSD` and `ETHUSD` at FULL. These host observations are evidence, not execution authorization. The separate versioned canonical-to-broker configuration is `config/broker_symbol_map/vt_markets_demo.yaml` (map version 2), consolidated by AGP-C2-SYMMAP in [PR #125](https://github.com/aungmyat1/AG-profit-trading-assit/pull/125); the cited host smoke output is historical map v1 and does not establish a live smoke of v2. Evidence: [`status/evidence/host_symbol_info_2026-10-09_symmap.json`](../status/evidence/host_symbol_info_2026-10-09_symmap.json), [`status/evidence/host_symbol_map_smoke_2026-10-09.txt`](../status/evidence/host_symbol_map_smoke_2026-10-09.txt).

1. **Session tickets — FX + Gold**
   - EURUSD
   - GBPUSD
   - USDJPY
   - XAUUSD
   - ASIAN → LONDON and LONDON → NEW YORK.
   - Owner-defined session windows are authoritative.
   - Each scheduled instrument/session evaluation must end in an explicit canonical terminal outcome; no forced trade is required.
   - Per applicable FX trading day: each instrument is evaluated once for `ASIAN_LONDON` and once for `LONDON_NEWYORK`, which is **exactly eight** scheduled instrument-session evaluations, using the existing authoritative session definitions and DST policy (AGP-OD1012-SESSION-CRYPTO).
   - A scheduled evaluation is not a trade quota: no mandatory trade and no forced READY. Two evaluations per instrument do not imply two executions; only a genuinely qualified setup that passes every applicable authorization and safety gate may execute.

2. **Crypto tickets — VT Markets CFDs (target capability)**
   - BTCUSD
   - ETHUSD
   - Daily, including weekends, at strategy-defined times.
   - Venue: VT Markets MT5 Demo CFDs; perpetual-futures (BTCUSDT/ETHUSDT) evidence is never substituted.
   - Both instruments are scanned dynamically; only qualified, current, non-expired opportunities are ranked (AGP-OD1012-SESSION-CRYPTO).
   - **Maximum two combined crypto entries per defined trading day** across both instruments and all strategies (not two per instrument). Zero or one is acceptable. Two may be on the same instrument when each is independently qualified and every other control permits it. No trade is generated to meet a daily target.
   - The ceiling is an execution-level limit at the canonical DEMO execution boundary. It is not satisfied by limiting Telegram messages, tickets or proposals.
   - Day boundary, scan cadence, ranking weights, tie-breaking and broker order-counting semantics (partial fills, retries, uncertain submissions) are pending implementation design and fail closed until separately approved and implemented. The dynamic scan, ranking and ceiling enforcement are **not implemented**.
   - This is a target production capability, not a claim that the current crypto runtime is already accepted. Venue/contract identity, market-data semantics, sizing and strategy admission must be validated before operational acceptance.
   - Intended runtime strategy (OD1009-D3): `ST_CRYPTO_CFD_SWEEP_RETEST_V1`. Admission requires Logic Gate L1–L6 evidence; it is **not admitted** today and the existing runtime binding is unchanged (see `strategies/registry.yaml`).

3. **Large-SMC watch / alerts — all six instruments (target capability)**
   - Use a separately versioned `ST_LARGE_SMC` strategy only after its contract/engine passes the required Logic Gate and is admitted for ticketing.
   - Delivery freshness, remaining-R and send-time usability belong to the post-signal actionability layer and must not alter frozen strategy market logic.
   - Current research/draft status does not constitute logical verification or ticket authority.
   - Large-SMC remains a separate six-instrument watch capability; its alerts are not entries and do not consume the crypto entry ceiling.

4. **Telegram owner interface**
   - Canonical-ticket delivery.
   - Complete session summaries.
   - Persistent logical-ticket deduplication across restart/retry.
   - Owner Confirm/Reject is a governed decision-capture path.
   - Confirm/Reject appends an owner decision and may hand off only to the canonical execution boundary; it does not bypass C14 gates or standing authorization.
   - Demo execution remains disabled/no-op unless separately recorded owner authorization enables it.
   - No Telegram control may independently bypass execution/risk/authorization gates.

### Issue #47 V5 requirement reconciliation (C14 authority)

Issue [#47](https://github.com/aungmyat1/AG-profit-trading-assit/issues/47) is retained as a historical delivery specification, not an independent execution authorization. The following requirements remain targets and may not be claimed implemented without accepted evidence:

- **FX/gold:** EURUSD, GBPUSD, USDJPY and XAUUSD; ASIAN_LONDON and LONDON_NEWYORK. Produce qualified deterministic tickets or explicit terminal reasons (including NO_TRADE and BLOCKED), never a forced trade.
- **Crypto CFDs:** BTCUSD and ETHUSD on the VT Markets DEMO CFD venue. At most two combined crypto entries per defined trading day is an execution-level ceiling (AGP-OD1012-SESSION-CRYPTO, superseding the earlier "two qualified tickets per day planning ceiling"); it is not a trade quota and grants no authorization. Never substitute BTCUSDT/ETHUSDT perpetual evidence, sizing or contract semantics for these CFDs.
- **Large-SMC:** watch and entry-confirmation alerts for all six instruments only from a contract/engine whose exact identity and entry/stop/target rules pass the required Logic Gate. WATCH or ALERT_ONLY is not execution authority.
- **Canonical provenance:** decision products must bind the current runtime code SHA, frozen strategy ID/version, canonical and broker symbol, account/venue, source and market-data timestamp, ticket identity, generation and expiry time. Telegram watch, proposals and daily summaries include side, entry/zone, invalidation/SL, TP(s), risk, logic/economic qualification states and explicit block reasons as applicable. Missing values are marked unavailable and block trading when execution-critical; never invent them.
- **Order identity and safety:** stale, replaced, expired or replayed tickets cannot execute; authorization applies to the immutable proposal identity and an approved strategy-version/symbol/account scope. Every automatic order must pass the canonical deterministic execution/risk authority (the `assistant.commands.execute_command()` boundary where implemented), DEMO account identity, freshness, geometry, broker `order_check`, risk/cost, duplicate prevention and broker-state reconciliation. No AI, LSMC watch, Telegram notification or callback may bypass this chain.
- **Auditable order lifecycle:** preserve proposal -> applicable standing owner authorization -> execution decision -> broker check -> order submission (only when authorized) -> confirmed, rejected or uncertain broker result -> reconciliation, with timestamps, immutable identities and Telegram reporting. Unknown broker outcomes must not be silently retried or presented as fills.
- **C14 supersession:** a separate scoped, revocable DEMO standing authorization replaces #47's *per-order owner confirmation* for that approved scope; EDGE_VERIFIED/economic qualification and mandatory 10-cycle shadow soak are not DEMO prerequisites. The applicable technical safety gates remain mandatory. No standing authorization is granted by this objective or a Telegram Confirm.

**Current status:** These are acceptance requirements, not proof of completion. R0–R6 operational acceptance, L1–L6 strategy admission and G6 broker round-trip require separately verified dated evidence. No strategy is granted demo/live authority by this reconciliation.

## Owner decisions OD1009-D1–OD1009-D6 (2026-10-09)

Source for all six decisions: owner chat, Aung, 2026-10-09; register entries `OD1009-D1` through
`OD1009-D6`. These identifiers are distinct from the 2026-09-30 D1–D8 in
[`AG_V1_TWO_GOALS_OWNER_DECISIONS.md`](governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md). These
records do not silently promote strategies or change demo/live authorization.

| Decision | Owner decision | Current authority / effect |
|---|---|---|
| OD1009-D1 | Confirm every Phase B row as recommended; use fixed UTC anchoring; accept packet proposal `SETUP_WINDOW_OPEN`; successor is `ST_ASIAN_SWEEP_5R_V1@1.1.2`. | Confirmation is recorded in the Phase B owner table and L2 closure. v1.1.1 remains the runtime authority; v1.1.2 is not admitted by this record. |
| OD1009-D2 | FX/gold manual tickets use `risk_pct: 0.5`, `cost_warn_R: 0.10`, and `cost_block_R: 0.25`; cost at or above 0.25R blocks. Missing required risk/cost configuration fails closed. | [`config/owner_ticket.yaml`](../config/owner_ticket.yaml) and `src/v1_tickets/manual_ticket.py`; strategy YAML risk and execution authorization remain unchanged. |
| OD1009-D3 | The crypto ticket path moves to `ST_CRYPTO_CFD_SWEEP_RETEST_V1` after L1–L6 pass; `ST_LIQUIDITY_SWEEP_RETEST_V1` remains research. | Intended path only; admission/runtime binding is unchanged until the evidence gate passes. |
| OD1009-D4 | Target `AG-V1-LSMC-Watch` daily at 00:04:15 UTC and retire `AG-V1-LSMC-Crypto-Weekend`. | Register-only schedule decision; no host task or installer change is made here. |
| OD1009-D5 | Historical 2026-10-09 decision required G1–G5 before per-strategy authorization and placed G6 after authorization. C14 supersedes its mandatory G5 prerequisite and per-order-confirmation requirement for DEMO; G1–G4, order-level safety gates, and separate strategy-specific authorization remain. | `demo_authorized=false`; this record does not authorize a demo order. See ratified C14. |
| OD1009-D5-ECONOMIC-STANDARD | No economic edge evidence is required for demo authorization in PRE-EDGE; `EDGE_VERIFIED=false` is accepted for demo. | Confirmed and unchanged by C14. Live trading remains out of scope; no demo flags change. |
| OD1009-D6 | `ST_ASIAN_SWEEP_5R_V1` READY may be ON only after G1 and G3 pass. | `ticket_ready` and [`ready_authority.yaml`](../config/v1_tickets/ready_authority.yaml) remain unchanged; current READY remains OFF. |

The 2026-09-30 D2 ("Telegram is DEFERRED") stays subject to rescission row C1. Open rows stay in [`OWNER_DECISION_REGISTER.md`](governance/OWNER_DECISION_REGISTER.md) until the owner records them.

## Definition of Done

The following gates are cumulative. Passing a gate is evidenced by its named artifact; no gate
implies another authorization state.

| Gate | Pass condition | Evidence artifact |
|---|---|---|
| G1 — Logic | L1–L6 pass for the exact contract and engine identity. | `LOGIC_VERIFICATION_REPORT`, including contract and engine hashes. |
| G2 — Data | VT MT5 `symbol_info` evidence exists for every traded broker symbol; no `FIXTURE_ONLY` value is used as traded-symbol evidence. | Dated host `symbol_info` capture with broker-symbol identities. |
| G3 — Cost/risk | Required risk and cost keys are present; missing-key and threshold tests prove the gates fail closed. | Owner ticket configuration plus focused test report. |
| G4 — Host acceptance | Read-only open-window acceptance passes for every scope item and a heartbeat is published. | Per-scope host acceptance report and published heartbeat artifact. |
| G5 — Optional shadow soak | Shadow observation may be used for diagnostics; no fixed number of zero-order cycles is required for DEMO eligibility or authorization. | Optional append-only observation evidence; never substitutes for G1–G4 or execution/broker safety acceptance. |
| G6 — Demo round trip | After G1–G4, runtime/READY/host/risk/broker safety gates, and separate valid strategy-specific standing DEMO authorization pass, one automatic demo order is accepted and reconciled with its correlated audit record. No per-order owner Confirm is required. | Standing authorization evidence, exact ticket/strategy/runtime identity, order checks, broker result, reconciliation and correlated audit record. |

C14 (2026-10-11) supersedes OD1009-D5's mandatory G5 soak prerequisite and Issue #47 V5's per-order owner-confirmation requirement for standing-authorized DEMO scopes. G1–G4, runtime binding, READY validation, execution-specific broker/risk controls, and separate strategy-specific standing owner authorization remain required. EDGE_VERIFIED and a scheduled zero-order shadow soak are not authorization prerequisites. G6 remains the later independently gated demo round-trip acceptance.
OD1009-D6 permits Asian Sweep READY only after G1 and G3. These conditions do not change current
authorization or readiness values.

### Approved DEMO risk ceilings — OD1010-C6-RISK

These approved initial DEMO limits must be enforced by the execution system. They do not authorize execution, change strategy eligibility, or enable READY.

| Control | Limit |
|---|---|
| Risk per trade | 0.5% of demo account equity |
| Maximum open positions | 1 per instrument across all strategies |
| Maximum trades | 5 per strategy per day |
| Daily loss per strategy | 1% |
| Account-wide daily loss | 2% |

Daily reset timezone and notification-failure behavior remain pending owner policy; unset execution-critical inputs block orders. The AGP-OD1012-SESSION-CRYPTO crypto ceiling (two combined crypto entries per defined day) is additional to these limits; where they overlap, the stricter binds.

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

### Optional operational soak (not a DEMO authorization prerequisite under C14)

If this optional diagnostic exercise is undertaken, the following evidence criteria describe a complete soak; none is a prerequisite for DEMO authorization:

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
2. **Asian Sweep Logic Gate reconciliation** — resolve L2 contract/engine divergences in a separately versioned successor; pass L1–L6 before actionable ticket admission. **OPEN**: OD1009-D1 confirms `ST_ASIAN_SWEEP_5R_V1@1.1.2` as successor; the runtime remains on v1.1.1 and admission is not done.
3. **Crypto CFD contract + sizing** — define and validate BTCUSD/ETHUSD VT Markets CFD identity, data semantics, risk/sizing and strategy admission. **OPEN**: D4 names `ST_CRYPTO_CFD_SWEEP_RETEST_V1` (D2/D4 risk, cost and spread policy); L1–L6 admission is not done.
4. **Large-SMC verification on six instruments** — resolve unsigned/research-only contract fields, provide deterministic engine authority and pass the required Logic Gate before actionable ticketing.
5. **AGP-LIVE-01** — open-window real-market acceptance of the admitted pipeline, including first live Telegram delivery proof. Requires the canonical-to-broker symbol map (AGP-C2-SYMMAP, pending) and its host acceptance first.
6. **Scheduler integration** — invoke the accepted pipeline unchanged and prove restart/retry idempotency.
7. **Telegram decision-capture path, execution flag OFF** — append-only owner decisions, with zero broker mutation; this path does not gate each order under a separately authorized C14 scope.
8. **Optional operational soak** — scheduled shadow observation is encouraged for diagnostics but no fixed number of cycles is required for DEMO authorization under C14. Do not infer readiness from missing soak evidence; rely on independently accepted required gates.
9. **Owner demo-authorization decision** — separate standing authorization after required logical, runtime, host, READY, risk and broker gates, not dependent on a mandatory soak. Authorization is not implied by successful tickets, logic verification, edge status, Telegram confirmation, or soak completion.

## Current-State Boundary

This document defines the **target product objective and Definition of Done**. It does not promote current research strategies, assert economic edge, enable demo/live execution, or claim that unaccepted crypto/LSMC runtime paths are already operational. Current implementation and validation truth remains in `PROJECT_STATUS.md`, `strategies/registry.yaml`, the strategy ledger, and dated `docs/status/` evidence.
