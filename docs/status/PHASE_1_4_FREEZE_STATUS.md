# Phase 1-4 Freeze Status (2026-08-27)

Scope: resolve the observed USDJPY `TIME_NORMALIZATION_ERROR`, establish
`AG_TIME_NORMALIZATION_V1`, and validate Phases 1-4 as a stable baseline before Phase 5
begins. No trading-meaning change to `AG_ORDER_BLOCK_V1` or `AG_LIQUIDITY_V1`. Execution
(`order_check`/`order_send`) untouched and still disabled throughout.

## 1. Root Cause

```
USDJPY_TIME_NORMALIZATION_ROOT_CAUSE = NOT DEFINITIVELY REPRODUCIBLE;
ONE REAL, GENERIC DEFECT FOUND AND FIXED DURING THE TRACE.
```

The single live `TIME_NORMALIZATION_ERROR` for USDJPY occurred during the prior Phase 4
smoke run. Reproduction was attempted directly against the live MT5 terminal:

- `mt5.broker_time.detect_broker_utc_offset_hours("USDJPY")` — succeeded (offset=3)
  consistently across 7 repeated fresh-process calls after this pass's fix.
- `liquidity.liquidity_result("USDJPY", "H1")` — succeeded (`LIQUIDITY_OK`) on repeat.
- Deselecting and reselecting USDJPY in Market Watch, then immediately re-fetching
  3000 M15 bars, returned the full history instantly (no cold-start/history-download
  delay reproduced on this terminal).
- Raw `rates[i]["time"]` for EURUSD/GBPUSD/USDJPY/XAUUSD are all `numpy.int64` epoch
  seconds — same type, same representation, no per-symbol format difference.

**Could not force a repeat failure.** This is reported honestly rather than assuming a
root cause not in evidence — the most likely explanation is a transient MT5 terminal/IPC
or demo-feed hiccup at the moment of the original call, not a persistent code defect
specific to USDJPY.

**One real, generic defect was found and fixed regardless**, independent of whether it
caused the original failure: `mt5.broker_time.detect_broker_utc_offset_hours()` finds
the weekly-reopen gap via `max(gaps, key=lambda g: g[0])`. Python's `max()` keeps the
*first* item on a tie. Because this feed produces an identically-sized weekly gap most
weeks, ties are the common case, and the old code silently anchored on the OLDEST tied
gap in the 3000-bar lookback window rather than the most recent one. If a DST transition
had occurred between that old week and now, the derived broker-UTC-offset would have
been silently wrong — a plausible-looking but incorrect value, not an error. This is
symbol-agnostic (affects the shared gap-detection code path for every symbol), so fixing
it satisfies the "no symbol-specific patch" requirement by construction — there was
never a per-symbol branch to add.

Affected code path (Task 2 trace):

```
MT5.copy_rates_from_pos (numpy.int64 epoch seconds, broker wall clock)
      -> broker_time.detect_broker_utc_offset_hours() [_largest_gap(), FIXED]
      -> broker_time.offset_from_reopen()
      -> market_data._broker_offset_hours() [lru_cache per symbol]
      -> market_data.get_candles() / get_latest_candles() / get_tick()
         [single inline UTC conversion formula, repeated identically 3x, not duplicated logic]
      -> strategy_engine.session.Candle.time (tz-aware UTC) / Tick.time_utc
      -> session_clock.py (pure UTC hour comparison, no re-conversion)
      -> market_structure / supply_demand / liquidity (consume Candle.time as-is)
```

No second, distinct defect was found in the conversion pipeline itself.

## 2. Fix

**Files modified:**
- `mt5/broker_time.py` — extracted `_largest_gap(times)` as a pure, testable function;
  changed tie-break from "first/oldest" to "most recent" via `key=lambda g: (g[0], g[1])`.
  `detect_broker_utc_offset_hours()` now calls it instead of `max(gaps, key=...)` inline.

**Behavior before:** on a tie for the largest inter-bar gap, the oldest matching gap in
the lookback window was used to derive the broker's UTC offset.

**Behavior after:** the most recent matching gap is used. No change in output for the
data queried during this pass (no DST transition fell inside the 3000-bar M15 lookback
window for any tested symbol), but the failure mode described above is closed for future
runs that do span a transition.

No other file in the time-normalization path was changed. No symbol-specific branch was
added anywhere.

## 3. Canonical Time Contract

```
TIME_CONTRACT = AG_TIME_NORMALIZATION_V1
```

New: `mt5/time_contract.py` (documentation module, mirrors the project's existing
`liquidity/contract.py` / `supply_demand/ob_contract.py` convention — no behavior of its
own).

```
MT5 input:                numpy.int64 epoch seconds; decodes (naively) to the BROKER'S
                           OWN wall clock, not true UTC, unless the broker server itself
                           runs on UTC.
internal representation:  strategy_engine.session.Candle.time / Tick.time_utc --
                           timezone-aware datetime, tzinfo=timezone.utc, always.
canonical timezone:        UTC.
conversion boundary:       mt5/market_data.py only -- one inline formula repeated at its
                           3 call sites (get_candles/get_latest_candles/get_tick), fed by
                           mt5/broker_time.py's single offset-detection heuristic. No
                           other module re-derives or re-applies a broker offset.
session consumer expectation: session_clock.py assumes candles/ticks handed to it are
                           already true UTC and performs no further conversion.
serialization:             not defined -- out of scope; Candle is not currently
                           serialized to JSON/CSV/wire format by any Phase 1-4 module.
```

## 4. Symbol x Timeframe Matrix

Live, read-only, run against the connected demo terminal (VantageMarkets-Demo) at
2026-08-27 ~05:15 UTC:

```
             M15       H1
EURUSD       PASS      PASS
GBPUSD       PASS      PASS
USDJPY       PASS      PASS
XAUUSD       PASS      PASS
```

Evidence (candles=20, structure=VALID, liquidity=LIQUIDITY_OK for all 8 cells):

```
EURUSD  M15  first=2026-08-27T00:15:00Z  last=2026-08-27T05:00:00Z
EURUSD  H1   first=2026-08-26T09:00:00Z  last=2026-08-27T04:00:00Z
GBPUSD  M15  first=2026-08-27T00:15:00Z  last=2026-08-27T05:00:00Z
GBPUSD  H1   first=2026-08-26T09:00:00Z  last=2026-08-27T04:00:00Z
USDJPY  M15  first=2026-08-27T00:15:00Z  last=2026-08-27T05:00:00Z
USDJPY  H1   first=2026-08-26T09:00:00Z  last=2026-08-27T04:00:00Z
XAUUSD  M15  first=2026-08-26T23:15:00Z  last=2026-08-27T04:00:00Z
XAUUSD  H1   first=2026-08-26T07:00:00Z  last=2026-08-27T03:00:00Z
```

All timestamps land on their timeframe's expected UTC boundary (M15 on :00/:15/:30/:45,
H1 on :00), consistent across all four symbols.

## 5. Regression Status

```
Phase 1 Market Data:       PASS
Phase 2 Market Structure:  PASS
Phase 3 Supply & Demand:   PASS
Phase 4 Liquidity:         PASS
```

## 6. Test Results

Full suite:

```
passed:  154
failed:  0
skipped: 1  (test_market_data.py: "today's Asian session has not completed yet" --
             a legitimate, explicit environmental skip, not hidden or forced)
xfailed: none
```

Breakdown (files directly touched or exercised by this pass):

```
time-normalization tests (test_broker_time.py):            9  (2 new: _largest_gap tie-break + ordinary-spacing)
market-data tests (test_market_data.py):                   5
session tests (test_assistant_market_data.py):             10
market-structure tests (test_market_structure.py):         6
order-block tests (test_ob_contract.py):                   17
supply/demand tests (test_supply_demand.py):                8
liquidity tests (test_liquidity.py):                        17
liquidity deterministic end-to-end (test_liquidity_session_availability.py): 17
interface-freeze tests (test_phase_interfaces.py, new):      5
live MT5 smoke tests (across the above files, MT5-guarded): 10
```

## 7. Frozen Contracts

```
AG_ORDER_BLOCK_V1 = FROZEN
AG_LIQUIDITY_V1   = FROZEN
```

No blockers remain against either. Neither contract's trading meaning was touched by
this pass — only the shared time-normalization layer beneath both.

## 8. Known Non-Blocking V1 Gaps

```
Liquidity (AG_LIQUIDITY_V1):
- SWING_HIGH/SWING_LOW scope is latest-swing-only, not full swing history
- cross-source dedup merge tolerance reuses equal_level_tolerance_points

Order Blocks (AG_ORDER_BLOCK_V1):
- FLIP_OB unsigned/disabled (never assigned)
- L1/L2 classification unsigned
- inside-bar classification unsigned
```

These are documented, pre-existing V1 limitations, unchanged by this pass. They do not
block Phase 5 readiness.

## 9. Execution Safety

```
ORDER_CHECK_ENABLED = NO
ORDER_SEND_ENABLED  = NO
```

Evidence: `execution/mt5_gateway.py`'s `order_check()` and `order_send()` both
unconditionally `raise NotImplementedError(...)`; neither function was touched this
pass. `PROJECT_STATUS.md`'s `ORDER_SEND = DISABLED` / `LIVE TRADING = DISABLED` remain
accurate.

## Cross-Layer Interfaces (Task 17)

```
PHASE 1 -- mt5.market_data.Candle / Tick
       v
PHASE 2 -- market_structure.StructureResult
       v
PHASE 3 -- supply_demand.ValidatedOrderBlock / ZoneResult
       v
PHASE 4 -- liquidity.LiquidityResult
       v
────────────────────────────────────────
future Phase 5 consumer
```

Explicitly documented (new: `tests/test_phase_interfaces.py` protects the field names
below from silent renames):

- Phase 5 must not independently calculate session highs/lows -- consume
  `supply_demand.session_zone()` / `liquidity.LiquidityResult`'s ASIAN/LONDON/NEW_YORK
  sources.
- Phase 5 must not independently detect market structure -- consume
  `market_structure.analyze_structure()`'s `StructureResult`.
- Phase 5 must not independently detect order blocks -- consume
  `supply_demand.validated_order_blocks_for()`'s `ValidatedOrderBlock`.
- Phase 5 must not independently recreate liquidity levels -- consume
  `liquidity.liquidity_result()`'s `LiquidityResult`.

## 10. Final Gate

```
PHASE_1_4_FREEZE = PASS
READY_FOR_PHASE_5 = YES
```
