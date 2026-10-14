---
class: authority
state: DESIGN
owner_reviewed: 2026-10-12
review_by: 2026-11-07
---
# AG Profit Trading — Project Objective (rev 2026-10-14)

**Repository:** `aungmyat1/AG-profit-trading-assit`  
**Target branch:** `main`  
**Venue:** VT Markets MT5 Demo  
**Product phase:** PRE-EDGE  
**Owner ratification:** Original objective RATIFIED 2026-10-09 by the owner — register entry `OBJ-RATIFY-2026-10-09`. C14 sequencing amendment RATIFIED 2026-10-11 — register entry `C14` and [owner decision](governance/AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md). FX/Gold session coverage and crypto entry ceiling OWNER_APPROVED 2026-10-12 — register entry `AGP-OD1012-SESSION-CRYPTO` and [owner decision](governance/AGP_OD1012_SESSION_CRYPTO_OWNER_DECISION_2026-10-12.md). Policy ratification is not strategy-specific execution authorization; `demo_authorized=false` and `live_authorized=false`. OD1012-S1-READY (owner Aung, 2026-10-12, AGP-OD1012-S1-ACTIVATION-R3) separately approves READY only for v1.1.2 GBPUSD × ASIAN_LONDON, bound to raw SHA256 `4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf`; OD1012-S1-NOTIFY requires confirmed pre-order Telegram delivery under BLOCK_NEW_ORDERS. Neither grants order authority or deployment. See the [S1 implementation record](status/AGP_OD1012_S1_ACTIVATION_R3_2026-10-12.md).


## C14 demo sequencing (ratified 2026-10-11)

After a strategy passes L1–L6 for its exact frozen identity and completes runtime binding, READY, host acceptance, execution-safety and broker gates, it may become eligible for automatic **DEMO-only** orders after separate, valid, revocable, strategy-specific standing owner authorization. Each order must independently pass current account, signal, freshness, geometry, spread/cost, sizing, duplicate, broker `order_check`, reconciliation and emergency-stop checks. No per-order owner Confirm is required within that authorized scope. Economic qualification (`EDGE_VERIFIED`) and a 10-cycle scheduled zero-order shadow soak are optional; neither is a DEMO prerequisite. G1–G4 remain required, G5 is optional observation, and G6 is the independently gated demo round trip. Live trading remains disabled and out of scope. See [C14 owner decision](governance/AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md).

The [AGP-C6 amendment](governance/AGP_C6_AUTO_DEMO_OBJECTIVE_AMENDMENT_2026-10-10.md) remains available as historical proposal evidence. Its mandatory soak and post-soak/per-order requirements were superseded by C14 and are not current policy.

## Ticket lanes & execution routing (2026-10-12)

**Status:** owner-directed amendment, DESIGN. Documentation and SPEC only. It enables no code path, changes no READY flag, and leaves `demo_authorized=false`, `live_authorized=false` and all execution flags OFF. Spec (SPEC ONLY, not read by any code): [`docs/schemas/ticket_verification_routing.yaml`](schemas/ticket_verification_routing.yaml). Decision record: [`governance/AGP_OD1012_ROUTING_OWNER_DECISION_2026-10-12.md`](governance/AGP_OD1012_ROUTING_OWNER_DECISION_2026-10-12.md).

**Intent.** During logical verification the system produces trade tickets from **all three strategy families** — Asian Sweep session FX/gold (`ST_ASIAN_SWEEP_5R_V1`), Crypto CFD sweep-retest (`ST_CRYPTO_CFD_SWEEP_RETEST_V1`) and Large-SMC (`ST_LARGE_SMC_V1`) — for every relevant pair. Every relevant scope is reported with its current status. Each ticket is stamped with its scope's `verification_status`, `eligibility` and `execution_route`.

**Scope.** A verification scope is the tuple **strategy × pair × session × branch** (for example `ST_ASIAN_SWEEP_5R_V1@1.1.2` × GBPUSD × ASIAN_LONDON × SWEEP). A passing scope verifies no other branch, symbol, session or venue (AGP-C15).

### Family → pair scope map (owner-stated target universe, 2026-10-12)

Canonical names only. Broker symbols resolve solely through `config/broker_symbol_map/vt_markets_demo.yaml`.

| Family | Strategy | Pairs | Sessions / cycle |
|---|---|---|---|
| Session FX/gold | `ST_ASIAN_SWEEP_5R_V1` | EURUSD, GBPUSD, USDJPY, XAUUSD | ASIAN_LONDON, LONDON_NEWYORK |
| Crypto CFD | `ST_CRYPTO_CFD_SWEEP_RETEST_V1` | BTCUSD, ETHUSD | daily incl. weekends, strategy-defined times |
| Large-SMC | `ST_LARGE_SMC_V1` | EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, ETHUSD | continuous watch |

- **AUDUSD is outside the owner's target universe and is not a reported scope.** It appears in the `ST_ASIAN_SWEEP_5R_V1` v1.0.0 and v1.1.2 contract `instruments` lists and is excluded in v2.0.0. This amendment does not edit any strategy contract.
- A scope is a (family, strategy, pair, session/branch) tuple. "Every relevant pair" means the pairs in this table for that family.

### Pass semantics (owner reading confirmed 2026-10-12)

- A scope that passes L1–L6 is `LOGIC_VERIFIED` only.
- It becomes `EXECUTION_ELIGIBLE` after G2–G4.
- It becomes `DEMO_ORDER`-routable only with the owner's separate, scope-specific standing DEMO authorization (C14).
- Passing L1–L6 alone never routes an order.
- Non-passing scopes: Telegram REPORT ONLY.
- Passing scopes: demo order (once routable) plus a Telegram report.

### States

Three independent axes replace any single "PASSED" state:

| Axis | Values | Meaning |
|---|---|---|
| `verification_status` | `UNVERIFIED` \| `IN_VERIFICATION` \| `LOGIC_VERIFIED` \| `STALE_IDENTITY` | `LOGIC_VERIFIED` = the exact scope passed **L1–L6**, with frozen identity, causality and deterministic replay. |
| `eligibility` | `NOT_ELIGIBLE` \| `EXECUTION_ELIGIBLE` | `EXECUTION_ELIGIBLE` = `LOGIC_VERIFIED` **+** data (G2 `symbol_info`) **+** cost (G3 risk/cost keys and threshold tests) **+** host acceptance (G4) **+** an owner per-scope **standing DEMO authorization** (C14). |
| `execution_route` | `REPORT_ONLY` \| `DEMO_ORDER` | `DEMO_ORDER` = `EXECUTION_ELIGIBLE` **AND** every per-ticket guard passes **at send time**. Otherwise `REPORT_ONLY`. |

- **PASSED makes a scope eligible; owner standing authorization makes it routable.** `LOGIC_VERIFIED` alone is never eligible.
- **Shadow soak** is an optional diagnostic and may be cited as host-acceptance evidence. It is **not** an eligibility gate (C14, OD1009-D5).
- Routing reads a single per-scope registry. That runtime registry does not exist yet (see Current state). Missing, unknown or malformed status fails closed to `REPORT_ONLY`. Live accounts are never routable.
- `route_reason` is required and non-empty whenever `execution_route=REPORT_ONLY`.

`LOGIC_VERIFIED`, `ACTIONABLE`, `EDGE_VERIFIED`, `DEMO_AUTHORIZED` and `LIVE_AUTHORIZED` remain independent states. Neither `LOGIC_VERIFIED` nor `EXECUTION_ELIGIBLE` implies `EDGE_VERIFIED` or `LIVE_AUTHORIZED`.

### Ticket lanes

- **All three families report every relevant scope**, with its status stamped on the ticket.
- **Non-eligible tickets** (`NOT_ELIGIBLE`, or any non-`DEMO_ORDER` route) carry the header **`REPORT ONLY — NON-ACTIONABLE`**. Prices on such tickets follow [Verification-phase opportunity tickets (OD1014)](#verification-phase-opportunity-tickets-od1014-2026-10-14). Such tickets **never enter the order queue**.
- **Large-SMC:** Large-SMC detection verification ≠ entry/proposal verification; eligible only after entry scope passes L1–L6 + owner authorization. Detection verification alone never makes a Large-SMC scope eligible. Watch and alert behaviour is unchanged.
- **No retroactive execution.** Tickets issued before a scope became `EXECUTION_ELIGIBLE` are never placed.

### Per-ticket guards (apply even when EXECUTION_ELIGIBLE)

A ticket is blocked, and routed `REPORT_ONLY` with the block reason, if any of these fail. Guards are referenced here and are not altered by this section.

| Guard | Rule | Source |
|---|---|---|
| Risk | `risk_pct` = 0.5 (owner ticket config; no fallback to strategy or `trading.yaml` risk). | OD1009-D2, OD1010-C6-RISK |
| Cost | Spread + commission ≥ **0.25R** blocks (`cost_block_R`). | OD1009-D2 |
| Crypto spread | Crypto CFD spread > **20%** of the stop/risk distance blocks (exactly 20% warns). | Owner ratification 2026-10-09 as stated by the owner (register `OD1009-CRYPTO-SPREAD`); key exists as `spread_block_pct: 20` (percent) in [`config/v1_tickets/crypto_cfd_ticket_policy.yaml`](../config/v1_tickets/crypto_cfd_ticket_policy.yaml), read by `src/v1_tickets/crypto_cfd_policy.py` |
| Large-SMC reward | `lsmc_min_remaining_reward_fraction` = 0.5 (≥ 50% of entry-to-target distance remaining). | `config/policy/actionability_policy.yaml` |

Cadence and session guards that apply to the same routing lanes:

- **15-minute cadence**, with **8 durable session outcomes** per applicable FX day (`AGP-OD1012-SESSION-CRYPTO`).
- **OD1012-S1-ACCEPT:** S1 acceptance is the open-window run; the optional soak is not a gate.
- **Combined crypto cap:** at most **2** combined crypto entries per day, enforced at the execution boundary.
- **Crypto day boundary** `00:00 Asia/Yangon` is separate from, and cumulative with, the broker-server-day risk reset (`VT_SERVER_DAY`). The strictest limit binds. This boundary is in PR #175, which is not yet on `main`.
- **No live routing ever.**

Any guard failure, missing execution-critical input, stale or expired ticket, or unknown status produces `execution_route=REPORT_ONLY` with a populated `route_reason`.

### Ticket schema additions

| Field | Type | Values / rule |
|---|---|---|
| `verification_status` | enum | `UNVERIFIED` \| `IN_VERIFICATION` \| `LOGIC_VERIFIED` \| `STALE_IDENTITY`. Read from the registry for the ticket's scope; never inferred from the ticket. |
| `eligibility` | enum | `NOT_ELIGIBLE` \| `EXECUTION_ELIGIBLE`. |
| `execution_route` | enum | `DEMO_ORDER` \| `REPORT_ONLY`. Fail-closed default is `REPORT_ONLY`. |
| `route_reason` | string | Required when `execution_route=REPORT_ONLY`: the failing status, guard or block reason (for example `REPORT-ONLY: LOGIC_VERIFIED` or `DEMO_AUTHORIZATION_ABSENT`). |

### Execution path and Telegram controls

- Every automatic order passes the canonical execution/risk authority (`assistant.commands.execute_command()` boundary where implemented), with `order_check`, duplicate prevention, reconciliation and emergency stop. No ticket generator, Telegram message or callback may place an order directly.
- The owner may **edit or close** demo orders from Telegram. Such actions are broker mutations and must pass through the same canonical executor, with an append-only audit record. They may not bypass routing, guards, authorization or the live exclusion.

### Supersession of the 2026-10-09 owner-approval order flow

The 2026-10-09 flow in which an owner Confirm places an order (Issue #47 V5 per-order confirmation, OD1009-D5) is **superseded for `EXECUTION_ELIGIBLE` scopes**. Per-order Confirm is no longer the placement trigger for those scopes. Owner Confirm/Reject remains decision capture for other scopes and never grants or extends authorization.

**Activation caveat (not changed by this amendment):** the per-order `user_confirmed` gate in `AGENTS.md` stays in force until the reviewed executor change and matching `AGENTS.md` update have landed together (see `docs/agents/INVARIANTS.md`). Until then, no scope can route `DEMO_ORDER` in practice.

### Current state

No scope is `LOGIC_VERIFIED` or `EXECUTION_ELIGIBLE` by this section. No runtime routing registry exists, so every ticket is `REPORT_ONLY` with reason `REGISTRY_ENTRY_MISSING` until the separately authorized registry PR lands. Strategy admission, READY, runtime binding and host acceptance are unchanged. This section sets target policy only and is not evidence that any gate has passed.

### Follow-ups (not in this PR)

(a) Executor change replacing per-order `user_confirmed` for `EXECUTION_ELIGIBLE` scopes. (c) Runtime scope registry and loader. (d) Read-only all-family Telegram status reports, the next implementation priority.

## Verification-phase opportunity tickets (OD1014, 2026-10-14)

This section is an additive reporting-policy clarification; it does not override any authorization, risk, guard or routing rule above. Ratification is recorded in the [owner decision register](governance/OWNER_DECISION_REGISTER.md), entries `OD1014` and `OD1014-FAST` (owner Aung, 2026-10-14, `AGP-OD1014-RATIFY-R1`).

A priced OPPORTUNITY contains strategy-generated prices calculated from validated VT Markets MT5 market data. These are observational strategy outputs, not fabricated examples, but their trading correctness has not necessarily been verified. They are non-actionable and carry no execution authority.

Rules:

- **Headers (ASCII, as implemented):** a priced CANDIDATE is headed `OPPORTUNITY -- REPORT ONLY -- NON-ACTIONABLE (verification: <status>)`; a Large-SMC CANDIDATE `LARGE-SMC OPPORTUNITY -- REPORT ONLY -- NON-ACTIONABLE (verification: <status>)`. Every other class keeps `REPORT ONLY -- NON-ACTIONABLE`. `<status>` is read from the registry for the ticket's own strategy version, never borrowed from another version.
- **Targets:** contract-defined targets only; a target the contract does not define (for example an uncontracted TP2) is never shown.
- **Sizing and cost:** a display-only lot preview and cost-in-R are shown only when every input is valid; otherwise the ticket says `sizing: n/a (<reason>)`. Zero, NaN and estimated values are never shown.
- **Incomplete plans:** a missing entry, SL or required target makes the ticket BLOCKED, with no prices.
- **Schedule unchanged:** eight FX evaluations per day are eight evaluations, not eight opportunities; crypto runs in its configured windows; the Large-SMC watch runs every 15 minutes.
- **Still BLOCKED:** suspended scopes and stale signals (STALE, MISSED or EXPIRED) are never presented as opportunities. A scope's `STALE_IDENTITY` verification status is not a stale signal: it is shown in the header like any other status.
- **Never queued, never retroactive, not evidence:** an OPPORTUNITY never enters the order queue, is never placed after a scope later becomes eligible, and is not verification or edge evidence.

### Coverage (against `main` @ `b588eb6`, 2026-10-14)

Classes: `IMPLEMENTED_AND_EVIDENCED` / `IMPLEMENTED_NOT_HOST_VERIFIED` / `NOT_IMPLEMENTED` / `BLOCKED_BY_POLICY` / `UNKNOWN_PENDING_INSPECTION`. Items that exist only on `feat/od1014-r2-followup` are `NOT_IMPLEMENTED` (pending PR #203).

| Family | Symbol | Session / cycle | OPPORTUNITY ticket on main | Sizing preview on main |
|---|---|---|---|---|
| Session FX/gold (v1.1.2) | EURUSD | ASIAN_LONDON | BLOCKED_BY_POLICY (v1.1.2 scope SUSPENDED; v1.1.3 report-lane evaluation NOT_IMPLEMENTED, pending PR #203) | NOT_IMPLEMENTED (pending PR #203) |
| Session FX/gold (v1.1.2) | EURUSD | LONDON_NEWYORK | IMPLEMENTED_NOT_HOST_VERIFIED | NOT_IMPLEMENTED (pending PR #203) |
| Session FX/gold (v1.1.2) | GBPUSD | ASIAN_LONDON | UNKNOWN_PENDING_INSPECTION (S1 canonical path; outside the report lane) | UNKNOWN_PENDING_INSPECTION |
| Session FX/gold (v1.1.2) | GBPUSD | LONDON_NEWYORK | IMPLEMENTED_NOT_HOST_VERIFIED | NOT_IMPLEMENTED (pending PR #203) |
| Session FX/gold (v1.1.2) | USDJPY | ASIAN_LONDON, LONDON_NEWYORK | IMPLEMENTED_NOT_HOST_VERIFIED | NOT_IMPLEMENTED (pending PR #203) |
| Session FX/gold (v1.1.2) | XAUUSD | ASIAN_LONDON, LONDON_NEWYORK | IMPLEMENTED_NOT_HOST_VERIFIED | NOT_IMPLEMENTED (pending PR #203) |
| Crypto CFD (1.0.0) | BTCUSD | WEEKDAY, WEEKEND | IMPLEMENTED_NOT_HOST_VERIFIED (SHORT `STALE_IDENTITY`, LONG `UNVERIFIED`) | NOT_IMPLEMENTED (pending PR #203) |
| Crypto CFD (1.0.0) | ETHUSD | WEEKDAY, WEEKEND | IMPLEMENTED_NOT_HOST_VERIFIED (LONG and SHORT `STALE_IDENTITY`) | NOT_IMPLEMENTED (pending PR #203) |
| Large-SMC (1.1.0) | EURUSD, GBPUSD | continuous watch | IMPLEMENTED_NOT_HOST_VERIFIED (SHORT C10 stop from the read-only MT5 tick) | NOT_IMPLEMENTED (pending PR #203) |
| Large-SMC (1.1.0) | USDJPY, XAUUSD, BTCUSD, ETHUSD | continuous watch | NOT_IMPLEMENTED (C10 pip = 10 × host-captured point per OD1014-FAST D2 is not in the engine; stays BLOCKED `C10_PIP_SIZE_NOT_EVIDENCED`) | NOT_IMPLEMENTED |

## Objective

Every trading day, AG Profit Trading reads real market data and evaluates the three target strategy families; logically verified scopes may progress to execution routing, and all other scopes report their complete priced plans as OPPORTUNITY tickets as REPORT_ONLY (OD1014) across the six target instruments. For each scheduled evaluation, it delivers to the owner on Telegram either an actionable informational trade/watch ticket or a deterministic terminal reason.

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
| OD1009-D6 | `ST_ASIAN_SWEEP_5R_V1` READY may be ON only after G1 and G3 pass. | Historical OFF state is superseded only for the exact S1 owner record by OD1012-S1-READY; all other scopes remain excluded. No execution authorization. |

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
