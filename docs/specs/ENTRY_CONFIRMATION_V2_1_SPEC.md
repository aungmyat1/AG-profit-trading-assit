# ENTRY_CONFIRMATION_V2_1 Spec — 2026-08-29

Package: `entry_confirmation/` (same package as V1/V2). New public entry point:
`evaluate_sweep_shift_array()` in `engine_v2_1.py`. Purely additive to V1 (`models.py`,
`engine.py`) and V2 (`models_v2.py`, `engine_v2.py`) — none of those files were modified.
Freezes **SMC_SWEEP_SHIFT_ARRAY_V1**: HTF liquidity/POI → sweep → valid structural pivot
→ body-close CHoCH/MSS → displacement → FVG/OB entry array → structural invalidation.

## Key reuse finding (audit)

`config/market_structure.yaml` already sets `close_break: true`, which
`market_structure/smc_adapter.py` passes straight into `smc.bos_choch(...,
close_break=...)`. This means **`StructureResult.latest_choch`/`latest_bos` were already
body-close events, never wick-only**, before this pass — the "wick != CHoCH" freeze
(spec rule 7) required composing existing signed capabilities, not building a new
CHoCH detector. Similarly `liquidity.LiquidityStatus` (`SWEPT`/`RECLAIMED`/`CONSUMED`)
already distinguishes a live wick-through from a closed-beyond level. New code in this
pass is a thin, deterministic composition layer over these existing guarantees, plus a
genuinely new piece: pivot *significance* classification via `market_structure.tiers`
(EXTERNAL/INTERNAL swing tiers, already existing, not previously wired into
`entry_confirmation`).

## New modules

| File | Responsibility |
|---|---|
| `models_v2_1.py` | `PivotRole`, `StructureShiftQualityStatus`, `SetupFamily`, `EntryArrayType`, `EntryMethodV21`, `ConfluenceRelation`, `PivotContext`, `StructureShiftQuality`, `DisplacementLeg`, `EntryArrayContext`, `SMCSweepShiftArrayResult` |
| `sweep_shift.py` | `classify_wick_or_close` (pure single-candle geometry), `evaluate_pivot_context` (tier-based pivot significance), `evaluate_structure_shift_quality` (composes V1's `StructureAlignment`/`DisplacementEvidence` into the quality axis) |
| `entry_array.py` | `fvg_associated_with_leg`, `ob_associated_with_shift` (causal/temporal association, not proximity), `evaluate_entry_array` (FVG/OB confluence + entry geometry) |
| `engine_v2_1.py` | `SweepShiftArrayRequest`, `evaluate_sweep_shift_array` (dispatch), `evaluate_reversal_sweep_shift` (SMC_REVERSAL_SWEEP_SHIFT_V1), `evaluate_continuation_pullback` (SMC_CONTINUATION_PULLBACK_V1) |

No new module redetects CHoCH/BOS, sweeps, FVG, or OB geometry. `evaluate_structure_shift_quality`
reuses `entry_confirmation.models.StructureAlignment` (V1) and `DisplacementEvidence`
(V1, `AG_ENTRY_DISPLACEMENT_V1`) verbatim; `evaluate_entry_array` reuses V2's `GapContext`
and `supply_demand.ValidatedOrderBlock` verbatim.

## Wick vs. body-close (spec rules 7-9, 39)

`classify_wick_or_close(candle, level_price, side)` is pure arithmetic (no threshold):
`wick_through` compares the candle's high/low against `level_price`; `close_through`
compares the candle's close. `fakeout = wick_through and not close_through`. This is a
single-candle helper distinct from `liquidity.LiquidityStatus`'s own stateful
sweep/reclaim state machine — used where a caller wants to classify one specific candle
against one specific level directly (e.g. the exact spec-39 fixture) rather than go
through the full multi-candle liquidity history.

## Pivot quality (spec rules 10-11)

`evaluate_pivot_context` classifies a broken pivot price against caller-supplied
`market_structure.StructureTier` objects (from `market_structure.tiers.analyze_structure_tiers`,
already existing, not previously consumed by `entry_confirmation`): a price matching an
EXTERNAL-tier swing → `EXTERNAL_SWING`; INTERNAL-tier only → `INTERNAL_SWING`; neither →
`MICRO_PIVOT`; no tiers supplied → `UNRESOLVED`. Matching is exact-price (tolerance
`1e-9`) — see Known Gaps below for the live-validation caveat this produced.

## Structure shift quality (spec rules 26, 42-43, 58)

`evaluate_structure_shift_quality` composes sweep presence, post-sweep ordering, pivot
validity, `StructureAlignment.status`, `DisplacementEvidence.status`, and FVG presence
into `StructureShiftQualityStatus` (`VALID_STRONG` / `VALID_WEAK` / `FAKEOUT_WICK` /
`INVALID_PIVOT` / `WRONG_SEQUENCE` / `MID_RANGE_LOW_CONTEXT` / `INDETERMINATE`) —
explicitly separate from the frozen 4-state `aggregation_status`
(`CONFIRMED`/`PARTIAL`/`NOT_CONFIRMED`/`INDETERMINATE`, unchanged from V1/V2). A
body-close event with valid pivot but unqualified displacement is `VALID_WEAK` →
`aggregation_status = PARTIAL`, never silently promoted to `CONFIRMED`.

## FVG/OB association (spec rules 17-18, 44-46)

`fvg_associated_with_leg` accepts a gap only when its `origin_time` falls inside the
caller-supplied displacement-leg time window — an old, unrelated FVG near the same price
is never promoted. `ob_associated_with_shift` accepts an OB only when its own recorded
`ValidatedOrderBlock.structure_event.time_utc` (an existing AG_ORDER_BLOCK_V1 field)
equals the structural-shift event time being evaluated.

## Entry array + confluence (spec rules 19-22)

`evaluate_entry_array` returns `FVG`, `ORDER_BLOCK`, `FVG_AND_ORDER_BLOCK`, or `NONE`.
When both are associated, `ConfluenceRelation` (`OVERLAP`/`PARTIAL_OVERLAP`/
`SAME_LEG_NO_OVERLAP`/`UNRELATED`) is computed from their boundaries; only on overlap is
`entry_method = FVG_OB_CONFLUENCE` with `entry_reference` = the overlap midpoint. FVG-only
uses the gap midpoint (mirroring V2's `FIFTY_PERCENT_INVERTED_GAP` precedent — deterministic
arithmetic, not a new threshold); OB-only uses the zone midpoint. `entry_status` is
`WAITING_ENTRY_PRICE` until a caller-supplied `current_price` reaches the reference, then
`ENTRY_REFERENCE_AVAILABLE` — never a claimed fill.

## Setup family dispatch (spec rules 29-31, 49)

`evaluate_sweep_shift_array` inspects the request: a `sweep_level` with `sweep_time` set
→ `evaluate_reversal_sweep_shift` (REVERSAL); no sweep but a `bos_time` supplied →
`evaluate_continuation_pullback` (CONTINUATION); neither → `SetupFamily.UNRESOLVED`,
never guessed. `evaluate_reversal_sweep_shift` requires the full causal chain and rejects
a structural break that predates its sweep (`WRONG_SEQUENCE`).
`evaluate_continuation_pullback` is intentionally implemented at reduced depth (no
sweep-ordering check applies; `ob_associated_with_shift` is called with
`structure_event_time=None` since BOS has no CHoCH event to match against) — see Known
Gaps.

## Structural invalidation (spec rule 23)

`EntryArrayContext.structural_invalidation_candidates` is a tuple (sweep price + OB
extreme when available) — no single value is silently chosen when more than one
candidate exists; downstream (Trade/Risk Management) picks the final stop.

## Known gaps

1. ~~Pivot-tier price matching uses exact equality.~~ **Fixed.** Live validation
   (EURUSD M5, 2026-08-28) showed a real CHoCH pivot price failing to match either tier
   because `analyze_structure()` (default single-tier, `swing_length=5`) and
   `analyze_structure_tiers()` (INTERNAL `swing_length=5`, EXTERNAL `swing_length=50`)
   are independently computed calls that can return microscopically different float
   values for what is conceptually the same swing — the pivot was classified
   `MICRO_PIVOT` when it was actually a genuine INTERNAL swing. Fixed by adding
   `evaluate_pivot_context(..., tolerance_price=...)` and threading
   `SweepShiftArrayRequest.pivot_tolerance_price` through to it. This reuses the SAME
   signed tolerance `market_structure/tiers.py` already applies to its own HH/HL/LH/LL
   labeling (`config/liquidity.yaml`'s `equal_level_tolerance_points` × the symbol's
   `tick_size`, computed by `mt5.symbol_resolver.get_symbol_meta`) — no new business
   threshold was invented; the caller computes and supplies it, matching
   `entry_confirmation`'s architecture boundary of never fetching market/symbol data
   itself. Omitting the parameter falls back to the original near-exact-equality
   behavior. Re-validated live (EURUSD M5, same session): the pivot now correctly
   resolves to `INTERNAL_SWING` instead of `MICRO_PIVOT`; the route now reports
   `NOT_CONFIRMED`/`WRONG_SEQUENCE` (structural break predates the sweep) — a different,
   still-honest, non-fabricated outcome. Tests:
   `test_pivot_tolerance_matches_a_near_miss_float_from_independent_computation`,
   `test_pivot_tolerance_does_not_rubber_stamp_a_genuinely_different_price`,
   `test_pivot_tolerance_defaults_to_near_exact_equality_when_omitted`.
2. `evaluate_continuation_pullback` has no dedicated "existing directional structure"
   verification beyond a caller-asserted `trend_context_valid` flag, and no sweep-style
   causal-ordering check between BOS and the pullback/correction — `PARTIAL` per the
   spec's own DoD allowance (`CONTINUATION_PULLBACK = VERIFIED/PARTIAL`).
3. Premium/discount is a pure pass-through string (`request.premium_discount_zone`); no
   `DealingRangeZones` object is consumed directly by `engine_v2_1.py` (the caller is
   expected to have already called `supply_demand.premium_discount_from_session/
   previous_day` and pass `.current_zone`).
4. `target_liquidity_reference` and `poi_reference` are opaque pass-through fields
   (metadata only, per spec rule 24) — no target/POI selection logic exists here.

## Execution / risk / trade-management boundary

Unchanged from V1/V2: no `order_send`, no lot sizing, no TP/RR calculation anywhere in
this pass. `EXECUTION_AUTHORITY_CHANGED = NO`.
