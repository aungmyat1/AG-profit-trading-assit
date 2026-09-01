# ST_LARGE_SMC_V1 — Post-READY Pending-Entry Expiry: Decision Packet

Status: **UNSIGNED — OWNER DECISION REQUIRED**. Date: 2026-09-02.
Phase: `ST_LARGE_SMC_V1_RESEARCH_ONLY_FUNNEL_V1`.

This is a decision packet, not a decision. No option below is selected, adopted, or
implemented. `src/large_smc_research/engine.py` returns `BLOCKED`
(`reason_code=UNSIGNED_CONTRACT:PENDING_ENTRY_EXPIRY`) for every candidate that reaches
its entry-available (READY-equivalent) state rather than assuming any lifetime for an
unfilled entry.

## Why this is distinct from C12 (already resolved)

`strategies/ST_LARGE_SMC_V1.yaml`'s `candidate_lifecycle:` block (C12,
`RESOLVED_BY_REUSE`) governs **pre-activation** validity only — whether the underlying
E-context reference is still eligible at all
(`historical_replay.stage1.QualifiedEEvent.is_eligible_at()`). It says nothing about how
long a specific READY-equivalent candidate, once formed, stays live waiting to be filled
before it should be treated as abandoned. Those are two different clocks:

- E-context eligibility expiry — **resolved** (C12): governs whether a candidate can
  even be evaluated/re-evaluated at all.
- Post-READY pending-entry expiry — **unresolved**: governs how long an already-formed,
  entry-available candidate remains actionable before an unfilled order should be
  treated as expired.

No AG-native clock for the second kind exists anywhere (the same audit that resolved
C12 found zero `EXPIRED`/`max_bars`/`timeout`/`window` hits tied to a post-READY timer
in `entry_confirmation/` or `historical_replay/`).

## Candidate options (research references and generic patterns — none adopted)

1. **Fixed N-bar / N-hour TTL** — e.g. the kind of arbitrary bar-count window seen in
   some SMC research resources (the task explicitly warns against silently adopting an
   arbitrary "15-M5-bar" style TTL from a resource without it being separately signed).
   Simple, but the exact N is a genuine parameter choice with no AG evidence behind it.
2. **Bound by the underlying eligibility interval** — the pending entry expires no later
   than the E-context eligibility interval's own `end` (already-computed,
   `QualifiedEEvent.eligibility_intervals`). Reuses an already-frozen boundary with zero
   new detection, but conflates a structural E-context question with a fill-lifetime
   question that may legitimately need its own, shorter window.
3. **Structural invalidation only, no time limit** — the pending entry stays live until
   the M-model's own structural invalidation triggers (already reused,
   `SMCEntryCombinationResult.invalidation*`) or the underlying E-context expires (C12).
   Simplest to state, but means an unfilled entry could remain nominally "live" for an
   unbounded span if neither condition fires, which may not reflect realistic order
   management.
4. **Session/day boundary** — expire at the next session or trading-day boundary. Not
   currently supported by any signed session field on this strategy (C15, time
   restrictions, is itself `UNRESOLVED_CONTRACT`, non-blocking) — would require
   resolving C15 first.

## What a signed contract must specify

- the exact clock/window (or explicit "no separate window, defer entirely to C12 + structural invalidation" if option 3 is chosen);
- decision timestamp / no-lookahead guarantee, matching every other contract here;
- same-bar precedence if a pending entry could both fill and expire on the same bar;
- missing-data behavior (fail closed, never fabricate an expiry from unprovable
  chronology, matching C12's own discipline).

## Next step

Owner reviews this packet and either selects one of the above (or a variant), producing
an explicit contract addition to `strategies/ST_LARGE_SMC_V1.yaml` with a strategy
version bump (`docs/VERSION_HISTORY.md`: "intrinsic trade eligibility logic" is an
explicit bump trigger), or requests further research. Until then, pending-entry expiry
stays `UNSIGNED` and the engine continues to fail closed.
