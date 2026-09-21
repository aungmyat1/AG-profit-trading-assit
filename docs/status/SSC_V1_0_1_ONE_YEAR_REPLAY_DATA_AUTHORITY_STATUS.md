# SSC_V1_0_1_ONE_YEAR_REPLAY_DATA_AUTHORITY_STATUS

ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 — Mission 1 (SSC ONE-YEAR REPLAY DATA AUTHORITY +
WARMUP READINESS, P0–P8). Date: 2026-09-21. Environment: local Windows workstation,
`.venv`, repository `D:\ddev\AG profit trading`, branch `main`. Mode: DATA-AUTHORITY /
WARMUP-READINESS ONLY — no SSC replay, no economic evaluation, no strategy or parameter
change, no optimization.

**FINAL_STATUS = `ONE_YEAR_REPLAY_DATA_AUTHORITY_READY`.** `ONE_YEAR_REPLAY_STACK_V1` is
frozen (`manifest_sha256 = 59896fe6227a577ec588c701765c4a78277415ca70f7a6987f485ff1708de0c7`)
with `DATA_COVERAGE_COMPLETE`, `CROSS_LEG_TIMEBASE_CONSISTENT` (`UTC_SINGLE_TIMEBASE`),
`WARMUP_STABLE`, and `PROTECTED_DATA_ACCESS_COUNT = 0`. No replay was executed. This
mission stops before R5/R6 by design.

---

## P0 — Preflight

| Item | Value |
| --- | --- |
| Branch | `main` |
| HEAD_BEFORE | `923d59b0b9b6695d0a60c88485b12993665b6893` |
| Concurrent writer | **DETECTED** — a separate process/session committed unrelated documentation and FX-scheduler-ledger updates to `main` during this mission (commit `8c42cb6`, "chore: sync repo state - validation artifacts, docs, scripts, tests, and state updates (2026-09-21)"); it also picked up this mission's then-in-progress files. Nothing in that commit was authored or requested by this mission; its non-mission content (`README.md`, `docs/README.md`, `docs/PROJECT_ROADMAP.md`, `docs/VERSION_HISTORY.md`, `docs/PROJECT_CAPABILITY_COMPLETENESS.md`, `state/proposal_ledger/`, `state/fx_schedule/`) was reviewed and left untouched. |
| Environment note | Per the mission's [ADDED] instruction: the non-Windows portability patch (`fix: make test installation portable outside Windows`, commit `923d59b`) was already present on HEAD_BEFORE. This mission ran on the Windows dev box; `pip install -r requirements.txt` / MetaTrader5 installability was not re-verified (unchanged from baseline). |

---

## P1 — DEV_002 H1 manifest remediation: verified NOT required on this environment

The mission package (`docs/plans/AG_mission1_package.zip`) asserted the committed H1
bytes are `sha256:9cb7c2da...` while the manifest/tests declare the stale
`sha256:93d27d8c...`, and supplied `patches/P1_dev002_remediation.patch` to rebind the
manifest to `9cb7c2da...`.

**Re-verified from bytes on this Windows dev box and found inverted for this
environment:**

| Check | Result |
| --- | --- |
| Working-tree file sha256 (`data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/EURUSD_H1.csv`) | `93d27d8cbeb85c0b595ece7d18a43ac66219ae9fbb137e23a9826b84fc191c79` (matches the manifest/tests, NOT `9cb7c2da...`) |
| `git cat-file` blob content (LF, repo-stored) sha256 | `9cb7c2da900e958ec092327d08e4506007146bda611c4b056c396f0e121dfa6f` |
| `git show f66d555:<path>` | same blob (`23c6a2a...` object id) as current HEAD — **file bytes never changed in git history**, confirming the package's lineage claim |
| Root cause of the discrepancy | `core.autocrlf=true` on this Windows checkout converts the repo's LF blob to CRLF on checkout; the CRLF working-tree bytes hash to `93d27d8c...`, matching the manifest. The mission package's values were computed on a Linux sandbox (`README.md`: "Verified... (Linux, 2026-09-21)"), where checkout produces LF bytes (`9cb7c2da...`) — a mismatch **on Linux**, not here. |
| `tests/test_ssc_dev002_h1_metadata_manifest.py` (unpatched) | **7/7 PASS** on this box, before any change |

**Disposition:** the P1 patch was **not applied**. Applying it would have rebound the
manifest to `9cb7c2da...`, which would then fail `_sha256(DEV002_H1) ==
EXPECTED_DEV002_H1_SHA256` on this Windows checkout (still `93d27d8c...`), breaking
currently-passing tests. Per the mission's own instruction ("If this remediation has
already landed on current HEAD, verify it and do not duplicate it"), the remediation
state on this environment is already correct; no repo change was needed. This is an
environment-dependent (LF/CRLF) fragility in how the fingerprint is computed (against
checked-out bytes rather than the git blob) — recorded here as a finding for future
governance, not corrected in this mission (out of scope; would touch frozen manifest
semantics).

---

## P1.5 — Stale governance test reconciled

`tests/test_external_candidate_governance_invariance.py::test_synthetic_oos_evidence_cannot_bypass_unsigned_r6_contract`
asserted `NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS` against the live repo contract, which
is `SIGNED` since `c995f08` (2026-09-20) — the evaluator now correctly returns
`EDGE_REJECTED` for the synthetic sample, and the test's premise (an always-unsigned
contract) was stale.

Applied `patches/P1_5_governance_test_fix.patch` (verified sound: constructs an
explicit unsigned-contract scenario for the original invariant, and adds a new test
proving the synthetic sample is evaluable-and-rejected against the real signed
contract) with one fix — the patch omitted `VERDICT_EDGE_REJECTED` from its import,
causing a `NameError`; added it to the existing `from validation_framework.economic_gate
import (...)` block.

`stale governance test reconciled = YES`. Result: `tests/test_external_candidate_governance_invariance.py`
**3/3 PASS**.

---

## P2 — One-year replay stack built and frozen

**Foundational legs were already admitted** by the 2026-09-20 cross-leg remediation
mission (`docs/status/SSC_ONE_YEAR_CROSS_LEG_AUTHORITY_REMEDIATION_STATUS.md`,
`CROSS_LEG_TIMEZONE_BLOCKER_RESOLVED`) — this mission builds the formal
`ONE_YEAR_REPLAY_STACK_V1` freeze manifest on top of them via the new
`scripts/build_ssc_v1_0_1_one_year_replay_stack.py` (read-only, fail-closed; delegates
to the existing coverage and cross-leg gates rather than re-implementing them) and adds
the previously-missing WARMUP_CONTEXT_ONLY leg wiring (P4) and GEN_002 quarantine (P5).

Every input verified from bytes at build time:

| Leg | Dataset ID | Role | SHA-256 | Rows | UTC range |
| --- | --- | --- | --- | --- | --- |
| M1 | `SSC_V1_0_1_HIST_1Y_M1_001` | `FILL_RESOLUTION_INPUT` | `50beb42a...d12f8a` | 373 421 | 2025-09-14T21:02:00Z → 2026-09-15T21:00:00Z |
| M15 | `SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::M15` | `STRATEGY_DECISION_INPUT` | `c9833427...9b6956` | 24 961 | 2025-09-14T21:00:00Z → 2026-09-15T21:00:00Z |
| H1 | `SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::H1` | `MARKET_BIAS_INPUT` | `4eb52294...905e288` | 6 241 | 2025-09-14T21:00:00Z → 2026-09-15T21:00:00Z |
| WARMUP H1 | `EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv` | `WARMUP_CONTEXT_ONLY` | `f1b456e4...d480a060` | 9 817 | 2025-01-01T22:00:00Z → 2026-07-30T21:00:00Z |

M15/H1 are deterministic exact-UTC-bucket derivations from the M1 authority
(`historical_replay.m1_derivation`, `NATIVE_FAITHFUL_INCLUSIVE` policy, unchanged from
the 2026-09-20 remediation). The WARMUP H1 leg is declared `WARMUP_CONTEXT_ONLY` and
never substitutes for the decision-window H1 leg's `MARKET_BIAS_INPUT` role.

No bar was manufactured or interpolated. `scripts/build_ssc_v1_0_1_one_year_replay_stack.py --check`
gates: `M1_IDENTITY`, `H1_IDENTITY`, `M15_IDENTITY`, `WARMUP_SOURCE_PRESENT`,
`CROSS_LEG_TIMEBASE_CONSISTENT`, `DATA_COVERAGE_COMPLETE`,
`WARMUP_SUFFICIENT_AT_FIRST_DECISION`, `PROTECTED_DATA_FIREWALL`, `GEN_002_QUARANTINE_RECORD_PRESENT`,
`GEN_002_NOT_A_STACK_INPUT` — **all PASS**.

---

## P3 — Cross-leg timebase gate hardened to an executable, zero-shift, conflict-safe gate

`scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` already existed
(2026-09-19/20) and was extended in place (no second arbiter module) after review found
four real gaps against the mission's admission requirements:

1. **ALIGNED previously accepted any whole-hour shift** reaching the exact-rate
   threshold, not only `+0h`. Fixed: `_classify_alignment` requires
   `best_shift_hours == 0 and exact_rate == 1.0` for `ALIGNED`; a leg exactly matching
   at, say, `+3h` is now `MISALIGNED`, never admitted.
2. **The consistent-leg union merged overlapping contributors last-writer-wins**
   (`merged[c.time] = c`) — a disagreeing overlapping bar could silently overwrite an
   earlier one, order-dependent. Fixed: `_merge_with_conflict_detection` verifies OHLC
   agreement on every shared timestamp; a disagreement is recorded in
   `report["cross_leg_conflicts"]` and the timestamp is **dropped** from the merge
   (fail closed), never resolved by source-list order. `FINAL_STATUS` becomes
   `BLOCKED_CROSS_LEG_CONFLICTS_DETECTED` if any conflict is found.
3. **DST season windows (`Nov1–Mar1` / `May1–Sep1`) never straddled either real EU DST
   transition** inside the mission window and left roughly 4.5 months
   (2025-09-15..2025-11-01, 2026-03-01..2026-05-01) unclassified by the per-season
   check. Fixed: `SEASON_SEGMENTS` now splits the window into three segments at the two
   transition instants that actually fall inside it — `2025-10-26` (EU fall-back) and
   `2026-03-29` (EU spring-forward) — covering the full window with no gap.
4. **A source confined to one season segment could be marked `DST_CONSISTENT`/admitted**
   purely because it was never tested across a boundary. Fixed: `_segments_with_coverage`
   + `_classify_alignment` return `NOT_EVALUABLE_SINGLE_SEASON` (excluded from admission)
   for any source with material data in fewer than 2 segments, even if perfectly aligned
   within its one segment.

Also added: a calendar-independent per-bucket bimodal shift census
(`_bimodal_shift_census`, ported from the mission package's
`cross_leg_timebase_arbiter.py` draft) that detects internal DST fracture (the DEV_002
shape) directly from data rather than only at the two fixed segment boundaries, and an
explicit `decision_window_timebase = UTC_SINGLE_TIMEBASE` report field, emitted only
when the full window is covered with zero conflicts.

**Re-run against the real one-year dataset after hardening:** `FINAL_STATUS =
CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW`, `decision_window_timebase =
UTC_SINGLE_TIMEBASE`, zero conflicts, exit 0 — unchanged from before hardening for this
dataset (the two now-excluded single-season legs, `SSC_V1_0_1_G2_DEV_001::H1`/`::M15`
and `SSC_V1_0_1_G2_DEV_002::M15`, were never load-bearing: `EXTERNAL_D_ROOT` and the
`DERIVED` legs alone already span the full window).

`tests/test_ssc_v1_0_1_one_year_cross_leg_consistency_gate.py` (new, 10 tests,
retargeted at the script itself via `importlib`, not a synthetic side module): the 5
mission-required cases (correct alignment, fixed-hour misalignment, winter/summer mixed
offset, missing bucket, duplicate timestamp) plus the two hardening-specific cases
(single-season exclusion, conflict-on-merge) — **10/10 PASS**.

---

## P4 — Warmup convergence (VA2)

Implemented as `tests/test_ssc_one_year_warmup_convergence.py`, using
`historical_replay.warmup_readiness.closed_h1_bar_count` (the named authority) plus a
new `historical_replay.warmup_merge.merge_warmup_and_decision_window` helper that
prepends the WARMUP_CONTEXT_ONLY H1 leg (pre-window history back to 2025-01-02) in
front of the decision-window derived H1 leg.

Representative decision points: `FIRST` (window start, 2025-09-15T00:00:00Z), `MID`
(2026-03-14), `LAST` (window end, 2026-09-14T23:59:59Z).

| Check | Result |
| --- | --- |
| Closed H1 bars before FIRST decision | 4 371 (min required 1 000, per `market_structure.tiers.analyze_structure_tiers`'s own `EXTERNAL_SWING_LENGTH(50) * 20` warmup formula) |
| Sufficiency at MID / LAST | both comfortably above 1 000 |
| Convergence | proved as a direct consequence of `HistoricalCandleStore.closed_candles`'s own slicing contract (`start_index = max(0, end_index - count)`): once `count` bars are closed by `as_of`, the returned window is always exactly the most recent `count` bars, so additional preceding history cannot change it. Locked with a general synthetic test (5 000 extra prepended bars, identical slice) AND empirically verified on the real merged one-year H1 series at all 3 representative points (minimal-tail store vs full-history store produce byte-identical slices) |

`WARMUP_STATUS = WARMUP_STABLE`. `tests/test_ssc_one_year_warmup_convergence.py` — **4/4
PASS**.

---

## P5 — GEN_002 quarantine

`SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914` remains internally inconsistent (H1
best=+3h exact=0.783602, M15 best=+3h exact=0.778562 against the canonical M1 arbiter,
reconfirmed live 2026-09-21 by the hardened cross-leg gate — `MISALIGNED`, never
`ALIGNED`), contradicting its own manifest's `timezone_status: VERIFIED` claim, which
was itself only ever supported by a same-package (tautological) `parity_diagnostic`.

Added `data/research/ssc_fresh_dev/SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914/GEN_002_QUARANTINE_RECORD_V1.json`
(additive; the original `dataset_manifest.json` is **not** rewritten). The stack builder
(`scripts/build_ssc_v1_0_1_one_year_replay_stack.py`) asserts the quarantine record is
present and that no leg it consumes resolves inside the GEN_002 package directory
(`GEN_002_QUARANTINE_RECORD_PRESENT`, `GEN_002_NOT_A_STACK_INPUT` — both PASS). No
evidence previously generated from GEN_002 is re-attributed or invalidated.

---

## P6 — Protected-data firewall

Reused the frozen `LINEAGE_CONTAMINATION_MAP_V1.json` `safety` block (regenerated
2026-09-21 by the coverage audit re-run, `safety` values unchanged) rather than
re-deriving:

```
CONFIRMATION_ROLE_CHANGED = false   CONFIRM_001_ACCESSED = false
H2_CONSUMED = false                 HOLDOUT_ACCESSED = false
OOS_ACCESSED = false                PROTECTED_DATA_ACCESSED = false
```

`PROTECTED_DATA_ACCESS_COUNT = 0`. CONFIRM_001 / HOLDOUT / OOS content was never opened
by this mission.

---

## P7 — Verification

Focused set (exactly per the mission's expected post-P1 green set, plus P1.5/P4/P3):

```
python -m pytest -q \
  tests/test_ssc_dev002_h1_metadata_manifest.py \
  tests/test_external_candidate_governance_invariance.py \
  tests/test_ssc_one_year_warmup_convergence.py \
  tests/test_ssc_v1_0_1_one_year_cross_leg_consistency_gate.py \
  tests/test_ssc_m1_derivation.py \
  tests/test_topdown_composer_replay.py \
  tests/test_td8e_shared_consumer_integration.py
-> 83 passed in 162.81s
```

Broad SSC regression suite:

```
python -m pytest -q \
  tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py \
  tests/test_session_sweep_continuation_replay_determinism.py tests/test_svos_ssc_adapter.py \
  tests/test_symbol_metadata_manifest.py tests/test_svos_mt5_isolation.py \
  tests/test_session_sweep_continuation_ema_invariant.py tests/test_session_sweep_continuation_h1_bias.py \
  tests/test_session_sweep_continuation_sessions.py tests/test_session_sweep_continuation_gap_remediation.py \
  tests/test_session_sweep_continuation_swing_structure.py tests/test_session_sweep_continuation_regime.py \
  tests/test_session_sweep_continuation_setups.py tests/test_session_sweep_continuation_stop_engine.py \
  tests/test_session_sweep_continuation_bias_gate.py tests/test_historical_replay_dataset_identity.py \
  tests/test_resampler.py tests/test_resampler_broker_aligned.py
-> 133 passed in 350.06s
```

Environment: Windows dev box, `.venv`, live MT5-adjacent fixtures ran normally (no
`live_mt5` skip markers triggered in this run). Known out-of-scope categories recorded,
not fixed (per mission instruction): hardcoded `D:\ddev` paths in
`test_market_data_readiness_scanner` / `test_m15_session_sweep_research_v1_parity`;
stale frozen-scope git-diff baselines in the Large-SMC mission guards; unmarked
runtime-MT5 tests.

---

## P8 — Freeze

```
FROZE artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/ONE_YEAR_REPLAY_STACK_V1.json
manifest_sha256 = 59896fe6227a577ec588c701765c4a78277415ca70f7a6987f485ff1708de0c7
```

No R5 contract and no R6 replay were created or executed in this mission.

---

## Required final classification

```
ONE_YEAR_REPLAY_DATA_AUTHORITY_READY

HEAD_BEFORE = 923d59b0b9b6695d0a60c88485b12993665b6893
HEAD_AFTER  = uncommitted at mission completion (see P0 concurrent-writer note; this
              mission did not commit anything itself -- see "Commit note" below)
COMMIT      = N/A (not committed by this mission)

M1  dataset  = SSC_V1_0_1_HIST_1Y_M1_001
    hash     = 50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a
    rows     = 373421
    range    = 2025-09-14T21:02:00Z -> 2026-09-15T21:00:00Z

M15 dataset  = SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::M15
    hash     = c9833427404d8634d8cf57b000017ecea7ad865ab22db4eadedacb80de9b6956
    rows     = 24961
    range    = 2025-09-14T21:00:00Z -> 2026-09-15T21:00:00Z

H1  dataset  = SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::H1
    hash     = 4eb522945697773ed34d1b8d47ab928b9e94e99828dade88db18fe186905e288
    rows     = 6241
    range    = 2025-09-14T21:00:00Z -> 2026-09-15T21:00:00Z

WARMUP source = EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv
    hash      = f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060
    bar_count = 4371 closed H1 bars before the first decision (>= 1000 required)

DATA_COVERAGE_STATUS      = DATA_COVERAGE_COMPLETE
CROSS_LEG_TIMEBASE_STATUS = CROSS_LEG_TIMEBASE_CONSISTENT (UTC_SINGLE_TIMEBASE)
WARMUP_STATUS             = WARMUP_STABLE
PROTECTED_DATA_ACCESS_COUNT = 0

FOCUSED_TEST_RESULT = 83 passed, 0 failed (162.81s)
BROAD_TEST_RESULT   = 133 passed, 0 failed (350.06s)

STALE_GOVERNANCE_TEST_RECONCILED = YES
STRATEGY_FILES_CHANGED = NONE
ECONOMIC_REPLAY_EXECUTED = NO
DEMO_AUTHORITY_CHANGED = NO
LIVE_AUTHORITY_CHANGED = NO
```

### Commit note

This mission did not run `git commit` or `git push` at any point (commits are made only
when the user explicitly asks). Partway through this mission a separate, non-mission
process committed the repository's then-current working tree to `main`
(commit `8c42cb6`, `chore: sync repo state - validation artifacts, docs, scripts, tests,
and state updates (2026-09-21)`), which incidentally included this mission's files as
they stood at that moment (before the P3 hardening pass and before the final freeze).
The genuinely final state — the P3-hardened gate, the P2/P4/P5 deliverables, and the
frozen `ONE_YEAR_REPLAY_STACK_V1.json` — was produced and verified (P7) after that
commit and remains uncommitted at the time this document was written; `git status`
should be checked before assuming `HEAD` reflects this mission's final output.

---

## Deliverables

| Path | Role |
| --- | --- |
| `scripts/build_ssc_v1_0_1_one_year_replay_stack.py` | P2/P8 — read-only stack builder/freeze emitter; delegates to the existing coverage and cross-leg gates |
| `scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` | P3 — hardened in place (zero-shift admission, bimodal DST census, real-transition season segments, single-season exclusion, conflict-safe merge, `UTC_SINGLE_TIMEBASE` emission) |
| `src/historical_replay/warmup_merge.py` | P2/P4 — merges the WARMUP_CONTEXT_ONLY leg in front of the decision-window leg |
| `data/research/ssc_fresh_dev/SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914/GEN_002_QUARANTINE_RECORD_V1.json` | P5 — additive quarantine record |
| `tests/test_ssc_one_year_warmup_convergence.py` | P4 — 4 tests |
| `tests/test_ssc_v1_0_1_one_year_cross_leg_consistency_gate.py` | P3 — 10 tests |
| `tests/test_external_candidate_governance_invariance.py` | P1.5 — patched, 3 tests |
| `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/ONE_YEAR_REPLAY_STACK_V1.json` | P8 — frozen stack manifest |

## FINAL_STATUS

`ONE_YEAR_REPLAY_DATA_AUTHORITY_READY` — the one-year SSC v1.0.1 replay data authority
is frozen, cross-leg-timebase-consistent at zero shift across the full window, warmup-
stable, and protected-data-clear. No replay, no economic evaluation, no strategy or
parameter change occurred. The next mission (deliberately small) may freeze R5 binding
to the already-signed `AG_R6_ECONOMIC_GATE_CONTRACT_V1` and execute R6 once.
