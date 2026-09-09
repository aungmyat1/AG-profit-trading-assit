# Market Swing Structure Skill — Architecture

`market-swing-structure-analysis` (skill) / `src/market_swing_structure/` (runtime) is an
**advisory analytical composition layer**, not a new market-structure engine.

```
Market Structure Engine (src/market_structure/)
        |
Liquidity Engine (src/liquidity/) / Supply-Demand Engine (src/supply_demand/)
        |
Multi-Timeframe Context (src/mtf_context/)   <-- existing, unchanged, not duplicated
        |
Market Swing Structure Skill (src/market_swing_structure/)
        |
normalized MARKET_SWING_STRUCTURE_V1 snapshot
        |
Strategy-specific Bias (e.g. SESSION_BIAS_V1)
        |
Strategy setup (Session Strategy / Large-SMC)
```

## Why this exists alongside `multi-timeframe-market-context`

`multi-timeframe-market-context` already orchestrates structure/liquidity/zones across a
caller-defined **role profile** (MACRO/BIAS/WORKING/SETUP/EXECUTION/MANAGEMENT) and
returns one `MTFContext` per role. `market-swing-structure-analysis` is a narrower,
swing-focused composition on top of the *same* underlying engines, adding exactly two
things neither `market_structure` nor `mtf_context` expose today:

1. **Explicit swing confirmation timestamps.** `market_structure.StructurePoint.time_utc`
   for a SWING_HIGH/SWING_LOW is the pivot bar's own time, not when the pivot became
   knowable. `market_swing_structure.confirmation` derives `confirmed_time_utc` (pivot
   time + `swing_length` bars of that timeframe's duration) so a consumer can assert
   `confirmed_time_utc <= as_of` before treating a swing as usable history — a concrete,
   testable no-lookahead guard rather than an implicit engine property.
2. **An explicit active dealing range keyed to a named swing pair.** Premium/equilibrium/
   discount arithmetic already exists (`supply_demand.native_zones.dealing_range_zones`),
   but nothing previously picked the canonical *structure* engine's own latest confirmed
   swing high/low as the range boundary and named that choice; this skill does exactly
   that (`market_swing_structure.dealing_range`), failing closed to `null` when the pair
   is missing or degenerate.

Both additions are pure derivations over already-computed engine output — neither
introduces a new swing/BOS/CHoCH/FVG detector, and neither can disagree with the engine
it reads from (see `tests/test_market_swing_structure.py`'s conflict tests).

## Reused, never reimplemented

| Concept | Authority | Reused as |
|---|---|---|
| Swing highs/lows, BOS/CHoCH, structure_state | `market_structure.analyze_structure()` | relayed verbatim per timeframe |
| EQH/EQL, PDH/PDL, session levels, sweep status | `liquidity.liquidity_result()` | `liquidity_context` |
| FVG detection + mitigation state | `supply_demand.fair_value_gaps_for()` | `imbalance_context` |
| Premium/equilibrium/discount arithmetic | `supply_demand.native_zones.dealing_range_zones()` | `active_dealing_range` |

## Advisory boundary

`authority: ADVISORY_CONTEXT_ONLY` on every returned snapshot. This layer cannot modify
strategy configuration, lifecycle state, risk, or execution, and it creates no trade
signal or bias decision — see `src/market_swing_structure/__init__.py`'s module
docstring and the authority-boundary tests in `tests/test_market_swing_structure.py`.
`mtf_alignment` is a structural-agreement LABEL (`ALIGNED_*` / `HTF_*_LTF_TRANSITION` /
`HTF_*_LTF_CONFLICT` / `UNKNOWN`), never a BULLISH/BEARISH/NEUTRAL bias — a dedicated
bias module (e.g. `SESSION_BIAS_V1`) owns that decision downstream.
