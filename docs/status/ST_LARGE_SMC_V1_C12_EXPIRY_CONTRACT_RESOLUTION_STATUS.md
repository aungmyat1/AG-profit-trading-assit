# ST_LARGE_SMC_V1 — C12 Expiry Contract Resolution (2026-09-01)

Status: **C12_RESOLVED_BY_REUSE**. `strategies/ST_LARGE_SMC_V1.yaml` version
`1.0.1 → 1.0.2`; `RESEARCH_DRAFT` preserved; no engine, proposal, or execution authority
added.

## Baseline gate

`git status --short` before this phase was clean; `HEAD` was `90d382a` ("Update
ST_LARGE_SMC_V1 strategy to version 1.0.1 with C11 contract finalization"),
confirmed via `git show --stat` to contain exactly the accepted UC-001/3×3/C11 work.
Baseline accepted.

## Version policy

`docs/VERSION_HISTORY.md:35-37` names "intrinsic trade eligibility logic" as an explicit
strategy-version-bump trigger; candidate expiry is exactly that. Same patch-increment
reasoning as the C11 phase (resolving a previously-unsigned contract by deriving the
only consistent answer from already-existing, already-frozen logic —
`STRATEGY_LEDGER.md`'s v1.1.0→v1.1.1 precedent): `1.0.1 → 1.0.2`.

## C11 preserved, not reopened

`target_model:` (anchor, primary/fallback tiers, `STATIC` mode, `NO_TRADE`/
`REJECT_NO_TARGET`) is unchanged. C12's one interaction with it (target consumed before
activation) resolves to `INVALIDATED`, explicitly without reselection — confirmed no
`C11_C12_SEMANTIC_CONFLICT`.

## The central finding

The prior assumption — that `EntryModelState.EXPIRED` was "reused end-to-end" with only
its trigger left open — did not survive direct verification. Targeted search (`EXPIRED
|expir|max_bars|timeout|stale|window|age` etc.) across `m1_character_change_
inducement.py`, `m2_supply_demand_shift.py`, `m3_sweep_drop_pump.py`, `entry_array.py`,
`engine_v2_1.py`, and `composer.py` found **zero hits outside the `EntryModelState` enum
declaration itself** (`entry_models_v1.py:101`). No M-model, the composer, or any
Stage2/live-snapshot caller ever transitions anything into `EXPIRED`.

The reason became clear from `historical_replay/stage2.py::evaluate_entry_stage()`
(`stage2.py:192-217`): it calls `get_tick()` and `_m5_side_primitives()` fresh on
**every invocation**, re-deriving `m5_candles`, `m5_fvg`, `m5_obs`, `m2_zones`, and
`inducement_candidates` from current market data each time. There is no persisted
candidate object anywhere that "waits" across evaluation timestamps and could time out
— consistent with the earlier architecture-audit finding that AG has no Large-SMC
research-candidate ledger at all.

The only real, already-implemented validity clock found anywhere is
`historical_replay/stage1.py::QualifiedEEvent.is_eligible_at(t)`
(`stage1.py:47,51-57`):

```python
eligibility_intervals: Tuple[Tuple[datetime, datetime], ...]

def is_eligible_at(self, t: datetime) -> bool:
    return any(start <= t < end for start, end in self.eligibility_intervals)
```

Stage2's own docstring states this gate is authoritative for *all three* M-models:
*"Stage 2 must not evaluate M1/M2/M3 for an event outside its real eligibility
window."* Since E1, E2, and E3 all produce `eligibility_intervals` the same way and are
gated identically, and no M-model has an independent clock anywhere in the code, C12
resolves to **`SHARED_EXPIRY_DEPENDENCY`** (not `E_CONTEXT_LIFETIME_ONLY`, not
independent `M_CANDIDATE_EXPIRY`): M1, M2, and M3 all defer entirely to this one shared
mechanism. This is presented as a discovery from tracing the actual call graph, not an
invented rule — flagged transparently in case independent M-specific timers were
intended but simply never built.

## What resolves deterministically from this (all by reuse)

- **Clock source**: `QualifiedEEvent.is_eligible_at(t)`, shared across M1/M2/M3.
- **Boundary semantics**: half-open `[start, end)`, exactly as coded — not an invented
  convention.
- **Same-bar precedence**: `EXPIRY_FIRST`, forced by construction — at `t == end`,
  `is_eligible_at` is already `False`, so a combination cannot newly qualify on the
  exact boundary bar. No owner decision needed (unlike C11's tie-break question, this
  one falls out of already-written code with no ambiguity).
- **Non-monotonic eligibility**: `stage1.py:11` — intervals may go
  `FALSE → TRUE → FALSE → TRUE`. A later eligible interval is a new evaluation, not a
  revived one.
- **Terminal semantics**: `EXPIRED` is non-actionable; revival of the *same* combination
  instance is prohibited — citing this engagement's own first architecture-audit-phase
  invariant ("...must eventually prevent...resurrecting invalidated candidates"), not
  reinventing it.
- **Structural invalidation** (kept distinct from time-based expiry, per the C11/C12
  phase's own instruction to preserve `INVALIDATED` vs. `EXPIRED`):
  `entry_confirmation/invalidation.py`'s `ManeuverInvalidation` (price, source_type,
  reason, trigger, triggered) — `EXACT_REUSE`, already wired for M1/M2 via
  `entry_array.py` and for M2's own zone-invalidation path (`m2_invalidation()`,
  `invalidation.py:103-128`). M3's IFVG-specific invalidation remains repo-wide
  `PARTIAL` (`inverted_gap_policy`), flagged rather than assumed equivalent.
- **Target consumed before activation** (a new composition, not yet wired anywhere,
  classified `THIN_CONTRACT_ADAPTER`): `INVALIDATED` for either tier — reusing
  `liquidity.status.compute_status` (the same function already used once at target
  selection) re-invoked at a later evaluation timestamp. Classified `INVALIDATED`
  rather than `EXPIRED` because it is a structural/liquidity-status change, not a
  time/interval boundary. Explicitly does **not** trigger reselection — C11's
  `TARGET_MODE=STATIC` stands unmodified; no `C11_C12_SEMANTIC_CONFLICT`.
- **Data-quality failure**: `INSUFFICIENT_DATA` (existing `EntryModelState` value) —
  never fabricate `EXPIRED` from unprovable chronology.
- **No-lookahead**: `is_eligible_at` itself takes no future information;
  `eligibility_intervals` are reconstructed only from already-closed evidence
  (previously verified project-wide).
- **Restart/replay determinism**: `EXACT_REUSE` — the same `(event, evaluation_time)`
  always yields the same `is_eligible_at()` result, previously proven byte-identical
  across repeated runs (`TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md`'s determinism
  check).
- **No C15 dependency**: `eligibility_intervals` derive from market/structural evidence
  (gap-fill/POI-reaction/sweep-reclaim windows per E-model), not from session/
  trading-hour definitions — `C12_DEPENDS_ON_C15` does not apply.

No item required `OWNER_DECISION_REQUIRED` — everything traced back to an
already-existing, already-frozen mechanism once the call graph was followed far enough.

## Entry-array expiry (per model)

M1 and M2 both call `entry_array.py::evaluate_entry_array` — the same
temporal/causal-association geometry cited in the C11 phase (FVG/OB origin must fall
within the displacement leg's own time window) already governs whether an entry array
is even recognized; no separate expiry timer needed beyond that association rule plus
the shared E-eligibility gate above. M3's IFVG entry array inherits the same repo-wide
`PARTIAL` caveat as its invalidation.

## YAML reconciliation

`strategies/ST_LARGE_SMC_V1.yaml` — added a `candidate_lifecycle:` block
(`status: CONTRACT_ONLY`, `implementation: NOT_IMPLEMENTED`), parallel in structure to
the prior phase's `target_model:` block. `entry.expiry: UNSIGNED` →
`entry.expiry: SEE_CANDIDATE_LIFECYCLE`. `exit_and_lifecycle.maximum_holding_period`
left untouched (`UNSIGNED`) — explicitly **post-fill** position duration, out of C12's
pre-activation scope (spec section 8 of this phase's own instructions). `version:
1.0.1 → 1.0.2`.

## Non-regression / authority

No file under `src/` was modified. `AG_TRADE_ASSISTANT_V1_0_2` and
`ST_ASIAN_SWEEP_5R_V1 v1.1.1` unaffected. `actionable_READY`, `portfolio_authority`,
`risk_sizing_authority`, `proposal_authority`, `execution_authority` remain `BLOCKED`;
`order_check=0`, `order_send=0`.

## Diff boundary check

```
git status --short (after this phase):
 M PROJECT_STATUS.md
 M docs/README.md
 M docs/VERSION_HISTORY.md
 M docs/specs/LARGE_SMC_V1_SPEC.md
 M strategies/STRATEGY_LEDGER.md
 M strategies/ST_LARGE_SMC_V1.yaml
?? docs/status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md
```

No `src/` file, no execution file, no Session-strategy file touched.

## Next remaining blocker

Completeness now: `RESOLVED=11` (C02, C03, C04, C05, C07, C08, C09, C11, **C12**, C13,
C17), `PARTIALLY_RESOLVED=5` (C01, C06, C10, C16, C18), `UNRESOLVED_CONTRACT=2` (C14,
C15). **UC-013 — C14 (duplicate/re-entry)** is the first remaining blocker:
`SMCEntryCombinationResult.selected_combination` is always `None`, and the composer
explicitly defers any dedup/selection policy (confirmed in the 3×3 phase). Target
identity (`target_model`) and candidate lifecycle (`candidate_lifecycle`, non-monotonic
per-interval evaluation) are now both available as potential inputs to a future
duplicate-identity rule, but the policy itself remains undefined. C15 (session/time,
non-blocking) does not block C14.

## Tests

`pytest tests/test_large_smc_registration.py tests/test_dual_workflow_boundaries.py` —
6/6 passed (yaml changed). Repo-wide suite and golden slice not run — no `src/` or
replay code changed.

## Files changed

`strategies/ST_LARGE_SMC_V1.yaml`, `docs/specs/LARGE_SMC_V1_SPEC.md`,
`docs/VERSION_HISTORY.md`, `strategies/STRATEGY_LEDGER.md`, `PROJECT_STATUS.md`,
`docs/README.md`, and this document. No production source file changed.
