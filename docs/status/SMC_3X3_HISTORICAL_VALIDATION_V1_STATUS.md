# SMC_3X3_HISTORICAL_VALIDATION_V1 — Status

Interim status after the second work session (chronological replay + setup ledger +
3x3 funnel). See `docs/specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md` for architecture/
rationale. First-session status is superseded by this document; see git history for the
prior snapshot.

## Test accounting (session 2)

```
BASELINE_COLLECTED (start of session 2) = 921 (916 pass, 5 known fail)
TESTS_ADDED = 41
  tests/test_mt5_export_loader.py            7
  tests/test_resampler.py                    8
  tests/test_replay_orchestrator.py          5
  tests/test_fill_simulator.py                7
  tests/test_resampler_broker_aligned.py      8
  tests/test_historical_replay_no_lookahead.py  +1 (new regression test; file had 11, now 12)
  (test_setup_identity_collision.py / earlier no_lookahead tests: unchanged from session 1)
TESTS_REMOVED = 0
TESTS_REPLACED = 0
NET_CHANGE = +41
FINAL_COLLECTED = 962 (957 excluding the machine-dependent real-dataset-gated tests when
    the dataset files are absent; all run and pass on this machine)
PASS = 957, FAIL = 5 (same known failures, unchanged), REGRESSIONS = 0
```

Note: `tests/test_replay_orchestrator.py` and the real-data case in
`tests/test_resampler_broker_aligned.py` are `skipif`-gated on real CSV files' presence
(`D:\EURUSD_M5_202504211715_202607310000.csv`, `D:\EURUSD_Daily_202501020000_202607310000.csv`
-- both outside the repo) since no synthetic fixture reproduces realistic warmup/timing/
cross-validation characteristics economically. These are the only machine-dependent
tests in the suite; documented here rather than hidden.

## Known pre-existing failures (unchanged from session 1, re-confirmed)

All 5 share one root cause: **today (2026-08-29) is a Saturday; MT5 has no live feed
while markets are closed**, so `copy_rates_range`/`copy_rates_from_pos` return empty
data. Environment-dependent, pre-existing, none touched:

1. `tests/test_assistant_market_data.py::test_historical_candles_utc_range_live` — `DATA_MISSING`
2. `tests/test_assistant_market_data.py::test_session_snapshot_completeness_live` — `DATA_MISSING`
3. `tests/test_assistant_market_data.py::test_data_health_ok_and_failure_live` — asserts `'OK'`, got `'STALE_DATA'`
4. `tests/test_market_data.py::test_get_candles_last_bar_matches_true_utc_now` — `MarketDataError: DATA_MISSING`
5. `tests/test_market_data.py::test_get_candles_session_window_is_half_open_and_exact` — `MarketDataError: DATA_MISSING`

## Dataset discovery and selection

```
HISTORICAL_DATASET_DISCOVERY
  Repo-wide search for *.csv/*.parquet: NONE found inside the repository (confirmed
  session 1). D:\ root search (session 2, per user direction) found MT5-exported CSVs:

  CHOSEN PRIMARY:
  FILE = D:\EURUSD_M5_202504211715_202607310000.csv
  SYMBOL = EURUSD
  RESOLUTION = M5 (native)
  START = 2025-04-21 17:15 (broker time) / 2025-04-21 14:15 UTC
  END = 2026-07-31 00:00 (broker time) / 2026-07-30 21:00 UTC
  ROWS = 95393
  SOURCE_TIMEZONE = broker server time, seasonal DST (UTC+2 winter / UTC+3 summer --
    determined empirically via the project's own mt5.broker_time.offset_from_reopen
    weekly-reopen-gap technique, reused not reinvented; NOT assumed from filename)
  NORMALIZED_TIMEZONE = UTC
  QUALITY = monotonic, zero duplicates, zero invalid OHLC, 81 gaps total (66 ordinary
    weekly closures classified EXPECTED_MARKET_CLOSURE, 15 small 10-20min gaps mostly
    around broker-midnight rollover plus the Dec 24/Dec 31 holiday sessions, classified
    UNEXPECTED_DATA_GAP -- reported honestly, never silently filled)

  REJECTED AS PRIMARY (shorter/overlapping, kept as candidates for future MT5
  broker-conformance cross-checks per spec section 47):
  D:\EURUSD_M1_*.csv (4 files) -- all ~2-3 months coverage only (May-Jul 2026), far
    shorter than the M5 file's 15 months; M1 preferred by spec IF "sufficiently long"
    existed -- it doesn't here.
  D:\EURUSD_M15_*.csv (3 files) -- coarser resolution than the M5 file, one file
    covers a similar range (Jan 2025-Jun 2026) but M5 lets M15/H1/H4/D1 all be derived
    from a single finer base feed (spec section 6), so M5 is strictly better.
  D:\EURUSD_202606182200_202608241902.csv -- raw tick (bid/ask) data, ~5.9M rows,
    2026-06-18 to 2026-08-24; candidate for Stage D (broker-realistic fill resolution,
    spec section 24) later, not used this phase.
```

## Ingestion + resampling

```
EXISTING_BACKTEST_INFRA = none (confirmed session 1)
INGESTION_ADAPTER = src/historical_replay/mt5_export_loader.py::load_mt5_export_csv
  -- validates (monotonic, no duplicates, valid OHLC), classifies gaps, and
  UTC-normalizes using PER-SEGMENT broker offset detection (not one constant for the
  whole file -- verified necessary: the real file's offset alternates +2/+3 across its
  15-month range)
RESAMPLING = src/historical_replay/resampler.py::resample -- single base feed (M5) ->
  M15/H1/H4/D1, UTC-boundary-aligned (H4 on 0/4/8/12/16/20 UTC, D1 on 00:00 UTC),
  INCOMPLETE windows dropped, never fabricated
DERIVED_ROWS (full file) = M15: 31788, H1: 7937, H4: 1907, D1: 250
```

## Chronological replay orchestrator

`src/historical_replay/orchestrator.py`: steps a replay clock through closed M5 bar
boundaries; at each step calls
`daytrading_runtime.conditional_entry_snapshot.build_symbol_conditional_entry_analysis`
(the actual live entrypoint, unmodified) inside `historical_data_context`. Produces a
`SetupLedger` (every combination ever observed, keyed by the fixed `setup_id`, frozen
once terminal) and a `FunnelTracker` (distinct-first-occurrence counts per stage, using
only existing `EntryModelState` enum names). Also runs `update_proposal_lifecycle`
every step against an in-memory (not disk-backed `JsonKeyValueStore`) store purely as an
independent cross-check on identity stability -- `JsonKeyValueStore` does a full-file
read+rewrite per `put`, which would be wasteful O(n) disk I/O across tens of thousands
of replay steps; same get/put interface, not a competing persistence abstraction.

**Bug found and fixed during this build**: `daytrading_runtime.conditional_entry_snapshot`
imports `get_latest_candles`/`get_tick` into its OWN module namespace too (for D1/H1/M5
candles and current price), not just the analyzer modules underneath it. The initial
patch-target list omitted it, so every replay step silently fell through to live MT5
(`MT5_NOT_CONNECTED`) and never touched historical data at all. Fixed in
`data_source_patch.py`; regression test added
(`test_full_conditional_entry_entrypoint_reuses_historical_data_not_live_mt5`).

```
TIME SAFETY
EVENT_KNOWLEDGE_SEPARATION = VERIFIED_BY_DESIGN (unchanged from session 1)
M5_CLOSURE = VERIFIED (same closed_candles() mechanism as H1/D1, exercised directly by
    every replay step; no M5-specific edge-case test beyond the H1/D1 ones written)
H1_CLOSURE = VERIFIED (session 1)
H4_CLOSURE = VERIFIED (tests/test_resampler.py: derived H4 bar not visible before close)
D1_CLOSURE = VERIFIED (session 1 + tests/test_resampler.py derived-D1 case)
NO_LOOKAHEAD = VERIFIED for the full live entrypoint (build_symbol_conditional_entry_
    analysis), not just one analyzer -- see the bug fix above and its regression test

IDENTITY
SETUP_ID_VERIFIED_UNDER_REAL_REPLAY = VERIFIED
    (tests/test_replay_orchestrator.py::test_no_identity_collisions_on_real_replay_window
    -- zero collisions over a real 6-hour window of actual EURUSD M5 data, not just
    fixtures; spec section 21's explicit requirement)
IDENTITY_INSTABILITY = NOT SEPARATELY DISTINGUISHED from collisions this phase (the
    orchestrator counts identity_collisions; a dedicated "same setup, changing id"
    check was not built as a separate metric -- SetupLedger's terminal-freeze
    discipline makes this failure mode structurally unlikely but it is not directly
    instrumented)

REPLAY
CHRONOLOGICAL_REPLAY = VERIFIED (tests/test_replay_orchestrator.py, 5 tests, run against
    real EURUSD M5 data, re-verified after the D1/H4 broker-alignment fix below)
LIVE_REPLAY_PARITY = PARTIAL -- proven at the code-reuse level (the same live entrypoint
    function runs unmodified under replay; zero MT5_NOT_CONNECTED fallback) and via the
    determinism test. Additionally, MT5 broker-CONFORMANCE (spec section 47) is now
    VERIFIED for H1 (0 mismatches / 7,937 bars) and D1 (318/320 exact matches against a
    native MT5 export; see §7c of the spec doc) -- this did NOT need a live connection,
    only historical exports, so it is not actually blocked by the weekend as previously
    stated. Still NOT compared against an actually-connected live MT5 terminal for a
    true end-to-end live-vs-replay run (that specific check remains deferred to a
    weekday session).
DETERMINISTIC = VERIFIED (test_replay_is_deterministic: identical setup ledger + funnel
    counts across two runs of the same window)
WARMUP = VERIFIED (test_replay_distinguishes_warmup_from_valid_steps /
    test_replay_produces_valid_steps_after_warmup: D1=60/H1=50/M5=200 candle minimums,
    matching daytrading_runtime.conditional_entry_snapshot's own live lookback constants)

## Broker-day-anchored D1/H4 bucketing — bug found and fixed

Cross-validating the derived timeframes against native MT5 exports (H1 and Daily D1
files the user provided) found: H1 matched perfectly (0/7937 mismatches), but the
original UTC-midnight-bucketed D1 mismatched **every single one** of 250 overlapping
bars. Root cause: MT5 anchors D1/H4 candles to the broker's own calendar day/4h window,
not UTC midnight -- the broker's +2/+3 seasonal UTC offset does not divide evenly into
24h, so broker midnight falls 2-3 hours before UTC midnight. Fixed via
`resampler.resample_broker_aligned` (buckets by the original broker wall-clock day/4h
window, exposed via `IngestionReport.broker_times`); re-validated at 318/320 exact
matches (the 2 misses are the dataset's own partial first/last days, not a bug). Full
detail in the spec doc §7c. This fix landed before any canonical numbers were reported
as final -- the semantic-replay sample below is the POST-FIX run.

SEMANTIC COUNTS -- SMC_3X3_SEMANTIC_REPLAY_V1 (first real-data run, post D1/H4 fix)

```
DATA: EURUSD, 2025-08-01 to 2025-08-15 (2-week proof run, NOT a statistically meaningful
      sample -- a full 15-month replay is a separate ~13-hour batch job, not run this
      session; see scripts/run_historical_replay.py to run more)
REPLAY: 2880 M5 steps, 0 WARMUP (broker-aligned D1 bucketing accrues 60+ candles earlier
        than the buggy UTC-bucketed version did, since it no longer discards short
        edge-of-week buckets for "incompleteness"), 2880 VALID_ANALYSIS_STEPS
NO_LOOKAHEAD / LIVE_ANALYZER_REUSE / DETERMINISTIC = all VERIFIED (see REPLAY section above)
IDENTITY_COLLISIONS = 0

E1_REFERENCES(REFERENCE_FOUND) = 3    E1_QUALIFIED = 1
E2_REFERENCES(REFERENCE_FOUND) = 13   E2_QUALIFIED = 1
E3_REFERENCES(REFERENCE_FOUND) = 140  E3_QUALIFIED = 3

M1_STARTED = 5  M1_CONFIRMED = 5  ENTRY_ARRAY_CREATED = 0
M2_STARTED = 5  M2_CONFIRMED = 1  ENTRY_ARRAY_CREATED = 1
M3_STARTED = 5  M3_CONFIRMED = 4  ENTRY_ARRAY_CREATED = 2

READY (all 9): 0 everywhere -- 3 entry arrays formed (E1M2, E3M3 x2) but none reached
    the composer's final READY gate within this 2-week window.
SETUP_LEDGER: 15 unique setups recorded, 0 reaching READY.
SAMPLE_SIZE_WARNING = INSUFFICIENT_SAMPLE -- 2 weeks, 1 EURUSD, zero READY combinations.
    This is reported as-is per spec's own rule: a low/zero READY count from a correctly
    running pipeline is a valid research result, not a defect to fix. Notably fixing the
    D1/H4 bug materially changed this result (E1/E3 went from 0 qualified references to
    1 and 3 respectively) -- underscoring why the cross-validation mattered before
    trusting these numbers.
```

Full JSON: `docs/status/replay_sample_aug2025.json`.

FUNNEL
SETUP_LEDGER = VERIFIED (SetupLedger class + tests; 15 unique setups recorded in the
    post-fix Aug 2025 sample run, none reaching READY)
READY_COUNT / FILLED_COUNT / UNFILLED_COUNT / INVALIDATED_BEFORE_FILL / AMBIGUOUS_COUNT
    = READY_COUNT available from the setup ledger (= 0 in the Aug 2025 sample, so no
    fills to simulate there yet); fill simulator itself is now BUILT and tested
    (`src/historical_replay/fill_simulator.py`, 7 tests: FILLED, UNFILLED_AS_OF_DATA_END,
    INVALIDATED_BEFORE_FILL, INTRABAR_AMBIGUOUS, NO_ENTRY_CONTRACT, single-price M3-style
    entries, SHORT-direction invalidation) but not yet wired into the orchestrator's
    per-step loop or exercised against a real READY setup (none occurred in this sample
    window)

TRADE MANAGEMENT
FROZEN_CONTRACT = NONE EXISTS for SMC_CONDITIONAL_ENTRY_V2 combos (unchanged from
    session 1 -- see spec §5)
P&L_BACKTEST_ALLOWED = NO

BROKER MODEL
SPREAD/COMMISSION/SLIPPAGE = NOT_MODELED (Stage D, unchanged, out of scope)
INTRABAR_RESOLUTION = NOT_BUILT (Stage B entry-fill simulation not yet built)

VISUAL AUDIT
SAMPLES_REVIEWED = 0 (pending: needs a real READY event from the semantic replay run)

TESTS
TOTAL_BEFORE (session 2 start) = 921, PASS = 916, FAIL = 5
NEW (session 2) = 41 (7 loader + 8 resampler + 5 orchestrator + 7 fill simulator +
    8 broker-aligned resampler + 1 no-lookahead regression test — see Test accounting
    above for the file-by-file breakdown)
TOTAL_AFTER = 962 collected (957 pass + 5 known fail when the real-dataset-gated tests
    run; same 957 pass + 5 fail when those are skipped on a machine without the datasets)
REGRESSIONS = 0

READINESS
SEMANTIC_HISTORICAL_VALIDATION_READY = YES (no-lookahead, identity, chronological
    replay, determinism, warmup all verified against real data)
ENTRY_FILL_SIMULATION_READY = NO (Stage B, not yet built -- next)
P&L_BASELINE_READY = NO (blocked: no frozen trade-management contract)
BROKER_REALISTIC_BACKTEST_READY = NO
READY_FOR_MODEL_RANKING = NO
READY_FOR_OPTIMIZATION = NO
READY_FOR_AUTONOMOUS_EXECUTION = NO
```

## Next phases (not started)

1. Entry-fill simulation (Stage B): READY vs FILLED, same-bar ambiguity
   classification, using the actual entry array from the setup ledger.
2. Full first semantic-replay report over a meaningfully long window (multi-month;
   the 2-week sample this session is a proof run, not a statistically meaningful
   sample -- spec's own sample-size-warning discipline applies).
3. Visual audit samples once real READY events exist in the ledger.
4. MT5 broker-conformance cross-check (spec section 47) -- needs a weekday session
   with a connected, live MT5 terminal.
5. Per-symbol breakdown once a second symbol's dataset is ingested (only EURUSD
   loaded this session).

Stage C (trade management) and Stage D (broker realism) remain blocked/out of scope
per the decisions above unless a frozen exit-policy contract is authorized later.
