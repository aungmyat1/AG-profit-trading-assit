# SMC_CONDITIONAL_ENTRY_V2 Runtime Wiring — 2026-08-29

Preserves `SMC_CONDITIONAL_ENTRY_V2`'s architecture unchanged (`docs/specs/SMC_CONDITIONAL_ENTRY_V2_SPEC.md`).
This pass: (1) freezes two remaining semantic ambiguities, (2) wires E1/E2/E3 +
M1/M2/M3 + composer into a new analysis-only runtime module, (3) adds runtime
integration tests. No new detector, no threshold change, no session routing, no trade
management, no execution authority.

## Runtime audit before editing (spec section 6)

```
CURRENT_E1_WIRING   = daytrading_runtime/snapshot.py::build_e1_result -- fetches D1 gap,
                       calls gap.py directly, wraps into smc_watcher's OLDER shallow
                       alert classifier (evaluate_e1_condition). Never touches the new
                       entry_confirmation.e1_daily_gap_reaction module.
CURRENT_E2_WIRING   = build_e2_result -- DOES call the new e2_h1_poi_reaction module
                       internally, but still collapses the result back into the same
                       older smc_watcher alert shape.
MISSING_E3_WIRING   = build_e3_results uses liquidity_result(symbol, "M15") + smc_watcher's
                       evaluate_e3_condition directly -- never calls
                       entry_confirmation.e3_liquidity_sweep at all, and uses M15, not
                       one of SMC_CONDITIONAL_ENTRY_V2's frozen E3 reference timeframes
                       (H1/H4/D1).
CURRENT_M1/M2/M3_WIRING = NONE. No caller of evaluate_m1/m2/m3_* existed anywhere in
                       the runtime before this pass.
COMPOSER_WIRING     = NONE.
RESULT_SERIALIZATION = SymbolSMCSnapshot(e1, e2, e3_buy_side, e3_sell_side) -- all
                       smc_watcher.SMCConditionResult (a third, older, separate
                       vocabulary from both V1/V2/V2.1 and the new
                       EConditionResult/M*Result/SMCEntryCombinationResult contracts).
OLD_FIELD_REFERENCES = one found and fixed: daytrading_runtime/snapshot.py line 129
                       still read `reaction.eligible_for_m2` (orphaned by the field
                       rename two passes ago) -- corrected to `.eligible_for_confirmation`.
OBSOLETE_HARD_WIRED_PAIR_ASSUMPTIONS = the entire snapshot.py module predates
                       SMC_CONDITIONAL_ENTRY_V2 and serves a DIFFERENT concern (live
                       alert/dedup/persistence via smc_watcher + PersistentSMCRuntime,
                       daytrading_runtime/smc_runtime.py) -- left untouched, not
                       repurposed, to avoid destabilizing a working, persisted alert
                       pipeline. A NEW module was added instead (see below).
```

## New module: `daytrading_runtime/conditional_entry_snapshot.py`

Two-layer split (same discipline `daytrading/pipeline.py` already uses):

- `compose_conditional_entry_analysis(...)` -- **pure**. Every E1/E2/E3/M1/M2/M3
  primitive is a parameter; calls nothing MT5-shaped. Fully unit-tested (13 tests,
  `tests/test_conditional_entry_snapshot.py`) with hand-built fixtures, no mocking.
- `build_symbol_conditional_entry_analysis(symbol)` -- thin MT5-fetching wrapper.
  Fetches D1/H1/M5 candles, M5 FVG/OB inventory, H1 liquidity, and current price
  **exactly once each** (spec section 14 — single-snapshot reuse), then delegates.
  Every fetch is individually try/except MarketDataError-wrapped; a failure degrades
  that one component to its own NOT_APPLICABLE/WAITING_HTF_TOUCH state and is recorded
  in `warnings` — it never raises out of this function and never fabricates a trigger
  (verified live against this sandbox's disconnected MT5: `data_quality="UNAVAILABLE"`,
  7 explicit per-component warnings, `combinations=()`, zero exceptions).

M1/M2/M3 are evaluated **once per distinct direction** present among the eligible
E-conditions (not once per E, and not tied to whichever E happened to qualify first) —
this is what makes "any E + any M" actually true at the runtime layer, not just in the
composer's unit tests. Each maneuver's own model-specific evidence (inducement
candidate, opposing S/D zone, HTF liquidity level) is drawn from a shared, once-fetched
"pool," filtered to the side/role that direction requires:

- **M1** — `liquidity.hierarchy.find_inducement_candidates` (existing, unwired
  primitive from an earlier pass) run once against a once-fetched M5 external/internal
  tier scope, exactly mirroring the composition `daytrading/pipeline.py` already uses
  for its own liquidity-affinity step (reused, not reinvented). A documented,
  best-effort extension (`_recently_taken_inducement`) additionally detects an
  inducement candidate that has **already** been taken within the same single snapshot
  — `find_inducement_candidates`'s own signed contract only ever returns still-UNSWEPT
  candidates, so an already-taken one is invisible to it by construction; this reapplies
  the identical relational test to a taken level. **Known limitation, stated in the
  module docstring, not hidden**: this does not replay history, so it cannot confirm
  the level was already between price and its target at the moment it was taken — only
  that a plausible target still exists now.
- **M2** — `supply_demand.analyzer.validated_order_blocks_for` (AG_ORDER_BLOCK_V1,
  which DOES track true closed-beyond INVALIDATED status, unlike the raw smc.ob() zones
  used elsewhere, which can only ever report FRESH/MITIGATED) adapted onto a
  `ZoneResult` via `_validated_ob_to_zone` — a pure status-vocabulary mapping between
  two already-signed contracts (`OBValidationStatus` → `ZoneStatus`), not a new
  invalidation rule.
- **M3** — reuses the exact same `LiquidityLevel` objects E3 itself evaluated
  (`liquidity_result(symbol, "H1").nearest_buy_side/nearest_sell_side`) — zero
  duplicate fetch.

## Explainability (spec section 18)

`SMCConditionalEntryAnalysis.e_conditions`/`m_maneuvers` always expose every E1/E2/E3
and every evaluated M1/M2/M3 — never only the "winning" one. `data_quality`/`warnings`
name exactly which fetch failed. `selected_combination` is always `None` — no
ranking/priority layer exists (verified: `test_selected_combination_is_always_none_no_ranking_layer`).

## Phase C — H1_REACTION_V1 frozen (spec section 3)

```
H1_REACTION_V1 = QUALIFYING_DIRECTIONAL_DISPLACEMENT_REACTION
```

Audited: E1 (`gap.py::evaluate_gap_context`'s `GAP_REACTED`) and E2
(`e2_h1_poi_reaction.py::_first_reacting_candle`) both gate "reaction" on exactly one
test — a caller-supplied reaction candle, strictly after the touch, passing
`AG_ENTRY_DISPLACEMENT_V1` in the candidate direction. Documented explicitly (constant +
docstring in `entry_confirmation/entry_models_v1.py`) what counts (one qualifying
displacement candle) and what does NOT (wick-only rejection, two-candle reclaim,
deceleration, failed acceptance without displacement, multi-candle reversal patterns) —
none of those are implemented, and this pass does not broaden the rule, only names it
precisely. Why displacement specifically: it is the only owner-signed generic candle
qualification rule in this package; `rejection.py`'s wick-dominance measurement exists
but its threshold is `UNSIGNED_RULE`.

## Phase D — M3 inverted-gap policy frozen (spec section 4)

```
M3_INVERTED_GAP_POLICY = OPTIONAL
```

Audited against both possible contracts (documented in `m3_sweep_drop_pump.py`'s module
docstring): Contract A (inverted gap optional, any already-implemented immediate entry
structure suffices) vs. Contract B (inverted gap mandatory, making M3 currently
`PARTIAL`). The existing implementation already matches Contract A exactly — its actual
gating entry structure is `entry_array.py`'s regular FVG/OB midpoint, never an
inverted-gap-specific one, and `pullback_percent` is computed from that regular
structure. No behavior changed; `M3_INVERTED_GAP_POLICY = "OPTIONAL"` constant added for
programmatic access, and `M3_FULL_REFERENCE_CONFORMANCE` is explicitly declared not
applicable under Contract A (there is no "full reference" gap to be partially
conformant to).

## Test accounting

```
BASELINE_COLLECTED = 805, BASELINE_PASS = 800, BASELINE_FAIL = 5 (pre-existing, unrelated)
TESTS_ADDED = 13 (tests/test_conditional_entry_snapshot.py)
TESTS_REMOVED = 0
FINAL_COLLECTED = 818, FINAL_PASS = 813, FINAL_FAIL = 5 (same pre-existing failures)
REGRESSIONS = 0
```

## Historical / live validation (spec sections 20-32)

**Blocked by environment, not by scope.** This sandbox has no reachable MT5 terminal
(`mt5.connection.connect() has not been called or the terminal dropped` — the same
condition underlying all 5 pre-existing `_live` test failures). `MT5_AVAILABLE = NO`.
`build_symbol_conditional_entry_analysis("EURUSD")` was run directly against this: it
did not raise, correctly reported `data_quality="UNAVAILABLE"` with 7 explicit
per-component warnings (`E1_D1_FETCH_FAILED:MT5_NOT_CONNECTED`, etc.),
`combinations=()`, and every E/M component in its own honest NOT_APPLICABLE/waiting
state — this IS the "successful wiring, no runtime error, no fabricated setup" outcome
spec section 32 defines as valid even without a ready combination, short of having real
market data to inspect semantically. Semantic historical validation (sections 20-25:
sampling 20-30 real M1/M2/M3 candidates, cross-pair evidence in live data) could not be
performed and is not fabricated here — it requires either a connected MT5 terminal or a
historical candle dataset neither of which exists in this session. The pure composition
layer (`compose_conditional_entry_analysis`) is exercised instead by 13 deterministic
integration tests covering exactly the section-26 required scenarios (E1 qualified + M2
engaged, E2 qualified + M1 engaged, E3 qualified + M2 engaged, two-E/one-M and
one-E/two-M cross products, multiple-E/multiple-M, no-E, insufficient M5/H1 data,
determinism, wrong-side-pool never fabricates readiness, timeframe responsibility
fields, `selected_combination` always `None`).

## Scope discipline

No session routing, no model ranking/selection, no trade-management change, no
execution-authority change. `daytrading_runtime/snapshot.py`'s existing
alert/dedup/persistence pipeline (smc_watcher + `PersistentSMCRuntime`) is untouched —
this pass adds a parallel, independent analysis-only module rather than repurposing it,
since the two serve different concerns (live alerting/dedup vs. this task's
E/M/composer semantic analysis).
