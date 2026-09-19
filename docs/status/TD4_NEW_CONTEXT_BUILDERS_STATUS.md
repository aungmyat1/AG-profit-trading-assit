# TD-4 — New Context Builders (W1/H4/M15)

**Status:** COMPLETE. Follows TD-0 (audit), TD-1 (`07743b6e`), TD-2 (`232e901`), TD-3
(`fb6486d`), TD-3A (`1455aef`) — all four confirmed committed ancestors of HEAD before
this work began.

## What this proves

All six TopDownContext V1 timeframes (W1/D1/H4/H1/M15/M5) now have an independent
context producer. W1→WeeklyContext, H4→H4Context, M15→M15Context are built by
adaptation only, reusing the exact same existing authorities and TD-3A fact-mapping
helpers TD-3 already established for D1/H1/M5 — no new detector was written.

## Authority reuse (audited live before writing any code)

| Timeframe | `analyze_structure` | `validated_order_blocks_for` | `fair_value_gaps_for` | `liquidity_result` | `session_zone` |
|---|---|---|---|---|---|
| W1 | VALID, smc_version present, BOS+CHOCH found | 8 candidates | 40 zones | 5 levels | n/a (no weekly reference-level authority) |
| H4 | VALID, smc_version present, BOS+CHOCH found | 10 candidates | 36 zones | 7 levels | n/a (see below) |
| M15 | VALID, smc_version present, BOS+CHOCH found | 4 candidates | 46 zones | 11 levels | Asian/London/NY all queried; all `SESSION_INCOMPLETE`/`DATA_MISSING` at audit time (weekend) — correctly absent, not fabricated |

All four confirmed to already operate on native W1/H4/M15 candles with **zero code
change beyond TD-2's one-line addition of `"W1"` to `mt5/market_data.py`'s timeframe
mapping** (H4/M15 were already fully supported before TD-2). No gap requiring
semantic modification of any existing authority was found.

## Builders

| Tier | Function | Orchestration convenience |
|---|---|---|
| W1 | `weekly_context_from_structure(structure, ...)` | `build_weekly_context(symbol)` |
| H4 | `h4_context_from_structure(structure, ..., parent_daily_context_id=None)` | `build_h4_context(symbol, parent_daily_context_id=None)` |
| M15 | `m15_context_from_structure(structure, ..., parent_h1_context_id=None)` | `build_m15_context(symbol, parent_h1_context_id=None)` |

All three reuse the exact same pure fact-mapping helpers TD-3 defined
(`structure_facts_from_result`, `data_quality_for_structure`,
`zone_facts_from_validated_obs`, `imbalance_facts_from_zones`,
`liquidity_facts_from_levels`, `reference_level_fact_from_zone`) via new public
aliases added to `topdown_context_adapters.py` — the private (underscore-prefixed)
names and their existing TD-3/TD-3A tests are completely unchanged; the aliases are a
zero-behavior-change addition.

`WeeklyContext` takes no parent-id parameter at all (TD-1's frozen contract has no
`parent_*` field on it — it is the top of the hierarchy). `H4Context`/`M15Context`
expose an optional parent-id parameter that is never populated automatically —
parent-child orchestration remains TD-7's job.

## Context coverage

**W1**
```
populated = structure_facts (BOS/CHOCH), zone_facts (order blocks), imbalance_facts (FVG), liquidity_facts
unsupported = none identified -- every queried authority already supports W1 natively
empty_by_design = reference_level_facts (no existing authority produces a weekly-scoped
                  reference level -- no "previous month high/low" function exists anywhere
                  in this repository; honest absence, not a gap in this WP's mapping)
```

**H4**
```
populated = structure_facts, zone_facts, imbalance_facts, liquidity_facts
unsupported = none identified
empty_by_design = reference_level_facts (previous-day/week facts already live on DailyContext,
                  TD-3A; re-attaching the identical value to H4Context would be meaningless
                  duplication of the same fact, not a new one -- deliberate scope decision)
```

**M15**
```
populated = structure_facts, zone_facts, imbalance_facts, liquidity_facts, reference_level_facts
            (session box -- Asian/London/NY, each independently)
unsupported = none identified
empty_by_design = none -- M15 is the one new tier where session_zone()'s own native M15
                  scoping (assistant.market_data.session_snapshot() always operates on M15
                  candles) made a reference-level mapping clearly justified; at audit/live-
                  smoke time all three sessions were legitimately incomplete (weekend), so
                  reference_level_facts was observed empty in practice -- correctly absent,
                  never fabricated
```

## No-redetection proof

Same two-layer proof as TD-3/TD-3A, applied to the new file:
- **Static** (`tests/test_topdown_new_builders_no_redetection.py`): AST scan forbids
  imports from `session_sweep_continuation`, `strategy_engine.sweep_retest`,
  `post_asian_pilot`, `large_smc_research`, `smartmoneyconcepts`,
  `market_structure.smc_adapter`, `supply_demand.smc_adapter`, and the execution
  surface; forbids swing/BOS/resample/order call names; positive allow-list confirms
  only `liquidity`, `liquidity.models`, `market_structure`, `market_structure.models`,
  `supply_demand` (plus stdlib and the local relative imports) are ever imported; a
  new literal-string scan confirms no `"S1"`/`"S2"`/`"S3"`/`"MSS"` string constant
  appears anywhere in the module.
- **Dynamic** (`tests/test_topdown_new_builders.py`): `unittest.mock.patch` proves
  each of `build_weekly_context`/`build_h4_context`/`build_m15_context` calls
  `analyze_structure`/`validated_order_blocks_for`/`fair_value_gaps_for`/
  `liquidity_result` (and, for M15, `session_zone` exactly 3 times, once per
  canonical session) with the expected arguments, and that the produced facts carry
  the mocked source objects' own values verbatim.

## Semantic firewall

```
SMC_structure_definition = SMC_MARKET_STRUCTURE_V1 (unchanged, unweakened -- StructureFact's
                            own whitelist enforcement was not touched)
SSC_imported = false
LSR_imported = false
AS5R_imported = false
trade_direction_added = false
```
Every `StructureFact` produced by any of the three new builders carries
`structure_definition_id = SMC_MARKET_STRUCTURE_V1` (asserted by test). No
`candidate_direction`/`trade_direction`/`bias`/`permission` field exists on
`WeeklyContext`, `H4Context`, or `M15Context` (asserted by test against the actual
TD-1 dataclass definitions).

## Provenance

Every produced context carries: `context_id` (deterministic,
`compute_context_id()`), `symbol`, `timeframe`, `source` (the specific existing
authority — `market_structure.analyze_structure` for all three, since none has a
composed orchestrator), `bar_close_time` (the underlying
`StructureResult.data_end_utc`), context-level `feature_version`
(`TD3_CONTEXT_ADAPTER_V1`, reused verbatim from TD-3/TD-3A — same adapter-layer
version, no new constant invented), and per-fact `feature_version` (the real detector
version where one exists, e.g. `StructureFact.feature_version` = the actual
`smc_version` string). `snapshot_fingerprint` is `None` throughout (same documented
gap as TD-3: none of these authorities attach a `MarketSnapshot` yet).

## Context identity

`compute_context_id()` is unchanged from TD-1 — same symbol/timeframe/source/
bar_close_time/feature_version/parent_context_id hash inputs. Verified deterministic:
two independently-constructed `StructureResult` objects with identical field values
produce identical `H4Context.context_id` (test).

## Live smoke test (read-only, no order operation)

Ran against the connected Vantage Demo terminal (EURUSD) on 2026-09-19:

```
status = RAN
symbol = EURUSD
W1  = context generated; bar_close_time 2026-09-05 21:00 UTC (in the past); structure_definition_id=SMC_MARKET_STRUCTURE_V1 x2; zone_definition_id=AG_SMC_SUPPLY_DEMAND_V1; liquidity_definition_id=AG_LIQUIDITY_V1; 2 structure, 8 zone, 40 imbalance, 5 liquidity, 0 reference facts
H4  = context generated; bar_close_time 2026-09-18 13:00 UTC (in the past); same definition IDs valid; 2 structure, 10 zone, 36 imbalance, 7 liquidity, 0 reference facts
M15 = context generated; bar_close_time 2026-09-18 20:30 UTC (in the past); same definition IDs valid; 2 structure, 4 zone, 46 imbalance, 11 liquidity, 0 reference facts (all 3 sessions genuinely incomplete at call time -- weekend)
```

All `data_quality_status == VALID`. No order operation was performed at any point.

## Files changed

- `src/mtf_context/topdown_new_builders.py` — **new**: `weekly_context_from_structure`,
  `build_weekly_context`, `h4_context_from_structure`, `build_h4_context`,
  `m15_context_from_structure`, `build_m15_context`.
- `src/mtf_context/topdown_context_adapters.py` — extended (additive-only public
  aliases for the existing private fact-mapping helpers; zero behavior change to any
  existing function or test).
- `src/mtf_context/__init__.py` — additive export only.
- `tests/test_topdown_new_builders.py` — **new**, 22 tests.
- `tests/test_topdown_new_builders_no_redetection.py` — **new**, 5 tests.
- `docs/status/TD4_NEW_CONTEXT_BUILDERS_STATUS.md` — this document.

No strategy file, YAML, proposal, risk, execution, API, or frontend file touched.
`topdown_contracts.py`, `topdown_market_data.py`, D1/H1/M5 adapter functions in
`topdown_context_adapters.py`, `daily_routine/`, `market_structure/`,
`supply_demand/`, `liquidity/` are all unmodified (read-only inputs to this WP).

## Test results

- `tests/test_topdown_new_builders.py`: **22 passed** (new).
- `tests/test_topdown_new_builders_no_redetection.py`: **5 passed** (new).
- Full `mtf_context`/topdown suite (`test_mtf_context.py`,
  `test_mtf_context_execution_guard.py`, `test_mtf_context_pivot_availability.py`,
  `test_topdown_context_contracts.py`, `test_topdown_market_data.py`,
  `test_topdown_context_adapters.py`, `test_topdown_context_adapters_no_redetection.py`,
  `test_topdown_fact_contracts.py`, plus the two new files above): **141 passed, 1
  skipped** — confirms existing D1/H1/M5 adapters and all TD-1/2/3/3A tests remain
  green, unchanged.

## Regression results

Bounded strategy-adjacent regression (`large_smc`, `session_sweep_continuation`,
`sweep_retest`, `asian`/`post_asian`, `proposal`, `market_structure`,
`supply_demand`; `slow` and `live_mt5` excluded): **596 passed, 6 failed, 2585
deselected**, 1180.82s. All 6 failures are the exact same pre-existing
`strategies/ST_LARGE_SMC_V1.yaml` baseline-mismatch tests already recorded at the
TD-3/TD-3A freezes (same test names, same root cause — an unrelated blank-line diff
against baseline `e596507`, never touched by TD-4). No new failure was introduced by
this work package.

## Pre-existing issues (not addressed, per instruction)

- `TD_TECH_DEBT_H1_RAW_CONTEXT_EXPOSURE` — untouched; `daily_routine/h1_setup.py` not
  refactored.
- `strategies/ST_LARGE_SMC_V1.yaml` frozen-baseline mismatch — untouched.
- TD-2's Friday-after-FX-close live-test skip guard — untouched.
- Full swing-history upstream limitation (`liquidity/contract.py`'s own documented
  gap) — untouched.
- Unrelated proposal-ledger/friction-campaign/SVOS/BTC-journal WIP — untouched.

## Out-of-scope confirmation

```
new_detector_added = false
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

TD-5 (shared feature review) — **only after owner review of this work package.**
