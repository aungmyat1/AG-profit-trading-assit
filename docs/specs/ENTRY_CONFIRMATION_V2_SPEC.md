# ENTRY_CONFIRMATION_V2 Spec — 2026-08-29

Package: `entry_confirmation/` (same package as V1). New public entry point:
`evaluate_entry_confirmation_v2()` in `engine_v2.py`. Purely additive to
`ENTRY_CONFIRMATION_V1` (`docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md`,
`docs/status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md`) — every V1 file, dataclass,
and the `evaluate_entry_confirmation()` entry point are untouched. `EntryConfirmationResult`
was not modified; V2 introduces its own `EntryConfirmationV2Result` that can optionally
embed a V1 result verbatim (`.v1`).

## Objective

Given caller-supplied HTF/liquidity/POI/gap context and an evaluation time, answer:
*which conditional-execution route is active (E1/E2/E3), has its required LTF
confirmation occurred, and what entry/invalidation geometry follows?* Never *"should I
buy or sell"*, never a lot size, never an `order_send` call.

## New modules

| File | Responsibility |
|---|---|
| `models_v2.py` | `ConfirmationRoute`, `ConfirmationModel`, `EntryMethod`, `StructuralInvalidationType`, `DirectionalContext`, `GapContext`, `InvertedGapContext`, `POIContext`, `SpreadContext`, `TypedEvent`, `RouteResult`, `EntryGeometry`, `EntryConfirmationV2Result` |
| `gap.py` | `evaluate_gap_context` (touch/fill/react on a caller-supplied `supply_demand.ZoneResult`, family=FVG), `evaluate_inverted_gap_context`, `gap_midpoint` |
| `poi.py` | `evaluate_poi_context` (OB/FVG/zone + optional `liquidity.LiquidityLevel` association) |
| `route.py` | `classify_route` (E1/E2/E3 dispatch, no invented priority), `evaluate_e1`/`evaluate_e2`/`evaluate_e3` |
| `spread.py` | `evaluate_spread_context` (A5 alert + invalidation adjustment) |
| `engine_v2.py` | `EntryConfirmationV2Request`, `evaluate_entry_confirmation_v2` |

No new module redetects structure, liquidity, OB, or FVG geometry — every function above
consumes a `market_structure.StructureAlignment` (V1), `liquidity.LiquidityLevel`, or
`supply_demand.ZoneResult` the caller already computed. `route.py::evaluate_e3` reuses
`entry_confirmation.displacement.evaluate_displacement` (`AG_ENTRY_DISPLACEMENT_V1`,
already owner-signed) for its drop/pump measurement rather than inventing a second
threshold.

## Audit performed before coding

Searched `market_structure/`, `supply_demand/`, `liquidity/` for signed definitions of:
"supply/demand shift", "last orderflow", inverted-gap identification, and an
entry-reference priority between "last pullback" and "gap". None found. Represented as:

```
SUPPLY_DEMAND_SHIFT_POLICY   = PARTIAL   (route.py::evaluate_e2)
LAST_ORDERFLOW_POLICY        = UNRESOLVED (route.py::evaluate_e2)
INVERTED_GAP_POLICY          = PARTIAL   (gap.py::evaluate_inverted_gap_context)
ENTRY_REFERENCE_SELECTION_POLICY = UNRESOLVED (route.py::evaluate_e1 — both
    LAST_PULLBACK and GAP returned as entry_candidates, no invented priority)
```

## Route classification (`ConfirmationRoute`)

`classify_route(gap_context, poi_context, poi_reacted, sweep_level)` checks each
condition independently and returns `NONE` (nothing qualifies — LTF confirmation is
never evaluated in this state, per "no LTF scan before condition"), a single route, or
`MULTIPLE` with `matching_routes` populated when more than one condition qualifies. No
route-priority rule exists anywhere in this repo, so `MULTIPLE` is never resolved to a
single route automatically.

Qualifying conditions:

- `DAILY_GAP_REACTION`: `gap_context.status == "GAP_REACTED"` (touch/fill alone does
  not qualify — see "touch vs reaction" below).
- `H1_POI_REACTION`: `poi_context.status == "POI_REACHED"` **and** caller-asserted
  `poi_reacted=True` (reaction evidence, distinct from mere proximity).
- `LIQUIDITY_SWEEP`: a caller-supplied `LiquidityLevel` with `sweep_time` set.

## Touch vs. reaction (gap.py)

`evaluate_gap_context` distinguishes `UNTOUCHED` / `GAP_TOUCHED` / `GAP_FILLED` (pure
range/close arithmetic against the zone's `low`/`high`) from `GAP_REACTED`, which
additionally requires a caller-supplied reaction candle that passes
`AG_ENTRY_DISPLACEMENT_V1` in the candidate direction. If no reaction candle is supplied
or it does not qualify, status stays at touch/fill level and `reaction_policy` stays
`"PARTIAL"` — reaction is never inferred from touch alone.

## POI never becomes an entry (poi.py)

`POIContext.status` vocabulary is `UNRESOLVED / WAITING_POI / POI_REACHED /
WAITING_CONFIRMATION / WAITING_LIQUIDITY_EVENT / INVALIDATED` — `CONFIRMED` does not
exist in this vocabulary by construction (`PRICE_AT_POI != ENTRY_CONFIRMED`, rule 14). A
`MITIGATED` zone whose associated liquidity is still `UNSWEPT`/`UNKNOWN` reports
`WAITING_LIQUIDITY_EVENT` rather than treating the mitigation as ready evidence ("filled
OB — wait for sweep").

## E1 / E2 / E3 (route.py)

Each function returns `(event_sequence: Tuple[TypedEvent, ...], entry_geometry,
confirmation_model, status)`. Every step checks causal ordering (`liquidity/gap time <=
inducement/reaction time <= character-change/displacement time`) and a zero-lookahead
guard (`_not_future`): any timestamp after the request's `evaluation_time` is treated as
not-yet-available evidence, never as confirming past evidence.

- **E1 (`evaluate_e1`)**: `D1_GAP_REACTION -> INDUCEMENT -> CHARACTER_CHANGE ->
  ENTRY_REFERENCE`. Missing inducement -> `INDETERMINATE` (never fabricated).
  Character-change event predating the gap reaction -> `NOT_CONFIRMED` (wrong-order
  evidence is rejected, not silently accepted). Confirmed case: `entry_candidates =
  (LAST_PULLBACK, GAP)`, `entry_reference = None` (policy unresolved),
  `structural_invalidation_type = CHOCH_EXTREME_SWING` from `structure_shift.event_price`.
- **E2 (`evaluate_e2`)**: `H1_POI_REACTION -> SUPPLY_DEMAND_SHIFT(PARTIAL) ->
  LAST_ORDERFLOW(UNRESOLVED) -> CURRENT_GAP/OB entry`. Never reports `CONFIRMED` — the
  undefined supply/demand-shift term caps this route at `PARTIAL`, an honest reflection
  of the audit finding, not a manufactured pass. `structural_invalidation_type =
  M5_ORDER_BLOCK_EXTREME` (OB low for LONG, OB high for SHORT) when an M5 OB zone is
  supplied.
- **E3 (`evaluate_e3`)**: `LIQUIDITY_SWEEP -> DROP_OR_PUMP -> INVERTED_GAP ->
  FIFTY_PERCENT_PULLBACK`. Sweep alone (no displacement, no gap) -> `PARTIAL`, never
  promoted to an entry (rule 32). `entry_reference = (gap_low + gap_high) / 2` exactly.
  Midpoint not yet traded -> `WAITING_ENTRY_PRICE`; traded -> `ENTRY_REFERENCE_AVAILABLE`
  / `CONFIRMED`, which is still distinct from a claimed fill (rule 51: no `FILLED` state
  exists in this contract). `structural_invalidation_type = LIQUIDITY_SWEEP_WICK` from
  `sweep_level.price`.

## Spread (spread.py)

```
BUY  alert = price - spread
SELL alert = price + spread
```

Spread is always caller-supplied (`request.spread`); no default, no hard-coded pip
value. Missing spread -> `SpreadContext(status="UNRESOLVED")`, never a zero-spread
assumption.

## `EntryConfirmationV2Result`

See `models_v2.py`. All new fields are additive; nothing in V1's `EntryConfirmationResult`
was changed. `unresolved_policies` accumulates the named policy gaps above so a caller
can see exactly which presenter concepts this pass left unresolved rather than silently
omitting them.

## Known gaps (unchanged from the audit, not resolved by this pass)

1. `SUPPLY_DEMAND_SHIFT_POLICY`, `LAST_ORDERFLOW_POLICY`, `INVERTED_GAP_POLICY`,
   `ENTRY_REFERENCE_SELECTION_POLICY` — all `UNRESOLVED`/`PARTIAL` by design; would need
   an explicit owner-signed rule to progress further.
2. `H1_POI_REACTION`'s "reaction" evidence (`poi_reacted`) is caller-asserted, not
   independently derived — no signed generic POI-reaction detector exists in this repo
   (mirrors V1's `rejection` gap: measurement primitives exist, no qualification rule).
3. Trade management (TP1/TP2/TP3) is out of scope — `TRADE_MANAGEMENT_CHANGED = NO`; see
   spec rules 53-54, 83.
