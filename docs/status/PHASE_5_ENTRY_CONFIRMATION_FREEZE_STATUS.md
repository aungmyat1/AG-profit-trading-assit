# Phase 5 — Entry & Confirmation Freeze Status (2026-08-28)

Scope: freeze the verified `AG_ENTRY_CONFIRMATION_V1` implementation as the stable
foundation for Phase 6's entry-side work (`AG_TRADE_MANAGEMENT_V1`, not started). No new
confirmation logic added in this pass -- see prior passes for the circular-import repair
and `AG_ENTRY_DISPLACEMENT_V1`/`event_sequence` implementation this freeze records.
Execution (`order_check`/`order_send`) untouched and still disabled throughout.

## 1. Freeze Decision

```
AG_ENTRY_CONFIRMATION_V1 = VERIFIED_AND_FROZEN
```

`FROZEN` means no silent semantic changes to the canonical chain, the displacement
contract, or the sequencing rule below -- a behavior change requires a new contract
version or explicit owner instruction, same convention as `AG_ORDER_BLOCK_V1` /
`AG_LIQUIDITY_V1` (`docs/status/PHASE_1_4_FREEZE_STATUS.md`).

## 2. Canonical Chain

```
LIQUIDITY EVENT
      v
STRUCTURE_SHIFT (CHoCH)
      v
DISPLACEMENT
      v
EVENT_SEQUENCE
      v
CONFIRMATION_STATE
```

`STRUCTURE_SHIFT_V1 = CHoCH` only. BOS remains available directly from
`StructureResult.latest_bos` but is not folded into `structure_shift` without a future
explicit owner decision.

## 3. Frozen Contract — `AG_ENTRY_DISPLACEMENT_V1`

```
body_ratio >= 0.60
AND body_size >= 1.30 x median_body_20
AND candle direction matches candidate_direction (BULLISH for LONG, BEARISH for SHORT)

body_ratio = abs(close - open) / (high - low)
median_body_20 = median(abs(close - open)) over the 20 completed candles strictly
                 preceding the evaluated candle (never the candle itself)
```

Reports `INSUFFICIENT_DATA` (not a guessed `PASS`/`FAIL`) when: `candidate_direction`
is `NONE`, range is zero, fewer than 20 valid prior candles are supplied, or
`median_body_20` resolves to zero. `rejection` remains `UNSIGNED_RULE` -- deliberately
not extended.

## 4. Frozen Contract — `event_sequence`

```
liquidity_time < structure_time <= displacement_time   -> PASS
otherwise                                               -> FAIL
any of the three timestamps missing                     -> INSUFFICIENT_DATA
```

`structure_time == displacement_time` is explicitly valid (the structural break and its
confirming displacement may be the same candle). Derived only -- not independently
requestable; evaluated only once `structure_shift`, `liquidity_reclaim`, and
`displacement` are all requested, and folded into `overall_state` like any other
requested primitive. No-lookahead: `mt5.market_data.get_latest_candles()` excludes the
still-forming bar by construction, and `displacement.py` additionally filters supplied
history to `c.time < candle.time` regardless of what a caller supplies.

## 5. Aggregation Model (unchanged, frozen)

```
CONFIRMED | PARTIAL | NOT_CONFIRMED | INDETERMINATE
```

No numeric confidence score exists or is planned for V1.

## 6. Architecture Preserved

`entry_confirmation` consumes `market_structure.StructureResult` and
`liquidity.LiquidityResult` verbatim -- it does not redetect pivots, CHoCH, BOS,
liquidity levels, sweeps, or reclaims. It answers "has price shown sufficient evidence,"
never "should I buy or sell" -- no execution call exists in this package (enforced by
`tests/test_entry_confirmation.py::test_entry_confirmation_package_has_no_execution_imports`,
which asserts no module under `entry_confirmation/` imports `execution` or `mt5`).

## 7. Circular Import Fix (root-caused, not just papered over)

```
entry_confirmation -> liquidity -> supply_demand -> assistant -> entry_confirmation
```

Root cause: `supply_demand/native_zones.py` imported `assistant.market_data` at module
load time -- a foundational-layer package reaching into the top orchestration layer.
Fixed by:

- `entry_confirmation/models.py`: `LiquidityResult`/`StructureResult` imports moved
  under `TYPE_CHECKING` (annotation-only, safe under `from __future__ import annotations`).
- `assistant/analysis_models.py`, `assistant/assessment.py`: import real runtime symbols
  (`ALL_CONFIRMATIONS`, `ConfirmationState`) from `entry_confirmation.models` directly
  rather than the package `__init__`.
- `supply_demand/native_zones.py`: deferred the `assistant.market_data.session_snapshot`
  import to call time -- the actual backwards edge.

No public API removed; `EntryConfirmationResult` is only ever constructed by
`entry_confirmation/engine.py` (grep-verified), so its new required `event_sequence`
field did not break any other caller.

**Known non-blocking residual:** `supply_demand -> assistant` is still a backwards
dependency in principle -- the deferred import only makes it non-fatal at runtime. A
future pass could move `session_snapshot`'s logic to a neutral layer so `supply_demand`
never imports `assistant` at all. Does not block Phase 5 or Phase 6.

## 8. Test Evidence

```
AG_ENTRY_CONFIRMATION_V1_BASELINE
467 passed
0 failed
```

19 new focused tests added in `tests/test_entry_confirmation.py` (11 for
`AG_ENTRY_DISPLACEMENT_V1` -- both directions, wrong-direction FAIL, both boundaries
exact + just-below, zero-range, insufficient history, history-after-candidate excluded,
median excludes candidate; 8 for `event_sequence` -- valid SELL, valid BUY, stale
structure-before-liquidity FAIL, premature displacement FAIL, same-candle PASS,
missing-timestamp INSUFFICIENT_DATA, NOT_REQUESTED unless all 3 inputs requested,
no-lookahead check). 2 pre-existing tests updated (one in `test_entry_confirmation.py`,
one in `test_five_skill_runtime.py`) because they asserted the old "displacement is
always `UNSIGNED_RULE`" behavior, which signing `AG_ENTRY_DISPLACEMENT_V1` retired --
not a silent rewrite, both changes documented inline in the test file and in this ledger.

## 9. Live Read-Only Validation

Read-only, via `mt5.connection.connect()` + `assistant.five_skill_runtime.analyze_market()`
-- no `order_send`, no synthetic data.

```
EURUSD M15 LONG
  structure_shift    PASS (BULLISH_CHOCH @ 2026-08-28 10:45 UTC)
  liquidity_reclaim  FAIL (UNSWEPT)
  displacement       FAIL (body_ratio 0.54 < 0.60, relative_body 0.74x < 1.30x)
  event_sequence     INSUFFICIENT_DATA (no reclaim_time -- level never reclaimed)
  overall_state      INDETERMINATE

EURUSD M5 LONG
  structure_shift    PASS
  liquidity_reclaim  FAIL (UNSWEPT)
  displacement       FAIL (body_ratio 0.63, relative_body 1.18x < 1.30x required)
  overall_state      INDETERMINATE
```

Both examples are real market evidence, not manufactured to force a pass. No
`CONFIRMED`/`PARTIAL` example was observed at validation time (no reclaimed liquidity
level was present on EURUSD) -- an honest, acceptable validation outcome, not a search
failure; not repeated further to avoid searching for a passing setup. `XAUUSD` returned
`STALE_DATA` (tick ~60 min old vs. the 120s freshness threshold) in this environment --
not an Entry Confirmation defect; investigate at the MT5/market-data layer if it recurs.

## 10. Execution Safety

```
ORDER_SEND_USED       = NO
REAL_MONEY_TRADING    = DISABLED
AUTONOMOUS_TRADING    = DISABLED
```

Unchanged by this phase; `AG_DEMO_EXECUTION_SAFETY_V1 = ACCEPTED_WITH_RESIDUAL_GAP`
carries forward as-is (no new live order test performed).

## 11. Deferred (not missing, not blocking)

```
REJECTION_QUALIFICATION   DEFERRED
POI_ALIGNMENT              DEFERRED
FVG_ENTRY_TRIGGER          DEFERRED
BOS_AS_STRUCTURE_SHIFT     DEFERRED
TRADE_MANAGEMENT           DEFERRED (Phase 6, separate mission)
```

## 12. Frozen File Surface

Treat as part of the verified V1 surface -- future changes require a clearly stated
reason, not casual edits:

```
src/entry_confirmation/models.py
src/entry_confirmation/displacement.py
src/entry_confirmation/sequence.py
src/entry_confirmation/engine.py
src/entry_confirmation/__init__.py

src/assistant/analysis_models.py
src/assistant/assessment.py
src/assistant/five_skill_runtime.py

src/supply_demand/native_zones.py

tests/test_entry_confirmation.py
tests/test_five_skill_runtime.py

docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md
```

## 13. Final Gate

```
PHASE_5_ENTRY_CONFIRMATION_FREEZE = PASS
READY_FOR_PHASE_6_ENTRY_SIDE      = YES
NEXT_PHASE                         = AG_TRADE_MANAGEMENT_V1 (entry-side) -- NOT_STARTED
```
