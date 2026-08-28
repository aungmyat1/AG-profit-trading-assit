---
name: supply-demand-analysis
description: Identify supply/demand zones, order blocks, FVGs, session highs/lows, and premium/discount context on a chart. Use when asked to map important price zones, find demand/supply areas, ask about order blocks, or explain where price sits relative to a session box or dealing range. Advisory only — does not decide trades.
---

# Supply & Demand Analysis

Second layer of the AG Profit Trading assistant pyramid, built on top of
`market-structure-analysis`. Identifies the price zones that matter once structure is known.

## Scope

Deterministic, project-owned — see `supply_demand/` (Phase 3, implemented 2026-08-26;
Order Block contract refined 2026-08-26). Request analysis via `supply_demand`'s public
functions rather than eyeballing raw candles: `order_blocks_for()`, `fair_value_gaps_for()`,
`validated_order_blocks_for()`, `session_zone()`, `previous_day_high_low()`,
`dealing_range_zones()` / `premium_discount_from_previous_day()` / `premium_discount_from_session()`.

## Rendering

`chart_renderer.render_chart(candles, zones=result.zones, out_path=...)` draws each
`ZoneResult` as a rectangle (`origin_time` to the chart's right edge — `ZoneResult` has
no separate "current extension" timestamp, so this is the documented default; color by
role, opacity by status) — it never recomputes zone boundaries itself.

## SMC_CANDIDATE_OB vs. AG_VALID_ORDER_BLOCK — critical distinction

`smartmoneyconcepts.smc.ob()` produces **candidates only** (`SMC_CANDIDATE_OB`).
`order_blocks_for()` returns these unchanged, as `ZoneResult` objects
(`family=ORDER_BLOCK`, `role` SUPPLY/DEMAND, `status` FRESH/MITIGATED — smc's own
mitigation rule). A raw candidate is **never** the owner's Order Block model on its own
and must never be reported as "a valid order block."

**AG_ORDER_BLOCK_V1** (frozen by the owner 2026-08-26, `supply_demand/ob_contract.py`)
is the actual authority. `validated_order_blocks_for()` runs each smc candidate through
it and returns a `ValidatedOrderBlock` (`AG_VALID_ORDER_BLOCK` when `status == VALID`)
with:

- `family`: `PIVOT_OB` (zone = full candle high/low) or `SHADOW_OB` (zone = wick tip to
  body edge) — split by the origin candle's body-to-range ratio (≥0.5 → PIVOT, <0.5 →
  SHADOW; documented in `ob_contract.py` as an interpretation of the owner's wording, not
  a frozen number). `FLIP_OB` is a frozen family (zone = full candle) but is **never
  assigned** — its identification rule (a prior failed supply/demand reaction) has no
  lookback/proximity definition yet; every candidate resolves to PIVOT_OB or SHADOW_OB.
- `status`: `CANDIDATE` / `VALID` / `MITIGATED` / `INVALIDATED` / `REJECTED`.
- Required checks before `VALID`: a matching-direction BOS or CHoCH confirmed at or
  after the OB's origin (`REQUIRED_STRUCTURE_MISSING` if none), and a same-direction FVG
  within `MAX_CANDLES_TO_FVG = 3` candles (`REQUIRED_FVG_MISSING` / `FVG_DIRECTION_MISMATCH`
  / `FVG_TOO_LATE` for the three ways this can fail) — no literal OB/FVG price overlap
  is required, only the candle-count proximity.
- Lifecycle after validation: `MITIGATED` the first time any candle's wick overlaps the
  zone at all (`WICK_TOUCH_BOUNDARY` — touch, not just a close); `INVALIDATED`
  (terminal) the first time a candle **closes** beyond the zone (below zone-low for
  bullish, above zone-high for bearish). A wick that pierces clean through the zone but
  closes back inside/beyond-the-original-side is `MITIGATED`, not `INVALIDATED` — closing
  price is what invalidates, not the wick.

**Still unsigned, per explicit owner instruction — do not infer from the reference
image:** `L1_L2_CLASSIFICATION` and `INSIDE_BAR_FLIP_RULE` (`supply_demand.L1_L2_CLASSIFICATION`
/ `INSIDE_BAR_FLIP_RULE`, both `"UNSIGNED"`). See `supply_demand.ORDER_BLOCK_CONTRACT_GAPS`
for the remaining open items (FLIP_OB identification, the PIVOT/SHADOW split
interpretation, and STRUCTURE's `INTERNAL_OR_EXTERNAL` source — `market_structure/` has
only one swing-length classifier today, no internal/external tiering, so
`structure_source` is a placeholder field for later research, not a real classification).

**Required phrasing:** call a raw candidate "an SMC candidate order block (not yet
validated)." Only call something "a valid PIVOT/SHADOW order block" or "AG-valid" when
`ValidatedOrderBlock.status == VALID` — and always report `MITIGATED`/`INVALIDATED`/
`REJECTED` candidates by their actual status, never as if they were still open/valid.

## Other zones

- Fair Value Gaps (`fair_value_gaps_for()`): bullish → demand-side reference, bearish →
  supply-side reference, `FRESH`/`MITIGATED` per `smc.fvg()`'s own `MitigatedIndex`.
- Session highs/lows as bounded zones (`session_zone()`) — frozen, already-completed
  session boxes, not live-forming zones.
- Previous Day High/Low (`previous_day_high_low()`) — project-owned, no smc.
- Premium/discount (`dealing_range_zones()`) — always from an **explicitly named**
  dealing range (previous day or a named session); never a guessed range.

## Reuses

- `session-box-drawing` — the canonical source for frozen session box levels (Asian/London/
  NY highs, lows, midlines), which `session_zone()` wraps. If this skill's own zone read
  disagrees with a frozen box from `session-box-drawing`, the frozen box wins for anything
  downstream that depends on canonical session levels.

## Output shape

Report instrument, timeframe, each zone with its price range, type, and — for order
blocks specifically — both the raw smc candidate status AND the AG validation status
(never just one). Report where current price sits relative to the nearest zone(s).

## Guardrails

- Zone quality is a descriptive judgment for the assistant, not a trade trigger. A price
  "approaching demand" is context, not a signal — that determination belongs to
  entry-confirmation-analysis and ultimately the strategy engine.
- Never derive or restate a frozen session box's numbers differently than
  `session-box-drawing`/`strategy_engine.session.reference_box` produced — session boxes are
  frozen once complete (see `session-box-drawing`'s own guardrails); this skill must not
  "re-draw" one from later candles.
- Never call an smc candidate order block "valid," "PIVOT," "SHADOW," or "FLIP" unless
  `validate_order_blocks()` actually returned that family/status — see the section above.
  `FLIP_OB` must never be reported for any candidate — it's a frozen family with no
  active identification logic.
- This skill has no independent broker execution authority. It may return analysis,
  structured evidence, levels, trade candidates, and management recommendations. Actual
  broker execution is delegated to the central Trade Assistant execution layer
  (`execution/executor.py`, via `assistant/commands.py`) and requires explicit user
  authorization.
