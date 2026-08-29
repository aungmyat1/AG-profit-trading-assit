# SMC_CONDITIONAL_ENTRY_V2 Spec — 2026-08-29

Supersedes `SMC_ENTRY_MODELS_V1`'s hard-wired E1→M1 / E2→M2 / E3→M3 pairing rule
(`docs/specs/SMC_ENTRY_MODELS_V1_SPEC.md` — not deleted; still accurate on what E1/E2/E3
and M1/M2/M3 individually mean, only the pairing rule changed). Corrected model:

```
ANY qualified E-condition + ANY qualified M-maneuver + DIRECTION ALIGNMENT
= a valid SMC entry candidate

3 entry contexts x 3 confirmation maneuvers = 9 possible combinations (E1M1..E3M3)
```

## Audit before editing (spec section 28)

```
E1_IMPLEMENTATION = e1_daily_gap_reaction.py::E1Result -- had `eligible_for_m1: bool`
E2_IMPLEMENTATION = e2_h1_poi_reaction.py::E2Result -- had `eligible_for_m2: bool`
E3_IMPLEMENTATION = e3_liquidity_sweep.py::E3Result -- had `eligible_for_m3: bool`
M1_IMPLEMENTATION = m1_character_change_inducement.py -- took `e1_result: E1Result` (typed)
M2_IMPLEMENTATION = m2_supply_demand_shift.py -- took `e2_result: E2Result` (typed)
M3_IMPLEMENTATION = m3_sweep_drop_pump.py -- took `e3_result: E3Result` (typed)

CURRENT_HARD_WIRED_PAIRS = E1->M1, E2->M2, E3->M3 (field naming + Python type signatures)
CALLERS_ASSUMING_E1_M1/E2_M2/E3_M3 = only this package's own test files. No live
    runtime caller wired M1/M2/M3 yet (only E1/E2 location+reaction were wired into
    daytrading_runtime/snapshot.py in the prior pass).
REUSABLE_COMPONENTS = EntryModelState lifecycle vocabulary (remapped, not rebuilt); all
    E/M internal evidence logic (gap/POI/liquidity detection, inducement, zone-failure,
    sweep-shift delegation) -- none of that changed.
REQUIRED_REFACTOR = generic EConditionResult envelope + SMCEntryCombinationResult;
    M1/M2/M3 signatures changed to accept EConditionResult instead of E1Result/
    E2Result/E3Result; reference_timeframe/check_timeframe added to each E-result; a
    composer module.
COMPATIBILITY_RISK = LOW (no live wiring depended on the hard-wired signatures)
```

## New/changed modules

| File | Change |
|---|---|
| `entry_models_v1.py` | Adds `SMC_CONDITIONAL_ENTRY_V2`, `EConditionResult`, `SMCEntryCombinationResult`, `ENTRY_CONDITIONS`/`MANEUVERS`/`COMBINATIONS` constants, timeframe constants. `EntryModelState` remapped to the section-20 vocabulary (`WAITING_LOCATION`→`WAITING_HTF_TOUCH`, `WAITING_REACTION`→`WAITING_H1_REACTION`, `WAITING_CONFIRMATION`→`WAITING_M5_CONFIRMATION`, `WAITING_ENTRY`→`WAITING_M5_ENTRY`; added `SCANNING_CONTEXT`, `HTF_QUALIFIED`, `INSUFFICIENT_DATA`, `NO_VALID_COMBINATION`). The old, unused `SMCEntryModelResult`/`MODEL_E1_M1`/`MODEL_E2_M2`/`MODEL_E3_M3` were removed (never constructed/returned by any function in the prior pass — dead code, not "working tested components"). |
| `e1_daily_gap_reaction.py` | `eligible_for_m1` → `eligible_for_confirmation`; new `e1_to_econdition()` converter |
| `e2_h1_poi_reaction.py` | `eligible_for_m2` → `eligible_for_confirmation`; new `e2_to_econdition()` converter |
| `e3_liquidity_sweep.py` | `eligible_for_m3` → `eligible_for_confirmation`; new `reference_timeframe` field (copied from the caller-supplied `LiquidityLevel.timeframe` — E3's own reference timeframe is never forced to H1); new `e3_to_econdition()` converter |
| `m1_character_change_inducement.py` | `evaluate_m1_character_change_with_inducement(e1_result: E1Result, ...)` → `(e_condition: EConditionResult, ...)`. M1 now derives its own direction from the inducement candidate's side and compares to `e_condition.direction`; mismatch → `NO_VALID_COMBINATION` (previously silently used E1's direction unconditionally). |
| `m2_supply_demand_shift.py` | `evaluate_m2_supply_demand_shift(e2_result: E2Result, ...)` → `(e_condition: EConditionResult, ...)`. M2 derives its own direction from the opposing zone's role; mismatch → `NO_VALID_COMBINATION`. |
| `m3_sweep_drop_pump.py` | `evaluate_m3_sweep_drop_pump(e3_result: E3Result, ...)` → `(e_condition: EConditionResult, liquidity_level: LiquidityLevel, ...)` — the concrete liquidity evidence is now a separate parameter, since it's no longer bundled inside a specific E3Result. M3 derives its own direction from the level's side; mismatch → `NO_VALID_COMBINATION`. |
| `composer.py` | New. `evaluate_entry_combinations(e_conditions, m_results) -> Tuple[SMCEntryCombinationResult, ...]` — cross-joins every supplied E with every supplied M, keeping only pairs where `E.eligible_for_confirmation`, `M.state not in (NOT_APPLICABLE, NO_VALID_COMBINATION)`, and `E.direction == M.direction`. No priority invented (spec section 22) — every valid pair is returned. |
| `daytrading_runtime/snapshot.py` | One-line fix: `reaction.eligible_for_m2` → `reaction.eligible_for_confirmation` (the prior pass's field rename left this live caller stale — caught here, not previously flagged). |

None of `engine.py`/`engine_v2.py`/`engine_v2_1.py`/`route.py`/`sweep_shift.py`/
`entry_array.py`/`gap.py`/`poi.py`/`displacement.py`/`structure_alignment.py` changed —
every E/M module is pure composition over them, unchanged.

## Direction alignment (spec section 10)

Each M-maneuver now computes its own direction independently from its own evidence
(inducement side for M1, opposing-zone role for M2, liquidity-level side for M3) rather
than trusting whichever E fed it. When that independently-derived direction contradicts
the E-condition's own direction, the maneuver reports `NO_VALID_COMBINATION` rather than
silently picking a side — this is the mechanism that makes "any E + any M" safe: a
caller can feed E2's SHORT context into M1 alongside a bullish inducement candidate and
get an honest rejection instead of a fabricated LONG result.

## Composer (spec section 18)

Pure cross-join, no duplicated M-logic. Multiple E's and multiple M's may be
simultaneously active (spec section 21) — `evaluate_entry_combinations` handles 0 to 9
combinations from whatever subset of E-conditions/M-results the caller supplies. No
routing/priority layer exists (spec section 22): `test_no_priority_is_invented_all_valid_combinations_returned`
asserts every valid combination is returned at the same "rank."

## Timeframe responsibility (spec section 23)

`EConditionResult.reference_timeframe`/`check_timeframe` are always populated by the
E-side converter (`e1_to_econdition`: D1→H1; `e2_to_econdition`: H1→H1;
`e3_to_econdition`: `LiquidityLevel.timeframe` (H1/H4/D1, caller-determined)→H1).
`SMCEntryCombinationResult.confirmation_timeframe`/`execution_timeframe` are always
`"M5"`. No caller can accidentally evaluate an H1 reaction on M5 data or M5 confirmation
on H1 data through this contract — the fields exist to make the mismatch visible, not to
enforce it at runtime (enforcement remains the caller's responsibility, same as V1).

## Test accounting (spec section 30)

**This pass:**

```
BASELINE_COLLECTED = 792 (end of prior SMC_ENTRY_MODELS_V1 pass)
BASELINE_PASS      = 787
BASELINE_FAIL      = 5 (pre-existing _live MT5-connection tests, unrelated)

TESTS_ADDED   = 13 (11 new tests/test_entry_combination_composer.py +
                     2 new tests in test_m3_sweep_drop_pump.py: no-liquidity-level
                     gating, direction-mismatch NO_VALID_COMBINATION gating)
TESTS_REMOVED = 0
TESTS_RENAMED = 2 (test_wrong_side_inducement_candidate_is_rejected ->
                    ..._is_no_valid_combination; test_wrong_role_opposing_zone_is_rejected
                    -> ..._is_no_valid_combination -- same assertions' *subject*, updated
                    expected state from a WAITING_* value to NO_VALID_COMBINATION)

EXPECTED_FINAL = 792 + 13 = 805
ACTUAL_FINAL   = 805
ACCOUNTING_RECONCILED = YES
```

**Full history, reconciling the previous pass's report too** (759 + 39 != 792 was
flagged as unexplained in this task's brief — reconciled here):

```
Original baseline (before any SMC_ENTRY_MODELS_V1/V2 work) = 759 collected, 754 pass

Pass 1 (SMC_ENTRY_MODELS_V1 -- E1/M1, E2/M2, E3/M3 built):
    TESTS_ADDED   = 47  (4 E1 + 9 M1 + 8 E2[rewritten] + 9 M2 + 6 E3 + 11 M3)
    TESTS_REMOVED = 14  (the OLD test_e2_h1_poi_reaction.py's 14 sweep-chain tests,
                          deleted when that file was rewritten down to E2's true scope)
    759 - 14 + 47 = 792  -- matches that pass's actual final count (792). The
    previous report's "NEW = 39" cited the net delta for that one file's replacement
    (39 = 47 - 8 counted oddly) rather than the full gross/removed breakdown -- this
    is the source of the flagged 759+39=798!=792 mismatch. Correct breakdown: 47 added,
    14 removed, 33 net -- 759 + 33 = 792.

Pass 2 (this pass, SMC_CONDITIONAL_ENTRY_V2 -- composer):
    TESTS_ADDED = 13, TESTS_REMOVED = 0
    792 + 13 = 805 -- matches actual (805).

Combined: 759 -> 805 (+46 net), 60 added total, 14 removed total. Reconciled.
```

## Execution / risk / trade-management boundary

Unchanged: no `order_send`, no lot sizing, no TP/RR calculation, no session-entry
routing added. `SESSION_ENTRY_LOGIC_ADDED = NO`, `TRADE_MANAGEMENT_CHANGED = NO`,
`LIVE_ORDER_AUTHORITY_CHANGED = NO`. This phase ends at `SMCEntryCombinationResult` with
`state` up to `READY` — never an `order_send` call.

## Known follow-ups (unchanged from the prior pass, not resolved here)

1. M1/M2/M3/E3/composer are not yet wired into `daytrading_runtime/snapshot.py`'s live
   `SymbolSMCSnapshot` — this pass is architecture-correction, not live-wiring
   expansion, per the mission's own scope limit ("Do NOT add new trading strategy logic
   beyond what is necessary for this architectural correction").
2. `INVERTED_GAP` remains undefined (`M3Result.inverted_gap_policy` stays `PARTIAL`,
   never gates `READY`).
3. No E/M/combination priority or routing layer exists (deliberately, per spec section
   22) — a future pass may add one, but nothing here presumes what it will look like.
