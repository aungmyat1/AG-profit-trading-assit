---
class: authority
state: DESIGN
owner_reviewed: 2026-10-12
review_by: 2026-11-07
---
# OWNER DECISION — OD1012-ROUTING (ticket lanes & execution routing)

**Register ID:** `OD1012-ROUTING`
**Status:** OWNER_APPROVED (Aung, 2026-10-12, owner rulings on PR #177, mission AGP-PR177-RECONCILE; supersedes the earlier single-`PASSED` draft).
**Scope:** documentation, decision record and SPEC only. No runtime code, config, registry, flag, READY, `demo_authorized` or `live_authorized` change. No merge is implied.

## 1. Decision

Tickets from all three strategy families report every relevant scope with its status ([`PROJECT_OBJECTIVE.md`](../PROJECT_OBJECTIVE.md#ticket-lanes--execution-routing-2026-10-12)).

| Axis | Values |
|---|---|
| `verification_status` | `UNVERIFIED` \| `IN_VERIFICATION` \| `LOGIC_VERIFIED` \| `STALE_IDENTITY` |
| `eligibility` | `NOT_ELIGIBLE` \| `EXECUTION_ELIGIBLE` |
| `execution_route` | `REPORT_ONLY` \| `DEMO_ORDER` (with required `route_reason`) |

- `LOGIC_VERIFIED` = exact scope (strategy × pair × session × branch) passed L1–L6.
- `EXECUTION_ELIGIBLE` = `LOGIC_VERIFIED` + data (G2) + cost (G3) + host acceptance (G4) + owner per-scope standing DEMO authorization (C14).
- `DEMO_ORDER` = `EXECUTION_ELIGIBLE` AND every per-ticket guard passes at send time.
- Non-eligible tickets are labelled **`REPORT ONLY — NON-ACTIONABLE`**, may show a clearly labelled hypothetical entry/SL/TP, and never enter the order queue.

**PASSED makes a scope eligible; owner standing authorization makes it routable.**

## 2. Rulings

- **R0 — base.** Branch base is `origin/main` at `39ed85f`. #175 and its regeneration PR are **not on main**. No merge-in was required because main has not moved. A follow-up merge is expected when #175 lands.
- **R1 — states.** The single `PASSED` state is replaced by the three axes above.
- **R2 — spec location.** `docs/schemas/ticket_verification_routing.yaml`, marked SPEC ONLY and not read by any code. No file under `config/` is part of this decision.
- **R3 — soak.** The shadow soak is an optional diagnostic, or host-acceptance evidence at most. It is **not** an eligibility gate. C14 and OD1009-D5 govern.
- **R4 — C14 kept.** `DEMO_ORDER` requires `EXECUTION_ELIGIBLE` **and** an owner per-scope standing DEMO authorization.
- **R5 — lanes.** Large-SMC detection verification is not entry verification. No retroactive execution of tickets issued before eligibility.
- **R6 — references only.** Guards (risk 0.5%, cost block 0.25R, crypto spread >20%, LSMC min remaining reward 0.5), the 15-minute cadence, the 8 durable session outcomes, OD1012-S1-ACCEPT, the combined 2-entry crypto cap and the `00:00 Asia/Yangon` crypto day boundary are referenced, not altered. The day boundary is in #175, not yet on main.
- **Mission (no flip).** No scope is `LOGIC_VERIFIED` or `EXECUTION_ELIGIBLE` by this decision. No execution flag is enabled.

## 3. Supersession

The 2026-10-09 flow in which an owner Confirm places an order (Issue #47 V5 per-order confirmation; OD1009-D5) is **superseded for `EXECUTION_ELIGIBLE` scopes** once follow-up (a) lands. Until then, no scope can route `DEMO_ORDER` in practice, because the per-order `user_confirmed` gate in `AGENTS.md` remains in force.

The owner may still **edit or close** demo orders from Telegram. Such actions go through the canonical executor with an append-only audit record.

## 4. Follow-ups (not in this decision)

- (a) Executor change replacing per-order `user_confirmed` for `EXECUTION_ELIGIBLE` scopes.
- (b) Record 2026-10-09 owner ratification of the crypto spread >20% block in the register (`OD1009-CRYPTO-SPREAD`, done in this PR) and add its config key. The config key is not yet added.
- (c) Runtime scope registry and loader.
- (d) Read-only all-family Telegram status reports. This is the next implementation priority.

## 5. Non-effects

- No scope is eligible; no runtime registry exists; the default route is `REPORT_ONLY`.
- `demo_authorized=false`, `live_authorized=false`, READY OFF, broker mutations 0.
- This decision is not evidence that any gate has passed (L1–L6, G2–G4).
- Live account is never routable.
