# SMC_ASSISTANT_RUNTIME_V1

Assistant-usability layer on top of the frozen `SMC_CONDITIONAL_ENTRY_V2` entry engine
(E1/E2/E3 -> H1 check -> M1/M2/M3 -> 3x3 composer, unchanged, see
`SMC_CONDITIONAL_ENTRY_V2_SPEC.md` / `SMC_CONDITIONAL_ENTRY_V2_RUNTIME_SPEC.md`). This
spec names a separate capability version deliberately (task instruction: do not rename
the entry algorithm merely because assistant capabilities were added).

## What this adds

```
src/smc_map/            SMC_MARKET_MAP_V1     -- normalized single-snapshot picture
src/surveillance/       SMC_SURVEILLANCE_V1   -- state tracking + transition events
src/proposals/          SMC_TRADE_PROPOSAL_V1 -- evidence-gated trade proposals
src/visual_explanation/ SMC_VISUAL_EXPLANATION_V1 -- portable annotation model
```

None of these are new detectors. Each wraps/normalizes output already produced by
`market_structure`, `supply_demand`, `liquidity`, and (for surveillance/proposals/visual)
`entry_confirmation`'s `SMC_CONDITIONAL_ENTRY_V2` pipeline
(`daytrading_runtime/conditional_entry_snapshot.py`). `NEW_DETECTORS_CREATED = 1`: PWH/PWL
(`supply_demand.previous_week_high_low`), the one primitive genuinely absent from the
liquidity taxonomy (see `docs/status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md` for the
full conformance matrix).

### `smc_map` -- SMC_MARKET_MAP_V1

`build_smc_market_map(symbol, timeframes=("D1","H4","H1","M15","M5"))` calls
`market_structure.analyze_structure_tiers`, `supply_demand.analyzer.{order_blocks_for,
fair_value_gaps_for}`, and `liquidity.analyzer.liquidity_result` exactly once per
timeframe, plus `supply_demand.native_zones.premium_discount_from_previous_day` once,
and stitches the results into one `SMCMarketMap` with stable evidence IDs
(`smc_map.evidence.evidence_id`) so downstream consumers can reference the SAME detected
object without re-deriving it. Fails closed per component (a fetch failure degrades that
one field to absence + a warning; `data_quality` becomes `PARTIAL`/`UNAVAILABLE`, never a
fabricated snapshot).

Deliberately does NOT feed `SMC_CONDITIONAL_ENTRY_V2`'s own E1/E2/E3/M1/M2/M3 evaluation
-- that pipeline already fetches and evaluates what it needs, independently, per its own
runtime spec, and stays untouched. `smc_map` exists for the broader "what's on the
chart" picture that pipeline does not expose wholesale.

### `surveillance` -- SMC_SURVEILLANCE_V1

`update_surveillance(analysis: SMCConditionalEntryAnalysis, store)` diffs the current
snapshot against the last-persisted state for that symbol
(`runtime_state.store.JsonKeyValueStore`, generalizing the ad hoc precedent in
`daytrading_runtime/smc_runtime.py`) and emits transition events ONLY for what changed:
`CONTEXT_QUALIFIED`, `REFERENCE_TOUCHED`, `H1_REACTION_CONFIRMED`,
`M_CONFIRMATION_DEVELOPING`, `ENTRY_READY`, `SETUP_INVALIDATED`, `SETUP_EXPIRED`. Every
event is a pure state-diff label over `EConditionResult.touch_status/reaction_status`
and `M*Result.state`/`SMCEntryCombinationResult.state` -- values SMC_CONDITIONAL_ENTRY_V2
already produces; no new detector backs any event. `compact_line()`/`detailed_report()`
give the compact-vs-detailed output split (spec token-efficiency requirement).
`poll_symbols()` fans this out over a caller-supplied symbol set (never hardcoded).

### `proposals` -- SMC_TRADE_PROPOSAL_V1

`generate_proposals(analysis)` emits one `SMCTradeProposal` per combination the composer
already marked `READY` -- nothing else. WAITING/direction-mismatch/INVALIDATED/EXPIRED
combinations never produce a proposal. Multiple simultaneous READY combinations are all
returned, unranked (no priority policy exists or is added here). `explain()` renders a
human-readable proposal strictly from fields already on the proposal -- no invented
narrative. Honest limitation, not papered over: no signed invalidation-PRICE contract
exists across M1/M2/M3 today, so `invalidation_state` reports the STATE name
(`INVALIDATED`/`EXPIRED`) rather than a fabricated price; similarly `entry_low`/
`entry_high` are only populated when the underlying M-result exposes an explicit range
(M1 always does; M2 via its entry zone; M3 exposes only a single `entry_level`, so the
proposal's range stays `None`, honestly).

### `visual_explanation` -- SMC_VISUAL_EXPLANATION_V1

`build_visual_explanation(analysis, combination)` turns one already-composed
`SMCEntryCombinationResult` into a portable, JSON-serializable `Annotation` list (BOX /
LINE / MARKER / LABEL) -- not coupled to matplotlib. Existing `chart_renderer/
renderer.py` remains the one module that touches matplotlib. Every annotation is read
off fields the frozen contracts already carry (`EConditionResult.reference_*`, M-result
`entry_array_low/high` / `entry_fvg` / `entry_ob` / `entry_level`) -- no independent
recomputation, and no detector reruns to produce it.

## Cross-layer consistency (spec section 61)

`tests/test_smc_assistant_consistency.py` proves surveillance's READY combination,
proposals' generated proposal, and visual explanation's highlighted POI/entry-array all
agree (same combination, same direction, same price bounds) when given the same
`SMCConditionalEntryAnalysis` snapshot -- because all three read the identical object,
none re-derives.

## Explicit non-goals (unchanged from the task)

No model ranking/priority, no session-strategy routing, no trade-management redesign, no
autonomous execution. `READY_FOR_LIVE_EXECUTION = NO`.
