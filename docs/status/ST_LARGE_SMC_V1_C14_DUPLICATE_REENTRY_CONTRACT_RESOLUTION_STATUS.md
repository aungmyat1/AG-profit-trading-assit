# ST_LARGE_SMC_V1 — C14 Duplicate/Re-entry Contract Resolution (2026-09-01)

Status: **C14_RESOLVED_WITH_POST_FILL_DEFERRED**. `strategies/ST_LARGE_SMC_V1.yaml`
version `1.0.2 → 1.0.3`; `RESEARCH_DRAFT` preserved; no engine, proposal, or execution
authority added; `composer.py` untouched.

## Baseline gate

`git status --short` before this phase showed the C12 phase's own uncommitted work
(exactly what the previous turn produced) atop `HEAD=90d382a` (C11 finalization commit).
No ambiguous or unattributed change present. Baseline accepted.

## Version policy

`docs/VERSION_HISTORY.md:35-37` names both "setup qualification" and "intrinsic trade
eligibility logic" as explicit strategy-version-bump triggers — candidate identity and
coexistence policy are exactly that. Same patch-increment reasoning as C11/C12:
`1.0.2 → 1.0.3`.

## C12 carried forward, not reopened

Confirmed still accurate: `C12_CONTRACT=RESOLVED`, `C12_RUNTIME_IMPLEMENTATION=
NOT_IMPLEMENTED`. `historical_replay/orchestrator.py`'s `SetupLedger` (discovered this
phase) is **replay-scoped, in-memory bookkeeping** (`InMemoryKeyValueStore`) used within
a single replay run's funnel-counting, not a persistent, cross-session operational
candidate ledger — this does not contradict the earlier "no persisted candidate object"
finding; it is prior art for how identity/lifecycle tracking *would* compose if an
engine were ever built, not evidence that one already exists operationally.

## The central finding

Targeted search across `proposals/`, `historical_replay/orchestrator.py`, and
`entry_confirmation/entry_models_v1.py` found that AG already has almost the entire
candidate-identity contract implemented as **generic, not Session-specific**
infrastructure, already wired to this exact E1-E3/M1-M3 pipeline:

- `src/proposals/identity.py::setup_id(symbol, combination, direction, reference_key)`
  — a pure `blake2b` hash (`identity.py:29-35`) with **zero** transient/wall-clock input
  (no current tick, no poll time, no snapshot id). Docstring: *"the same underlying SMC
  setup keeps the same identity across every poll regardless of what price does"*
  (`identity.py:1-5`).
- `reference_key_for(reference_type, reference_low, reference_high, reference_level)`
  (`identity.py:38-45`) pins the **E-condition's own structural reference** — the HTF
  gap/POI/liquidity level itself — explicitly so that "two independent setups on the
  same symbol/combination/direction... do NOT collide into one setup_id"
  (`identity.py:7-14`).
- `src/proposals/lifecycle.py` — a full `CREATED`/`STILL_VALID`/`UPDATED`/`INVALIDATED`/
  `EXPIRED` state machine (`lifecycle.py:8`), with an explicit
  `_TERMINAL = (LIFECYCLE_INVALIDATED, LIFECYCLE_EXPIRED)` constant (`lifecycle.py:34`)
  and `_SIGNATURE_FIELDS` (`lifecycle.py:39-40`, including `entry_reference`) defining
  which changes count as `UPDATED` on the *same* identity vs. a new one. This module's
  own docstring **independently corroborates** the C12 finding: *"EXPIRED is supported
  structurally... but this module invents no time-based expiry rule of its own — none
  exists anywhere in entry_confirmation today"* (`lifecycle.py:8-13`).
- `src/historical_replay/orchestrator.py::SetupLedger`/`SetupLedgerRow` — already keys
  bookkeeping by `setup_id` (`orchestrator.py:85`) with an explicit `terminal: bool`
  field (`orchestrator.py:104`) and a `(combination, setup_id)` dedup key
  (`orchestrator.py:177`), all built and tested against this exact pipeline.

Nothing above is Session-Trading-specific — no session windows, no per-day slot counts,
no symbol-priority ordering. It operates purely on symbol/combination/direction/
reference_key and generic entry-metadata fields, so reusing it does not violate the
"do not import Session limits" boundary.

## What resolves deterministically from this (all by reuse)

- **Exact duplicate key**: `setup_id(symbol, combination, direction, reference_key)`.
- **Identity layers**: `E_event_identity` = `QualifiedEEvent.event_id`; `M_model_identity`
  = `SMCEntryCombinationResult.maneuver`; `combination_identity` =
  `SMCEntryCombinationResult.combination` (`"E1M1".."E3M3"`, already part of the
  `setup_id` hash input); `target_identity_role` = **attribute only** — confirmed
  directly from the hash formula, target fields are absent from `setup_id`'s inputs, so
  a different C11 target never implies a different candidate; `strategy_candidate_
  identity` = `setup_id` itself.
- **Coexistence matrix** — all six cross-combinations resolve by construction, not
  judgment call: same-E/same-M/same-interval → `SAME_CANDIDATE_UPDATED` (lifecycle
  transition, not a new identity); same-E/different-M and different-E/(same or
  different)-M → `DISTINCT_CANDIDATE` (hash input differs); any entry/target
  combination → identity is never entry-price- or target-derived, so numeric
  coincidence never implies duplication. Verified the different-E/same-M row directly
  against the golden setup IDs (`SETUP-EURUSD-E1M3-29ef3d6e78d5f9c2` vs.
  `SETUP-EURUSD-E3M3-27d758322ae69d05`, same symbol/direction/timestamp, different
  `setup_id`) — read, not rerun.
- **Multi-candidate output is deliberate architecture**: `composer.py`'s own docstring
  — "every valid combination is returned... producing anywhere from 0 to 9
  combinations" — settles `selected_combination=None` as `OPTIONAL_PORTFOLIO_HANDOFF`,
  not an unimplemented gap. `MULTI_CANDIDATE_OUTPUT` is confirmed correct;
  `ONE_SELECTED_COMBINATION` was never the intended architecture.
- **Selection boundary preserved**: strategy emits all distinct valid candidates;
  portfolio/selection remains a downstream, not-yet-built authority — matching this
  project's own preferred separation (spec section 41 of this phase), not invented.
- **Terminality**: `EXPIRED` and `INVALIDATED` both terminal, per
  `proposals/lifecycle.py`'s own `_TERMINAL` constant — code evidence, not the earlier
  citation-only reasoning C12 relied on.
- **Revival**: a later, *different* eligibility interval under the *same* `setup_id`
  (non-monotonic per C12) is a new **occurrence** under a stable identity, not a
  "revived" one and not a new `setup_id` (interval bounds are excluded from the hash).
  Revival of the *same* occurrence remains prohibited.
- **Suppression point**: conceptually belongs after `composer.compose()` output
  (computing `setup_id` per result and comparing against prior occurrences), not inside
  `composer.py` or any single M-model — `composer.py` was not modified.
- **C18 interaction**: opposite-direction candidates are distinct identities (direction
  is part of the hash) by construction; whether/how simultaneously-valid opposite-
  direction candidates should be reconciled remains C18's open question, not resolved
  here.
- **Post-fill re-entry**: `DEFERRED` — no execution or position-lifecycle authority
  exists for `ST_LARGE_SMC_V1` (`status=RESEARCH_DRAFT`, `engine=NOT_IMPLEMENTED`);
  this is a future execution/portfolio-contract question.

No item required `OWNER_DECISION_REQUIRED` — everything traced back to already-existing,
already-tested infrastructure.

## YAML reconciliation

`strategies/ST_LARGE_SMC_V1.yaml` — added a `candidate_identity:` block (`status:
CONTRACT_ONLY`, `implementation: NOT_IMPLEMENTED`), parallel in structure to the prior
`target_model:` and `candidate_lifecycle:` blocks. `version: 1.0.2 → 1.0.3`. No field in
`exit_and_lifecycle` touched (out of C14's scope). `composer.py` not modified, no
persistent candidate state created — this phase is contract-only, as instructed.

## Non-regression / authority

No file under `src/` was modified — `composer.py`, Stage1, Stage2, `proposals/`,
`market_structure/`, `liquidity/`, `entry_confirmation/`, `trade_management/`,
`portfolio`, `risk`, `execution`, `mt5` all untouched (read-only inspection only).
`AG_TRADE_ASSISTANT_V1_0_2` and `ST_ASIAN_SWEEP_5R_V1 v1.1.1` unaffected.
`actionable_READY`, `portfolio_authority`, `risk_sizing_authority`,
`proposal_authority`, `execution_authority` remain `BLOCKED`; `order_check=0`,
`order_send=0`.

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
?? docs/status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md
```

No `src/` file, `composer.py`, Stage1, Stage2, Session-strategy file, or execution file
touched.

## Next remaining blocker

Completeness now: `RESOLVED=12` (C02, C03, C04, C05, C07, C08, C09, C11, C12, C13,
**C14**, C17), `PARTIALLY_RESOLVED=5` (C01, C06, C10, C16, C18),
`UNRESOLVED_CONTRACT=1` (C15, non-blocking). Per the minimum-core ordering
(...→ invalidation → target → expiry → lifecycle → data), the earliest still-open item
is **C10's residual SL-distance formula (UC-009)** — deliberately left open across the
C11 and C12 phases; its candidate-invalidation half is already reused, only the actual
broker-stop distance (a genuine, still-un-adopted fork between ST-C1's unified rule and
`v3.6`'s per-model formulas) remains.

## Tests

`pytest tests/test_large_smc_registration.py tests/test_dual_workflow_boundaries.py` —
6/6 passed (yaml changed). Repo-wide suite and golden slice not run — no `src/` or
replay code changed.

## Files changed

`strategies/ST_LARGE_SMC_V1.yaml`, `docs/specs/LARGE_SMC_V1_SPEC.md`,
`docs/VERSION_HISTORY.md`, `strategies/STRATEGY_LEDGER.md`, `PROJECT_STATUS.md`,
`docs/README.md`, and this document. No production source file changed.
