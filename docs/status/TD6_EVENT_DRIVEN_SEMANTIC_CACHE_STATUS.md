# TD-6 — Event-Driven Semantic Cache

**Status:** COMPLETE (scoped). Prerequisite verified: `18c3f30`
("docs(mtf-context): audit shared feature semantics", TD-5) is a committed ancestor
of HEAD (`ef1189c`) — not `BLOCKED_DEPENDENCY_NOT_FROZEN`.

## What this implements

A bounded, deterministic, in-process cache for **Layer A** (raw closed-candle
requests), wired directly into production, plus a correct, fully-tested **Layer B**
(derived shared-market-fact) primitive that is **not** wired into any production
authority this pass — see "Why Layer B is not wired" below. No six-timeframe
composition, no strategy behavior change.

This document was rewritten from an earlier draft that described a larger,
more invasive integration (external raw-cache wrapper module, `analyze_structure()`
Layer-B wiring, 4-file/7-call-site Layer-A wiring). That draft was attempted, found
to break `historical_replay/data_source_patch.py`'s replay-substitution mechanism and
to introduce a real replay/fixture timestamp-collision risk for Layer B, and was
reverted in favor of the narrower, safer scope actually on disk and described here.
Nothing below claims work that isn't present in the diff.

## Cache architecture

```
raw_market_data      = IMPLEMENTED (Layer A) -- wired directly inside
                        src/mt5/market_data.py::get_latest_candles(), using
                        BoundedCache from src/shared_cache/bounded_cache.py
derived_market_facts = BUILT, NOT WIRED (Layer B) -- src/shared_cache/
                        derived_fact_cache.py is a correct, unit-proven, collision-
                        safe primitive; no production authority calls it yet
timeframe_contexts   = NOT IMPLEMENTED -- per TD-5's own OPTIONAL/LOW_PRIORITY
                        classification; no repository evidence required it
storage_policy       = bounded LRU (collections.OrderedDict), max_entries=256 per
                        cache instance, evicts least-recently-used on overflow --
                        src/shared_cache/bounded_cache.py::BoundedCache
concurrency_model    = one threading.Lock per BoundedCache instance, guarding every
                        read/write. No evidence of multi-process or multi-threaded
                        concurrent access to this runtime was found; a single
                        in-process lock is the minimum synchronization that keeps
                        this safe if a future caller adds threads. No Redis, no
                        external service, no database.
```

## RAW_CACHE_KEY
```
fields = (symbol, timeframe, count) -- the exact positional arguments of
         get_latest_candles(); "source" is not a separate field today because this
         function has exactly one data source (live MT5) and TD-8 replay works by
         monkeypatching this function's own name (see "Replay boundary" below), not
         by adding a runtime source argument. Any future second raw-data provider
         calling through this same key space would need to add source explicitly.
invalidation = data-identity-driven, NOT wall-clock TTL as sole correctness
         authority. Each entry stores valid_until = last_fetched_candle.time +
         one_timeframe_period, computed from the ACTUAL fetched data. A new bar of
         that timeframe cannot exist before that instant, so a lookup strictly
         before valid_until is provably still describing the same closed-bar state;
         a lookup at/after it is unconditionally a miss and refetches.
```

## DERIVED_CACHE_KEY
```
fields = (symbol, timeframe, closed_bar_identity, authority_definition_id,
          feature_version, parameters)
semantic_discriminators = authority_definition_id + parameters (an order-independent,
         sorted tuple of (name, value) pairs) + feature_version. closed_bar_identity
         is intended to be the REAL last-candle timestamp from a raw fetch (never
         predicted), so a real integration's freshness would be entirely inherited
         from Layer A's already-proven invalidation rule rather than a second
         staleness mechanism. This is proven at the key-builder/store level only
         (test_shared_cache_derived_fact_cache.py) -- see below for why it is not
         yet exercised through a real authority call path.
```

## AUTHORITY_IDENTITIES
No authority module was modified this pass (no new `_STRUCTURE_DEFINITION_ID` or
equivalent constant added anywhere). `derived_fact_cache.build_key()`'s
`authority_definition_id` parameter is a plain caller-supplied string; a future
integration should reuse `mtf_context/topdown_contracts.py`'s existing
`STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1` (or the equivalent for whichever
authority it wires) rather than inventing a parallel identity scheme.

## COLLISION_PROOF
```
example_1 = Collision A -- test_shared_cache_derived_fact_cache.py::
            test_collision_a_different_swing_length_never_reuses: same symbol/
            timeframe/closed_bar_identity/authority_definition_id, swing_length=5 vs
            swing_length=50 in `parameters` -- proven at the key-builder/store level
            (key_5 != key_50, no reuse of the stored value).
example_2 = Collision B -- test_shared_cache_derived_fact_cache.py::
            test_collision_b_different_authority_definition_id_never_reuses: same
            symbol/timeframe/closed_bar_identity/parameters, different
            authority_definition_id (e.g. a hypothetical SSC-derived id vs
            SMC_MARKET_STRUCTURE_V1) -- proven not to reuse. Additionally,
            test_shared_cache_no_strategy_import_guard.py statically proves (AST
            scan) that shared_cache is never imported by SSC/Sweep-Retest/
            AS5R/Large-SMC modules and never imports them back, so this collision
            class cannot occur via this cache in the wired code today, by
            construction -- because nothing strategy-specific calls into it at all.
```
Both proofs are at the cache primitive's own key/store boundary, not through an
integrated authority call path, because Layer B is not wired into one (see below).

## INTEGRATION
```
raw_cache_integration_points = mt5/market_data.py::get_latest_candles() only. This
         is the single canonical entry point every consumer in the repository
         already calls (directly, or via a per-module bound name that
         historical_replay/data_source_patch.py monkeypatches for replay) --
         caching inside it benefits every caller transparently, with zero call-site
         changes anywhere else in the repository.
derived_cache_integration_points = none. See "Why Layer B is not wired" below.
strategy_files_changed = false -- confirmed by
         tests/test_shared_cache_no_strategy_import_guard.py (static AST guard: no
         file under session_sweep_continuation/, strategy_engine/sweep_retest/,
         post_asian_pilot/, large_smc_research/ imports shared_cache, and
         shared_cache imports no strategy-specific module).
```

## Why Layer B is not wired into a production authority this pass

An earlier draft of this work wired `derived_fact_cache` into
`market_structure.analyze_structure()` directly. Two problems surfaced during that
attempt, both now guarded against:

1. **Replay-substitution break.** `historical_replay/data_source_patch.py` replays
   history by monkeypatching each consumer module's own bound name of
   `get_latest_candles` (e.g. `market_structure.analyzer.get_latest_candles`). An
   earlier, separate draft of Layer A (an external wrapper module imported under a
   new name) broke this by removing the attribute `unittest.mock.patch`/the replay
   patcher targets. Layer A was therefore moved inside `get_latest_candles()`'s own
   body (see RAW_CACHE_KEY section) specifically so that patching the function
   replaces the cache too, by construction.
   `tests/test_mt5_market_data_replay_patch_compatibility.py` proves every attribute
   `historical_replay/data_source_patch.py::_PATCHED_CANDLE_TARGETS` names is still a
   real, patchable attribute.
2. **Replay/fixture timestamp collision risk for Layer B specifically.** A
   derived-fact key keyed on `(symbol, timeframe, closed_bar_identity, ...)` is safe
   for LIVE data, where `closed_bar_identity` is a real, globally unique market
   timestamp. It is unsafe for REPLAY or hand-built test-fixture data, where two
   different, unrelated candle sets (different historical datasets, different test
   fixtures) can share the exact same timestamp — producing a silently wrong cached
   result for the second query, since `analyze_structure()` (or any authority) has no
   way to know which dataset it is really answering for. Resolving this correctly
   needs the caller to supply a replay/dataset-scoped identity component, which is
   out of TD-6's explicit scope ("Do NOT implement replay integration now").

Given both, this pass ships Layer B as a correct, independently-tested primitive
(`src/shared_cache/derived_fact_cache.py`, 10 tests) without integrating it, rather
than integrating it in a way that is either fragile (breaks replay) or unsafe
(collides across datasets). `tests/test_td6_deterministic_dedup_targets.py`'s module
docstring records this same reasoning next to the actual dedup proofs, so a future
pass finds it beside the code it constrains.

## D1_DUPLICATE_FETCH_RESULT
```
requests_before = TD-5 found repeated get_latest_candles(EURUSD,"D1",...) calls
         across one build_daily_context()-shaped call chain, including analyze_
         structure() being invoked once directly and once more internally inside
         liquidity_result() with an IDENTICAL (symbol, timeframe, count) shape --
         a literal duplicate raw request.
provider_calls_after = tests/test_td6_deterministic_dedup_targets.py::
         test_d1_analyze_structure_called_directly_and_again_inside_liquidity_
         result_dedupes_raw_fetch -- real production code path (analyze_structure +
         liquidity_result), mocked only at mt5.market_data.mt5.copy_rates_from_pos
         (the actual MT5 SDK boundary): the count=120 request appears in the
         provider-call log exactly ONCE despite being requested twice; the second,
         differently-shaped count=100 request inside liquidity_result is correctly
         NOT merged with it.
         test_d1_different_requested_counts_are_never_incorrectly_merged further
         proves previous_day_high_low(count=1) and previous_week_high_low(count=15)
         never collapse into each other's or analyze_structure's cache entry.
hits = 1 of 2 identical-shape raw requests served from cache in the deterministic
         proof (the literal duplicate); non-identical-shape requests correctly never
         merge.
```

## H1_DUPLICATE_COMPUTE_RESULT
```
Deterministic proof (test_h1_duplicate_raw_fetch_is_eliminated_even_though_compute_
is_not_yet_cached, real production code path): two back-to-back
analyze_structure("EURUSD","H1", config) calls with identical parameters --
  raw provider calls: 1 (not 2) -- Layer A hit
  smc swing/BOS computation: reruns both times -- Layer B not wired to production,
    so no compute-level dedup occurs yet (result_1 == result_2 by value, but
    result_1 is not result_2 -- proven, not glossed over)
```
This is an honest, partial result against the mission's named H1 target: TD-6
eliminates the duplicate raw I/O TD-5 quantified for H1 (and D1), but does **not**
yet eliminate the duplicate smc computation itself, because doing so safely requires
resolving the replay/fixture collision risk described above first.
`daily_routine.h1_setup.build_h1_setup_context()` itself was **not** refactored, per
instruction.

## DIAGNOSTICS
`mt5.market_data.raw_candle_cache_diagnostics()` and
`shared_cache.derived_fact_cache.cache_diagnostics()` each return
`{hits, misses, evictions, puts, size}` — plain dicts, read-only by convention,
suitable for a future TD-9 exposure. No frontend/API work done this pass; these are
only importable Python functions today.

## MEMORY_BOUND
Bounded LRU, `max_entries=256` per `BoundedCache` instance (one for the raw cache
inside `mt5/market_data.py`, one for `derived_fact_cache`). Chosen as the simplest
deterministic bounded policy for this project's realistic single-owner usage
pattern, with zero external/distributed infrastructure.
`tests/test_shared_cache_bounded_cache.py` proves LRU ordering and eviction.

## FAILURE_BEHAVIOR
A `MarketDataError` raised during the raw fetch inside `get_latest_candles()` is
never cached and propagates verbatim
(`test_data_missing_error_is_never_cached_and_propagates`,
`test_failure_then_success_recovers_normally`, both in
`tests/test_mt5_market_data_raw_cache.py`). Pre-existing guards
(`UNSUPPORTED_TIMEFRAME`/`DATA_MISSING`/etc.) are unchanged — caching only wraps
around the existing fetch, never bypasses a guard
(`test_existing_guards_still_enforced_on_a_miss`). `derived_fact_cache` itself takes
no position on what counts as a valid negative result to cache, since it is not
wired to a real authority this pass; a future integration must decide that per the
authority's own semantics (e.g. `NO_CONFIRMED_STRUCTURE_BREAK` is a legitimate,
stable "nothing found" fact for `analyze_structure()`, not a failure, and would be
reasonable to cache; `STRUCTURE_LIBRARY_ERROR`/`STRUCTURE_OUTPUT_INVALID` would not).

## Mutation isolation
`test_returned_list_mutation_does_not_corrupt_cached_entry`
(`tests/test_mt5_market_data_raw_cache.py`) proves mutating a caller's returned
candle list does not corrupt the cached entry — the cache stores its own tuple
internally and returns a fresh `list()` copy on every hit.

## Provenance
Cache reuse returns the original fetched/computed object (or a shallow list copy of
it for Layer A) unchanged — no field of a returned `Candle` or (if wired in future)
`StructureResult` is overwritten with cache-internal metadata. Cache metadata
(`hits`/`misses`/`evictions`/`puts`/`size`) lives only in the separate diagnostics
dict, never inside a returned market-data object.

## Replay boundary
No MT5-specific assumption is hard-coded into the cache primitives themselves
(`bounded_cache.py`, `derived_fact_cache.py` are provider-agnostic). Layer A's
placement inside `get_latest_candles()` (rather than an external wrapper) is
precisely what keeps TD-8's future replay substitution mechanism intact, per "Why
Layer B is not wired" above. TD-8 replay integration itself is not implemented here.

## FILES_CHANGED

**New:**
- `src/shared_cache/__init__.py`, `bounded_cache.py`, `derived_fact_cache.py`
- `tests/test_shared_cache_bounded_cache.py` (11 tests)
- `tests/test_shared_cache_derived_fact_cache.py` (10 tests)
- `tests/test_shared_cache_no_strategy_import_guard.py` (3 tests)
- `tests/test_mt5_market_data_raw_cache.py` (10 tests)
- `tests/test_mt5_market_data_replay_patch_compatibility.py` (6 tests)
- `tests/test_td6_deterministic_dedup_targets.py` (3 tests)
- `docs/status/TD6_EVENT_DRIVEN_SEMANTIC_CACHE_STATUS.md` (this file)

**Modified:**
- `src/mt5/market_data.py` — Layer A cache added directly inside
  `get_latest_candles()`'s own body (new `_RAW_CANDLE_CACHE`, `_RawCacheEntry`,
  `_is_raw_cache_entry_valid`, `clear_raw_candle_cache()`,
  `raw_candle_cache_diagnostics()`). No other function in this module touched; every
  other one of its consumers repo-wide is unaffected beyond fewer redundant I/O
  calls when request shapes are byte-identical within the same closed bar.

No strategy file, YAML, proposal, risk, execution, API, or frontend file touched.
`market_structure/analyzer.py`, `liquidity/analyzer.py`, `supply_demand/analyzer.py`,
`supply_demand/native_zones.py` are **unmodified** — they benefit from Layer A
transparently through their existing, unchanged call to `get_latest_candles()`.

## TEST_RESULTS (this session, actual run)
- New TD-6 tests: **43 passed** (11 bounded-cache + 10 derived-cache + 3 no-strategy-
  import guard + 10 raw-cache + 6 replay-patch-compatibility + 3 deterministic dedup-
  target proofs). One test
  (`test_d1_analyze_structure_called_directly_and_again_inside_liquidity_result_
  dedupes_raw_fetch`) had a mock-configuration bug on first run (raised a bare
  `Exception` where `liquidity/analyzer.py` only catches `SymbolMetaError`) — fixed
  in this session to raise `SymbolMetaError`, matching the real caught type; now
  passes.
- Directly-affected existing suites (`test_market_structure.py`,
  `test_supply_demand.py`, `test_liquidity.py`,
  `test_liquidity_session_availability.py`, `test_liquidity_hierarchy.py`,
  `test_liquidity_affinity.py`, `test_liquidity_proxies.py`,
  `test_smc_walkforward.py`): **85 passed**, zero behavior change.
- Strategy-adjacent regression (`test_structure_tiers.py`,
  `test_daytrading_pipeline_ltf_wiring.py`, `test_market_snapshot_contract.py`,
  `test_proposal_formation_gate.py`,
  `test_strategy_decision_market_snapshot_propagation.py`): **30 passed**.
- Full `mtf_context`/topdown suite (TD-1 through TD-5): **141 passed, 1 skipped** —
  unaffected by TD-6 (these tests mock `analyze_structure()` etc. at the
  `topdown_context_adapters`/`topdown_new_builders` boundary, never reaching
  `get_latest_candles()` or the cache).

## PERFORMANCE_EVIDENCE
See D1_DUPLICATE_FETCH_RESULT / H1_DUPLICATE_COMPUTE_RESULT above for the exact,
reproducible before/after provider-call counts, proven through the real integrated
code path (mocked only at the MT5 SDK boundary). No live-terminal performance claim
is made in this document; the deterministic unit-test evidence above is the only
performance claim made, and it is not extrapolated beyond what those tests show.

## PRE_EXISTING_ISSUES (not addressed, per instruction)
- `TD_TECH_DEBT_H1_RAW_CONTEXT_EXPOSURE` — untouched; `daily_routine/h1_setup.py` not
  refactored. TD-6's Layer A caching mitigates the redundant raw-I/O cost of this
  duplication (proven above) but does not close the underlying architecture debt,
  and does not yet mitigate the redundant *computation* cost (Layer B not wired).
- `strategies/ST_LARGE_SMC_V1.yaml` frozen-baseline mismatch — untouched (file shown
  modified in `git status` at session start is unrelated concurrent work, not this
  pass's change).
- TD-2's Friday-after-FX-close live-test skip guard — untouched.
- Full swing-history upstream limitation (`liquidity/contract.py`'s own documented
  gap) — untouched.
- Unrelated concurrent WIP observed in the working tree at session start (proposal
  ledger, friction-campaign artifacts, BTC journal, other agents' worktrees under
  `.claude/worktrees/`) — untouched; none of it was staged, committed, or read
  beyond what was necessary to confirm it was unrelated.

## OUT_OF_SCOPE_CONFIRMATION
```
six_timeframe_composition = false
strategy_logic_changed = false
proposal_logic_changed = false
risk_logic_changed = false
validation_evidence_changed = false
holdout_accessed = false
replay_integrated = false
api_changed = false
frontend_changed = false
demo_authority_changed = false
live_authority_changed = false
execution_authority_changed = false
```

## FINAL_STATUS = COMPLETE (scoped: Layer A wired; Layer B built, not wired)

## NEXT
Any future pass wiring Layer B into a real authority must first resolve the
replay/fixture timestamp-collision risk described above (a caller-supplied,
dataset-scoped identity component in the derived cache key). TD-7 (topdown
composition) only after owner review of this pass.
