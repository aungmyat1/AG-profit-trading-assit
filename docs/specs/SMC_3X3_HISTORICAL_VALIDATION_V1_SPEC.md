# SMC_3X3_HISTORICAL_VALIDATION_V1 — Spec

Research/backtesting layer built **around** the frozen `SMC_CONDITIONAL_ENTRY_V2`
(E1/E2/E3 × M1/M2/M3, composer, `SMC_TRADE_PROPOSAL_V1`) and `SMC_ASSISTANT_RUNTIME_V1`
engines. Does not redesign SMC semantics, does not rank models, does not optimize.

## 1. Scope boundary

Preserved untouched: `entry_confirmation/` (E1–E3, M1–M3, composer), `smc_map/` builder
semantics, `surveillance/`, `proposals/gate.py` READY-gating logic, all live execution
paths. The only change made to a "frozen" module is a **bug fix** (setup identity — see
§3) required before historical lifecycle statistics can be trusted at all; the fix is
additive (new optional parameter, defaults preserve prior behavior).

## 2. Architecture: reuse the live engine (spec source §9–11)

The live pipeline is entirely: `mt5.market_data.get_latest_candles/get_tick` (live MT5)
→ `market_structure` / `supply_demand` / `liquidity` analyzers → `smc_map.build_smc_market_map`
→ `entry_confirmation` E/M/composer → `proposals.gate/lifecycle`.

Every analyzer module imports `get_latest_candles`/`get_tick` as a **top-level bound
name** (`from mt5.market_data import get_latest_candles`), so replay cannot reach them
by monkeypatching `mt5.market_data` alone — each importing module's own namespace
must be patched. `src/historical_replay/data_source_patch.py`'s
`historical_data_context(store, as_of)` does exactly this (patch target list documented
in that module), for the same clock instant across all consumers, then yields control
so any frozen analyzer call inside the `with` block transparently reads historical data
instead of live MT5. `liquidity.affinity` does its import locally inside the function
body every call, so patching the source (`mt5.market_data.get_latest_candles/get_tick`)
covers it without a separate module-level patch.

**Differences from live are limited to**: data source (historical store vs. live MT5),
clock (replay `as_of` vs. wall clock / live tick), and (later, Stage D) execution
simulator. SMC semantics are byte-for-byte the same code path — proven by
`tests/test_historical_replay_no_lookahead.py::test_historical_context_reuses_real_analyzer_previous_day_high_low`,
which calls the real `supply_demand.native_zones.previous_day_high_low` through the
patch and checks correct D1 closure.

## 3. No-lookahead / knowledge-time (spec source §5–7, 51)

Audit finding: `time_utc` on `market_structure` swing/BOS/CHoCH events already
represents **confirmation time** (`smc_adapter.py`'s own comment: events are reported at
`BrokenIndex`'s time — when the break was confirmed — not the raw swing candle's time).
There is no separate `event_time`/`knowledge_time` pair anywhere in `market_structure`,
`smc_map`, `supply_demand`, `liquidity`, or `entry_confirmation` — confirmation
semantics are baked into what `time_utc` means, not a distinct field. This is judged
sufficient: it satisfies the spec's requirement (§7) that evidence consumed at
replay-time T have `knowledge_time <= T`, because `time_utc` for every structure event
already **is** the knowledge time.

The remaining no-lookahead surface is therefore multi-timeframe bar closure (§51):
`HistoricalCandleStore.closed_candles(symbol, timeframe, as_of, count)` only returns a
bar once `bar_open_time + timeframe_duration <= as_of` — enforced identically for every
timeframe including D1 — mirroring live `get_latest_candles`'s "position 1 = last fully
closed bar" contract. Verified for H1 and D1 in
`tests/test_historical_replay_no_lookahead.py` (§54–56 of the source task spec).

## 4. Setup identity repair (spec source §17–19, 59)

**Finding**: `proposals.identity.setup_id` was a pure function of
`(symbol, combination, direction)` only — no reference/POI identity. Two independent
setups sharing those three fields (Monday's EURUSD E2M1 SHORT from H1 POI A vs.
Wednesday's from H1 POI B) collided into one `setup_id`, which would corrupt historical
setup-lifecycle/funnel statistics (though largely masked live by the terminal-state
CREATED-after-INVALIDATED path in `lifecycle.py`).

**Fix**: `setup_id` gained an optional 4th parameter, `reference_key` (default `None`,
preserving every existing caller/test that only cares about the 3-field identity).
`reference_key_for(reference_type, reference_low, reference_high, reference_level)`
derives a stable string from the **qualifying E-condition's own structural reference**
(`EConditionResult.reference_type/low/high/level` — the HTF gap/POI/liquidity price
level itself, never current tick price or snapshot time). `gate.py` and `lifecycle.py`
now always look up `analysis.e_conditions[combo.entry_condition]` and pass its
reference fields through. Verified in `tests/test_setup_identity_collision.py`,
including the exact two-concurrent-POI scenario from spec §17.

**Residual known limitation**: a second, independent M-confirmation on the *same* E
reference while the first is still non-terminal is not separately disambiguated (no
stable M-confirmation-instance id exists on `SMCEntryCombinationResult` today). Not
observed as a practical collision risk relative to the POI-level fix; flagged here for
awareness, not treated as blocking.

## 5. Trade management (spec source §25–29, 74) — P&L backtest is BLOCKED

`src/trade_management/` (manager/rules/risk/sizing/geometry) is a real, frozen, generic
75%-partial / breakeven-to-entry / final-R-multiple-exit engine — but it is
**combo-agnostic**: nothing in it reads `SMCTradeProposal`/`SMCEntryCombinationResult`,
and nothing derives SL/TP from M1/M2/M3 structure (inducement level, sweep price, OB/FVG
edge). `grep` for `combination|E1M1|SMC_CONDITIONAL_ENTRY_V2` across
`src/trade_management` returns no matches.

Per the source task spec's own rule (§25–27): **no frozen exit policy exists for
SMC_CONDITIONAL_ENTRY_V2, therefore canonical P&L backtesting is blocked.** Per the
user's explicit decision this phase, no `RESEARCH_EXIT_BASELINE` is built either — this
phase stops at Stage B (semantic replay + setup ledger + funnel + entry-fill
simulation). Stage C/D (trade management, broker costs, R/PF/drawdown metrics) are
**not attempted**.

## 6. Reused infrastructure (do-not-duplicate list)

- `smc_map.build_smc_market_map(symbol, timeframes, snapshot_time)` — the one snapshot
  builder; replay calls it unmodified inside `historical_data_context`, passing the
  replay clock as `snapshot_time`.
- `entry_confirmation.route.evaluate_e1/e2/e3`, `m1/m2/m3` evaluators, `composer.compose`
  — unmodified.
- `proposals.gate.generate_proposals`, `proposals.lifecycle.update_proposal_lifecycle`
  — unmodified except the setup-identity fix (§4), which is additive.
- `runtime_state.store.JsonKeyValueStore` — the same store primitive
  `lifecycle.update_proposal_lifecycle` already uses; replay's setup-ledger persistence
  reuses it rather than inventing a second store.

## 7. Components built (session 1)

- `src/historical_replay/candle_store.py` — `HistoricalCandleStore`,
  `HistoricalDataError`, `TIMEFRAME_MINUTES`, `timeframe_duration`.
- `src/historical_replay/data_source_patch.py` — `historical_data_context`.
- `src/proposals/identity.py` — `reference_key_for` (new), `setup_id` (extended,
  backward-compatible).

## 7b. Components built (session 2) — dataset, replay, ledger, funnel

**Dataset**: `D:\EURUSD_M5_202504211715_202607310000.csv` (MT5 export, 95,393 M5 rows,
Apr 2025–Jul 2026) chosen as the single base feed. Timezone determined empirically
(never assumed): broker server time with seasonal DST (UTC+2/+3), verified via the
project's existing `mt5.broker_time.offset_from_reopen` weekly-reopen-gap technique,
reused rather than reinvented — necessary because the file's own offset genuinely
changes mid-file.

- `src/historical_replay/mt5_export_loader.py` — `load_mt5_export_csv`: parses,
  validates (monotonic, no duplicates, valid OHLC), classifies gaps
  (`EXPECTED_MARKET_CLOSURE` vs `UNEXPECTED_DATA_GAP`, never silently filled), and
  UTC-normalizes using **per-segment** offset detection (a single constant offset is
  provably wrong for this file).
- `src/historical_replay/resampler.py` — `resample`: derives M15/H1/H4/D1 from the one
  M5 base feed, UTC-boundary-aligned, dropping (never fabricating) incomplete windows.
- `src/historical_replay/orchestrator.py` — `run_replay`: the chronological replay
  engine. Steps through closed M5 bars; at each step calls
  `daytrading_runtime.conditional_entry_snapshot.build_symbol_conditional_entry_analysis`
  — the actual live entrypoint, completely unmodified — inside `historical_data_context`.
  Builds a `SetupLedger` (every combination ever observed, not just READY ones, keyed by
  the same `setup_id`/`reference_key_for` the live proposal system uses) and a
  `FunnelTracker` (distinct-first-occurrence stage counts, using only existing
  `EntryModelState` enum values: `REFERENCE_FOUND`/`E_QUALIFIED` from `EConditionResult`,
  `M_STARTED`/`M_CONFIRMED`/`ENTRY_ARRAY_CREATED`/`READY` from `SMCEntryCombinationResult.state`).
  Distinguishes `WARMUP` from a genuine "no setup" result using the live entrypoint's
  own lookback constants (D1=60, H1=50, M5=200 candles).
- `scripts/run_historical_replay.py` — CLI wrapper: load → derive timeframes → replay a
  date range → write a JSON semantic-replay report.

**Bug found and fixed**: `daytrading_runtime.conditional_entry_snapshot` imports
`get_latest_candles`/`get_tick` into its own module namespace (for D1/H1/M5 candles and
current price) in addition to the analyzer modules it calls underneath. The original
patch-target list (§2 above) missed this, so the entire replay silently fell through to
live MT5 (`MT5_NOT_CONNECTED`) every step — historical data was never actually consumed
by the full pipeline until this was found and fixed. Regression test:
`test_full_conditional_entry_entrypoint_reuses_historical_data_not_live_mt5`. This is
exactly the class of error the spec's "prove live/replay parity" requirement (§29) exists
to catch.

**Performance**: ~0.6s/replay-step (dominated by the `smartmoneyconcepts` library's
pandas-based recomputation per timeframe). A full 15-month/~75,000-step replay is a
~13-hour batch job — correctly treated as a separate long-running run (spec §49: "correctness
first... optimization only after equivalence proven"), not something to force into one
sitting. Tests use short real-data windows (hours, not months) to stay fast.

**In-memory lifecycle store**: `orchestrator.InMemoryKeyValueStore` implements the same
get/put interface `runtime_state.store.JsonKeyValueStore` exposes, used only because
`JsonKeyValueStore` does a full-file read+rewrite per `put` — correct for live polling
cadence, but needless O(n) disk I/O across tens of thousands of replay steps. Not a
competing persistence abstraction; same interface, in-memory backing.

## 7c. Broker-day-anchored D1/H4 bucketing — a real bug found and fixed via cross-validation

The user provided native MT5-exported D1 (`EURUSD_Daily_202501020000_202607310000.csv`)
and H1 (`EURUSD_H1_202501020000_202607310000.csv`) files, enabling a direct
broker-conformance cross-check (spec §47) without needing a live, connected terminal
(this dataset comparison works entirely offline).

**H1**: comparing `resample(m5, "M5", "H1")` against the native H1 export — **zero
mismatches across all 7,937 overlapping bars**. Whole-hour broker UTC offsets (+2/+3)
preserve hour boundaries, so plain UTC bucketing is correct for H1 (and M15).

**D1**: comparing the same UTC-midnight-bucketed `resample(..., "D1")` against the
native Daily export — **every single one of 250 overlapping bars mismatched**. Root
cause: MT5's D1 (and H4) candles are anchored to the **broker's own calendar day/4h
window**, not UTC midnight. A broker offset of +2/+3h does not divide evenly into 24h,
so broker midnight falls at 21:00 or 22:00 UTC the *previous* day — a UTC-midnight
bucket boundary is simply the wrong boundary for D1/H4.

**Fix**: `resampler.resample_broker_aligned(base_candles, broker_times, base_timeframe,
target_timeframe)` — buckets by the ORIGINAL broker wall-clock day/4h window
(`mt5_export_loader.IngestionReport.broker_times`, now exposed alongside the
UTC-normalized candles), labeling each derived bar with the UTC time of its first
member (exactly matching how MT5's own timestamp conversion labels a broker-anchored
bar). Completeness for this variant means internal contiguity, not a fixed bar count —
a broker day near a holiday or the dataset's own start/end can be legitimately shorter,
matching MT5's own D1 candle for such a day being naturally shorter rather than
"incomplete." Re-validated against the native Daily export: **318 of 320 buckets match
exactly**; the only 2 mismatches are the dataset's own first/last partial days (M5 data
starts/ends mid-day), a data-coverage boundary effect, not a bucketing defect.

`scripts/run_historical_replay.py` and `tests/test_replay_orchestrator.py`'s fixture
now use `resample_broker_aligned` for H4/D1 and plain `resample` for M15/H1. This fix
landed *before* any canonical semantic-replay numbers were finalized (the Aug 2025
sample report was regenerated after the fix), so no invalid numbers were reported as
final. Tests: `tests/test_resampler_broker_aligned.py` (8 tests, including a live
cross-validation against the native MT5 export when present on the machine).

## 8. Not yet built (remaining phases)

Entry-fill simulator, same-bar ambiguity classification (Stage B), visual audit samples,
a full-history (multi-month) semantic replay run and report, per-symbol breakdown
(only EURUSD loaded so far), MT5 broker-conformance cross-check (blocked until a weekday
session with a connected terminal). See the status doc for exact current field-by-field
state.
