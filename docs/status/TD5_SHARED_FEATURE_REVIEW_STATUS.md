# TD-5 — Shared Feature Semantic Review

**Status:** COMPLETE (audit + classification + evidence tests only; no production code
changed). Follows TD-0 through TD-4 (`bc23dd58af2a879ddfea86ec1c3e716e1e365c28`,
confirmed committed ancestor of HEAD before this work began).

## Mission

Audit every ATR/EMA/swing/BOS-CHOCH-MSS/FVG/order-block/liquidity/session
implementation across the repository, classify each, and prepare (without
implementing) TD-6's cache-key design and the H1-duplication zero-behavior-change
proposal. **Critical rule enforced throughout: similar names do not establish
equivalent semantics; no implementation was modified to match another.**

## FEATURE_INVENTORY

### ATR

| Implementation | Consumers | Formula | Timeframe | Closed-bar/lookahead | Version identity |
|---|---|---|---|---|---|
| `session_sweep_continuation/swing_structure.py::compute_atr(candles, period=14)` | `session_sweep_continuation/stop_engine.py` | Wilder's ATR: TR=max(H-L,\|H-prevC\|,\|L-prevC\|); seed=mean(first `period` TRs); then `atr=(atr*(period-1)+tr)/period` | Caller-supplied (generic; docstring: "callers must never silently substitute a different timeframe's candles") | Trusts caller for closed/ordered candles; returns `None` if `len(candles) < period+1` (fail-closed) | none (no smc dependency; pure Python) |
| `large_smc_research/c10_stop_policy.py::compute_atr14_m5(candles, period=14)` | `large_smc_research/engine.py`, `large_smc_research/decision.py`, `validation_framework/adapters/large_smc_adapter.py` | **Byte-identical formula** to the above (verified by test, see below) | Hardcoded to M5 (`ATR_TIMEFRAME="M5"` constant; function name pins it) | Same fail-closed contract, same docstring convention | Part of `C10_STRUCTURAL_INVALIDATION_V1` (SIGNED_AND_LOCKED, `strategies/ST_LARGE_SMC_V1.yaml`) |

**Classification: STRATEGY_OWNED** (each is embedded in a strategy's own frozen
stop-loss contract — SSC's stop_engine and Large-SMC's signed C10 policy
respectively; changing either's authority would be a strategy behavior change
requiring re-freezing). **Recommended future authority:** the underlying Wilder-ATR
*formula* is a universal, non-proprietary definition — `SHARE_SAFE_WITH_ADAPTER` for
a future `indicators.atr()` pure utility, with each strategy's existing frozen
contract wrapping it unchanged (same signed parameters, zero behavior change).
Proven algorithmically identical by `tests/test_td5_shared_feature_review_evidence.py`
(new, this pass) — not merged or modified.

### EMA

| Implementation | Consumers | Formula | Timeframe | Closed-bar/lookahead | Version identity |
|---|---|---|---|---|---|
| `session_sweep_continuation/regime.py::ema(values, period)` | `classify_regime()` (same module) only | Standard EMA, `k=2/(period+1)`, seed=SMA(first `period`), then iterate; `None` if `len(values) < period` | Caller-supplied | Fail-closed, no partial estimate | none |

**Classification: STRATEGY_OWNED** — `classify_regime()`'s TREND/RANGE/TRANSITION
output is SSC-specific market interpretation, not a raw fact; no competing EMA
implementation exists anywhere else in the repository (confirmed by repo-wide grep).
**Recommended future authority:** `SHARE_SAFE_WITH_ADAPTER` for a shared
`indicators.ema()` utility (same universal-formula reasoning as ATR); SSC's own
TREND/RANGE classification remains strategy-owned regardless.

### Swing/fractal detection

| Implementation | Consumers | Algorithm | Timeframe | Version identity |
|---|---|---|---|---|
| `market_structure/smc_adapter.py::full_swings()` (wraps `smc.swing_highs_lows`) | `market_structure/analyzer.py`, `market_structure/tiers.py` | Configurable `swing_length` (library algorithm) | Any (config `swing_length: 5`) | smartmoneyconcepts library version (`smc_version`) |
| `market_structure/tiers.py` two-tier (EXTERNAL `swing_length=50`, INTERNAL `swing_length=5`) | 15 consumers incl. `large_smc_research/engine.py`, `historical_replay/*`, `daytrading_runtime/*`, bias resolvers | Same `full_swings()` engine, two parameterizations | Any | Same smc_version; INTERNAL matches `config/market_structure.yaml` exactly, EXTERNAL is tiers.py-only |
| `session_sweep_continuation/swing_structure.py::detect_fractal_swings(candles, bars_each_side=2)` | `session_sweep_continuation/{replay,stop_engine,setups}.py` | Fixed 2-bar-each-side fractal, strict inequality (a tie disqualifies), confirmation at `i+bars_each_side` (M15-hardcoded, `+15min`) | M15 only | none (no smc dependency) |

**Classification:** `market_structure/smc_adapter.py` + single-tier `analyzer.py` =
**SHARE_SAFE** (already the canonical authority behind `StructureFact`).
`market_structure/tiers.py`'s two-tier output = **SHARE_SAFE_WITH_ADAPTER** — same
underlying detector, but **not yet adapted into any TD fact contract** (TD-3/TD-4's
`StructureFact` mappings all draw from the single-tier `analyze_structure()`, never
from `tiers.py`). Flagged as an open architecture question for a future WP, not
decided here: if tiers.py's output is ever adapted, its EXTERNAL/INTERNAL facts must
carry a **distinct** `structure_definition_id` from `SMC_MARKET_STRUCTURE_V1` (e.g. a
future `SMC_MARKET_STRUCTURE_TIERED_V1`), since `swing_length=50` vs the single-tier
default produces objectively different BOS/CHOCH events on the same candles — merging
them under one id would be exactly the kind of collision the semantic firewall
exists to prevent. `session_sweep_continuation/swing_structure.py::detect_fractal_swings`
= **KEEP_SEPARATE_SEMANTICS** — a genuinely different algorithm (fixed 2-bar fractal
vs. configurable `swing_highs_lows`), never to be aliased or merged.

### BOS / CHOCH / MSS structure semantics

| Implementation | Consumers | Definition | Classification |
|---|---|---|---|
| `market_structure/smc_adapter.py` + `analyzer.py` (`latest_bos`/`latest_choch`) | `StructureFact` (TD-1/3/3A/4), `daily_routine/*`, `entry_confirmation/*` | smc-derived BOS=continuation, CHOCH=character change | **SHARE_SAFE** — `SMC_MARKET_STRUCTURE_V1`, the sole authority behind every TD `StructureFact` |
| `market_structure/tiers.py` (same detector, two swing_lengths) | see above | Same BOS/CHOCH definition, different parameterization | **SHARE_SAFE_WITH_ADAPTER** (needs its own definition id if ever adapted — see above) |
| `strategy_engine/sweep_retest/trend.py::h1_trend_direction()` | `strategy_engine/sweep_retest/engine.py`, `btc_sweep_research/pipeline.py` | Calls canonical `market_structure.structural_breaks_for_candles` directly (no reimplementation); maps latest break → `LONG_ONLY`/`SHORT_ONLY`/`NO_TRADE_DIRECTION` | Base structure lookup = **SHARE_SAFE** (already canonical); the directional-permission mapping itself = **STRATEGY_OWNED** (same category TD-3 already excluded for D1's `directional_permission`) |
| `strategy_engine/sweep_retest/mss.py::find_mss()` | `strategy_engine/sweep_retest/{retest,engine}.py` | Swing location reuses canonical `market_structure.smc_adapter.full_swings` (no reimplementation); "MSS" = a **strategy-specific confirmation gate** — the most recent opposite-type swing (located only from candles up to a liquidity sweep) must be broken by a subsequent *closed* candle's `.close` (never wick) | Swing lookup = **SHARE_SAFE** (canonical); the MSS *event* itself = **STRATEGY_OWNED** — narrower and definitionally different from BOS/CHOCH (a single swing-break-after-a-sweep gate, not a general structure-state classifier) |
| `session_sweep_continuation/swing_structure.py::detect_bos()` | SSC only | Close-only break of the most-recently-confirmed unbroken fractal swing, plus a displacement ratio (`body/range >= 0.60`) — entirely independent of smc | **KEEP_SEPARATE_SEMANTICS** |

**`SMC_MARKET_STRUCTURE_V1 != SSC structure semantics != Sweep-Retest MSS
semantics` — confirmed, unchanged, and re-verified this pass** (see
`tests/test_td5_shared_feature_review_evidence.py::
test_structure_definition_whitelist_is_the_single_member_set_the_firewall_relies_on`).

### FVG / imbalance

| Implementation | Consumers | Algorithm | Classification |
|---|---|---|---|
| `supply_demand/smc_adapter.py::fair_value_gaps()` → `supply_demand/analyzer.py::fair_value_gaps_for()` | `ImbalanceFact` (TD-3A/4), `daily_routine/d1_context.py`, `supply_demand/ob_contract.py` (matching_fvg) | smc-derived 3-candle gap | **SHARE_SAFE** (already `ImbalanceFact`'s sole authority) |
| `session_sweep_continuation/swing_structure.py::detect_fvg()` | SSC only | Hand-rolled 3-candle check (`c1.high<c3.low` bullish / `c1.low>c3.high` bearish), config-driven pip-size filter, own `eligible`/ineligible flag | **KEEP_SEPARATE_SEMANTICS** — different algorithm, different output shape (no `ZoneResult`-style status/lifecycle) |

### Order block / supply-demand

| Implementation | Consumers | Version identity | Classification |
|---|---|---|---|
| `supply_demand/smc_adapter.py::order_blocks()` → `supply_demand/ob_contract.py` (validator) | `ZoneFact` (TD-3A/4), `daily_routine/h1_setup.py` (role-filtered `poi_candidates`) | `AG_ORDER_BLOCK_V1` (frozen by owner 2026-08-26) | **SHARE_SAFE** — no competing implementation found anywhere in the repository |

### Liquidity

| Implementation | Consumers | Version identity | Classification |
|---|---|---|---|
| `liquidity/analyzer.py::liquidity_result()` | `LiquidityFact` (TD-3A/4), `daily_routine/{d1_context,h1_setup}.py` | `AG_LIQUIDITY_V1` (`liquidity/contract.py`) | **SHARE_SAFE** — no competing generic liquidity-level implementation found |

**`ST_LIQUIDITY_SWEEP_RETEST_V1`'s own "sweep" detection** (the specific module that
identifies a liquidity-sweep event for that strategy, distinct from
`liquidity.liquidity_result`'s sweep/reclaim state machine on a *level*) was **not
located and audited this pass** — the file was not in this session's read set.
Per the TD-5 acceptance gate ("any uncertainty defaults to KEEP_SEPARATE_SEMANTICS
or is explicitly reported as unresolved — do not infer equivalence"):
```
classification = KEEP_SEPARATE_SEMANTICS
confidence = INSUFFICIENT_FOR_SHARING
```
Recommend a narrow follow-up audit of this specific module before any TD-6 caching
of liquidity-adjacent facts assumes full consumer-set knowledge.

### Session / reference-range calculations

| Implementation | Consumers | Behavior | Classification |
|---|---|---|---|
| `session_clock.py` (`CANONICAL_SESSION_WINDOWS_V1`) | `supply_demand/native_zones.py`, `liquidity/analyzer.py`, and (per its own docstring) the project's single source of truth | Config-driven (`config/canonical_sessions.yaml`), fail-closed on contract conflict | **SHARE_SAFE** |
| `supply_demand/native_zones.py::session_zone()/previous_day_high_low()/previous_week_high_low()` | `ReferenceLevelFact` (TD-3A/4), `liquidity/analyzer.py`, `daily_routine/h1_setup.py` | Built on `session_clock.py` via `assistant.market_data.session_snapshot()`; closed-D1/closed-session only | **SHARE_SAFE** (already `ReferenceLevelFact`'s sole authority) |
| `session_sweep_continuation/sessions.py::SessionWindow`/`build_reference_session()`/`trade_session_candles()` | SSC only | **Does NOT call `session_clock.py` at all** — reimplements its own UTC time-of-day parsing (`_parse_utc_time`) and window-bounding (`bounds_for_date`), with its own independent `as_of`-gated no-lookahead check | **KEEP_SEPARATE_SEMANTICS**, but flagged as a genuine duplication *risk* (two independent sources of truth for session start/end hours that could silently drift if `config/canonical_sessions.yaml` changes without SSC's parser being updated in lockstep) — not fixed this pass; recommended future authority is `SHARE_SAFE_WITH_ADAPTER` (SSC adopts `session_clock.py`'s canonical bounds while keeping its own candle-slicing/no-lookahead gate) |

## RAW DATA / DERIVED FACT / STRATEGY-INTERPRETATION BOUNDARY

Explicit, per the acceptance gate's requirement to distinguish these three layers:

| Layer | Examples (this audit) | Authority |
|---|---|---|
| **Raw closed market data** | Closed OHLCV candles for a symbol/timeframe | `mt5/market_data.py::get_latest_candles()` (TD-2's sole entrypoint) |
| **Reusable derived market fact** | BOS/CHOCH event, order block, FVG, liquidity level, previous-day/week/session high-low | `StructureFact`/`ZoneFact`/`ImbalanceFact`/`LiquidityFact`/`ReferenceLevelFact` (TD-1/TD-3A), produced by `market_structure`/`supply_demand`/`liquidity`'s canonical functions over raw candles |
| **Strategy-owned interpretation** | D1 `directional_permission`, H1 `selected_poi`/`current_location`, SSC `classify_regime()`'s TREND/RANGE/TRANSITION, Sweep-Retest's LONG_ONLY/SHORT_ONLY mapping and MSS confirmation event, SSC's S1/S2/S3 (never audited here — never imported by any TD adapter) | Strategy-specific modules only; never enters a TD fact contract |

Every `SHARE_SAFE`/`SHARE_SAFE_WITH_ADAPTER` classification below sits at the middle
layer (derived fact from raw data) or is itself the raw-data layer; every
`STRATEGY_OWNED` classification sits at the third layer.

## SHARE_SAFE
`market_structure/smc_adapter.py`+`analyzer.py` (structure), `supply_demand/smc_adapter.py`+`analyzer.py` (OB, FVG), `supply_demand/ob_contract.py` (AG_ORDER_BLOCK_V1), `liquidity/analyzer.py` (AG_LIQUIDITY_V1), `session_clock.py`, `supply_demand/native_zones.py` — all already the sole authorities behind TD-1/3/3A/4's fact contracts; no change recommended or made.

## SHARE_SAFE_WITH_ADAPTER
`market_structure/tiers.py`'s two-tier BOS/CHOCH/swings (needs its own future `structure_definition_id` before ever being TD-adapted), `strategy_engine/sweep_retest/trend.py`'s base structure lookup (already calls the canonical function, just never TD-adapted), `strategy_engine/sweep_retest/mss.py`'s swing lookup (ditto), the two ATR formulas (candidate for a future shared `indicators.atr()`), the EMA formula (candidate for a future shared `indicators.ema()`), `session_sweep_continuation/sessions.py`'s session-boundary hours (candidate to adopt `session_clock.py`).

## KEEP_SEPARATE_SEMANTICS
`session_sweep_continuation/swing_structure.py` (`detect_fractal_swings`, `detect_bos`, `detect_fvg` — all three, genuinely different algorithms), `session_sweep_continuation/sessions.py`'s own window/candle-slicing implementation, `strategy_engine/sweep_retest/mss.py`'s MSS confirmation event (definitionally narrower than BOS/CHOCH).

## STRATEGY_OWNED
`session_sweep_continuation/regime.py::classify_regime()` (TREND/RANGE/TRANSITION interpretation), the two ATR call sites as currently embedded in each strategy's frozen stop-loss contract (SSC stop_engine, Large-SMC C10), `strategy_engine/sweep_retest/trend.py`'s directional-permission mapping, `strategy_engine/sweep_retest/mss.py`'s MSS event itself, `daily_routine/h1_setup.py`'s `selected_poi`/`current_location`/`directional_permission`-filtered `poi_candidates` (already excluded from TopDownContext since TD-3).

## DEPRECATED_OR_UNUSED
None identified this pass — every implementation audited has at least one live consumer.

## H1_DUPLICATION

**`TD_TECH_DEBT_H1_RAW_CONTEXT_EXPOSURE`, quantified:**

| Call | Made inside `build_h1_setup_context()`? | Made again inside `build_h1_context()` (TD-3/3A adapter)? | Duplicated? |
|---|---|---|---|
| `market_structure.analyze_structure(symbol,"H1")` | Yes (to derive `.state` only) | Yes (to recover full `StructureResult`) | **YES — duplicate call** |
| `supply_demand.validated_order_blocks_for(symbol,"H1")` | Yes (to derive role-filtered `poi_candidates`) | Yes (to recover unfiltered set) | **YES — duplicate call** |
| `supply_demand.session_zone(symbol,"asian")` | Yes (to derive `asian_session_high/low` floats) | Yes (to recover full `ZoneResult`) | **YES — duplicate call** |
| `liquidity.liquidity_result(symbol,"H1")` | Yes (stored in `evidence["liquidity"]`) | **No** — TD's adapter reads `h1_setup.evidence["liquidity"]` directly | Not duplicated (already correctly reused) |
| `supply_demand.fair_value_gaps_for(symbol,"H1")` | **No** — never called by `build_h1_setup_context()` at all | Yes | Not duplicated (net-new at H1, not wasted) |

**3 of 5 H1-tier calls the TD adapter makes are literal duplicates** of computations
`build_h1_setup_context()` already performs and discards or filters.

**Proposed future zero-behavior-change data-flow improvement (not implemented this
pass):** `H1SetupContext.evidence` is already an open `Dict[str, Any]` (no schema
break risk). `build_h1_setup_context()` could additionally store the three raw
objects it already computes and currently discards/reduces —
`evidence["structure"]` (mirroring `D1Context`'s own existing convention),
`evidence["order_blocks"]` (the full `validated_order_blocks_for()` return, before
role-filtering into `poi_candidates`), and `evidence["asian_session_zone"]` (the full
`ZoneResult`, before flattening into `asian_session_high/low` floats). No existing
field name, dataclass shape, or consumer behavior changes — every current reader of
`structure_direction`/`poi_candidates`/`asian_session_high`/`asian_session_low` sees
identical values. TD's H1 adapter would then read from `evidence` instead of
re-calling, eliminating all 3 duplicate calls. **This is a recommendation for a
future work package, not implemented in TD-5.**

## TD4_FEATURE_VERSION_REVIEW

**Classification: KEEP_COMMON_VERSION.**

TD-4's W1/H4/M15 builders do not merely resemble TD-3's D1/H1/M5 adapters — they
**literally call the same functions** (`structure_facts_from_result`,
`data_quality_for_structure`, `zone_facts_from_validated_obs`,
`imbalance_facts_from_zones`, `liquidity_facts_from_levels`,
`reference_level_fact_from_zone`, exposed as public aliases in
`topdown_context_adapters.py`, zero duplication). `TD3_CONTEXT_ADAPTER_V1` names the
**transformation/mapping-layer version** — i.e. which version of the fact-population
rules produced a context — and that rule-set is, today, byte-for-byte identical
across all six tiers. Reusing the same constant accurately reflects shared
implementation, not a coincidental naming choice.

**Trigger condition for a future split, recorded but not acted on:** if any tier's
fact-mapping logic materially diverges from the shared helpers in
`topdown_context_adapters.py` (M15's own 3-session reference-level loop is already a
tier-specific *orchestration* difference, but it still calls the identical shared
mapper function per session — this does not yet constitute a mapping-rule
divergence), split the feature version at that point, not before. No context ID or
`feature_version` was changed by this audit (no churn, per instruction).

## TD6_CACHE_KEY_RECOMMENDATION

**Which expensive calculations are safely reusable:** every raw authority call made
by the TD-3/3A/4 adapters — `market_structure.analyze_structure()`,
`supply_demand.validated_order_blocks_for()`, `supply_demand.fair_value_gaps_for()`,
`liquidity.liquidity_result()`, `supply_demand.session_zone()` — each re-fetches
candles and re-runs its underlying computation from scratch on every call (confirmed,
TD-0 finding, unchanged). All are pure functions of (symbol, timeframe, the closed
candle set as of call time, and their own config parameters) — safe to cache keyed
on exactly those inputs, invalidating naturally on the next new closed bar.

**Proposed semantic cache key:**
```
(symbol, timeframe, closed_bar_identity, authority_definition_id, feature_version, relevant_parameters)
```
- `symbol` — e.g. `"EURUSD"`.
- `timeframe` — the canonical TD timeframe string (W1/D1/H4/H1/M15/M5).
- `closed_bar_identity` — the latest closed bar's timestamp at computation time
  (`StructureResult.data_end_utc` today; a `MarketSnapshot.fingerprint` if/when TD-8
  wires one in) — uniquely identifies which candle-set version produced the result.
- `authority_definition_id` — `SMC_MARKET_STRUCTURE_V1` / `AG_SMC_SUPPLY_DEMAND_V1` /
  `AG_NATIVE_REFERENCE_ZONE_V1` / `AG_LIQUIDITY_V1` (or a future
  `SMC_MARKET_STRUCTURE_TIERED_V1` if `tiers.py` is ever adapted) — the field that
  makes the cache key semantics-aware, not just data-aware.
- `feature_version` — the adapter/mapping-layer version (`TD3_CONTEXT_ADAPTER_V1`
  today) plus, where relevant, the underlying detector's own version
  (`StructureResult.smc_version`).
- `relevant_parameters` — `swing_length` (5 vs 50 distinguishes single-tier vs.
  `tiers.py`'s EXTERNAL/INTERNAL), ATR/EMA period, `close_mitigation`,
  `join_consecutive`, warmup/count — any config-driven input that changes the raw
  authority's output for the same candle set.

**Proof (by construction, not new code) that incompatible structure semantics cannot
collide:** `authority_definition_id` is already a **mandatory, whitelisted** field on
every TD fact contract (`StructureFact.structure_definition_id`,
`ZoneFact`/`ImbalanceFact`/`ReferenceLevelFact.zone_definition_id`,
`LiquidityFact.liquidity_definition_id`), enforced in each dataclass's own
`__post_init__` since TD-1/TD-3A. A cache keyed on this same field partitions cache
space along exactly the boundary the fact contracts themselves already enforce at
construction time. SSC and Sweep-Retest never construct a `StructureFact`/`ZoneFact`/
`ImbalanceFact` at all (neither module is imported by any TD adapter — verified by
the AST no-redetection guards across TD-3/3A/4), so they cannot enter this cache
under any key, correct or not. Re-verified this pass:
`tests/test_td5_shared_feature_review_evidence.py::
test_structure_definition_whitelist_is_the_single_member_set_the_firewall_relies_on`
proves `ALLOWED_STRUCTURE_DEFINITION_IDS` is still exactly the one-member set TD-1
froze. **No TD-6 cache was implemented.**

### CACHE_LAYER_RECOMMENDATION

```
raw_market_data      = YES -- highest volume of duplicate work. A single
                        build_daily_context() call today triggers FIVE independent
                        get_latest_candles(symbol,"D1",...) fetches (one each inside
                        analyze_structure, validated_order_blocks_for,
                        fair_value_gaps_for, liquidity_result, and
                        previous_day_high_low/previous_week_high_low) for the
                        IDENTICAL symbol/timeframe/closed-bar window. Caching at this
                        layer, keyed on (symbol, timeframe, closed_bar_identity)
                        alone (no authority_definition_id needed -- raw candles carry
                        no detector semantics), eliminates the most MT5-round-trip-
                        expensive duplication with the simplest possible key.
derived_market_facts = YES -- this is where the actual CPU-expensive computation
                        lives (smc library swing/BOS/CHOCH/OB/FVG detection,
                        liquidity's sweep/reclaim state machine + equal-level
                        clustering). Caching StructureResult/ZoneQueryResult/
                        LiquidityResult/ValidatedOrderBlock-list objects, keyed on the
                        FULL proposed key (including authority_definition_id and
                        parameters), is the layer where per-symbol/timeframe
                        recomputation cost is actually avoided, not just I/O.
timeframe_contexts   = OPTIONAL / LOW PRIORITY -- WeeklyContext/DailyContext/etc. are
                        thin, cheap frozen-dataclass compositions of already-derived
                        facts (no further computation happens in the TD adapters
                        themselves, per the no-redetection rule already enforced).
                        Caching this layer saves only object-construction cost, not
                        fetch or compute cost. Still safe to cache (same key
                        discriminators apply) and becomes worthwhile once TD-7's
                        parent-child composition or multiple strategies request the
                        same tier context repeatedly within one closed bar -- but it
                        is not where TD-6's caching value is concentrated.
reasoning            = Cache at BOTH the raw-data and derived-fact layers (more than
                        one layer, per the audit requirement) because they eliminate
                        two DIFFERENT costs (network/MT5 round-trips vs. CPU
                        computation) that do not disappear if only one layer is
                        cached -- caching derived facts alone still leaves 5x
                        redundant candle fetches per D1 context build; caching raw
                        candles alone still leaves every authority re-running its own
                        smc/liquidity computation on every call. The context layer is
                        deferred as optional since it adds no cost savings beyond what
                        the derived-fact layer already provides.
```

### SEMANTIC_COLLISION_EXAMPLES

At least two concrete, repository-evidenced examples of how an underspecified cache
key could return a semantically wrong result if built naively:

**Example 1 — single-tier vs. two-tier structure detection (same detector family,
different parameter)**
```
request_A = market_structure.analyze_structure("EURUSD", "H4")
            [smc_adapter.full_swings, swing_length=5, single-tier]
request_B = market_structure.tiers.analyze_structure_tiers("EURUSD", "H4").external
            [same smc_adapter.full_swings engine, swing_length=50, EXTERNAL tier]
shared_dimensions = symbol=EURUSD, timeframe=H4, identical closed_bar_identity
                    (same latest closed H4 candle at call time)
different_semantic_dimension = swing_length parameter (5 vs 50) -- produces
                    objectively different confirmed swings and therefore different
                    BOS/CHOCH events on the SAME candle set
unsafe_collision = a cache keyed only on (symbol, timeframe, closed_bar_identity),
                    with no `relevant_parameters`/authority discriminator, could
                    return request_A's swing_length=5 result to a caller that asked
                    for request_B's swing_length=50 tiered result (or vice versa) --
                    a silent substitution of one structure definition for another,
                    exactly the class of error the semantic firewall exists to
                    prevent
required_discriminator = swing_length (a `relevant_parameter`) AND, per this audit's
                    recommendation, a distinct `authority_definition_id` if
                    tiers.py's output is ever TD-adapted (e.g. a future
                    SMC_MARKET_STRUCTURE_TIERED_V1, never SMC_MARKET_STRUCTURE_V1)
```

**Example 2 — canonical SMC BOS vs. SSC's independent hand-rolled BOS (different
detector families entirely)**
```
request_A = market_structure.analyze_structure("EURUSD", "M15")
            -> StructureFact.structure_definition_id = SMC_MARKET_STRUCTURE_V1
            (smc.bos_choch-derived: swing_highs_lows + library BOS/CHOCH rule)
request_B = session_sweep_continuation.swing_structure.detect_bos(...) on the
            identical M15 candle window -- SSC's own fixed 2-bar fractal swing +
            close-only break + displacement-ratio (body/range >= 0.60) rule
shared_dimensions = symbol=EURUSD, timeframe=M15, identical closed-bar window
different_semantic_dimension = the detector algorithm/definition itself -- these two
                    can and do disagree on whether, where, and when a BOS occurred on
                    the exact same candles (different swing-confirmation timing,
                    different break rule: wick-permitting library rule vs. SSC's
                    close-only + displacement gate)
unsafe_collision = a cache keyed only on (symbol, timeframe, closed_bar_identity)
                    with no authority_definition_id would let a lookup intended for
                    one detector silently return the other detector's BOS
                    price/time/direction -- e.g. SSC's own stop_engine (which expects
                    ITS OWN BOS semantics) receiving the canonical SMC BOS instead,
                    or a TD StructureFact consumer receiving SSC's BOS mislabeled as
                    SMC_MARKET_STRUCTURE_V1
required_discriminator = authority_definition_id (SMC_MARKET_STRUCTURE_V1 is exactly
                    the field that prevents this). NOTE: in this repository's ACTUAL
                    TD adapters this specific collision is already structurally
                    prevented today -- SSC's module is never imported by any TD
                    adapter (verified by the AST no-redetection guards across
                    TD-3/3A/4) and therefore never constructs a StructureFact at all.
                    This example illustrates why the discriminator is a REQUIRED
                    cache-key field going forward, not a claim that the collision has
                    ever actually occurred.

## NOTES on this audit's own process

A research subagent's report (used to gather file:line detail for
`session_sweep_continuation`/`strategy_engine.sweep_retest`/`large_smc_research`
files this session had not yet read) contained one false claim — that
`mtf_context/topdown_contracts.py` imports `session_sweep_continuation.swing_structure`.
This was independently verified and disproven before inclusion in this report: the
match was a grep hit on a *prose mention* of the filename inside
`topdown_contracts.py`'s own docstring (explaining why that module is excluded), not
an actual import. `topdown_contracts.py` has zero imports beyond `.models` and
stdlib. Flagging this here for transparency, not because it changed any conclusion.

## FILES_CHANGED

- `tests/test_td5_shared_feature_review_evidence.py` — **new**, 3 tests (test-only;
  no production code touched).
- `docs/status/TD5_SHARED_FEATURE_REVIEW_STATUS.md` — this document.

No source file under `market_structure/`, `supply_demand/`, `liquidity/`,
`session_sweep_continuation/`, `strategy_engine/`, `large_smc_research/`,
`daily_routine/`, or `mtf_context/` was modified. No strategy YAML, proposal, risk,
execution, API, or frontend file touched.

## TEST_RESULTS

- `tests/test_td5_shared_feature_review_evidence.py`: **3 passed** (new).
- Full `mtf_context`/topdown suite (`test_mtf_context.py`,
  `test_mtf_context_execution_guard.py`, `test_mtf_context_pivot_availability.py`,
  `test_topdown_context_contracts.py`, `test_topdown_market_data.py`,
  `test_topdown_context_adapters.py`, `test_topdown_context_adapters_no_redetection.py`,
  `test_topdown_fact_contracts.py`, `test_topdown_new_builders.py`,
  `test_topdown_new_builders_no_redetection.py`, plus the new file above): **144
  passed, 1 skipped** — no regression from TD-1 through TD-4.
- Bounded strategy-adjacent regression: **not run**, per instruction ("only run the
  long strategy regression if production code changes") — this WP made no
  production-code change.

## OUT_OF_SCOPE_CONFIRMATION

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
No refactoring was performed. No implementation was modified to resemble another.
`SMC_MARKET_STRUCTURE_V1`, SSC's structure semantics, and Sweep-Retest's MSS
semantics remain three distinct, unmerged definitions.

## FINAL_STATUS = COMPLETE

## NEXT = TD-6_EVENT_DRIVEN_CACHE only after owner review.
