# TD-2 — Top-Down Data Foundation

**Status:** COMPLETE. Follows TD-0 (audit, READY_FOR_TD1) and TD-1 (contract freeze,
commit `07743b6e4fd8bc5f01cb73a90bfc902ebadcb9cb`).

## What this proves

AG Profit Trading can reliably acquire and represent native MT5 broker closed candles
for all six TopDownContext V1 timeframes (W1/D1/H4/H1/M15/M5), with symbol, timeframe,
source, close-time, and data-quality provenance intact — by reusing the existing MT5
acquisition entrypoint and `MarketSnapshot`, not by building a second provider.

## Data authority

`src/mt5/market_data.py::get_latest_candles()` remains the sole acquisition path.
`copy_rates_from_pos(symbol, timeframe, 1, count)` — position 1, never 0 — is
unchanged; the still-forming bar was already excluded before TD-2 and remains
excluded. No timeframe is synthesized from a lower one (no M1→M5/M15/H1/H4/D1/W1
aggregation was written).

## Changes (minimal, additive)

1. **`src/mt5/market_data.py`** — added one entry to `_TIMEFRAMES`:
   `"W1": mt5.TIMEFRAME_W1`. D1/H4/H1/M15/M5 were already present (TD-0 finding,
   re-confirmed by test — H4 in particular needed no change at all).
2. **`src/strategy_contract/market_snapshot.py`** — added one entry to
   `_TIMEFRAME_MINUTES`: `"W1": 10080` (7×1440), so
   `from_mt5_latest_closed(symbol, "W1")` can compute `bar_close_time`. No other line
   in this module changed.
3. **`src/mtf_context/topdown_market_data.py`** — new. One function,
   `closed_snapshot_for_topdown_timeframe(symbol, timeframe, source=...)`, that
   validates `timeframe` is one of TD-1's `TOPDOWN_TIMEFRAMES` (fail-closed otherwise,
   `InvalidTimeframeError`, before any I/O) and then delegates entirely to
   `strategy_contract.market_snapshot.from_mt5_latest_closed`. No candle fetching,
   normalization, or validation logic is duplicated — this file contains no MT5 import
   at all.
4. **`src/mtf_context/__init__.py`** — additive export of the one new function.

No other file changed. `market_structure/`, `supply_demand/`, `liquidity/`,
`daily_routine/`, `historical_replay/`, `entry_confirmation/`, and every
`strategies/*.yaml` are untouched.

## Timeframe support

| Timeframe | MT5 mapping | Status |
|---|---|---|
| W1 | `mt5.TIMEFRAME_W1` | **Added this WP** (genuinely new, per TD-0) |
| D1 | `mt5.TIMEFRAME_D1` | Already present (verified, not modified) |
| H4 | `mt5.TIMEFRAME_H4` | Already present (verified, not modified — TD-0's audit question "does H4 already work" answered: yes) |
| H1 | `mt5.TIMEFRAME_H1` | Already present (verified, not modified) |
| M15 | `mt5.TIMEFRAME_M15` | Already present (verified, not modified) |
| M5 | `mt5.TIMEFRAME_M5` | Already present (verified, not modified) |
| M1 | `mt5.TIMEFRAME_M1` | Unchanged; explicitly excluded from `TOPDOWN_TIMEFRAMES` and rejected by `closed_snapshot_for_topdown_timeframe` (verified by test, before any I/O) |

## Data-quality guards — all reused, none duplicated

| Condition | Guard | Location |
|---|---|---|
| Empty result | `DATA_MISSING` / `INSUFFICIENT_CANDLES` | `mt5/market_data.py::get_latest_candles` (pre-existing) |
| Forming/unclosed latest bar | `copy_rates_from_pos(..., 1, ...)` | `mt5/market_data.py::get_latest_candles` (pre-existing; verified live — see below) |
| Duplicate timestamps | `DUPLICATE_TIMESTAMPS` | `mt5/market_data.py::_validate_monotonic` (pre-existing, already unit-tested in `tests/test_mt5_market_data_guards.py`) |
| Non-monotonic timestamps | `NON_MONOTONIC_TIMESTAMPS` | same |
| Invalid OHLC geometry | `INVALID_OHLC` / `NONFINITE_PRICE` | `mt5/market_data.py::_validate_ohlc` (pre-existing, already unit-tested) |
| Unsupported/out-of-scope timeframe | `UNSUPPORTED_TIMEFRAME` (MT5 level) / `InvalidTimeframeError` (TopDownContext-scope level, new, TD-2) | both layers verified by test |

No new duplicate validation semantics were introduced; the one new check
(`InvalidTimeframeError` in `closed_snapshot_for_topdown_timeframe`) narrows scope to
the six TopDownContext timeframes and is distinct in purpose from MT5's own
`UNSUPPORTED_TIMEFRAME` (which governs the full MT5-supported set including M1/M30).

## Provenance

Every `closed_snapshot_for_topdown_timeframe(...)` call returns a `MarketSnapshot`
(unmodified type) carrying: `symbol`, `timeframe`, `source`, `market_data_mode`
(`"REAL"`), `bar_open_time`, `bar_close_time`, `market_data_asof`, `retrieved_at`,
`is_closed` (always `True` on this path), and `fingerprint` (deterministic
sha256 over symbol/timeframe/mode/candle OHLCV — pre-existing, unmodified). This is
sufficient input for TD-3/TD-4 tier-context builders to populate `WeeklyContext.
..M5Context`'s own provenance fields (`context_id`, `snapshot_fingerprint`,
`feature_version`, `data_quality_status`) without re-deriving any of it.

No `WeeklyContext`/`DailyContext`/etc. value is constructed in TD-2 — this WP proves
the *input* data is available and provenanced, per mission scope.

## Live smoke test (read-only, no order operation)

Ran against the connected Vantage Demo terminal (account 26088035,
`VantageMarkets-Demo`) on 2026-09-18 ~23:34 UTC:

```
status = RAN
symbol = EURUSD
W1  = 2026-09-05 21:00 UTC -> 2026-09-12 21:00 UTC  (closed=True, mode=REAL)
D1  = 2026-09-16 21:00 UTC -> 2026-09-17 21:00 UTC  (closed=True, mode=REAL)
H4  = 2026-09-18 13:00 UTC -> 2026-09-18 17:00 UTC  (closed=True, mode=REAL)
H1  = 2026-09-18 19:00 UTC -> 2026-09-18 20:00 UTC  (closed=True, mode=REAL)
M15 = 2026-09-18 20:30 UTC -> 2026-09-18 20:45 UTC  (closed=True, mode=REAL)
M5  = 2026-09-18 20:50 UTC -> 2026-09-18 20:55 UTC  (closed=True, mode=REAL)
```

All six close times are strictly in the past relative to wall-clock now at call time
(the closed-bar invariant) and each was returned with `market_data_mode == "REAL"`,
`is_closed == True`, and a non-empty `fingerprint`.

## Live MT5 dependency recorded for TD-8 (replay boundary)

`closed_snapshot_for_topdown_timeframe` reaches a connected MT5 terminal via
`strategy_contract.market_snapshot.from_mt5_latest_closed` →
`mt5.market_data.get_latest_candles` → `MetaTrader5.copy_rates_from_pos`, and
`market_data_mode` is hardcoded `"REAL"` on this path (no `REPLAY` entrypoint exists
here yet). `historical_replay/data_source_patch.py` is the existing, project-wide
mechanism (TD-0 audit finding) that substitutes replay data at that same
`mt5.market_data` call site by monkeypatching each importing module's own bound name.
A future TD-8 will need to patch `strategy_contract.market_snapshot`'s bound name of
`get_latest_candles` the same way (or add a `from_replay_candle()`-based path in
`topdown_market_data.py`) — no new pattern to invent, but not yet wired. This module
introduces no MT5-specific object beyond what `MarketSnapshot`/`mt5.market_data`
already carry, so it does not foreclose that future patching.

## Test results

- `tests/test_topdown_market_data.py` — **17 passed** (11 deterministic/unit, 6 live
  smoke, all against the connected terminal).
- `tests/test_market_data.py`, `tests/test_mt5_market_data_guards.py`,
  `tests/test_mtf_context.py`, `tests/test_mtf_context_execution_guard.py`,
  `tests/test_mtf_context_pivot_availability.py`,
  `tests/test_topdown_context_contracts.py`, `tests/test_assistant_market_data.py` —
  **77 passed, 3 failed, 1 skipped.**
  - The 3 failures (`test_get_candles_last_bar_matches_true_utc_now`,
    `test_historical_candles_utc_range_live`, `test_data_health_ok_and_failure_live`)
    were reproduced identically by stashing all TD-2 changes and re-running against
    the TD-1 HEAD (`07743b6`) — **same 3 failures, pre-existing.** Root cause: these
    tests' own `skipif` guards check `weekday() < 5` only; the actual run landed at
    2026-09-18 23:33 UTC (Friday, weekday 4), after FX's real ~21:00 UTC Friday close
    but before the date rolls to Saturday, so the guard doesn't skip even though the
    market is already closed for the weekend. Not a TD-2 regression; not modified as
    part of this WP (out of scope — pre-existing test-guard gap, unrelated to
    `mt5/market_data.py`'s W1 addition or `market_snapshot.py`'s W1 addition).
- Bounded strategy-adjacent regression (`large_smc`, `session_sweep_continuation`,
  `sweep_retest`, `asian`/`post_asian`, `proposal`, `market_structure`,
  `supply_demand`, `slow`/`live_mt5` excluded): **600 passed, 0 failed, 2475
  deselected, 462.87s.**

## Replay future notes

See "Live MT5 dependency recorded for TD-8" above — the concrete gap is: no
`REPLAY`-mode path exists in `topdown_market_data.py` yet, and
`strategy_contract.market_snapshot` imports `mt5.market_data.get_latest_candles` at
module load time (same import-time-binding pattern TD-0 already documented for every
other consumer `historical_replay/data_source_patch.py` patches).

## Out-of-scope confirmation

```
market_interpretation_added = false
strategy_logic_changed = false
proposal_logic_changed = false
risk_logic_changed = false
validation_evidence_changed = false
holdout_accessed = false
demo_authority_changed = false
live_authority_changed = false
execution_authority_changed = false
```

No order operation was performed at any point (read-only market-data calls only).

## Next

TD-3 (existing-context adapters) — **only after owner review of this data foundation.**
