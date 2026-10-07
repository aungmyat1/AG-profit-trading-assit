# Owner Decision Packet: D_EXEC_DEMO

## Option A — Manual/non-executing Stage A

Current state for every strategy in `strategies/registry.yaml`:
`demo_authorized: false`, `live_authorized: false`, ticket authority `MANUAL_ONLY`
where set. This is where the system already is today — no new work required to stay here.

## Option B — Governed Demo execution

Requires, at minimum (per mission spec, recorded as a checklist — none of these are
claimed satisfied by this mission):

```
[ ] DEMO account identity
[ ] exact ticket/proposal identity
[ ] LOGIC_VERIFIED (not found for any strategy this mission — see T1/T3/T6)
[ ] strategy demo_authorized = true (currently false everywhere)
[ ] owner-required economic gate (none currently passing)
[ ] freshness check
[ ] risk sizing
[ ] cost check
[ ] idempotent intent
[ ] duplicate prevention
[ ] kill switch
[ ] order_check
[ ] same-turn explicit owner confirmation
[ ] canonical Python execution boundary
[ ] broker reconciliation
[ ] static no-Live proof
```

Telegram may transport the owner's command but must not itself mutate broker state —
`src/host_delivery/telegram_message.py` / `src/ticket_delivery/*` exist as delivery
infrastructure; whether any code path lets a Telegram message trigger `order_send` was
NOT behaviorally tested this mission (static name-only grep found no obvious execution
callback, but this is not a proof of absence).

## Bottom line

Every item in Option B's checklist is currently unmet or unverified for every strategy
examined this mission (`ST_ASIAN_SWEEP_5R_V1`, `ST_LARGE_SMC_V1`, `ST_LIQUIDITY_SWEEP_
RETEST_V1`, and the two PR-only candidates). This packet does not choose A or B; it
records that B is not currently reachable without first closing T3/T4/T6's blockers.
