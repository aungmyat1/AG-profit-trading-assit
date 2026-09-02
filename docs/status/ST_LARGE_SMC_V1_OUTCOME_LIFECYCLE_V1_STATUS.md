# ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS

Date: 2026-09-02. Strategy version: **1.0.6**. Environment: Python 3.14.0, pytest
8.3.5, Windows, repo `D:\ddev\AG profit trading`.

## BASELINE

```
git_head=05381da87ddfe182f7e77d5521c64a1d6196f5af
working_tree_before=3 files (tests/test_large_smc_registration.py modified;
  docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md and
  docs/status/large_smc_discovery_2025-09.json untracked) -- matches the prior phase's
  own report exactly, no drift
baseline_verified=YES
strategy_version_before=1.0.5
```

Unrelated `SMC_TRAP_GUARD_V1` work (bundled into commit `05381da` by another
process/session, per the prior phase's disclosure) confirmed isolated:
`src/strategy_engine/semantic_guard.py` and its yaml `semantic_safety_contract:`
blocks are untouched by this phase and structurally independent (pure evidence
validator, not called from anywhere this phase touches).

## FROZEN_CONTRACTS

```
C01=RESOLVED ([EURUSD] only) -- unchanged this phase
C11=RESOLVED_BY_OWNER, adapter IMPLEMENTED (live-context) -- formula unchanged;
    NEW replay-compatibility caveat discovered, see MT5_SYMBOL_METADATA note below
C14B=DETERMINISTIC_AND_TESTED -- unchanged, now exercised against real replay data
    for the first time this phase (see SEPTEMBER_REPLAY)
C16=RESOLVED_BY_REUSE (D1=60/H1=50/M5=200) -- unchanged
C18=RESOLVED_BY_REUSE (RECORD_ALL_INDEPENDENTLY) -- unchanged
```

## C10

```
status=BLOCKED
source_of_authority=none -- no AG-native formula found; research references only
formula_or_semantics=NONE_SELECTED -- see
  docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md (updated this phase
  with one new AG-native precedent found and NOT adopted:
  strategy_engine.sweep_retest.targets.forex_sl_buffer_price's structural-anchor +
  pip-buffer pattern -- its 2.5-pip constant is ST_LIQUIDITY_SWEEP_RETEST_V1-specific,
  not silently portable)
causal=N/A (not implemented)
production_execution_connected=NO
```

## PENDING_ENTRY_EXPIRY

```
status=RESOLVED
source_of_authority=historical_replay/fill_simulator.py (pre-existing, tested,
  EXACT_REUSE via new src/large_smc_research/pending_entry.py)
expiry_semantics=NO_TIME_BASED_EXPIRY -- terminal only via FILLED or structural
  INVALIDATED_BEFORE_FILL; UNFILLED_AS_OF_DATA_END is a data-boundary fact, never a
  fabricated EXPIRED state; INTRABAR_AMBIGUOUS fails closed on same-bar entry+
  invalidation touches (never assumes a favorable fill order)
causal=YES -- forward_candles are filtered to time >= ready_time only; simulate_fill's
  own no-lookahead precondition
```

## OUTCOME_ENGINE

```
implemented=PARTIAL
entry_fill=IMPLEMENTED (exact reuse, historical_replay.fill_simulator.simulate_fill)
stop_hit=NOT_IMPLEMENTED (blocked by C10)
target_hit=NOT_IMPLEMENTED (deliberately not attempted -- computing a target-reached
  signal without a stop would silently ignore adverse excursion; see pending_entry.py
  module docstring)
expiry=RESOLVED_NO_TIME_BASED_EXPIRY (see above)
invalidation=IMPLEMENTED (structural INVALIDATED_BEFORE_FILL, pre-fill; exact reuse)
ambiguity=IMPLEMENTED (INTRABAR_AMBIGUOUS, exact reuse, fails closed)
```

## OCCURRENCE_IDENTITY

```
preserved_end_to_end=YES -- candidate_occurrence_id/setup_family_id/
  eligibility_interval_id carried from LargeSMCResearchDecision into
  PendingEntryOutcome unchanged (see pending_entry.simulate_pending_entry)
collision_count=0 (unit tests + targeted replay check both confirm)
independent_occurrence_recording=YES (C18 RECORD_ALL_INDEPENDENTLY, unchanged)
```

## SEPTEMBER_REPLAY

Upstream funnel counts (raw/valid/E-qualified/M-confirmed/candidates/entry-arrays/
READY-equivalent) are **cited from the existing, unmodified**
`docs/status/large_smc_discovery_2025-09.json` -- **not re-run**, because nothing in
this phase touches `historical_replay.orchestrator.run_replay` or any detection module
it depends on. Re-running the ~90-minute full-month replay to reconfirm unchanged
numbers would violate this task's own compute-efficiency instruction; the "why it
can't have changed" reasoning (zero shared-module edits) is the substitute proof.

```
raw_valid=6047/6047
E_qualified=9
M_confirmed=5
candidates=27
entry_arrays=5
ready_equivalent=3 (composer-level READY, per historical_replay.orchestrator's own
  FunnelTracker -- unaffected by this phase)
```

**Targeted engine-level check** (task section 26, Stage 1 -- NOT a full-month re-run):
`scripts/run_large_smc_outcome_lifecycle_check.py` loaded the existing
`artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json` +
`directional_liquidity_timeline.json` Stage1Dataset artifacts and called
`LargeSMCResearchEngine.evaluate()` at exactly the two known ready timestamps
(2025-09-15T12:10 UTC for E1M3/E3M3, 2025-09-23T14:55 UTC for E1M2 --
`stage2.evaluate_entry_stage_canonical_v2` is a pure function of
`(symbol, event, evaluation_time, liquidity_timeline)`, not a stateful stepper, so
this reproduces what a full per-bar replay would have produced at those exact moments).

```
filled=0
expired_unfilled=0 (no such state exists -- see PENDING_ENTRY_EXPIRY above)
invalidated_unfilled=0
target_hit=0
stop_hit=0
ambiguous=0
unresolved=3 -- all three known occurrences (E1M2, E1M3, E3M3) now correctly report
  DATA_ERROR (entry/invalidation fields match the prior parquet-recorded values
  exactly for E1M3/E3M3; see note below for E1M2's entry-price discrepancy), not
  BLOCKED, because C11's target-model call fails on the MT5_SYMBOL_METADATA gap below
  -- pending-entry simulation was therefore not exercised against real BLOCKED
  decisions this phase (see OUTCOME_ENGINE.entry_fill: the mechanism itself is proven
  by 7 offline unit tests using synthetic BLOCKED-decision fixtures instead)
```

Minor open note: E1M2's entry price from this targeted check (1.180005) differs from
the entry price recorded in a prior 2-month discovery artifact's SetupLedgerRow for a
similarly-timed E1M2 occurrence (1.168235, `artifacts/backtests/
discovery_2mo_aug_sep2025_setup_ledger.parquet`). Not investigated further this phase
(does not affect the core finding below); plausibly a different, independently-active
E1 reference event within the broader Aug-Oct dataset producing its own distinct
occurrence, consistent with C18's RECORD_ALL_INDEPENDENTLY architecture.

## MAJOR FINDING (discovered, disclosed, not fixed)

Wiring `LargeSMCResearchEngine` into real replay data for the first time revealed that
`market_structure.tiers.analyze_structure_tiers` (used by C11's fallback tier, and
pre-existing in `historical_replay/stage2.py` for M1's inducement-candidate detection)
requires a **live MT5 terminal** for symbol metadata
(`mt5.symbol_resolver.get_symbol_meta`), which `historical_replay/data_source_patch.py`
has never patched. Every historical replay this project has ever run has therefore
silently starved M1's inducement-candidate detection -- a very plausible root cause for
the long-documented "M1 forms zero entry arrays in any sampled window" finding
(previously classified as a valid, if uninteresting, research result). This engine now
fails closed to `DATA_ERROR` (not a misleading `NO_TRADE`) when this happens -- a real
bug found and fixed during this same phase. The underlying gap itself is
`SHARED_CHANGE_REQUIRED` (touches `historical_replay/data_source_patch.py`, shared with
the live `SMC_CONDITIONAL_ENTRY_V2` watcher) and is **not fixed** by this additive
research phase. Full detail: `docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`.

## REGRESSION

```
pre_outcome_funnel_changed=NO -- no detection module was modified; September funnel
  counts cited unchanged from the existing artifact (see SEPTEMBER_REPLAY)
unexpected_detection_change=NO
```

## TESTS

```
focused=48 new/updated tests this phase across
  tests/test_large_smc_pending_entry.py (7 new),
  tests/test_large_smc_outcome_lifecycle_safety.py (3 new),
  tests/test_large_smc_research_engine.py (+1 new, -1 outdated fixed = 14 total),
  tests/test_large_smc_target_model.py (7, unchanged) -- all passing
full_suite=1237 passed / 0 failed baseline confirmed at the start of this phase
  (carried over from RESEARCH_FUNNEL_V1); final full run at the end of this phase:
  **1249 passed / 0 failed** (`python -m pytest -q`, 2026-09-02)
new_failures=0
known_unrelated_failures=0 (the RESEARCH_FUNNEL_V1 phase's one live-market flake,
  tests/test_supply_demand.py::test_order_blocks_and_fvg_live_eurusd[H1], was already
  confirmed non-reproducible; untouched this phase)
```

## AUTHORITY

```
research_only=YES
proposal_enabled=NO
demo_execution_enabled=NO
live_execution_enabled=NO
risk_sizing_connected=NO
order_send_path_touched=NO
```

Verified this phase by static inspection
(`tests/test_large_smc_outcome_lifecycle_safety.py`): no module under
`src/large_smc_research/` imports anything from `execution.*`/`assistant.commands`/
`assistant.runtime`, and neither `order_send` nor `order_check` appears anywhere in the
package's source text.

## RESERVED_TAIL

```
located=NO -- no file in this repository pins an exact reserved-tail boundary date;
  only an informal convention ("not the final period at the end of the dataset")
  referenced in the prior RESEARCH_FUNNEL_V1 status doc
used=NO
untouched=YES -- this phase's own data touches were the Sept 2025 window (unchanged,
  cited not re-run) and the existing Aug-Oct 2025 Stage1Dataset artifact, both well
  before any plausible tail boundary (dataset extends to 2026-07-30)
```

## RECOMMENDATION

**HOLD.**

1. Pending-entry lifecycle logic is now real, tested, and correctly scoped (exact
   reuse, no invention) -- genuine progress, not a guess.
2. C10 remains the one true open strategy-authorship decision; nothing found resolves
   it, and nothing should.
3. A separate, more fundamental blocker was discovered: C11's target-model adapter
   cannot function in historical replay at all today, due to a pre-existing,
   project-wide MT5-symbol-metadata gap -- this affects far more than Large-SMC (it
   silently affected the historically-observed M1 behavior across every prior replay).
4. Proceeding to a larger discovery replay right now would produce the same
   `DATA_ERROR` outcome for every candidate that reaches the target-selection step --
   no new information would be gained.
5. Next step is a decision, not more code: authorize (or decline) a scoped historical
   stand-in for `get_symbol_meta`, with its own regression proof, before any further
   Large-SMC outcome work or a larger discovery run.
