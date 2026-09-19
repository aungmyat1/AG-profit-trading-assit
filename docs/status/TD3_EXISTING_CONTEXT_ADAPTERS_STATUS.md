# TD-3 — Existing Context Adapters

**Status:** COMPLETE. Follows TD-0 (audit), TD-1 (contract freeze,
`07743b6e4fd8bc5f01cb73a90bfc902ebadcb9cb`), TD-2 (data foundation, uncommitted at
start of TD-3).

## What this proves

Existing D1/H1/M5 market-context facts (already computed by
`daily_routine.d1_context.build_d1_context`, `daily_routine.h1_setup.
build_h1_setup_context`, and `market_structure.analyze_structure`) can be
deterministically, losslessly (within contract limits) translated into TD-1's frozen
`DailyContext`/`H1Context`/`M5Context` — by adaptation only. No swing, BOS/CHOCH, FVG,
order-block, or liquidity detection was implemented in this work package.

## Adapters

| Tier | Function | Orchestration convenience |
|---|---|---|
| D1 | `daily_context_from_d1(d1: D1Context, ...)` — pure mapping | `build_daily_context(symbol, ...)` — calls `build_d1_context` then adapts |
| H1 | `h1_context_from_sources(h1_setup, structure, ...)` — pure mapping | `build_h1_context(symbol, ...)` — calls `build_d1_context` + `build_h1_setup_context` + `analyze_structure` |
| M5 | `m5_context_from_structure(structure, ...)` — pure mapping | `build_m5_context(symbol, ...)` — calls `analyze_structure` |

## Authority reuse

```
D1_source              = daily_routine.d1_context.build_d1_context
H1_source               = daily_routine.h1_setup.build_h1_setup_context
                          (+ market_structure.analyze_structure, see H1 gap below)
M5_structure_source     = market_structure.analyze_structure
                          (no composed M5 orchestrator exists in this repo -- TD-0 finding)
M5_supply_demand_source = NOT MAPPED this WP -- see ADAPTER_COVERAGE (contract gap, not source gap)
M5_liquidity_source     = NOT MAPPED this WP -- see ADAPTER_COVERAGE (contract gap, not source gap)
```

### Documented gap in the existing H1 authority (not fixed here)

`daily_routine.h1_setup.build_h1_setup_context()` calls
`market_structure.analyze_structure(symbol, "H1")` internally but only preserves
`.state` on its own `H1SetupContext` — the full `StructureResult` (needed for
`H1Context.bar_close_time`, `structure_facts`, `feature_version`) is discarded after
that call returns. Since `H1Context.bar_close_time` is mandatory, `build_h1_context()`
makes its own second call to the **same** `market_structure.analyze_structure`
function to recover those fields. This is invoking the existing authority twice, not a
second implementation of it — verified by the no-redetection guard tests (below), which
confirm the adapter module imports nothing beyond `daily_routine.d1_context`,
`daily_routine.h1_setup`, `daily_routine.models`, and `market_structure`/
`market_structure.models`.

### Strategy-owned interpretation deliberately excluded

`H1SetupContext`'s own `selected_poi`, `current_location`, `alert_zone`,
`midnight_open`, `asian_session_high`/`low` fields are H1-strategy-specific
interpretation (POI selection driven by D1's directional permission) — per the TD-3
mission's structure-semantic boundary, **none of it is copied into `H1Context`**.
Structurally enforced: `H1Context` (TD-1's frozen contract) has no field with those
names at all (asserted by test).

## Adapter coverage

### D1
```
available            = structure_direction (via latest_bos/latest_choch -> structure_facts),
                        closed-bar timestamp (data_end_utc), detector version (smc_version)
unavailable           = MarketSnapshot fingerprint (build_d1_context uses get_latest_candles
                        directly, not strategy_contract.market_snapshot -- D1 authority never
                        attaches one)
intentionally_not_mapped = directional_permission, external_buy/sell_side_liquidity,
                        internal_liquidity, gap_liquidity (FVG zones), fundamental_context --
                        all either D1-strategy-specific interpretation (directional_permission)
                        or facts TD-1's DailyContext has no field to carry yet (liquidity/FVG;
                        see CONTRACT GAP below) -- not a detection gap, a contract-scope gap
```

### H1
```
available            = structure_direction (via latest_bos/latest_choch -> structure_facts,
                        recovered via a second analyze_structure(symbol,"H1") call -- see
                        documented H1 gap above), closed-bar timestamp, detector version
unavailable           = none from the source beyond what's already excluded below --
                        H1SetupContext's own liquidity levels (evidence["liquidity"]) exist
                        at the source but are not surfaced because TD-1's H1Context has no
                        field for them (contract gap, not source gap)
intentionally_not_mapped = selected_poi, current_location, alert_zone, midnight_open,
                        asian_session_high/low, poi_candidates, d1_directional_permission --
                        all H1-strategy-owned interpretation, deliberately excluded per the
                        TD-3 structure-semantic boundary
```

### M5
```
available            = structure_direction (via latest_bos/latest_choch -> structure_facts),
                        closed-bar timestamp, detector version -- all from
                        market_structure.analyze_structure(symbol, "M5"), the same function
                        D1/H1 already call at their own timeframes
unavailable           = none identified -- analyze_structure() is the canonical M5 structure
                        authority and was fully consulted
intentionally_not_mapped = order blocks (supply_demand.validated_order_blocks_for),
                        FVG zones (supply_demand.fair_value_gaps_for), liquidity levels
                        (liquidity.liquidity_result) -- all three ALREADY EXIST at the source
                        (same functions D1Context/H1SetupContext already call) but TD-1's
                        frozen M5Context has no order_block_facts/fvg_facts/liquidity_facts
                        field to carry them. This is a CONTRACT gap, not a detection or
                        adapter gap -- flagged as an input to a future TD-1 contract revision
                        or TD-4+ work package, not silently worked around by inventing a field
                        here (TD-1 is frozen; this WP does not modify topdown_contracts.py).
                        entry_confirmation / M1-M3 maneuver confirmation (SMC_CONDITIONAL_
                        ENTRY_V2-specific) also deliberately excluded -- that's strategy-owned
                        entry interpretation, not a raw market fact.
```

## No-redetection proof

`tests/test_topdown_context_adapters_no_redetection.py` — static AST scan (same
technique as `tests/test_mtf_context_execution_guard.py`) proves
`topdown_context_adapters.py`:
- imports nothing from `session_sweep_continuation`, `strategy_engine.sweep_retest`,
  `smartmoneyconcepts`, `market_structure.smc_adapter`, `supply_demand.smc_adapter`,
  or the execution surface;
- calls no swing/BOS/CHOCH/resample/order function directly;
- imports only `daily_routine.d1_context`, `daily_routine.h1_setup`,
  `daily_routine.models`, `market_structure`, `market_structure.models`, plus stdlib
  and the local `topdown_contracts` module (positive allow-list check).

`tests/test_topdown_context_adapters.py` — dynamic proof via `unittest.mock.patch`:
`build_daily_context`/`build_h1_context`/`build_m5_context` are asserted to call
`build_d1_context`/`build_h1_setup_context`/`analyze_structure` **exactly once each**
with the expected arguments, and the returned `StructureFact`s are asserted to carry
the exact `.price`/`.time_utc` values from the mocked `StructureResult`'s own
`latest_bos`/`latest_choch` objects — proving the adapter transcribes, never
recomputes.

## Structure semantics

```
definition = SMC_MARKET_STRUCTURE_V1
SSC_semantics_changed = false
LSR_semantics_changed = false
```
Every `StructureFact` produced by any of the three adapters carries
`structure_definition_id = SMC_MARKET_STRUCTURE_V1` (asserted by test) — the same,
single definition TD-1 froze, sourced only from
`market_structure.analyze_structure()`'s own `StructureResult.latest_bos`/
`.latest_choch`. `session_sweep_continuation` and `strategy_engine.sweep_retest` are
never imported (static guard) and their own BOS/MSS semantics are untouched.

## Provenance

Every produced context carries: `context_id` (deterministic, `compute_context_id()`
over symbol/timeframe/source/bar_close_time/feature_version/parent_context_id),
`symbol`, `timeframe`, `source` (the specific existing-authority function consulted),
`bar_close_time` (the underlying `StructureResult.data_end_utc`), `feature_version`
(`TD3_CONTEXT_ADAPTER_V1` at the context level; each `StructureFact.feature_version`
carries the actual `smc_version` string from the detector that produced it —
market-data identity → existing source analysis → adapter → TD context identity is
fully traceable). `snapshot_fingerprint` is `None` throughout this WP (none of D1/H1/M5
authorities attach a `strategy_contract.market_snapshot.MarketSnapshot` — TD-2's
fingerprint mechanism is not yet wired to these orchestrators; recorded as an
"unavailable at source" gap above, not fabricated).

## Files changed

- `src/mtf_context/topdown_context_adapters.py` — **new**: `daily_context_from_d1`,
  `build_daily_context`, `h1_context_from_sources`, `build_h1_context`,
  `m5_context_from_structure`, `build_m5_context`, plus shared pure helpers
  (`_structure_facts`, `_data_quality_for_structure`).
- `src/mtf_context/__init__.py` — additive export only.
- `tests/test_topdown_context_adapters.py` — **new**, 22 tests.
- `tests/test_topdown_context_adapters_no_redetection.py` — **new**, 4 tests.
- `docs/status/TD3_EXISTING_CONTEXT_ADAPTERS_STATUS.md` — this document.

No strategy file, YAML, proposal, risk, execution, API, frontend, `topdown_contracts.py`,
`topdown_market_data.py`, `mt5/market_data.py`, or `strategy_contract/market_snapshot.py`
file was touched.

## Test results

- `tests/test_topdown_context_adapters.py` + `tests/test_topdown_context_adapters_no_redetection.py`: **22 + 4 = 26 passed.**
- Full `mtf_context`/topdown suite (`test_mtf_context.py`, `test_mtf_context_execution_guard.py`,
  `test_mtf_context_pivot_availability.py`, `test_topdown_context_contracts.py`,
  `test_topdown_market_data.py`, plus the two new TD-3 files): **80 passed, 1 skipped.**
- Live read-only smoke check (no order operation): `build_daily_context`,
  `build_h1_context`, `build_m5_context` each called for real against the connected
  Vantage Demo terminal (EURUSD) — all three returned populated contexts with real
  BOS/CHOCH facts, correct `structure_definition_id`, and closed-bar timestamps
  strictly in the past.
- Bounded strategy-adjacent regression (`large_smc`, `session_sweep_continuation`,
  `sweep_retest`, `asian`/`post_asian`, `proposal`, `market_structure`,
  `supply_demand`; `slow` and `live_mt5` excluded): **594 passed, 6 failed, 2509
  deselected**, 398.22s. All 6 failures are pre-existing and unrelated to TD-3 — see
  Pre-existing issues below.

## Pre-existing issues

**New this WP, root-caused precisely (not a TD-3 regression):** 6 tests failed —
`test_large_smc_eurusd_admission_wp2.py::test_strategy_semantics_files_unchanged_by_this_mission`,
`::test_frozen_validation_core_unchanged_by_this_mission`, and the same two tests
duplicated in `test_large_smc_eurusd_friction_campaign_wp3a1.py` and
`test_large_smc_eurusd_friction_evidence_wp3a.py`. Each asserts
`git diff e596507 -- strategies/ST_LARGE_SMC_V1.yaml ... == ""` (byte-identical to a
frozen baseline commit). Reproduced independently:
`git diff e596507 -- strategies/ST_LARGE_SMC_V1.yaml` shows exactly one unrelated
blank-line insertion under `stop_loss_contract.broker_constraints:` — a change already
present in the working tree (`git status` showed ` M strategies/ST_LARGE_SMC_V1.yaml`)
**before any TD-3 file was touched**, i.e. concurrent WIP from another process (the
active friction-campaign/SVOS work already flagged as untouched WIP at the start of
this session). No TD-1/TD-2/TD-3 change touches `strategies/ST_LARGE_SMC_V1.yaml`,
`src/large_smc_research/`, or `src/validation_framework/`. Per this mission's
working-tree-safety instruction, this file was left untouched rather than "fixed."

TD-2's three live-MT5 test failures (`test_get_candles_last_bar_matches_true_utc_now`,
`test_historical_candles_utc_range_live`, `test_data_health_ok_and_failure_live` — an
inadequate Friday-after-close weekday guard) were **not encountered or modified** in
this work package; the bounded regression above explicitly excludes `live_mt5`-marked
tests, and this WP's own live smoke check does not touch those three test files.

## Out-of-scope confirmation

```
new_market_detector_added = false
market_data_authority_changed = false
strategy_logic_changed = false
proposal_logic_changed = false
risk_logic_changed = false
validation_evidence_changed = false
holdout_accessed = false
demo_authority_changed = false
live_authority_changed = false
execution_authority_changed = false
```

## Next

TD-4 (new context builders — WeeklyContext/H4Context/M15Context) — **only after owner
review of this work package.**
