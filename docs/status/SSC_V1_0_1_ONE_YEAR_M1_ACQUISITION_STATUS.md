# SSC_V1_0_1_ONE_YEAR_M1_ACQUISITION_STATUS

Acquisition of the missing EURUSD M1 `FILL_RESOLUTION_INPUT` leg for the SSC v1.0.1
one-year `HISTORICAL_RESEARCH_ONLY` window. Date: 2026-09-19. Environment: local
Windows workstation, `.venv`, branch `main`, MT5 terminal build 6182.

**`FINAL_STATUS = READY_FOR_ONE_YEAR_REPLAY`** — the one-year M1 leg now exists, is
quality-validated, parity-proven against owner-approved canonical M1, and the canonical
coverage audit reports `DATA_COVERAGE_COMPLETE`. **The SSC replay was NOT run** (A8).

## A0 — Preflight

| Check | Result |
| --- | --- |
| Base commit `de46737` present | **YES** (HEAD at mission start) |
| Prior evidence re-verified | target gap `2025-09-15T00:00:00Z → 2026-05-18T06:46:00Z`; tick export `2026-06-18 → 2026-08-24` `UNVERIFIED_TICK_DATA`; BID @ +3 h, 43 292/43 292 exact, 0 missing, 0 deviation |
| Tick parity re-interpreted as provenance? | **NO** — content consistency is not provenance; the tick export remains `UNVERIFIED_TICK_DATA` and was not used |
| Foreign/concurrent WIP | **preserved** (`src/mtf_context/*`, `src/historical_replay/*`, `state/proposal_ledger/*`, `tests/test_topdown_*`, `docs/status/TD8_*` untouched) |

## A1 — Source priority: route 1 succeeded (root cause was NOT broker retention)

The mission's own instruction — *do not assume the setting solved the problem* — was
honoured: the previous `NO_SUITABLE_LOCAL_SOURCE` verdict was first re-diagnosed, and the
blocker turned out to be a **terminal setting**, not missing broker history.

Pre-change evidence (all recorded before any acquisition):

| Probe | Result |
| --- | --- |
| Live terminal `config\common.ini` | `MaxBars=100000` |
| `copy_rates_from_pos(M1, 0, 99999)` | exactly 99 999 bars, starting `2026-06-15T09:58` |
| The "degenerate 1 bar" M1 answer | literally the **oldest bar of that capped base** (`2026-06-15T09:57`), returned for every earlier request |
| Local `.hcc` archives (`VantageMarkets-Demo/EURUSD`) | **2010 → 2026** already on disk, incl. `2025.hcc` 21.34 MB, `2026.hcc` 17.70 MB |
| Same dates, M5/M15/H1 | real bars (211–289 / 71–97 / 18–24) → history exists |
| Deep position access | `start=100000` → `Terminal: Call failed` |

Post-change re-probe (`terminal_info.maxbars` = **100 000 000**; owner raised "Max bars in
chart" and restarted the terminal), same broker/server/account
(**Vantage Markets (Pty) Ltd / VantageMarkets-Demo / login 26088035** ✅):

| Representative date (M1, UTC-day request) | Pre-change | Post-change |
| --- | --- | --- |
| `2025-09-15` | 1 degenerate bar | **1 049 bars** |
| `2025-12-15` | 1 degenerate bar | **1 046 bars** |
| `2026-02-16` | 1 degenerate bar | **1 051 bars** |
| `2026-04-15` | 1 degenerate bar | **1 439 bars** |
| `2026-05-15` | 1 degenerate bar | **1 439 bars** |

Routes 2 (provenanced tick export) and 3 (external provider) were **not** needed and were
not used. No M5/M15 substitution, no interpolation, no synthetic candles, no other symbol.

## A2 — Provenance contract

Recorded in `data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_M1_001/acquisition_provenance.json`:

| Field | Value |
| --- | --- |
| provider | Vantage Markets (Pty) Ltd |
| broker/server | `VantageMarkets-Demo` |
| account | 26088035 (DEMO) |
| environment | `DEMO` (verified `trade_mode == 0`) |
| symbol / metadata | EURUSD · digits 5 · point 1e-05 · tick_size 1e-05 |
| data type | M1 OHLCV bars (`MetaTrader5.TIMEFRAME_M1`) |
| acquisition method | `MetaTrader5.copy_rates_range` (python bridge), chunked by calendar month (14 calls, all recorded) |
| acquisition timestamp | recorded in the provenance file |
| bridge / terminal | MetaTrader5 5.0.5735 · terminal build 6182 · `maxbars` 100 000 000 |
| requested interval | `2025-09-14T00:00:00Z → 2026-09-16T00:00:00Z` (target gap + 1-day margin each side) |
| actual interval | raw broker wall clock `2025-09-15T00:02 → 2026-09-16T00:00` |
| timezone | see A4 |
| price convention | MT5 native BID-based bar OHLC |
| file format | raw: MT5 Export tab-delimited; dataset: `timestamp_utc,open,high,low,close,tick_volume,spread,real_volume` |
| row count | 373 421 (raw and normalized) |
| SHA-256 | raw `3fdd97cf…`, normalized M1 `50beb42a…` (full values in the manifest) |

Provenance is **established** by the same mechanism every owner-approved SSC dataset used
(DEV_001/DEV_002/GEN_002 were all acquired from this account with this call).

## A3 — Direct-M1 validation (parity against canonical)

| Check | Result |
| --- | --- |
| Coverage of the target gap | **complete** — data spans `2025-09-14T21:02:00Z → 2026-09-15T21:00:00Z` |
| Monotonic timestamps | PASS — 0 non-monotonic |
| Duplicate timestamps | PASS — 0 |
| OHLC validity | PASS — 0 invalid bars |
| Gap structure | 373 074 native 1-minute steps · **52 weekend closures** · 294 intraday break steps (2–7 min and occasional ~1 h rollover), largest gap 49.08 h — the import layer labels every sub-40 h break "UNEXPECTED_DATA_GAP", which would mislabel this broker's ordinary rollover behaviour; the structure is recorded explicitly instead |
| **Parity vs canonical** | **`PASS_EXACT`** — 43 292 / 43 292 bars, exact all-four OHLC rate **1.000000**, **0 canonical minutes missing**, overlap `2026-06-21T21:02:00Z → 2026-08-02T23:59:00Z` (already-consumed `SSC_V1_0_1_G2_DEV_002` M1) |
| SSC outcomes inspected | **NO** |

## A4 — Timezone authority (measured, not assumed)

The acquisition was **not** converted with a blanket `+3 h`. Two independent measurements
were used:

1. **Shift scan** against canonical M1 found the exact alignment at **−180 min** with rate
   **1.0000** and no competing offset (next best 0.0089) — proving the bridge returns
   *broker wall-clock* epochs, exactly as `src/mt5/broker_time.py` documents.
2. Normalization therefore went through the repository's own authority —
   `historical_replay.mt5_export_loader.load_mt5_export_csv` /
   `mt5.broker_time.offset_from_reopen` — which resolves the offset **per weekly reopen**.

**Result: the broker DOES shift seasonally inside the target period.** Detected offsets:
`[2, 3]` across 53 weekly segments → loader authority string
**`BROKER_SERVER_TIME(UTC+2/UTC+3 seasonal DST)`**, `offset_changes_inside_period = true`.
Applying a fixed `+3 h` across the whole year — the shortcut the mission prohibited —
would have corrupted every winter week. No bar was interpolated or shifted by anything
other than the per-week resolved offset.

## A5 — Quality gate

`QUALITY_STATUS = PASS`, on the normalized UTC series.

- First timestamp `2025-09-14T21:02:00Z`, last `2026-09-15T21:00:00Z`
- 0 duplicate timestamps, 0 non-monotonic timestamps, 0 invalid OHLC bars
- 13 calendar months covered (`2025-09` … `2026-09`)
- Gaps: 52 weekend closures + intraday rollover steps only; nothing filled
- The manifest's simple-calendar minute estimate is labelled
  `minutes_absent_under_simple_utc_fx_calendar_model` with an explicit caveat: it
  approximates the FX calendar rather than this broker's (holidays, irregular rollover,
  seasonal offset), so it is **not** the coverage gate. The authoritative verdict is the
  canonical audit below.

## A6 — Frozen historical input

`DATA_ROLE = HISTORICAL_RESEARCH_INPUT_ONLY`. Frozen in
`data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_M1_001/dataset_manifest.json`:
dataset id `SSC_V1_0_1_HIST_1Y_M1_001`, source SHA-256, M1 SHA-256, timezone authority,
symbol metadata, coverage, quality status. This does **not** make the dataset independent
validation evidence — the window overlaps only already-consumed periods (see
`LINEAGE_CONTAMINATION_MAP_V1.json`).

## A7 — One-year coverage recheck

`python scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` →

```
FINAL_STATUS: DATA_COVERAGE_COMPLETE
primary window: 2025-09-15T00:00:00Z → 2026-09-14T23:59:59Z
primary_common_covered_days: 365.0
primary_blocking_missing_intervals: {}
primary_warmup_pass: true
```

H1 ∩ M15 ∩ M1 coverage is complete across the whole primary window (previously
`BLOCKED_INCOMPLETE_ONE_YEAR_DATA` with 245.3 missing days). The alternate
calendar-shifted window (`2025-09-19 → 2026-09-18`) remains `BLOCKED_INCOMPLETE_ONE_YEAR_DATA`
because it extends past the acquisition's end (`2026-09-15T21:00:00Z`); it is a
robustness probe, not the mission window, and filling it would require acquiring bars
past the current date range for no mission benefit.

## A8 — No backtest

`SSC_REPLAY_EXECUTED = false`. `session_sweep_continuation.replay.run_replay` was never
called. The one-year replay remains a separate, one-shot mission to be run after this
dataset identity is frozen.

## A9 — Safety

```
STRATEGY_CHANGED=false            PARAMETERS_CHANGED=false
OPTIMIZATION_RUN=false            SSC_REPLAY_EXECUTED=false
CONFIRMATION_ACCESSED=false       HOLDOUT_ACCESSED=false
OOS_ACCESSED=false                BROKER_MUTATION=false
DEMO_ORDER=false                  LIVE_ORDER=false
```

Only read-only broker history calls were made. No order, position, SL/TP or account state
was touched. No strategy YAML or parameter was edited. The one environment change in this
mission (`MaxBars`) was made **by the owner**, not by this session.

## Status block

| Field | Value |
| --- | --- |
| `SOURCE_TYPE` | direct broker M1 OHLC bars (no tick→M1 derivation needed) |
| `SOURCE_AUTHORITY` | owner-authorized Vantage/MT5 route 1 — same broker/account/terminal as every owner-approved SSC dataset |
| `PROVENANCE_STATUS` | **ESTABLISHED** (provider, broker/server, account, method, timestamp, requested vs actual interval, hashes all recorded) |
| `TARGET_INTERVAL` | `2025-09-15T00:00:00Z → 2026-05-18T06:46:00Z` |
| `ACTUAL_COVERAGE` | `2025-09-14T21:02:00Z → 2026-09-15T21:00:00Z` (373 421 M1 bars) |
| `TIMEZONE_AUTHORITY` | `BROKER_SERVER_TIME(UTC+2/UTC+3 seasonal DST)`, resolved per weekly reopen (53 segments, 2 distinct offsets) |
| `PRICE_STREAM` | MT5 native BID-based bar OHLC |
| `RAW_SOURCE_SHA256` | `3fdd97cfba62c37251f401c9e357833da4df3da48729d8edf9363ef2a6fe7fdd` |
| `DERIVATION_CONTRACT_HASH` | `NOT_APPLICABLE_DIRECT_M1_ACQUISITION` |
| `M1_SHA256` | `50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a` |
| `QUALITY_STATUS` | **PASS** |
| `ONE_YEAR_COVERAGE_STATUS` | **`DATA_COVERAGE_COMPLETE`** |
| `PROTECTED_DATA_CLEAR` | **YES** |
| `FINAL_STATUS` | **`READY_FOR_ONE_YEAR_REPLAY`** |
| `NEXT_SINGLE_ACTION` | Run the one-shot one-year `HISTORICAL_RESEARCH_ONLY` SSC replay as a separate mission against the frozen dataset `SSC_V1_0_1_HIST_1Y_M1_001` (report gross/net metrics, decompositions and the DEV_002 overlap caveat) — not started here, and never to be labelled independent confirmation |

## Evidence files

- `data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_M1_001/` — `raw/EURUSD_M1.csv`,
  `raw/EURUSD_M1_broker_export.csv`, `acquisition_provenance.json`, `dataset_manifest.json`
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/DATA_COVERAGE_AUDIT_V1.json`
  (now `DATA_COVERAGE_COMPLETE`)
- `scripts/acquire_ssc_one_year_m1_mt5.py` — reproducible acquisition + validation
