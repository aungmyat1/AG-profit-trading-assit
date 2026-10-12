---
class: authority
state: DESIGN
owner_reviewed: 2026-10-12
review_by: 2026-11-07
---
# OWNER DECISION — AGP-OD1012-SESSION-CRYPTO

**Status:** OWNER_APPROVED (Aung, 2026-10-12, explicit owner approval). **Scope:** objective/governance only.
**Implementation status:** `NOT_IMPLEMENTED`. Approving this objective does not show that any part of it is implemented.

This decision clarifies the daily FX/Gold evaluation coverage and sets an execution-level ceiling on crypto entries.
It does **not** authorize execution or grant or extend standing DEMO authorization.
It does not change strategy admission, READY, `demo_authorized`, `live_authorized`, risk ceilings, strategy contracts or runtime code.
Ratified C14 ([owner decision](AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md)) is preserved unchanged.

## 1. FX/Gold session coverage

Canonical instruments: **EURUSD, GBPUSD, USDJPY, XAUUSD**.

For each applicable FX trading day:

- Each instrument is evaluated once for `ASIAN_LONDON` and once for `LONDON_NEWYORK`.
  The target is **exactly eight** scheduled instrument-session evaluations (4 × 2).
- Session windows and the DST policy are the existing authoritative definitions (`config/canonical_sessions.yaml`, owner-defined windows). This decision does not change them.
- Every scheduled evaluation produces a deterministic, auditable terminal outcome, for example READY/WATCH, NO_TRADE, BLOCKED or DATA_ERROR.
- A scheduled evaluation is **not a trade quota**. There is no mandatory trade and no forced READY outcome.
- Only a genuinely qualified setup that independently passes every applicable authorization and safety gate may execute.
  Two evaluations per instrument do not imply two executions.

## 2. Crypto dynamic scan and combined entry ceiling

Canonical instruments: **BTCUSD, ETHUSD**. Venue: **VT Markets MT5 Demo CFDs**.
Perpetual-futures evidence (BTCUSDT/ETHUSDT) is never substituted.

- Both instruments are scanned dynamically at suitable strategy-defined times.
- Only qualified, current, non-expired opportunities are ranked.
- **Maximum two combined crypto entries per defined trading day**, across both instruments. The ceiling is not two per instrument.
- Zero or one entry is acceptable.
- Both entries may be on the same instrument if each is independently qualified and every other control permits it. That includes OD1010-C6-RISK's "1 open position per instrument across all strategies".
- No trade is generated to meet a daily target.
- The two-entry ceiling is an **execution-level** ceiling. It must ultimately apply across all strategies and both crypto instruments.
  Limiting Telegram messages, tickets or proposals does not satisfy it.
- Independent strategy admission (L1–L6), runtime binding, READY, standing DEMO authorization and broker risk checks remain separately required.
  This ceiling adds a restriction and replaces none of them.

The earlier wording "up to two qualified crypto tickets per day is a planning ceiling, not an authorization cap" (Issue #47 reconciliation in `docs/PROJECT_OBJECTIVE.md`) is superseded by this execution-level entry ceiling.

## 3. Unchanged

- C14 sequencing, gates and supersession (G1–G4 required, G5 optional, G6 independently gated). `EDGE_VERIFIED` is not a DEMO prerequisite.
- OD1010-C6-RISK DEMO risk ceilings: 0.5% risk per trade, 1 open position per instrument, 5 trades per strategy per day, 1% daily loss per strategy, 2% account-wide daily loss.
  The crypto ceiling is additional; where limits overlap, the stricter one binds.
- Large-SMC remains a separate six-instrument watch capability. Its alerts are not entries and do not count toward, or consume, the crypto entry ceiling.
- No strategy admission, registry, contract, execution, Telegram, scheduler, MT5 or host-configuration change.

**NO EXECUTION AUTHORIZATION CHANGE.**

## 4. Pending implementation-design items (not decided here)

This decision does not set the values below. Any execution-critical item that is still unresolved must **fail closed** (no crypto entry) until it is separately approved and implemented.

| Item | Status |
|---|---|
| Daily reset timezone / day boundary for the crypto ceiling | PENDING_OWNER (OD1010-C6-RISK reset policy is also open in `docs/PROJECT_OBJECTIVE.md`) |
| Exact crypto scanning cadence and times | PENDING_DESIGN (strategy-defined) |
| Ranking weights / any profitability score | PENDING_DESIGN (none authorized; no economic score is implied) |
| Tie-breaking between equally ranked opportunities | PENDING_DESIGN |
| Broker order-counting semantics: partial fills, retries, rejected and uncertain submissions | PENDING_DESIGN (an uncertain submission must count against the ceiling until reconciled) |

## 5. Implementation tasks after this governance merge

1. Specify and implement a durable, cross-strategy crypto daily entry counter at the canonical DEMO execution boundary (`src/demo_execution/`). It should fail closed on a missing day boundary or an uncertain broker state, with tests.
2. Design the crypto scanning cadence and the qualified-opportunity ranking and tie-break rules. Get owner approval before activation.
3. Make the scheduler produce exactly the eight FX/Gold instrument-session terminal records per applicable day, and add an audit check for missing records.
4. Provide evidence of the above before any claim of implementation.
