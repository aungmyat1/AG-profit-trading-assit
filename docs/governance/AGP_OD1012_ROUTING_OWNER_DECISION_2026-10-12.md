---
class: authority
state: DESIGN
owner_reviewed: 2026-10-12
review_by: 2026-11-07
---
# OWNER DECISION — OD1012-ROUTING (ticket lanes & execution routing)

**Register ID:** `OD1012-ROUTING`
**Status:** OWNER_APPROVED (Aung, 2026-10-12, owner rulings R1–R6 on PR #177).
**Scope:** documentation, decision record and SPEC only. No runtime code, config, registry, flag, READY, `demo_authorized` or `live_authorized` change.

## 1. Decision

Trade tickets from all three strategy families are routed by the verification status of their **strategy scope** (strategy × pair × session/branch), as set out in [`docs/PROJECT_OBJECTIVE.md`](../PROJECT_OBJECTIVE.md#ticket-lanes--execution-routing-2026-10-12):

- `PASSED` scope **and** owner standing DEMO authorization for that scope → `DEMO_ORDER` (order placed, Telegram report).
- Otherwise → `REPORT_ONLY` (Telegram only, labelled `REPORT-ONLY: <status>`).

**PASSED makes a scope eligible; owner standing authorization makes it routable.**

## 2. Rulings on PR #177

- **R3 — shadow soak removed from PASSED.** `PASSED` = L1–L6 + data (G2) + cost (G3) + host acceptance (G4). C14 and OD1009-D5 govern. The optional soak is at most observation (G5) and is not a routing gate.
- **R4 — C14 kept.** Routing to `DEMO_ORDER` requires `PASSED` **and** a per-scope standing DEMO authorization recorded by the owner.
- **R5 — accepted as encoded, tracked as follow-ups:** (a) executor change replacing per-order `user_confirmed` for authorized scopes; (b) config key for the crypto spread >20% block; (c) runtime scope registry and loader.
- **R2 — spec location.** The schema is `docs/schemas/ticket_verification_routing.yaml`, marked SPEC ONLY and not read by any code. No file under `config/` is part of this decision.
- **Mission item 7 (no flip):** no scope is `PASSED` by this decision. No execution flag is enabled.

## 3. Supersession

The 2026-10-09 flow in which an owner Confirm places an order (Issue #47 V5 per-order confirmation; OD1009-D5) is **superseded for `PASSED` scopes** once the executor change in follow-up (a) lands. Until then, `PASSED` scopes cannot route `DEMO_ORDER` in practice, because the per-order `user_confirmed` gate in `AGENTS.md` remains in force.

The owner may still **edit or close** demo orders from Telegram. Such actions go through the canonical executor with an append-only audit record.

## 4. Non-effects

- No scope is `PASSED`; no runtime registry exists; the default route is `REPORT_ONLY`.
- `demo_authorized=false`, `live_authorized=false`, READY OFF, broker mutations 0.
- This decision is not evidence that any gate has passed (L1–L6, G2–G4).
- Live account is never routable.
