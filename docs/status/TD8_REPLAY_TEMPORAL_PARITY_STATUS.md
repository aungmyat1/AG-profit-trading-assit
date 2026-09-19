# TD-8 — Replay Temporal Parity & Dataset Identity

**Status:** COMPLETE. Prerequisite verified: TD-7 (`4aefc73c7c56e304fdff3c3634d27646031d0c79`)
is a committed ancestor of HEAD.

## What this implements

`HISTORICAL_AS_OF` composition for `mtf_context.topdown_composer.build_topdown_context()`,
reusing the repository's existing, already-tested replay-substitution mechanism
(`historical_replay/data_source_patch.py::historical_data_context`) verbatim rather than
building a parallel one. No strategy logic touched; no TD-6 derived-cache wiring; no
strategy population generated; no holdout accessed.

## P1 audit summary (existing replay architecture)

`historical_replay/data_source_patch.py::historical_data_context(store, as_of, ...)`
already existed, fully independent of TD-7/TD-8, and already:
- monkeypatches `get_latest_candles`/`get_tick` at every consumer module's own bound
  name (`market_structure.tiers`/`.analyzer`, `supply_demand.analyzer`/`.native_zones`,
  `liquidity.analyzer`, `mt5.market_data` itself), covering the ENTIRE dependency chain
  TD-7's six tier builders use, with zero new patch targets needed;
- fails closed on the one uncovered path (`assistant.market_data.get_candles`, used
  only by `supply_demand.native_zones.session_zone()`) via
  `_PATCHED_RANGE_CANDLE_TARGETS`, raising `HISTORICAL_SESSION_DATA_UNAVAILABLE` rather
  than reaching live MT5;
- defends in depth by patching the raw `MetaTrader5.copy_rates_from_pos`/
  `copy_rates_range` SDK calls themselves to raise
  `HISTORICAL_REPLAY_MT5_ACCESS_FORBIDDEN` if any unpatched path is ever reached.

`historical_replay/candle_store.py::HistoricalCandleStore.closed_candles` already
implements the true no-lookahead boundary (`bar_open_time + timeframe_duration <=
as_of`), proven by the pre-existing `tests/test_historical_replay_no_lookahead.py`.

**Gaps found and closed this pass (additive only):**
1. `TIMEFRAME_MINUTES` had no `W1` entry (TopDownContext's weekly tier could not be
   served by the store at all) — added (`10080`, same value already used elsewhere).
2. No naive-datetime rejection on `as_of` — a naive value would previously fail with an
   unrelated `TypeError` deep inside `bisect_right`. Added `_require_aware_utc`
   (`NAIVE_DATETIME_REJECTED`, same idiom as `mt5/market_data.py::get_candles`).
3. No dataset/source identity concept existed for a loaded `(symbol, timeframe)` series
   specifically (the existing `HistoricalSymbolMetadataManifest.dataset_fingerprint` is
   a whole-FILE byte hash for tick_size authorization, a different concept). Added
   `historical_replay/dataset_identity.py` (content-derived SHA-256 fingerprint,
   `"sha256:<hex>"` framing reused verbatim from `symbol_metadata_manifest.py`) and
   wired it into `HistoricalCandleStore.load_series`/`dataset_identity()`.
4. `topdown_composer.py` and `strategy_contract/market_snapshot.py` are two
   disconnected subsystems — the six TD-7 builders never call `market_snapshot.py` at
   all, so TD-8 integrates directly at the `historical_data_context` layer the builders
   actually reach, not at `market_snapshot.py` (which remains orphaned, unrelated to
   this work).

## REPLAY_ARCHITECTURE
```
live_path       = build_<tier>_context() -> analyze_structure()/liquidity_result()/
                  supply_demand.* -> mt5.market_data.get_latest_candles() (TD-6 Layer A
                  raw-candle cache lives inside this function's own body)
replay_path     = SAME build_<tier>_context() calls, unmodified, running inside
                  historical_replay.historical_data_context(replay_store, as_of_time) --
                  every one of those bound names is monkeypatched to read from
                  replay_store instead; TD-6's raw cache is never reached at all (see
                  RAW_CACHE_ISOLATION)
provider_boundary = historical_data_context's own per-consumer-module monkeypatch
                  mechanism (pre-existing, reused verbatim) -- no new provider
                  abstraction/refactor introduced; the composer depends only on the
                  existing build_<tier>_context() interfaces, never on MT5 directly
```

## REPLAY_CLOCK
```
historical_evaluation_time = as_of_time, supplied by the caller, set onto
         TopDownContext.evaluation_time EXACTLY -- never datetime.now()
wall_clock_used_for_historical = false (verified by test:
         test_evaluation_time_equals_supplied_as_of_time_exactly_not_wall_clock)
timezone_policy = as_of_time must be timezone-aware UTC; a naive value raises
         NaiveAsOfTimeError immediately (same NAIVE_DATETIME_REJECTED idiom used
         throughout this repo for caller-supplied clock arguments)
```

## DATASET_IDENTITY
```
type    = historical_replay.dataset_identity.ReplayDatasetIdentity (frozen dataclass)
fields  = dataset_id, source, symbol, timeframe, fingerprint, coverage_start, coverage_end
fingerprint_source = content-derived SHA-256 over JSON-canonicalized (time, OHLC,
         volume) rows, sorted by time, symbol/timeframe included in the hash --
         computed automatically on every HistoricalCandleStore.load_series() call
         (dataset_id/source are optional, auto-derived from the fingerprint when
         omitted; collision-safety comes from the fingerprint, never from the label)
same_timestamp_collision_safe = true -- proven at the unit level
         (tests/test_historical_replay_dataset_identity.py::
         test_fingerprint_differs_for_different_content_same_timestamps) and end to
         end through the real composer
         (tests/test_topdown_composer_replay.py::
         test_dataset_collision_same_timestamps_different_content_different_composed_identity)
```
The six per-tier `ReplayDatasetIdentity`s are folded into one composed
`dataset_identity` token stored on `TopDownContext` (a new, additive field --
`InvalidCompositionModeError` enforces it is REQUIRED for `HISTORICAL_AS_OF` and
FORBIDDEN for `LIVE_CURRENT`) and into `compute_topdown_context_id`'s own hash payload.

## TEMPORAL_VISIBILITY (synthetic smoke test, T = 2026-09-19T10:37:00Z, deliberately mid-bar for every timeframe)
```
W1  = 2026-09-10T00:00:00Z
D1  = 2026-09-18T00:00:00Z
H4  = 2026-09-19T04:00:00Z
H1  = 2026-09-19T09:00:00Z   -- the forming 10:00-11:00 H1 bar is correctly excluded
M15 = 2026-09-19T10:15:00Z   -- the forming bar containing 10:37 is correctly excluded
M5  = 2026-09-19T10:30:00Z   -- the forming bar containing 10:37 is correctly excluded
max_information_time = every candle instrumented via a spy on
         HistoricalCandleStore.closed_candles satisfies open_time + duration <= T
         (tests/test_topdown_composer_replay.py::
         test_actual_candle_inputs_never_exceed_the_as_of_boundary) -- this is the
         PRIMARY no-lookahead proof, not merely the six reported bar_close_time values
all_lte_T = true (all six, both by reported bar_close_time AND by instrumented actual
         candle input, per the two tests above)
```

## BAR_CLOSE_SEMANTICS
`Candle.time` is documented and confirmed as bar OPEN time, UTC, throughout this
repository (`strategy_engine/session/candles.py`, `mt5/market_data.py`'s own
docstrings, `strategy_contract/market_snapshot.py::_bar_close_time`'s add-duration
convention). Every tier's `bar_close_time` field (topdown_contracts.py, frozen since
TD-1) is populated from `structure.data_end_utc`, which is itself the last candle's
OPEN time -- an inherited naming choice, not something TD-8 introduces or corrects
(out of scope; frozen contract). The TRUE no-lookahead authority for replay is
`HistoricalCandleStore.closed_candles`'s own `open_time + duration <= as_of` check,
never `_require_tier`'s `bar_close_time <= composition_as_of_time` comparison (which,
in this mode, is a secondary, always-trivially-satisfied safety net -- see
`topdown_composer.py`'s own "NO-LOOKAHEAD ENFORCEMENT" docstring section for the full
reasoning). `W1`/`D1`/`H4`/`H1`/`M15`/`M5` all use the identical rule via one shared
`TIMEFRAME_MINUTES` duration table (`10080`/`1440`/`240`/`60`/`15`/`5` minutes).

## LIVE_FALLBACK_GUARD
```
historical_live_mt5_calls = zero -- `as_of_time` without `replay_store` raises
         ReplayStoreRequiredError before any tier is built; once inside
         historical_data_context, every one of the six builders' actual data-access
         paths is monkeypatched, and the raw MetaTrader5 SDK calls themselves are
         guarded (HISTORICAL_REPLAY_MT5_ACCESS_FORBIDDEN) as a second independent layer
guard   = ReplayStoreRequiredError (composer-level, new) +
         historical_data_context's pre-existing SDK-level guard (reused, unmodified).
         Proven end to end: tests/test_topdown_composer_replay.py::
         test_replay_composition_never_touches_the_live_raw_cache (TD-6's raw cache
         counters, which live inside get_latest_candles's own body, never move during
         a real six-tier replay composition -- direct proof the real function body,
         and therefore any path to live MT5 through it, was never entered)
```

## RAW_CACHE_ISOLATION
```
LIVE_vs_REPLAY     = proven: a LIVE-mocked fetch is used to pre-populate TD-6's raw
         cache for an exact (symbol, timeframe, count) shape, then the SAME shape is
         requested inside historical_data_context for a different dataset -- the
         replay result is returned (not the stale live-cached entry) and the cache's
         own hit counter never increments (tests/test_topdown_composer_replay.py::
         test_pre_existing_live_cache_entry_cannot_answer_a_replay_request_of_the_same_shape)
REPLAY_A_vs_REPLAY_B = proven: two independent stores, entered as two independent
         historical_data_context scopes, each answer only from their own data despite
         identical (symbol, timeframe, as_of) shape; their dataset fingerprints differ
         (tests/test_topdown_composer_replay.py::test_replay_a_cannot_answer_replay_b_for_the_same_shape)
```
Resolution chosen: **bypass the live raw cache entirely for replay** (the simpler,
correctness-preserving option this mission explicitly preferred) -- achieved for free,
by construction, since `historical_data_context` replaces `get_latest_candles`'s own
bound name at every consumer, so the cache-bearing real function body is never called
during replay. No change to TD-6's live raw-cache identity/behavior was made or needed.

## DERIVED_CACHE
```
implemented = true (TD-6, unchanged)
wired = false
dataset_identity_ready_for_future_key = true -- ReplayDatasetIdentity.fingerprint is a
         ready-made, collision-safe discriminator a future Layer-B key could add:
         (dataset_identity.fingerprint, symbol, timeframe, closed_bar_identity,
         authority_definition_id, feature_version, parameters). Not wired this pass.
TD6_DERIVED_CACHE_INTEGRATION_DEFERRED = STILL_DEFERRED
```

## PARITY
```
structure   = equal (proven: test_parity_same_content_different_dataset_labels_semantic_payload_equal)
imbalance   = equal (same test, imbalance_facts compared)
zones       = equal (same test, zone_facts compared)
liquidity   = equal (same test, liquidity_facts compared)
references  = equal (same test, reference_level_facts compared) -- see
         SESSION-REFERENCE-LEVEL LIMITATION below for the one honest gap
context_semantics = composed identity (context_id/dataset_identity) legitimately
         DIFFERS between the two runs above (dataset_id/source labels differ, which is
         intentionally part of provenance identity) -- per this mission's own
         instruction, semantic payload was compared separately from identity, not
         instead of proving parity
```
**Known, reported (not hidden) limitation:** `supply_demand.native_zones.session_zone()`
(feeding H1's "asian" session and M15's three session ReferenceLevelFacts) internally
calls `assistant.market_data.session_snapshot()`, which is entirely wall-clock-driven
(`datetime.now()` for both its default session date and its own completeness check)
and has no as-of parameter. `historical_data_context` already fails this one path
closed (`HISTORICAL_SESSION_DATA_UNAVAILABLE`) rather than leaking live data, so
session-derived reference facts are simply ABSENT during `HISTORICAL_AS_OF` (H1Context/
M15Context still build successfully; only this one fact family is missing) -- reported
as an explicit, out-of-scope-for-TD-8 limitation (fixing it means changing
`assistant/market_data.py`, a strategy-adjacent module TD-8's mandate says not to
refactor).

## FUTURE_LEAK_SENTINEL
```
result = PASS -- an extreme-value candle strictly after T (open time > every tier's
         own "current" bucket boundary, hence never eligible per
         HistoricalCandleStore's closure rule regardless of content) produces a
         composition whose dataset_identity/context_id legitimately differ (the
         dataset really is different) but whose ENTIRE semantic payload -- every
         tier's structure_facts, zone_facts, imbalance_facts, liquidity_facts,
         reference_level_facts, bar_close_time, and data_quality_status -- is BYTE
         IDENTICAL to the unmutated run.
         (tests/test_topdown_composer_replay.py::
         test_future_leak_sentinel_does_not_alter_semantic_payload_at_t)
```

## DATASET_COLLISION_TEST
```
result = PASS -- two full six-timeframe datasets sharing symbol/timeframe/timestamps
         but different OHLC content (different base price) produce different composed
         identity AND different per-timeframe dataset fingerprints; proven both at the
         unit level (dataset_identity.py) and end to end through the real composer.
```

## LINEAGE
All five parent links (`daily.parent_weekly_context_id` through
`m5.parent_m15_context_id`) verified equal to the real, just-built parent's own
`context_id` in every HISTORICAL_AS_OF test, using the exact same
`TopDownContext.__post_init__` lineage check LIVE_CURRENT already relies on (TD-7,
unmodified) -- no lineage loosening for replay.

## LIVE_REGRESSION
Live smoke test re-run (read-only, Vantage Demo, EURUSD, market closed/weekend):
```
composition_boundary = 2026-09-19T12:47:55.640418+00:00
composition_mode = LIVE_CURRENT
dataset_identity = None
context_id = TDTOP-c72c3ad2b80c828ddb29b458
data_quality_status = VALID
W1  = 2026-09-05T21:00:00+00:00
D1  = 2026-09-16T21:00:00+00:00
H4  = 2026-09-18T13:00:00+00:00
H1  = 2026-09-18T19:00:00+00:00
M15 = 2026-09-18T20:30:00+00:00
M5  = 2026-09-18T20:50:00+00:00
```
Identical shape/values to the TD-7 smoke test (only the wall-clock boundary itself and
context_id differ, as expected for two different real calls) -- LIVE_CURRENT semantics
fully unaffected by TD-8. No order operation.

## REPLAY_SMOKE_TEST
Synthetic deterministic fixture used (per this mission's own stated preference over a
real dataset -- no governance lookup needed, no risk of touching holdout):
```
dataset_identity (W1 slice) = SYNTHETIC_TD8_SMOKE:W1|SYNTHETIC_DETERMINISTIC_TD8|
         EURUSD|W1|sha256:c8322a909200... (full token includes all six timeframes,
         pipe-joined)
symbol = EURUSD
T = 2026-09-19T10:37:00+00:00
W1  = 2026-09-10T00:00:00+00:00
D1  = 2026-09-18T00:00:00+00:00
H4  = 2026-09-19T04:00:00+00:00
H1  = 2026-09-19T09:00:00+00:00
M15 = 2026-09-19T10:15:00+00:00
M5  = 2026-09-19T10:30:00+00:00
lineage = all five links valid
context_id = TDTOP-8ffd4b5c411b3552b198e3f2
composition_mode = HISTORICAL_AS_OF
data_quality_status = VALID
maximum candle information time observed <= T = true (instrumented directly via the
         spy test above; also true by inspection of the six closes reported here)
```
No real/holdout data accessed for this smoke test.

## FILES_CHANGED

**New:**
- `src/historical_replay/dataset_identity.py`
- `src/mtf_context/topdown_composer.py` -- rewritten in place (TD-7's file), adding
  HISTORICAL_AS_OF support; LIVE_CURRENT code path unchanged
- `docs/status/TD8_REPLAY_TEMPORAL_PARITY_STATUS.md` (this file)
- `tests/test_topdown_composer_replay.py` (31 tests)
- `tests/test_historical_replay_dataset_identity.py` (17 tests)
- `tests/test_topdown_contracts_composition_mode.py` (6 tests)

**Modified (additive only, backward compatible):**
- `src/historical_replay/candle_store.py` -- W1 added to `TIMEFRAME_MINUTES`, naive-
  datetime rejection added, `dataset_identity()` accessor added, `load_series()` gained
  optional `dataset_id`/`source` kwargs (every existing call site keeps working
  unmodified -- 115 pre-existing replay tests re-run and pass unchanged)
- `src/historical_replay/__init__.py` -- exports the three new dataset-identity names
- `src/mtf_context/topdown_contracts.py` -- `TopDownContext` gained
  `composition_mode`/`dataset_identity` fields (both default to exactly what every
  pre-TD-8 construction already implied: LIVE_CURRENT, no dataset identity) plus
  `COMPOSITION_MODE_*` constants and `InvalidCompositionModeError`
- `src/mtf_context/__init__.py` -- exports the new names
- `tests/test_topdown_composer.py` -- 2 TD-7-era tests updated (not deleted) to assert
  the new, correct behavior (`ReplayStoreRequiredError` instead of the now-obsolete
  `HistoricalAsOfNotSupportedError` for an `as_of_time` given without a `replay_store`)
- `tests/test_topdown_composer_no_strategy_import_guard.py` -- allowlist extended for
  the one new, deliberate `historical_replay` dependency; one new test added

No strategy file, YAML, proposal, risk, execution, API, or frontend file touched.
`market_structure/`, `liquidity/`, `supply_demand/`, `daily_routine/`,
`assistant/market_data.py` are all **unmodified**.

## TEST_RESULTS

Independent freeze verification on 2026-09-19, Windows / Python 3.14, `main` at
`de467373027dbb5669b1946c50d550f8159c38fa` before the freeze commit:

- `python -m pytest -q tests/test_historical_replay_dataset_identity.py tests/test_topdown_contracts_composition_mode.py tests/test_topdown_composer_replay.py`:
  **54 passed**.
- `python -c "import glob,subprocess,sys; p=sum((glob.glob('tests/'+x) for x in ('test_mtf_context*.py','test_topdown*.py','test_historical_replay*.py','test_candle_store*.py')),[]); print('files',len(p),flush=True); sys.exit(subprocess.call([sys.executable,'-m','pytest','-q','--disable-warnings',*p]))"`:
  **249 passed, 1 skipped** across 18 files.
- `python -m pytest -q --disable-warnings tests/test_mt5_market_data_replay_patch_compatibility.py tests/test_replay_orchestrator.py tests/test_stage2_identity_fidelity.py tests/test_stage1_directional_liquidity.py tests/test_stage1_canonical_contract.py`:
  **34 passed**. Together, the nonoverlapping relevant slices are **283 passed,
  1 skipped**. The earlier 290-pass review used a different test selection; the
  changed count is a selection difference, not a failing test.

No live broker or holdout checks were run during freeze verification. The session
reference replay parity limitation remains `TD8_SESSION_REFERENCE_REPLAY_PARITY`.
- New TD-8 tests: **54 passed** (31 composer-replay + 17 dataset-identity unit +
  6 composition-mode contract).
- Full mtf_context/topdown/historical_replay/candle_store/dataset_identity suite:
  **all green** (227 passed, 1 skipped on the `mtf_context or topdown` slice alone;
  115 pre-existing historical_replay/stage1/stage2/orchestrator tests re-verified
  unaffected).
- 2 pre-existing TD-7 tests updated (not broken) to reflect that HISTORICAL_AS_OF is
  now implemented.

## PRE_EXISTING_ISSUES (not addressed, per instruction)
- `TD6_DERIVED_CACHE_INTEGRATION_DEFERRED` -- still deferred; TD-8 only prepared the
  dataset-identity discriminator a future key would need.
- `TD_TECH_DEBT_H1_RAW_CONTEXT_EXPOSURE` -- untouched; `build_h1_context` still builds
  its own internal `daily_routine.D1Context` rather than reusing the composed
  `DailyContext` (true for both LIVE_CURRENT and HISTORICAL_AS_OF).
- `TD4_CONTEXT_FEATURE_VERSION_REVIEW`, `FULL_SWING_HISTORY_LIMITATION`,
  `FX_FRIDAY_CLOSE_TEST_GUARD`, `ST_LARGE_SMC_BASELINE_MISMATCH` -- untouched.
- New, TD-8-specific limitation: session-based ReferenceLevelFacts are unavailable in
  HISTORICAL_AS_OF mode (see PARITY section above) -- not a blocker, not fixed, fully
  reported.

## OUT_OF_SCOPE_CONFIRMATION
```
strategy_logic_changed = false
proposal_logic_changed = false
risk_logic_changed = false
validation_evidence_changed = false
holdout_accessed = false
derived_cache_wired = false
strategy_population_generated = false
api_changed = false
frontend_changed = false
demo_authority_changed = false
live_authority_changed = false
execution_authority_changed = false
```

## FINAL_STATUS = COMPLETE

## NEXT
TD-8B_DERIVED_CACHE_REVIEW or TD-9_READ_ONLY_OBSERVABILITY only after owner review.
Not begun.
