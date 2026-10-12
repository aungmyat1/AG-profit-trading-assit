---
class: authority
state: DESIGN
owner_reviewed: 2026-10-12
review_by: 2026-11-07
---
# OWNER DECISION — AGP-OD1012-SESSION-CRYPTO

| Field | Value |
|---|---|
| Decision ID | `AGP-OD1012-SESSION-CRYPTO` |
| Owner approval date | 2026-10-12 (Aung, explicit owner approval) |
| Decision status | `OWNER_APPROVED` |
| Implementation status | `NOT_IMPLEMENTED` |
| Execution authorization | `UNCHANGED` |
| Scope | Objective and governance only |
| Recorded against | `origin/main` `f6afc0e8e4173d3a8a8571e84423ee22ade3c732` |

**NO EXECUTION AUTHORIZATION CHANGE.** This decision grants no standing DEMO authorization and does not change `demo_authorized`, `live_authorized`, READY, `ticket_ready`, strategy admission, `logic_verified_scopes`, risk ceilings, strategy contracts, scheduler definitions, broker settings, MT5 configuration or runtime code. Ratified C14 ([owner decision](AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md)) stays authoritative.

`NOT_IMPLEMENTED` means no accepted evidence yet shows the requirements below are enforced. The approval is not a claim that any of them is already implemented.

## 1. FX/Gold — eight durable session-level outcomes

**Canonical instruments:** EURUSD, GBPUSD, USDJPY, XAUUSD.  
**Operating sessions (both preserved):** `ASIAN_LONDON`, `LONDON_NEWYORK`. Session windows and DST handling remain the existing authoritative definitions (`config/canonical_sessions.yaml`, owner-defined windows). This decision does not change them.

### 1.1 Cadence stays as it is

- The existing **15-minute intra-window evaluation cadence** is preserved. Each M15-close slot inside a session window remains one scheduled cycle. For reference, the current installer is `scripts/install_fx_scheduler.ps1`: 17 slots for `ASIAN_LONDON` and 13 for `LONDON_NEWYORK`. This decision does not change it.
- No scheduler rewrite is required or authorized by this decision.

### 1.2 Session-level outcome requirement

- For every applicable FX trading day, each **instrument × session** pair must have **exactly one durable session-level terminal outcome**. That is 4 instruments × 2 sessions = **eight outcomes per applicable FX trading day**.
- Eight session-level outcomes are **not eight scanner invocations**. One session may contain many 15-minute cycles, and an instrument may be evaluated more than once in it. The session-level outcome is the instrument's durable terminal decision for that session, aggregated under the existing `SESSION_SUMMARY` semantics (`scripts/host/canonical_fx_delivery.py`). Those semantics count only the latest terminal decision per instrument. Superseded decisions stay in the audit journal and never add a second outcome.
- Each session's `SESSION_SUMMARY` must report its four instrument-level outcomes with the existing semantics. The target is `Durable evaluations: 4/4`. A shortfall such as `3/4` with a `MISSED` pair does not meet this requirement. It must be reported truthfully and never backfilled, invented or converted into `NO_TRADE`.
- Valid terminal outcomes come from the **current canonical outcome taxonomy**, used with their existing meanings. Examples are `NO_TRADE`, `BLOCKED`, `INSUFFICIENT_DATA`, `EXPIRED`, `OUT_OF_SESSION`, `WATCH_READY` and the `INFO_ONLY_*` states. `LOGIC_SCOPE_NOT_VERIFIED` and `MARKET_CLOSED` keep their existing semantics. Today `LOGIC_SCOPE_NOT_VERIFIED` is the reason code on a `BLOCKED` decision, and a market-closed condition is reported through the existing market-closed / `OUT_OF_SESSION` handling. **This decision adds no terminal state.**
- "Applicable FX trading day" uses the existing session and market-closed rules. A day the existing rules treat as closed is reported through those rules and is not counted as a shortfall in fabricated evaluations.

### 1.3 A session outcome is not a mandatory order

- The eight outcomes are an **outcome-coverage requirement, not a trade quota**. There is no forced trade, no forced READY or WATCH_READY, and no strategy tuning to produce one.
- Only an independently qualified setup that passes every applicable C14, READY, runtime, host, risk and broker gate under a valid standing authorization could ever reach an order. Today no scope holds such authorization.

### 1.4 Acceptance and soak accounting are unchanged

- [`OD1012-S1-ACCEPT`](OWNER_DECISION_REGISTER.md), merged through [PR #169](https://github.com/aungmyat1/AG-profit-trading-assit/pull/169) (merge commit `1f8bf7a`), is preserved unchanged. The **intra-window scheduled cycle** (one scheduled task run) remains the unit for S1 acceptance and soak accounting. The raw-run-record rule (`UNRESOLVED_NO_RECORD`) still applies.
- The session-level outcome defined here is an additional daily coverage and reporting requirement. It does **not** redefine the soak unit and does **not** reinterpret historical acceptance evidence.

### 1.5 Verified scope is unchanged

- The only currently reported verified strategy scope is **`ST_ASIAN_SWEEP_5R_V1@1.1.2` — GBPUSD × ASIAN_LONDON × SWEEP** (scope `S1` in [`strategies/registry.yaml`](../../strategies/registry.yaml), evidence [`docs/status/AGP_ASW_V112_S1_60D_2026-10-11.json`](../status/AGP_ASW_V112_S1_60D_2026-10-11.json)).
- This decision promotes **no** other instrument, session or branch to verified, ready or tradeable status. Outside S1, the existing fail-closed path, such as `BLOCKED` / `LOGIC_SCOPE_NOT_VERIFIED`, is itself the valid session-level outcome. EURUSD stays suspended per the registry.

## 2. Crypto — dynamic scan, combined two-entry ceiling

**Canonical instruments:** BTCUSD, ETHUSD.  
**Venue:** VT Markets MT5 Demo CFDs.

### 2.1 Approved policy

1. Both instruments are scanned dynamically at strategy-appropriate times.
2. Qualified opportunities are ranked by a **deterministic, versioned selection policy**. That policy is not defined here and belongs to the runtime PR. Ranking never replaces qualification: only opportunities that have independently passed their strategy and actionability gates may be ranked.
3. A maximum of **two combined crypto entries across both instruments per MMT trading day**. The cap is combined, not two per instrument.
4. Zero, one or two entries are all acceptable, depending on how many qualified opportunities exist.
5. No trade is forced to meet the daily target.
6. Crypto perpetual-futures contracts or evidence (for example BTCUSDT/ETHUSDT) are never substituted for the VT Markets CFD requirements: contract identity, sizing, cost or data semantics.

### 2.2 Approved crypto trading-day boundary

| Item | Value |
|---|---|
| Timezone | `Asia/Yangon` (IANA zone name; no DST) |
| UTC offset | `UTC+06:30` |
| Daily reset | `00:00:00` MMT |
| Equivalent UTC boundary | `17:30:00 UTC` on the preceding UTC calendar date |

- MMT trading day `D` covers the half-open interval `[D−1 17:30:00 UTC, D 17:30:00 UTC)`.
- Example: `2026-10-12 23:59:59 MMT` (= `2026-10-12T17:29:59Z`) belongs to trading day **2026-10-12**. `2026-10-13 00:00:00 MMT` (= `2026-10-12T17:30:00Z`) belongs to trading day **2026-10-13**.
- Implementations must use timezone-aware timestamps and one canonical MMT trading-day identifier, for example the ISO date `YYYY-MM-DD` of the MMT calendar day. Do not hard-code a bare integer offset. This follows the existing `config/ag_scheduler_v2.yaml` rule.
- The maximum-two-entry counter resets at **00:00:00 MMT**. It does not reset at UTC midnight or broker-server midnight.
- The boundary applies every calendar day, including weekends.
- Scope of this boundary: it defines the **combined crypto entry counter** only. It does not change the daily-reset basis of other OD1010-C6-RISK limits. For example, `config/demo_execution_s1.yaml` keeps its existing `daily_reset_basis: VT_SERVER_DAY` for the S1 scope. The general OD1010-C6-RISK reset timezone stays pending owner policy, as recorded in `docs/PROJECT_OBJECTIVE.md`.

This is an approved governance requirement. It does not authorize runtime changes in this PR.

### 2.3 Enforcement requirements for the later runtime implementation

The separate runtime PR must:

- Enforce the combined daily ceiling across **both** crypto instruments and **all applicable strategies**.
- Use durable, **account-scoped**, concurrency-safe execution accounting, keyed by the canonical MMT trading-day identifier.
- Handle retries, restarts, duplicate submissions, partial fills and uncertain broker outcomes without bypassing the cap. Counting must be conservative: a submission whose broker outcome is uncertain, or a partially filled entry, must never free capacity for another entry until it is reconciled.
- Reconcile broker orders and deals against the canonical trading-day identity.
- **Fail closed** with no crypto entry if the daily counter, the boundary conversion, broker state or any execution-critical identity cannot be trusted. Fail closed also while the versioned selection policy is undefined.
- Never treat two Telegram messages, tickets, proposals or alerts as equivalent to two executed entries. Large-SMC watch alerts are not entries.

The exact implementation and its tests belong to that separate runtime PR.

## 3. C14 and existing risk policy — preserved

Unchanged by this decision:

- Strategy-specific standing-authorization requirements.
- Required gates G1–G4. G5 stays optional observation and G6 stays independently gated.
- Runtime, READY, host and broker safety requirements.
- Strategy L1–L6 verification rules and branch-scoped verification (OD1011-SCOPE).
- The live trading prohibition.
- All existing execution flags (`demo_authorized=false`, `live_authorized=false`, READY OFF).

C14 remains authoritative. Separately authorized automatic DEMO execution requires all applicable independent gates. No per-order Confirm is required within a valid standing-authorized scope. **This decision grants no standing authorization.**

Approved risk ceilings:

| Control | Limit |
|---|---|
| Risk per trade | 0.5% |
| Open positions | Maximum 1 per instrument |
| Trades per strategy | Maximum 5 per day |
| Daily strategy loss | Maximum 1% |
| Account-wide daily loss | Maximum 2% |
| Combined crypto entries | Maximum 2 per MMT trading day, once implemented |

The crypto entry ceiling is an **additional** restriction. It does not replace or weaken any existing control. Where limits overlap, every limit applies and the most restrictive one binds. For example, two same-instrument crypto entries are only possible when the one-open-position-per-instrument limit also permits it.

## 4. Reconciliation with earlier wording

- `docs/PROJECT_OBJECTIVE.md` previously read: "Up to two qualified crypto tickets per day is a planning ceiling, not a trade quota and not an authorization cap" (Issue #47 V5 reconciliation). That bullet is superseded by the combined two-entry **execution** ceiling per MMT trading day in §2. It is still not a trade quota and still not an authorization grant.
- Issue [#47](https://github.com/aungmyat1/AG-profit-trading-assit/issues/47) keeps its historical role as a delivery specification. It is not an independent execution authorization. The current authoritative references are `docs/PROJECT_OBJECTIVE.md`, this record, C14 and the owner decision register.

## 5. Follow-up runtime work (separate PRs; not started here)

1. Crypto combined-entry ceiling: a durable, account-scoped, concurrency-safe counter keyed by MMT trading day at the canonical DEMO execution boundary, with reconciliation and fail-closed behavior as in §2.3, plus tests for boundary conversion, restart, retry, duplicate, partial-fill and uncertain-outcome cases.
2. A deterministic, versioned crypto selection (ranking and tie-break) policy, with a scan schedule at strategy-appropriate times. No profitability score is implied or authorized.
3. FX/Gold coverage audit: verify against durable records that each applicable day yields eight session-level outcomes (`Durable evaluations: 4/4` per session), using the existing scheduler and summary semantics.
4. Dated, accepted evidence before any status claims implementation.
