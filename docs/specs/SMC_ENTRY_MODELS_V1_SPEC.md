# SMC_ENTRY_MODELS_V1 Spec — 2026-08-29

Package: `entry_confirmation/` (same package as V1/V2/V2.1). Additive: no V1/V2/V2.1
file, dataclass, or entry point was removed. Freezes the E1/M1, E2/M2, E3/M3
architecture:

```
E1 = DAILY_GAP_REACTION            -> M1 = CHARACTER_CHANGE_WITH_INDUCEMENT
E2 = H1_POI_REACTION                -> M2 = SUPPLY_DEMAND_SHIFT
E3 = HTF_LIQUIDITY_SWEEP             -> M3 = SWEEP_DROP_PUMP
```

E answers WHY price is eligible (HTF location/reaction). M answers HOW the M5 execution
model confirms and constructs the entry. `E != M`: touching an HTF level alone never
produces a trade.

## Audit finding that shaped this pass

The prior revision of `e2_h1_poi_reaction.py` (`E2_PRICE_REACT_H1_POI_V2`) delegated
everything downstream of "a relevant M5 sweep occurred" to
`engine_v2_1.evaluate_reversal_sweep_shift` (`SMC_SWEEP_SHIFT_ARRAY_V1`: sweep -> CHoCH
-> displacement -> FVG/OB). That pipeline is HTF-liquidity-sweep-driven, not
supply/demand-shift-driven — it belongs to **M3**, not M2. Reusing it for "E2" would
have produced `M1 == M2 == M3 == sweep + CHoCH + displacement + FVG`, the exact
distinctness failure this spec's own section 15 prohibits. This pass:

1. Re-homed that pipeline, unmodified, to `m3_sweep_drop_pump.py` (anchored to an E3
   HTF-liquidity-sweep location instead of an E2 H1-POI location — structurally
   identical composition, correct model).
2. Rewrote `e2_h1_poi_reaction.py` down to its true scope: H1 POI touch + qualifying M5
   reaction candle only (no sweep, no CHoCH, no displacement chain).
3. Built `m2_supply_demand_shift.py` from scratch: the first real implementation of
   `SUPPLY_DEMAND_SHIFT`, previously flagged `PARTIAL`/`UNRESOLVED` everywhere it was
   named (`route.py::evaluate_e2`'s own docstring). No liquidity sweep anywhere in this
   model — that is precisely what keeps it distinct from M1 (inducement sweep) and M3
   (HTF sweep).

`engine_v2_1.py`, `sweep_shift.py`, `entry_array.py`, `gap.py`, `poi.py`,
`displacement.py`, `structure_alignment.py` are all byte-for-byte unchanged — every new
module is pure composition over them.

## New modules

| File | Model | Responsibility |
|---|---|---|
| `entry_models_v1.py` | common | `SMC_ENTRY_MODELS_V1`, `EntryModelState` (8-state lifecycle), `SMCEntryModelResult` (normalized explainable envelope) |
| `e1_daily_gap_reaction.py` | E1 | `E1Result`, `evaluate_e1_daily_gap_reaction` — thin wrapper over `gap.py::evaluate_gap_context` |
| `m1_character_change_inducement.py` | M1 | `M1Result`, `evaluate_m1_character_change_with_inducement` — inducement (from `liquidity.hierarchy.InducementCandidate`) -> taken -> CHoCH -> displacement -> entry array |
| `e2_h1_poi_reaction.py` (rewritten) | E2 | `E2Result`, `evaluate_e2_h1_poi_reaction` — POI touch + qualifying M5 reaction only |
| `m2_supply_demand_shift.py` | M2 | `M2Result`, `evaluate_m2_supply_demand_shift` — opposing-zone failure (`ZoneStatus.INVALIDATED`) -> CHoCH -> displacement -> new opposing-role zone -> entry array |
| `e3_liquidity_sweep.py` | E3 | `E3Result`, `evaluate_e3_htf_liquidity_sweep` — relabels `liquidity.LiquidityStatus`'s TOUCH/PENETRATION/SWEEP/RECLAIM state machine |
| `m3_sweep_drop_pump.py` | M3 | `M3Result`, `evaluate_m3_sweep_drop_pump` — delegates to `engine_v2_1.evaluate_reversal_sweep_shift` verbatim, anchored to an E3 sweep+reclaim location |

## Common lifecycle (`EntryModelState`)

```
NOT_APPLICABLE -> WAITING_LOCATION -> WAITING_REACTION -> WAITING_CONFIRMATION
    -> WAITING_ENTRY -> READY
                      -> INVALIDATED
                      -> EXPIRED
```

Every M-model's `state` is drawn from this vocabulary — never reduced to a boolean. A
caller always knows what is *missing* (see each `*Result` dataclass's explicit
sub-fields: `inducement_taken`, `choch_confirmed`, `zone_failure`, `reclaim`, etc.).

## Fail-closed primitives (spec section 29 stop conditions)

| Primitive | Status | Resolution this pass |
|---|---|---|
| `INDUCEMENT` | **DEFINED** (pre-existing, unwired) | `liquidity.hierarchy.InducementCandidate` wired into M1 for the first time. A CHoCH found without a caller-supplied, side-matched, taken `InducementCandidate` never reaches READY (`test_no_inducement_candidate_is_never_ready_even_with_choch`). |
| `SUPPLY_DEMAND_SHIFT` | Was **UNRESOLVED** everywhere named | Newly signed as `M2_SUPPLY_DEMAND_SHIFT_V1`: opposing-role zone must report `ZoneStatus.INVALIDATED` (closed beyond, reused verbatim from `supply_demand`) before a CHoCH is even searched. A CHoCH without zone failure never confirms a shift (`test_choch_alone_without_zone_failure_never_confirms_shift`). |
| `TOUCH/PENETRATION/SWEEP/RECLAIM` (E3) | **DEFINED** (pre-existing, unwired to E3 vocabulary) | Directly relabels `LiquidityStatus` (`UNSWEPT`/`SWEPT`/`CONSUMED`/`RECLAIMED`) — no new state machine. |
| `50% pullback` (M3) | **DEFINED** (pre-existing arithmetic) | `entry_array.py`'s FVG-midpoint/OB-midpoint/confluence-overlap-midpoint IS the 50% pullback reference by construction; `M3Result.pullback_percent` is always `50.0` when an entry reference exists. |
| `INVERTED_GAP` | Remains **UNDEFINED** | `gap.py::evaluate_inverted_gap_context` already reports `policy="PARTIAL"`; `M3Result.inverted_gap_policy` surfaces this honestly and never gates `READY` on it (per spec section 13/29 — fail closed, no fabricated threshold). |

## Directional symmetry

Every model has an explicit bullish and bearish test (`test_full_bearish_*` /
`test_full_bullish_*` in each new test file) — the bearish path is never assumed to
mirror automatically.

## Closed-candle safety / no lookahead

All CHoCH/structural-break searches reuse `market_structure.structural_breaks_for_candles`
(itself built on `close_break=true`, body-close only) and the same `evaluation_time`
upper-bound guard used throughout V2/V2.1 (`b.time_utc <= evaluation_time`). Every new
model has a dedicated `test_zero_lookahead_future_mutation_does_not_change_past_result`.

## Live wiring

`daytrading_runtime/snapshot.py::build_e2_result` was repaired to call the rewritten
`E2PoiReactionRequest` (its stale `m5_liquidity_levels`/`m5_fvg_zones`/`m5_order_blocks`
fields were removed from the request contract by this pass but the caller had not been
updated — fixed here). It wires E2 only; M2 is not yet wired into the live runtime
(needs an M5 opposing-zone feed this snapshot module does not currently fetch) — flagged
as a follow-up, not silently left broken. `build_e1_result`/`build_e3_results` are
unchanged (still the shallower `smc_watcher` alert-level classifiers; the new
`e1_daily_gap_reaction.py`/`m1_character_change_inducement.py`/`e3_liquidity_sweep.py`/
`m3_sweep_drop_pump.py` engines are standalone and tested but not yet wired into
`snapshot.py` — same follow-up category as M2).

## Regression policy

Baseline (before this pass): 759 tests collected, 754 passed, 5 pre-existing failures
(all `_live`, require an MT5 terminal connection — unrelated to entry_confirmation).
After this pass: 792 tests collected, 787 passed, the same 5 pre-existing failures.
**Zero regressions, zero new failures, 33 net new tests** (39 new across
`test_e1_daily_gap_reaction.py`/`test_m1_character_change_inducement.py`/
`test_m2_supply_demand_shift.py`/`test_e3_liquidity_sweep.py`/
`test_m3_sweep_drop_pump.py`, minus 6 from `test_e2_h1_poi_reaction.py`'s rewrite to the
new, narrower E2 scope).

## Execution / risk / trade-management boundary

Unchanged: no `order_send`, no lot sizing, no TP/RR calculation, no session-entry
routing added anywhere in this pass. `SESSION_ENTRY_LOGIC_ADDED = NO`,
`TRADE_MANAGEMENT_CHANGED = NO`, `LIVE_ORDER_AUTHORITY_CHANGED = NO`.

## Known follow-ups (not done in this pass)

1. M2/M1/M3 are not yet wired into `daytrading_runtime/snapshot.py`'s live
   `SymbolSMCSnapshot` (only E1/E2 location+reaction and E3's shallow alert classifier
   are). Wiring requires deciding how each model's caller-supplied inputs (opposing
   zone, inducement candidate, HTF liquidity level) get fetched live — a data-plumbing
   decision, not a modeling one, deliberately left for a dedicated pass.
2. No priority/routing rule between E1_M1/E2_M2/E3_M3 was introduced (spec section 20
   explicitly prohibits inventing one) — each model is evaluated independently.
3. `INVERTED_GAP` and `rejection` qualification remain unsigned, per the audit; both
   report themselves honestly rather than fabricating a threshold.
