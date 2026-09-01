# ST_LARGE_SMC_V1 — C14A Candidate Occurrence Identity Audit (2026-09-01)

Status: **OWNER_DECISION_REQUIRED**. This is a correction to the prior C14 phase's
overclaim, not a new resolution. `strategies/ST_LARGE_SMC_V1.yaml` version **not**
bumped (remains `1.0.3`) — no new semantics were frozen. No production code changed.

## Baseline gate

`git --no-pager status --short` was clean; `HEAD=5211edb` ("Update ST_LARGE_SMC_V1
strategy to version 1.0.3 with C12 and C14 contract resolutions"), matching the
accepted prior work exactly. Baseline accepted.

## What the prior C14 phase got right

`setup_id(symbol, combination, direction, reference_key)`
(`src/proposals/identity.py:29-35`) is a genuine, already-implemented, generic
(not Session-specific) **setup-family** identity: pure `blake2b` hash, zero
transient/wall-clock input, `reference_key` correctly excludes M-model geometry and
target fields. The coexistence findings built on it (different E/M → distinct family;
target is an attribute, not identity) remain correct and are unchanged.

## What the prior C14 phase got wrong

It treated `setup_id` as sufficient for the *entire* duplicate-suppression/terminal-
lifecycle contract. Two things were missed:

**1. `setup_id` cannot distinguish occurrences within a family.**
`QualifiedEEvent.eligibility_intervals: Tuple[Tuple[datetime, datetime], ...]`
(`historical_replay/stage1.py:47`) — confirmed directly: one `event_id` (and by
identical hash-shape, one `setup_id`) legitimately spans **multiple, disjoint**
eligibility intervals (non-monotonic, `FALSE→TRUE→FALSE→TRUE` per `stage1.py:11`,
already established in C12). The prior phase's "revival" reasoning ("a later interval
is a new occurrence, not revived, since interval bounds are excluded from the hash")
was directionally right but never actually verified that anything could *tell two such
occurrences apart* — it can't, today.

**2. No canonical M-candidate structural identifier exists anywhere.** Inspected
directly:

| Type | Timestamp fields | ID field |
|---|---|---|
| `M1Result` (`m1_character_change_inducement.py:75-104`) | **none** | none |
| `M2Result` (`m2_supply_demand_shift.py:74-104`) | `zone_failure_time`, `structural_break_time` | none |
| `M3Result` (`m3_sweep_drop_pump.py:98-126`) | `choch_time` | none |
| `ZoneResult` (`supply_demand/models.py:43-55`) | `origin_time` | none |
| `ValidatedOrderBlock` (`supply_demand/ob_contract.py:96-109`) | `origin_time` | none |

M1 is the weakest case: zero timestamp fields at all, only
`entry_array_type`/`entry_array_low`/`entry_array_high` (price/type). M2/M3 have a
partial timestamp via their own fields or the `ZoneResult`/`ValidatedOrderBlock`
objects they reference, but no id field anywhere in the chain.

**3. The lifecycle store cannot distinguish "revival" from "new occurrence" either —
confirmed by code, not inferred.** `proposals/lifecycle.py::update_proposal_lifecycle`'s
`store` is keyed **only** by `setup_id`:

```python
prior = store.get(proposal.setup_id)          # lifecycle.py:69
...
if prior is None or prior.get("lifecycle") in _TERMINAL:
    lifecycle, changed = LIFECYCLE_CREATED, ()  # lifecycle.py:72-73
...
store.put(proposal.setup_id, {...})            # lifecycle.py:80
```

When a prior record is terminal (`_TERMINAL = (LIFECYCLE_INVALIDATED,
LIFECYCLE_EXPIRED)`, `lifecycle.py:34`) and new evidence arrives for the *same*
`setup_id`, the code transitions to `CREATED` — but **overwrites** the prior terminal
record in the same store slot. This is `SETUP_FAMILY_STATE_OVERWRITE`, not
`OCCURRENCE_HISTORY`. `OCCURRENCE_IDENTITY_GAP = YES`. (Separately, `historical_
replay/orchestrator.py`'s `SetupLedger` was re-confirmed as replay-scoped, in-memory
bookkeeping — not a live, persistent occurrence store either.)

## What is frozen this pass (composition, not full resolution)

- **`eligibility_interval_identity = hash(event_id, interval_start, interval_end)`** —
  `THIN_ADAPTER`: composed entirely from fields that already exist
  (`event_id`, and the interval bounds already present in `eligibility_intervals`), no
  new detection logic, market-time-only (interval bounds are candle/event-derived,
  never wall-clock — inherits C12's no-lookahead guarantee), restart-stable. No
  function currently computes this exact hash; nothing was implemented.
- **The two-layer identity model itself** (`SETUP_FAMILY_ID` = existing `setup_id`;
  `CANDIDATE_OCCURRENCE_ID` = a function of `setup_family_id` +
  `eligibility_interval_id` + `M_candidate_identity`) is confirmed structurally sound
  and consistent with all existing evidence — the *shape* of the answer is right, only
  the `M_candidate_identity` input remains genuinely unresolved.

## What remains genuinely open — owner decision

**`M_candidate_identity`: no canonical id exists for any of M1/M2/M3.** Per instruction,
prices must not be the *primary* identity component (they're attributes, can shift due
to normalization/re-computation). Two evidence-supported options, neither adopted:

- **Option A — best available evidence tuple per model** (`M2`/`M3` →
  `(entry_array_type, origin_time-or-structural_break_time/choch_time)`; `M1` →
  `(entry_array_type, entry_array_low, entry_array_high)` only, since no timestamp
  exists at all for M1). Stable, restart-reproducible, no code change required — but
  M1's tuple is price-only, carrying real collision risk if price re-tests the same
  zone within one eligibility interval and produces a structurally-different-but-
  numerically-similar array.
- **Option B — add an explicit `source_id`/`origin_id` field** to `M1Result` and
  formalize one on `ZoneResult`/`ValidatedOrderBlock`. The clean, durable fix, but is a
  `src/entry_confirmation`/`src/supply_demand` code change — explicitly out of scope
  for this contract-only phase (`DO NOT MODIFY proposal lifecycle code`, `DO NOT
  IMPLEMENT`).

No recommendation is made between these without owner input — Option A costs nothing
now but leaves a known weak spot at M1; Option B is more correct but requires
authorizing a small code change in a later, separately-scoped phase.

## Test specification (not implemented — per phase policy, no test-only additions were authorized)

- **Repeated poll**: same setup family, same eligibility interval, same M candidate,
  multiple evaluation timestamps → same `candidate_occurrence_id`.
- **New interval**: same setup family, interval A (terminal), later interval B → old
  occurrence remains terminal, new occurrence gets a distinct `candidate_occurrence_id`
  (requires `eligibility_interval_id` to differ, which it does by construction).
- **Multiple M candidates, same interval**: if the (currently unresolved)
  `M_candidate_identity` differs, expect a distinct `candidate_occurrence_id` — cannot
  be verified deterministically today given the M-candidate identity gap.
- **Terminal reappearance**: occurrence A = `EXPIRED`; later occurrence B qualifies → A
  must remain `EXPIRED`, B is distinct and current — **currently fails** against the
  existing `store` (keyed only by `setup_id`, overwrites rather than preserves).
- **Restart**: same evidence after restart reconstructs the same `setup_family_id`,
  `eligibility_interval_id`, and (once resolved) `M_candidate_identity` — the first two
  are already restart-stable; the third is blocked on the owner decision above.

## Non-regression / authority

No file under `src/` was modified — `proposals/identity.py`, `proposals/lifecycle.py`,
`composer.py`, Stage1, Stage2 all untouched (read-only inspection only).
`AG_TRADE_ASSISTANT_V1_0_2` and `ST_ASIAN_SWEEP_5R_V1 v1.1.1` unaffected.
`actionable_READY`, `portfolio_authority`, `risk_sizing_authority`,
`proposal_authority`, `execution_authority` remain `BLOCKED`; `order_check=0`,
`order_send=0`.

## Diff boundary check

```
git status --short (after this phase):
 M PROJECT_STATUS.md
 M docs/README.md
 M docs/specs/LARGE_SMC_V1_SPEC.md
 M strategies/ST_LARGE_SMC_V1.yaml
?? docs/status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md
```

No `src/` file, `proposals/`, `composer.py`, Stage1, Stage2, Session-strategy file, or
execution file touched. `docs/VERSION_HISTORY.md` and `strategies/STRATEGY_LEDGER.md`
were **not** touched — no new semantics were frozen this pass, only an overclaim was
corrected (per phase policy: do not update version history as if C14 were complete).

## Next remaining item

`strategies/ST_LARGE_SMC_V1.yaml` version remains `1.0.3`. C14 is now honestly
`PARTIALLY_RESOLVED`. Two open threads exist: (1) this phase's own
`M_candidate_identity` owner decision (Option A vs. B above), and (2) C10's residual
SL-distance formula (`UC-009`), earlier in the minimum-core ordering and left open
since the C11 phase. Neither is resolved here.

## Tests

`pytest tests/test_large_smc_registration.py tests/test_dual_workflow_boundaries.py` —
6/6 passed (yaml changed). No new tests added (not authorized this phase). Repo-wide
suite and golden slice not run — no `src/` or replay code changed.

## Files changed

`strategies/ST_LARGE_SMC_V1.yaml` (correction: `candidate_identity.authority`
downgraded, new `candidate_occurrence_identity` block added), `docs/specs/
LARGE_SMC_V1_SPEC.md` (§19 rewritten, register/completeness corrected),
`PROJECT_STATUS.md`, `docs/README.md`, and this document. No production source file
changed.
