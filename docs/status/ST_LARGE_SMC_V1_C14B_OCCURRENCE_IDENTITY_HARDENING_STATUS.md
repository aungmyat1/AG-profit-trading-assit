# ST_LARGE_SMC_V1 — C14B Occurrence Identity Hardening (2026-09-01)

Status: **C14 identity layer hardened (`SHARED_CHANGE_REQUIRED` for the one remaining
piece)**. `strategies/ST_LARGE_SMC_V1.yaml` version `1.0.3 → 1.0.4`; `RESEARCH_DRAFT`
preserved; no engine, proposal, or execution authority added.

## Baseline gate

`git --no-pager log --oneline --decorate -10` confirmed `HEAD=5211edb` with the C14A
correction's changes present in the working tree, uncommitted, exactly as the prior
turn left them. `docs/VERSION_HISTORY.md`/`strategies/STRATEGY_LEDGER.md`'s `v1.0.3`
bullets still read as an unqualified "resolved by reuse" claim at the start of this
phase — confirmed stale (the C14A correction intentionally left them untouched, per
its own scoping) and corrected in this phase (see below). No `VERSION_STATE_CONFLICT`:
the discrepancy was fully traceable and resolvable from git history and the existing
status documents, not ambiguous.

## Version reconciliation

- `REPOSITORY_CURRENT_STRATEGY_VERSION` (before this phase) = `1.0.3`.
- `VERSION_1_0_3_ORIGIN` = commit `5211edb` ("Update ST_LARGE_SMC_V1 strategy to
  version 1.0.3 with C12 and C14 contract resolutions").
- `VERSION_1_0_3_MEANING` = C12 (expiry) correctly resolved by reuse; C14
  (duplicate/re-entry) claimed resolved by reuse, later shown (same day, C14A) to
  have overclaimed — `setup_id` is a setup-family identity only.
- `C14A_CORRECTION_EFFECT` = `candidate_identity.authority` downgraded to
  `PARTIALLY_RESOLVED` in the strategy YAML and spec; **no version bump** applied for
  that correction (per its own explicit scoping — correcting an overclaim is not new
  semantics).
- Treatment chosen: **preserve v1.0.3's historical meaning, annotate it with the
  correction, and bump forward to v1.0.4** for this phase's actual new content (real
  code implementing what C14A found missing) — not a silent rewrite of v1.0.3, not a
  new v1.0.3 variant, not skipping to an arbitrary number. `docs/VERSION_HISTORY.md`
  and `strategies/STRATEGY_LEDGER.md`'s `v1.0.3` bullets now carry an explicit
  "Correction, same day" annotation rather than standing as an uncorrected overclaim.
- `STRATEGY_VERSION_CHANGE_REQUIRED` = YES this phase (real `source_id` fields added
  to `M1Result`/`M2Result`/`M3Result`, new `proposals/occurrence_identity.py` —
  "setup qualification"/"intrinsic trade eligibility logic" per
  `docs/VERSION_HISTORY.md:56-58`). `STRATEGY_VERSION_AFTER` = `1.0.4`.
- `APPLICATION_VERSION_CHANGE_REQUIRED` = **NO**. `AG_TRADE_ASSISTANT_V1_0_2` covers
  "reporting, persistence, runtime operations, recovery, CLI, journaling, monitoring,
  execution plumbing" — none of which this phase touches. The changed files
  (`entry_confirmation/`, `supply_demand/`, `proposals/`) are shared with the live
  `SMC_CONDITIONAL_ENTRY_V2` watcher, but every change is additive (new optional
  fields defaulting to `None`, new functions) — verified by running the full
  pre-existing regression suite for those packages (172 tests) plus the golden
  vertical slice (7) and Stage1/Stage2 identity tests (21), all unchanged. No
  existing caller's behavior changed.

## What was implemented (Option B, owner-selected)

All additive; no existing field removed, renamed, or given new required-input
semantics; no detection logic invented — every new value is derived from evidence the
functions already computed internally.

- **`src/supply_demand/models.py`**: new `zone_id(zone: ZoneResult) -> str` function,
  mirroring `liquidity.hierarchy.level_id()`'s exact construction
  (`symbol:timeframe:family:role:source:origin_time:low:high`). Exported from
  `supply_demand/__init__.py`.
- **`src/entry_confirmation/m1_character_change_inducement.py`**: `M1Result` gains
  `source_id: Optional[str] = None`. Computed as
  `hash(inducement_candidate.candidate_id, choch_point.time_utc)` — reusing
  `InducementCandidate.candidate_id` (itself already `liquidity.hierarchy.level_id()`
  of the inducement level) plus the confirming CHoCH's timestamp, both already
  available inside `evaluate_m1_character_change_with_inducement()`. Set once
  `choch_confirmed=True`; `None` before (no concrete candidate exists yet).
- **`src/entry_confirmation/m2_supply_demand_shift.py`**: `M2Result` gains
  `source_id`. Computed as `hash(zone_id(opposing_zone), zone_failure_time)`. Set
  once `zone_failure=True`; `None` before.
- **`src/entry_confirmation/m3_sweep_drop_pump.py`**: `M3Result` gains `source_id`.
  Computed as `hash(level_id(liquidity_level), choch_point.time_utc)`. Set once the
  M5 structural failure (`choch_point`) is found; `None` before. The pre-existing,
  unrelated `inverted_gap_policy="PARTIAL"` caveat is unchanged — this addition does
  not resolve or paper over that separate gap.
- **`src/proposals/occurrence_identity.py`** (new file): `eligibility_interval_id(
  event_id, interval_start, interval_end)` and `candidate_occurrence_id(
  setup_family_id, eligibility_interval_id, m_candidate_identity)`, both pure
  `blake2b` functions using the exact same convention as
  `proposals/identity.py::setup_id` — no new hashing infrastructure. Exported from
  `proposals/__init__.py`. Not imported by `proposals/identity.py` or
  `proposals/lifecycle.py` — those two files are unmodified.

All three `_mN_source_id` helper functions and `zone_id`/`eligibility_interval_id`/
`candidate_occurrence_id` are pure, deterministic, restart/replay-stable, with zero
wall-clock or random input — matching the project's existing identity conventions
throughout (verified against `proposals/identity.py::setup_id`,
`historical_replay/stage1.py::_make_event_id`, and `liquidity/hierarchy.py::level_id`).

## What was deliberately NOT implemented

`proposals/lifecycle.py::update_proposal_lifecycle`'s `store` is still keyed only by
`setup_id`. Migrating it to key by `candidate_occurrence_id` was assessed and
consciously deferred: that module is shared with the live `SMC_CONDITIONAL_ENTRY_V2`
watcher (`daily_routine/m5_execution.py`), not just Large-SMC historical research
(`historical_replay/orchestrator.py`). Changing its store key is a live-behavior
change to a shared module and needs its own, separately-authorized regression scope —
this phase's "smallest safe model" is: prove the new identity layer is correct and
sufficient, without touching the shared function that would consume it.
`SHARED_CHANGE_REQUIRED` for that migration specifically, not for the identity layer
itself (which required no shared-code change at all).

## Tests

`tests/test_candidate_occurrence_identity.py` (new, 16 tests):

- `eligibility_interval_id`: deterministic (2 tests — stability, separation across
  disjoint intervals of the same event).
- M1/M2/M3 `source_id`: `None` before a concrete candidate exists (3 tests), stable
  for identical evidence, and separated for different structural evidence or
  confirming bar (5 tests) — 8 tests total across the three models.
- `candidate_occurrence_id`: composition determinism, same-family/different-interval
  separation, same-family-same-interval/different-M-candidate separation, and 3×3
  E×M coexistence preservation (4 tests).
- **`test_c14a_defect_reproduced_setup_id_only_store_overwrites_terminal_occurrence`**:
  builds a *real* `SMCConditionalEntryAnalysis` (real `EConditionResult`, real
  READY `M1Result`, real `composer.compose()` output) and runs the actual, unmodified
  `update_proposal_lifecycle()` against it. Confirms the exact C14A-documented defect
  in the live code: a manually-marked-terminal record is silently overwritten when
  new evidence arrives under the same `setup_id`.
- **`test_c14b_occurrence_id_would_distinguish_what_c14a_defect_conflates`**: proves
  `candidate_occurrence_id` produces different ids for the two occurrences the
  previous test showed colliding on `setup_id` alone — the identity layer is ready
  for the deferred store migration, without that migration having been performed.

Full regression: `pytest tests/test_m1_character_change_inducement.py
tests/test_m2_supply_demand_shift.py tests/test_m3_sweep_drop_pump.py
tests/test_entry_confirmation.py tests/test_entry_confirmation_v2.py
tests/test_entry_confirmation_v2_1.py tests/test_proposals.py
tests/test_proposal_lifecycle.py tests/test_setup_identity_collision.py
tests/test_stage2_identity_fidelity.py tests/test_candidate_occurrence_identity.py
tests/test_supply_demand.py` — 198 passed (172 pre-existing + 16 new identity tests +
10 `supply_demand` — all pre-existing tests pass unchanged).
`pytest tests/test_golden_vertical_slice.py` — 7 passed, unchanged.
`pytest tests/test_stage1_directional_liquidity.py
tests/test_stage1_canonical_contract.py tests/test_true_stage2_eligibility_gate.py`
— 21 passed, unchanged. `pytest tests/test_large_smc_registration.py
tests/test_dual_workflow_boundaries.py` — 6 passed (yaml changed).

## Non-regression / authority

`composer.py`, Stage1, Stage2, `proposals/identity.py`, `proposals/lifecycle.py`, and
every M-model's *decision logic* (qualification, direction, state transitions) are
byte-for-byte unchanged — only new, additive, optional fields and new, unimported-
elsewhere functions were added. `AG_TRADE_ASSISTANT_V1_0_2` and
`ST_ASIAN_SWEEP_5R_V1 v1.1.1` unaffected (verified: `proposals` package has exactly
two consumers outside itself, `historical_replay/orchestrator.py` and
`daily_routine/m5_execution.py` — neither is Session Trading). C11 and C12 unchanged.
`actionable_READY`, `portfolio_authority`, `risk_sizing_authority`,
`proposal_authority`, `execution_authority` remain `BLOCKED`; `order_check=0`,
`order_send=0`. No portfolio-selection policy, no execution change, no strategy
activation.

## Contract register (post C14B)

Unchanged top-level tally from C14A: `RESOLVED=11`, `PARTIALLY_RESOLVED=6` (C01, C06,
C10, C14, C16, C18), `UNRESOLVED_CONTRACT=1` (C15, non-blocking). C14's internal
composition changed substantially: `candidate_occurrence_identity` moved from
`OWNER_DECISION_REQUIRED` to `DETERMINISTIC_AND_TESTED`; the sole remaining open
piece is the live-storage migration (`SHARED_CHANGE_REQUIRED`), not a contract
question.

**First remaining blocker: UC-009 (C10 residual SL-distance formula)** — earlier in
the minimum-core ordering, deliberately left open since the C11 phase, not yet
revisited. C14's remaining item is an infrastructure-migration decision, not a
specification gap blocking further contract work.

## Files changed

`src/supply_demand/models.py`, `src/supply_demand/__init__.py`,
`src/entry_confirmation/m1_character_change_inducement.py`,
`src/entry_confirmation/m2_supply_demand_shift.py`,
`src/entry_confirmation/m3_sweep_drop_pump.py`,
`src/proposals/occurrence_identity.py` (new), `src/proposals/__init__.py`,
`tests/test_candidate_occurrence_identity.py` (new), `strategies/ST_LARGE_SMC_V1.yaml`,
`docs/specs/LARGE_SMC_V1_SPEC.md`, `docs/VERSION_HISTORY.md`,
`strategies/STRATEGY_LEDGER.md`, `PROJECT_STATUS.md`, `docs/README.md`, and this
document. `src/proposals/identity.py`, `src/proposals/lifecycle.py`, `composer.py`,
Stage1, Stage2, execution, portfolio, and risk code are untouched.
