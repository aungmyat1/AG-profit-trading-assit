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
narrative.

**Identity & lifecycle** (`proposals/identity.py`, `proposals/lifecycle.py`, added in the
operational-completion pass): `setup_id` is a pure function of `(symbol, combination,
direction)` only -- never a transient field (current tick, snapshot timestamp) -- so the
same underlying setup keeps the same identity across every poll. `proposal_id` is derived
purely from `setup_id` (one proposal tracked per active setup; entry-metadata changes are
lifecycle transitions on that same id, never a new one). `snapshot_id` names one specific
poll's observation and changes every time. `update_proposal_lifecycle(analysis, store)`
(reuses `runtime_state.store.JsonKeyValueStore`, same convention as `surveillance`) tracks
`CREATED -> STILL_VALID -> UPDATED -> INVALIDATED/EXPIRED` per setup_id, deduplicating
repeated identical polls and reporting an invalidated setup's last-known entry metadata
plus its precise invalidation evidence exactly once. `EXPIRED` is supported structurally
(mirrors whatever a composed combination reports) but this module invents no time-based
expiry rule of its own -- none exists anywhere in `entry_confirmation` (see the
Invalidation section below).

### Invalidation (`entry_confirmation/invalidation.py`, operational-completion pass)

Each M model owns distinct invalidation semantics -- never one generic rule:

- **M1** (`CHARACTER_CHANGE_WITH_INDUCEMENT`) and **M3** (`SWEEP_DROP_PUMP`) both call
  `entry_array.py::evaluate_entry_array()`, which already computed
  `structural_invalidation_candidates` = `[sweep/inducement price]` + `[entry Order
  Block's far boundary, if associated]` -- M3's own delegate (`engine_v2_1.py`) already
  applied the comparison (`current_price < min(...)` for LONG / `current_price >
  max(...)` for SHORT); M1 computed the same candidates but discarded them. Both now
  expose `invalidation_price/source_type/reason/trigger` via the SAME shared,
  already-frozen comparison (`entry_array_invalidation()`), never a second rule. Trigger
  is honestly labeled `LIVE_PRICE` (current tick, `engine_v2_1`'s existing behavior --
  not closed-candle).
- **M2** (`SUPPLY_DEMAND_SHIFT`) has no sweep/inducement concept by design. Its
  invalidation source is the NEW controlling zone (the zone whose formation IS the M2
  thesis) reusing `supply_demand.ZoneStatus.INVALIDATED` exactly as `ob_contract.py`
  already computes it (closed-candle close-beyond-boundary) -- the same convention M2
  already reused for the OLD zone's failure. Trigger is honestly labeled
  `CLOSED_CANDLE_CLOSE`.
- **Protected High/Low, CHoCH-level-as-invalidation**: considered and NOT used --
  neither is an already-computed invalidation candidate anywhere in this repo; using
  them would have been inventing a new rule (task stop condition, section 56).

Propagated verbatim (never recomputed) through `SMCEntryCombinationResult` (composer.py)
and `SMCTradeProposal` (proposals/gate.py) -- `invalidation_price`,
`invalidation_source_type`, `invalidation_reason`, `invalidation_trigger`.

### `visual_explanation` -- SMC_VISUAL_EXPLANATION_V1

`build_visual_explanation(analysis, combination)` turns one already-composed
`SMCEntryCombinationResult` into a portable, JSON-serializable `Annotation` list (BOX /
LINE / MARKER / LABEL) -- not coupled to matplotlib. Every annotation is read off fields
the frozen contracts already carry (`EConditionResult.reference_*`, M-result
`entry_array_low/high` / `entry_fvg` / `entry_ob` / `entry_level`, and now
`invalidation_price/source_type` -> an `INVALIDATION` line annotation) -- no independent
recomputation, and no detector reruns to produce it.

**Raw-evidence builders** (`visual_explanation/raw_builders.py`, operational-completion
pass): `build_structure_annotations`/`build_liquidity_annotations`/
`build_supply_demand_annotations`/`build_fvg_annotations`/`build_raw_evidence_annotations`
turn an `SMCMarketMap` (not a single combination) into the broader chart-wide picture --
every confirmed swing/BOS/CHoCH per structure tier, every liquidity level (with
TOUCH/SWEEP/RECLAIM semantic roles from its own `LiquidityStatus`), every OB/S&D zone
with lifecycle in its label, every FVG plus its 50%/CE midpoint line. Every annotation's
`source_id` resolves back through `SMCMarketMap.resolve_evidence()` -- no orphan
annotations (spec section 27). `PROTECTED_HIGH`/`PROTECTED_LOW` remain valid
`semantic_role` values in the schema but are never emitted (no detector for that
primitive exists -- see the conformance matrix; not invented to fill the slot). To
support this, `smc_map`'s own structure-evidence indexing was extended to cover every
confirmed swing/event per tier (`tier.swings`/`tier.events`), not only the latest of
each -- the one non-additive change this pass made to `smc_map`, and still purely a
wider index over already-computed objects, no new detection.

**Renderer adapter** (`chart_renderer/renderer.py::render_annotations`, additive to the
existing `render_chart()`, same module -- matplotlib stays confined to `chart_renderer`):
consumes a `visual_explanation.Annotation` list directly (BOX/LINE/MARKER/LABEL), draws
exactly what it is given, performs no SMC detection. Caller filters annotations by
`.timeframe` before calling (once per desired HTF/H1/M5 view) rather than overcrowding
one chart -- spec section 33.

## Cross-layer consistency (spec section 61)

`tests/test_smc_assistant_consistency.py` proves surveillance's READY combination,
proposals' generated proposal, and visual explanation's highlighted POI/entry-array all
agree (same combination, same direction, same price bounds) when given the same
`SMCConditionalEntryAnalysis` snapshot -- because all three read the identical object,
none re-derives.

## Explicit non-goals (unchanged from the task)

No model ranking/priority, no session-strategy routing, no trade-management redesign, no
autonomous execution. `READY_FOR_LIVE_EXECUTION = NO`.
