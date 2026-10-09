---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# SESSION_TRADE_V1 ticket authority — MANUAL_ONLY, no order authority (2026-10-06)

Owner-requested authority change. Base: `main` at `13ffc38`.

## Registry state (unchanged by this PR)

`strategies/registry.yaml` `SESSION_TRADE_V1` already reads `ticket_authority: MANUAL_ONLY`,
`demo_order_authority: NONE` (PR #37 Phase 1). `demo_authorized` is **already `false`**: it was
withdrawn by owner decision D3 on 2026-09-30, and no authority source in this repository still
says `true`. The only remaining `"demo_authorized": true` is in the historical snapshot
`docs/v2/AG_V2_BASELINE_MANIFEST_V1.json`. It is not read by any loader and is left unchanged
(historical evidence).

## Change: the ticket loader fails closed on demo/live flags

Until now, `src/v1_tickets/authority.py` validated `ticket_authority`, `logic_status`,
`economic_status` and `demo_order_authority`, but not `demo_authorized`/`live_authorized`. A
registry edit back to `demo_authorized: true` would therefore not have blocked tickets. Now, for
any strategy resolved for manual tickets, `demo_authorized` and `live_authorized` must be
**present and exactly `false`**. Missing, `true`, a string or any non-bool value gives
`REGISTRY_TICKET_AUTHORITY_INVALID:<field>` and zero tickets. Order authority on this path is
expressed only as `demo_order_authority: NONE`.

No effect on current behavior: both ticket strategies (`ST_ASIAN_SWEEP_5R_V1`,
`SESSION_TRADE_V1`) carry `false`/`false`. Execution gates (`config/trading.yaml`,
`execution/`) and the `demo_authorized` readers outside `v1_tickets` are untouched.

Tests: `tests/test_manual_ticket_authority.py` (+13 cases: each flag missing / `true` /
non-bool for both strategies; the SESSION_TRADE_V1 registry pin).
