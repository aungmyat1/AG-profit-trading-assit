# ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS

Date: 2026-09-02. Strategy version: **1.0.6** (unchanged -- this phase repairs replay
infrastructure, not strategy semantics). Environment: Python 3.14.0, pytest 8.3.5,
Windows, repo `D:\ddev\AG profit trading`.

## BASELINE

```
git_head=ee26776b263931e4b87de7151323f3cf767e6c00
origin_main=ee26776b263931e4b87de7151323f3cf767e6c00
synchronized=YES
working_tree_before=4 files: docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md
  (user-owned edit), plus PROJECT_STATUS.md / strategies/ST_LARGE_SMC_V1.yaml /
  strategies/registry.yaml (this session's own prior, uncommitted documentation
  corrections from the immediately preceding phase) -- not drift, unchanged since ee26776
user_owned_edit_preserved=YES (untouched throughout this phase)
strategy_version=1.0.6
```

## TEST_EVIDENCE_BEFORE

```
1249_claim_source=this session's own background pytest run (task b2hjjaz7l), full
  output inspected directly: "1249 passed, 10719 warnings in 44601.20s (12:23:21)"
1249_claim_verified=YES
previous_independently_verified_baseline=1237 passed / 0 failed (RESEARCH_FUNNEL_V1 phase)
```

## OWNER_METADATA_AUTHORITY

```
dataset_id=EURUSD_M5_202504211715_202607310000
symbol=EURUSD
tick_size=0.00001
metadata_scope=HISTORICAL_ANALYSIS_ONLY
authority=OWNER_APPROVED_DATASET_MANIFEST
approval_date=2026-09-02
dataset_fingerprint=sha256:0c269b9aae1a610cddc87b61f30c12bcd89bcd25c7276e5406a6e36c409957e8
source_file=D:\EURUSD_M5_202504211715_202607310000.csv
```
Manifest: `config/historical_datasets/EURUSD_M5_202504211715_202607310000.yaml`.

## METADATA_IMPLEMENTATION

```
required_fields=[tick_size]  -- confirmed by direct code read, market_structure/tiers.py:147:
  tolerance_price = equal_level_tolerance_points * get_symbol_meta(symbol).tick_size
representation=HistoricalSymbolMetadataManifest (new, minimal dataclass) ->
  .to_synthetic_symbol_meta() builds a real mt5.symbol_resolver.SymbolMeta with ONLY
  tick_size authorized; every other field (tick_value, contract_size, volume_min/max/
  step, digits, point) is an inert 0.0/0, never a fabricated plausible number; tagged
  metadata_source=SYNTHETIC_RESEARCH (mt5.symbol_resolver.METADATA_SOURCE_SYNTHETIC_
  RESEARCH -- the same tag strategy_engine/sweep_retest/crypto_symbols.py's existing
  synthetic-metadata precedent already uses, already refused by
  execution.adapter.require_exchange_verified_metadata() if it ever reached an
  execution path)
fake_broker_metadata_created=NO
shared_boundary=historical_replay/data_source_patch.py::historical_data_context --
  new opt-in `symbol_metadata_manifest` parameter (default None, fully backward
  compatible) patches market_structure.tiers.get_symbol_meta -- the SAME single call
  site both C11's target adapter (src/large_smc_research) and the pre-existing M1
  inducement-candidate detection (historical_replay/stage2.py, via
  analyze_structure_tiers) already go through, so one shared fix covers both --
  historical_replay/orchestrator.py::run_replay also threads the same optional
  parameter through, so the Large-SMC discovery funnel itself picks it up.
files_changed=
  config/historical_datasets/EURUSD_M5_202504211715_202607310000.yaml (new, manifest)
  src/historical_replay/symbol_metadata_manifest.py (new, loader/validator)
  src/historical_replay/data_source_patch.py (modified, additive opt-in parameter)
  src/historical_replay/orchestrator.py (modified, additive opt-in parameter)
  src/historical_replay/__init__.py (modified, new exports)
  src/large_smc_research/engine.py (docstring only -- no code change needed)
  scripts/run_large_smc_discovery.py (modified, loads+validates+passes manifest)
  scripts/run_large_smc_outcome_lifecycle_check.py (modified, same)
  tests/test_symbol_metadata_manifest.py (new, 23 tests)
  strategies/registry.yaml (stale "pending-entry expiry unsigned" wording corrected)
  strategies/ST_LARGE_SMC_V1.yaml (same stale wording corrected near decision_states)
  PROJECT_STATUS.md (snapshot date + full-regression line corrected)
```

## ANALYTICAL_SEMANTICS

```
structure_formula_changed=NO -- tolerance_price = equal_level_tolerance_points *
  tick_size is untouched; proven identical by test_equal_level_tolerance_formula_unchanged
C11_formula_changed=NO -- target_model.py untouched this phase
M1_formula_changed=NO -- m1_character_change_inducement.py untouched; only its
  UPSTREAM DATA AVAILABILITY (inducement-candidate detection in stage2.py's
  _m5_side_primitives) was restored, not its detection logic
live_behavior_changed=NO -- symbol_metadata_manifest defaults to None everywhere;
  the live watcher (daily_routine/m5_execution.py) never enters historical_data_context
  at all, so it is structurally unreachable by this change
```

## PARITY

```
analytical_parity=PASS -- test_equal_level_tolerance_formula_unchanged feeds the same
  tick_size through the manifest path and a live-shaped SymbolMeta patch, asserts
  identical latest_swing_high/latest_swing_low output
replay_live_MT5_required=NO -- test_manifest_supplied_replay_never_calls_live_get_symbol_meta
  patches the real mt5.symbol_resolver.get_symbol_meta to raise AssertionError if
  called at all; replay with a manifest never touches it
hidden_MT5_lookup=NO
```

## M1_REVALIDATION

```
old_zero_finding=SUPERSEDED_BY_CORRECTED_REPLAY
detector_executed=YES -- direct check at 2025-09-15T12:10 UTC:
  WITHOUT manifest: inducement_candidates = 0
  WITH manifest:    inducement_candidates = 1 (SELL_SIDE, candidate=1.17513, target=1.17156)
tick_size_available=YES (0.00001, from the manifest)
data_error=NO
entry_arrays=1 (September 2025 corrected funnel: PER_M.M1 = {M_STARTED:9, M_CONFIRMED:1,
  ENTRY_ARRAY_CREATED:1, READY:1}, all under combination E1M1)
```
Not described as a strategy improvement -- this is a measurement-infrastructure
correction. The single new occurrence (E1M1) is subject to exactly the same C10
blocker as the other three; it does not change C10's status or imply anything about
profitability.

## C11_REVALIDATION

```
metadata_available=YES
live_MT5_dependency=NO
data_error=NO
replayable=YES -- confirmed against real data: all three previously-known occurrences
  (E1M3, E3M3, E1M2) now resolve to BLOCKED with a real target_price (1.17156, 1.17156,
  1.18119) instead of the pre-fix DATA_ERROR; C10 remains the sole blocking reason_code
```

## LARGE_SMC_REPLAY

```
dataset=EURUSD_M5_202504211715_202607310000
period=2025-09-01T00:00:00 -> 2025-09-30T00:00:00
duration=12457.33s replay + 35.9s load (corrected run; prior uncorrected run: 5327.81s +
  47.96s -- slower this time because analyze_structure_tiers now runs to full
  completion on every step instead of failing fast on SYMBOL_METADATA_MISSING)
```

OLD (`docs/status/large_smc_discovery_2025-09.json`, pre-fix):
```
raw_valid=6047/6047
E_qualified=9
M_confirmed=5
candidates=27
entry_arrays=5
ready_equivalent=3
```

CORRECTED (`docs/status/large_smc_discovery_2025-09_corrected.json`):
```
raw_valid=6047/6047
E_qualified=9
M_confirmed=6
candidates=27
entry_arrays=6
ready_equivalent=4
```

```
differences_explained=YES
classification=REPLAY_METADATA_CORRECTION
unexpected_regression=NO
```

Per-combination diff (all 9 cells compared byte-for-byte): **only `E1M1` changed**
(`M_CONFIRMED` 0→1, `ENTRY_ARRAY_CREATED` 0→1, `READY` 0→1) -- exactly the cell whose
maneuver (M1) was the one proven starved by the missing tick_size. All eight other
cells (E1M2, E1M3, E2M1, E2M2, E2M3, E3M1, E3M2, E3M3) are identical between the old
and corrected runs, as are `PER_E`, raw/valid/warmup counts, and identity-collision
count. This is the strongest available evidence that the change is a scoped,
fully-explained metadata correction, not an unrelated regression.

## OCCURRENCE_IDENTITY

```
preserved=YES
collision_count=0 (both old and corrected runs)
record_all_independently=YES (C18, unchanged)
```

## CONTRACTS

```
C01=UNCHANGED
C11=UNCHANGED
C14B=UNCHANGED
C16=UNCHANGED
C18=UNCHANGED
pending_entry_expiry=RESOLVED
C10=BLOCKED
```

## FULL_REGRESSION

```
pre_phase_baseline=1249 passed / 0 failed
command=python -m pytest -q
```
Targeted/broad regression covering every file this phase touched (manifest module,
`historical_data_context`, `orchestrator.run_replay`, `large_smc_research`, market
structure, golden vertical slice): **132 passed, 0 failed** (23 new manifest tests +
109 adjacent tests; one test was found to depend on live-MT5-connectivity state rather
than the feature under test, fixed to be deterministic, and re-verified at 23/23).

A full-suite run was separately launched for the final record. **Note on repository
state at that time:** an unrelated, concurrent, uncommitted change set (BTC/crypto
sweep-research files -- `requirements.txt`, `src/execution/executor.py`,
`src/execution_runtime/binance_usdtm_feed.py`,
`src/strategy_engine/sweep_retest/{engine,models,occurrence_enumerator}.py`, and their
tests) was present in the working tree from a different, concurrent session -- entirely
unrelated to ST_LARGE_SMC_V1, left untouched per this task's own git-safety
instructions. Any full-suite pass/fail delta involving those specific files is not
attributable to this phase; every file this phase actually changed is covered by the
132/132 targeted result above, independent of that concurrent work.

## AUTHORITY

```
research_only=YES
proposal_enabled=NO
demo_execution_enabled=NO
live_execution_enabled=NO
risk_sizing_connected=NO
order_send_touched=NO
```

## RESERVED_TAIL

```
formally_pinned=NO
used=NO
```

## CLASSIFICATION

```
CODE_REGRESSION=NO
HISTORICAL_RESULT_COMPARABILITY=RESTORED
REPLAY_INFRASTRUCTURE_VALID=YES
```

## RECOMMENDATION

**GO_TO_C10_DECISION.**

1. Replay infrastructure is now trustworthy: the metadata gap is fixed, bound to an
   explicit fingerprinted authorization, proven not to touch live behavior, and its
   only observed effect (E1M1) is fully explained and isolated.
2. C11's target adapter and M1's inducement detection are both now genuinely
   replayable -- the prior `HOLD` reason no longer applies.
3. Pending-entry lifecycle is already resolved and now exercisable against real
   `BLOCKED` decisions (verified: E1M3/E3M3 → `INVALIDATED_BEFORE_FILL`, E1M2 →
   `FILLED`, all from real September 2025 data).
4. The only remaining blocker to outcome simulation is C10 -- exactly the owner
   decision flagged as the next step in the prior phase, now unblocked to actually
   proceed with once decided.
5. No profitability claim is made or implied; this phase validated measurement
   infrastructure only.
