# TD-3A — Top-Down Fact Contract Gap Audit

**Status:** COMPLETE. Follows TD-0 (audit), TD-1 (contract freeze,
`07743b6e4fd8bc5f01cb73a90bfc902ebadcb9cb`), TD-2 (data foundation, uncommitted), TD-3
(existing-context adapters, `fb6486d34601b7e5b905ec82757f456eebe4d379`).

## Mission

TD-3 proved existing D1/H1/M5 authorities expose reusable market facts (liquidity,
order blocks, FVGs, reference levels) that TD-1's original contract had no field to
carry. TD-3A audits that gap precisely and implements the minimum additive contract
amendment directly justified by evidence, plus the adapter mapping to populate it.
**No W1/H4/M15 analytical builders were implemented.**

## Fact inventory

| Fact | Producing authority | Timeframe support | Semantic definition | Version/provenance | Representable in TD-1 (before)? | Current consumers | Classification |
|---|---|---|---|---|---|---|---|
| BOS/CHOCH structural event | `market_structure.analyze_structure()` → `StructureResult.latest_bos/.latest_choch` | any (D1/H1/M5 used so far) | smartmoneyconcepts-derived, via `market_structure/smc_adapter.py` | `StructureResult.smc_version` (real per-call library version) | YES (`StructureFact`, TD-1) | `daily_routine.d1_context`/`h1_setup`, `liquidity.analyzer`, `entry_confirmation` | **SHARED_MARKET_FACT** (already contracted) |
| Liquidity level (buy/sell-side resting liquidity) | `liquidity.liquidity_result()` → `LiquidityLevel` | any | `AG_LIQUIDITY_V1` (`liquidity/contract.py`) — structural/session/PDH-PDL/PWH-PWL/equal-highs-lows sources, sweep/reclaim state machine | `liquidity/contract.py::CONTRACT_VERSION = "AG_LIQUIDITY_V1"` | NO | `daily_routine.d1_context`/`h1_setup` (evidence dict only), advisory skills | **SHARED_MARKET_FACT** → new `LiquidityFact` |
| Fair value gap (FVG) | `supply_demand.fair_value_gaps_for()` → `ZoneResult` (family=FVG) | any | smartmoneyconcepts-derived, via `supply_demand/smc_adapter.py` | no per-call version field exists at the source (unlike `StructureResult.smc_version`) | NO | `daily_routine.d1_context` (`gap_liquidity`), `supply_demand.ob_contract` (matching_fvg) | **SHARED_MARKET_FACT** → new `ImbalanceFact` |
| Order block (validated) | `supply_demand.validated_order_blocks_for()` → `ValidatedOrderBlock` | any | `AG_ORDER_BLOCK_V1` (frozen by owner 2026-08-26, `supply_demand/ob_contract.py`) — PIVOT_OB/SHADOW_OB geometry, required matching BOS/CHOCH, required same-direction FVG, mitigation/invalidation lifecycle | `AG_ORDER_BLOCK_V1` (named, frozen contract — reused verbatim) | NO | `daily_routine.h1_setup` (role-filtered into `poi_candidates`) | **SHARED_MARKET_FACT** → new `ZoneFact` (unfiltered) |
| Previous-day high/low | `supply_demand.previous_day_high_low()` → `ZoneResult` (family=PREVIOUS_DAY) | D1-candle-derived, timeframe-independent | native (no smc), closed-D1-candle only | no library version (native Python); source string is the provenance | NO | `liquidity.analyzer` (PDH/PDL levels) | **SHARED_MARKET_FACT** → new `ReferenceLevelFact` |
| Previous-week high/low | `supply_demand.previous_week_high_low()` → `ZoneResult` (family=PREVIOUS_WEEK) | D1-candle-derived | native, excludes in-progress ISO week | same as above | NO | `liquidity.analyzer` (PWH/PWL levels) | **SHARED_MARKET_FACT** → new `ReferenceLevelFact` |
| Session box (Asian/London/NY) | `supply_demand.session_zone()` → `ZoneResult` (family=SESSION) | session-window-derived | native, `config/canonical_sessions.yaml`-driven, only reports once a session is fully closed | same as above | PARTIAL (H1SetupContext exposes plain floats, no provenance) | `daily_routine.h1_setup` (`asian_session_high/low`, floats only), `liquidity.analyzer` | **SHARED_MARKET_FACT** → new `ReferenceLevelFact` |
| Dealing-range premium/discount classification | `supply_demand.native_zones.dealing_range_zones()` / `premium_discount_from_*()` | any | Pure calc from an explicit low/high; `current_zone` depends on a LIVE tick read at call time | n/a | NO | none in D1/H1/M5 pipelines audited | **NOT_NEEDED_V1** (live-tick current-price classification, not a closed-bar fact; deferred, not rejected as unsafe) |
| H1 selected POI / current_location / alert_zone | `daily_routine.h1_setup.build_h1_setup_context()` | H1 | Driven by D1's `directional_permission` (role-filtered order block + recency tie-break) | n/a | NO (by design, TD-3) | `daily_routine.h1_setup` only | **STRATEGY_INTERPRETATION** — excluded (unchanged from TD-3) |
| D1 directional_permission | `daily_routine.d1_context.build_d1_context()` | D1 | `LONG_ONLY`/`SHORT_ONLY`/`INDETERMINATE` derived from `StructureResult.state` | n/a | NO | `daily_routine.h1_setup` (role filter input) | **STRATEGY_INTERPRETATION** — excluded |
| SSC hand-rolled BOS | `session_sweep_continuation/swing_structure.py::detect_bos()` | M15 (that strategy's own) | Independent, hand-rolled, close-only, no CHOCH concept | n/a | N/A — never imported here | SSC only | **CONFLICTING_SEMANTICS** with `SMC_MARKET_STRUCTURE_V1` — never mapped, firewall enforced (test) |
| Sweep-Retest MSS | `strategy_engine/sweep_retest/mss.py::find_mss()` | strategy-specific | "Market Structure Shift" confirmation layered after a liquidity sweep | n/a | N/A — never imported here | Sweep-Retest only | **CONFLICTING_SEMANTICS** — never mapped, firewall enforced (test) |
| SSC S1/S2/S3 classification, campaign state, entry scoring | SSC-specific modules | SSC-specific | Strategy setup qualification | n/a | N/A — never imported here | SSC only | **STRATEGY_INTERPRETATION** — never referenced in this codebase's adapters |
| Asian-Sweep-5R qualified setup / trade direction / 5R target | `post_asian_pilot`/session-trading modules | strategy-specific | Strategy decision | n/a | N/A — never imported here | AS5R only | **STRATEGY_INTERPRETATION** — never referenced |
| Large-SMC final setup qualification / execution eligibility | `large_smc_research/decision.py` | strategy-specific | Strategy decision | n/a | N/A — never imported here | Large-SMC only | **STRATEGY_INTERPRETATION** — never referenced |

## Shared facts approved

`LiquidityFact`, `ZoneFact` (order blocks), `ImbalanceFact` (FVG), `ReferenceLevelFact`
(previous-day/previous-week/session) — all classified `SHARED_MARKET_FACT` and
implemented this pass, each with its own mandatory, whitelisted `*_definition_id`:

```
ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1  = "AG_SMC_SUPPLY_DEMAND_V1"    (order blocks + FVG)
ZONE_DEFINITION_NATIVE_REFERENCE_V1   = "AG_NATIVE_REFERENCE_ZONE_V1" (session/prev-day/prev-week)
LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1  = "AG_LIQUIDITY_V1"             (reused verbatim from liquidity/contract.py)
```

`ZoneFact.feature_version` for order blocks specifically reuses the existing, real,
owner-frozen contract name `"AG_ORDER_BLOCK_V1"` (from `supply_demand/ob_contract.py`)
rather than the coarser zone-definition constant, since that IS a genuinely versioned
per-instance contract at the source. FVG/reference facts have no such finer version
at the source, so they fall back to their own `zone_definition_id` value.

Order blocks and FVGs share one `zone_definition_id` (both produced by
`supply_demand/smc_adapter.py`'s smartmoneyconcepts wrapper) but remain **separate
fact types** (`ZoneFact` vs `ImbalanceFact`) — order blocks carry a real
validation/lifecycle state (`validation_status`, `structure_confirmation_time`) that
FVGs do not, so forcing them into one object would have hidden that distinction.

## Rejected or deferred facts

```
fact = dealing-range premium/discount current_zone classification
reason = depends on a LIVE tick read at the moment of calculation (dealing_range_zones()'s
         current_price/current_zone), not solely closed-bar history -- a genuinely different
         determinism profile than every other fact in this contract. Deferred, not rejected as
         unsafe: could be revisited as its own fact type with an explicit "observed_at" caveat,
         same as LiquidityFact's SWEPT status caveat below, if a future WP needs it.
classification = NOT_NEEDED_V1
```
```
fact = full swing history (all swings, not just latest per StructureResult)
reason = TD-0/liquidity's own LIQUIDITY_CONTRACT_GAPS already documents this as PARTIAL/
         unresolved at the SOURCE (liquidity/contract.py) -- not something this WP's contract
         can fix without the underlying authority itself being extended first.
classification = NOT_NEEDED_V1 (tracked upstream, not a TD-3A gap)
```

## Contract amendments

```
new_types = ImbalanceFact, ZoneFact, ReferenceLevelFact, LiquidityFact  (src/mtf_context/topdown_contracts.py)
extended_contexts = WeeklyContext, DailyContext, H4Context, H1Context, M15Context, M5Context
                     -- each gained 4 new OPTIONAL tuple fields (liquidity_facts, zone_facts,
                     imbalance_facts, reference_level_facts), all defaulting to () (sparse valid)
existing_types_changed = NONE -- StructureFact, structure_definition_id, TimeframeRequirement,
                     TopDownContext, compute_context_id() are byte-for-byte unchanged in shape;
                     only new fields/types were ADDED, never renamed/removed/reinterpreted
```
All 33 pre-existing TD-1 contract tests pass unchanged against the amended module.

## Adapter amendments

```
D1 = daily_context_from_d1()/build_daily_context() now also map:
     imbalance_facts <- D1Context.gap_liquidity (already a field, ZERO extra I/O)
     liquidity_facts <- D1Context.evidence["liquidity"].levels (already present, ZERO extra I/O)
     reference_level_facts <- previous_day_high_low()/previous_week_high_low() (2 NEW calls;
        no D1 orchestrator exposes these at all, same "no orchestrator -> call the raw
        authority directly" rule already used for M5 structure in TD-3)

H1 = h1_context_from_sources()/build_h1_context() now also map:
     liquidity_facts <- H1SetupContext.evidence["liquidity"].levels (already present, ZERO extra I/O)
     zone_facts <- a FRESH, UNFILTERED validated_order_blocks_for(symbol,"H1") call (1 NEW call;
        deliberately NOT h1_setup.poi_candidates, which is role-filtered by D1's directional_permission
        -- see semantic firewall)
     imbalance_facts <- a FRESH fair_value_gaps_for(symbol,"H1") call (1 NEW call; H1SetupContext
        never calls this at all)
     reference_level_facts <- a FRESH session_zone(symbol,"asian") call (1 NEW call; recovers full
        ZoneResult provenance H1SetupContext's own asian_session_high/low floats discard)

M5 = m5_context_from_structure()/build_m5_context() now also map:
     zone_facts <- validated_order_blocks_for(symbol,"M5"), imbalance_facts <- fair_value_gaps_for(symbol,"M5"),
     liquidity_facts <- liquidity_result(symbol,"M5") -- all 3 NEW calls, but consistent with the
     already-established M5 rule: no M5 orchestrator exists anywhere in this repo, so the raw
     existing authority functions ARE the M5 authority (same reasoning already applied to M5
     structure in TD-3)
```
Every mapping is a pure helper (`_imbalance_facts_from_zones`, `_zone_facts_from_validated_obs`,
`_reference_level_fact_from_zone`, `_liquidity_facts_from_levels`) that silently **skips** (never
fabricates) a source instance missing a mandatory field (low/high/origin_time) — proven by test.

## Semantic firewall

```
SSC_semantics_changed = false
LSR_semantics_changed = false
AS5R_semantics_changed = false
Large_SMC_strategy_logic_changed = false
```
`session_sweep_continuation`, `strategy_engine.sweep_retest`, and every strategy-specific
module named in the mission (SSC S1/S2/S3, AS5R qualification, Large-SMC decision) are
never imported by `topdown_context_adapters.py` (static AST allow-list test, extended
this pass to also permit `liquidity`/`liquidity.models`/`supply_demand`) or referenced
by literal string (new test scans for `"S1"`/`"S2"`/`"S3"`/`"MSS"`/`"SSC"` as AST string
constants — none found).

## No-redetection proof

Same two-layer proof as TD-3, extended to cover the new mappings:
- **Static**: `tests/test_topdown_context_adapters_no_redetection.py`'s AST scan
  (forbidden-import list unchanged; positive allow-list extended to include
  `liquidity`, `liquidity.models`, `supply_demand` — all pre-existing, already-audited
  canonical authorities, never a new detector).
- **Dynamic**: `unittest.mock.patch` on `build_d1_context`, `previous_day_high_low`,
  `previous_week_high_low` (D1); `build_d1_context`, `build_h1_setup_context`,
  `analyze_structure`, `validated_order_blocks_for`, `fair_value_gaps_for`,
  `session_zone` (H1); `analyze_structure`, `validated_order_blocks_for`,
  `fair_value_gaps_for`, `liquidity_result` (M5) — every orchestration wrapper is
  proven to call each existing authority **exactly once** with the expected
  arguments. (This also caught and fixed a real gap during this WP: the first draft
  of these tests only mocked the pre-existing TD-3 calls, so the new TD-3A calls were
  silently hitting the live terminal in this dev environment — now every call in every
  orchestration wrapper is mocked.)

## H1 duplicate structure call

```
status = unchanged from TD-3
action = DEFERRED
reason = Per this mission's explicit instruction, build_h1_setup_context() is not
         refactored. TD-3A's H1 adapter now makes THREE additional direct calls
         (validated_order_blocks_for, fair_value_gaps_for, session_zone) beyond the
         one TD-3 already added (analyze_structure) -- all for the same reason (the
         existing H1 orchestrator computes or could compute these internally but
         either discards the full object or role-filters it). This is now a slightly
         larger version of the same recorded technical debt, not a new one -- a
         single future refactor of build_h1_setup_context() to expose its own
         already-computed raw objects would let TD_H1_DUPLICATE_STRUCTURE_CALL and
         this pass's three new duplicate calls all be resolved together. Not done
         here per explicit instruction to avoid turning this into a runtime refactor.
```

## Files changed

- `src/mtf_context/topdown_contracts.py` — extended (new fact types + 4 new optional
  fields per tier context; nothing existing removed/renamed).
- `src/mtf_context/topdown_context_adapters.py` — extended (new pure mapping helpers +
  new calls in each `build_*` orchestration wrapper).
- `src/mtf_context/__init__.py` — additive export only.
- `tests/test_topdown_context_adapters.py` — extended: fixed 3 orchestration-wrapper
  tests that had become silently live-dependent, added 11 new TD-3A mapping tests.
- `tests/test_topdown_context_adapters_no_redetection.py` — extended allow-list only.
- `tests/test_topdown_fact_contracts.py` — **new**, 23 tests.
- `docs/status/TD3A_TOPDOWN_FACT_CONTRACT_GAP_AUDIT_STATUS.md` — this document.

No strategy file, YAML, proposal, risk, execution, API, or frontend file touched.
`market_structure/`, `supply_demand/`, `liquidity/`, `daily_routine/` source modules
are all read-only inputs to this WP — none were modified.

## Test results

- `tests/test_topdown_fact_contracts.py`: **23 passed** (new).
- `tests/test_topdown_context_adapters.py`: **29 passed** (18 pre-existing + 11 new
  TD-3A mapping tests; 3 pre-existing tests fixed to stop depending on live MT5).
- `tests/test_topdown_context_adapters_no_redetection.py`: **4 passed** (allow-list
  extended).
- Full `mtf_context`/topdown suite (`test_mtf_context.py`,
  `test_mtf_context_execution_guard.py`, `test_mtf_context_pivot_availability.py`,
  `test_topdown_context_contracts.py`, `test_topdown_market_data.py`, plus the three
  files above): **114 passed, 1 skipped.**
- Live read-only smoke check (no order operation): `build_daily_context`,
  `build_h1_context`, `build_m5_context` all called for real against the connected
  Vantage Demo terminal (EURUSD) — populated `LiquidityFact`/`ZoneFact`/
  `ImbalanceFact`/`ReferenceLevelFact` instances observed with correct
  `*_definition_id`s and closed-bar-derived provenance (H1's `reference_level_facts`
  was legitimately empty at call time because the Asian session box had not yet fully
  closed — absence is valid, never fabricated, per the existing `session_zone()`
  contract this adapter inherits).

## Regression results

Bounded strategy-adjacent regression (`large_smc`, `session_sweep_continuation`,
`sweep_retest`, `asian`/`post_asian`, `proposal`, `market_structure`, `supply_demand`;
`slow` and `live_mt5` excluded): **596 passed, 6 failed, 2548 deselected**, 398.05s.
All 6 failures are the exact same pre-existing `strategies/ST_LARGE_SMC_V1.yaml`
baseline-mismatch tests already recorded in the TD-3 freeze
(`test_large_smc_eurusd_admission_wp2.py`, `test_large_smc_eurusd_friction_campaign_wp3a1.py`,
`test_large_smc_eurusd_friction_evidence_wp3a.py`, 2 tests each) — same test names,
same root cause (an unrelated blank-line diff against baseline `e596507`, never
touched by TD-3A). No new failure was introduced by this work package.

## Unrelated WIP

Inspected before and after this work package: `state/proposal_ledger/proposal_ledger.json`
(modified), `strategies/ST_LARGE_SMC_V1.yaml` (modified, pre-existing baseline
mismatch), Large-SMC friction-campaign session artifacts (untracked), `src/svos/`
(untracked, not observed this session but previously noted), and a newly-observed
`journal/reports/btc/2026/2026-09-18.json` (untracked, concurrent-agent WIP). None
touched, staged, or modified by this work package.

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

TD-4 (new context builders — WeeklyContext/H4Context/M15Context) — **only after owner
review of this work package.**
