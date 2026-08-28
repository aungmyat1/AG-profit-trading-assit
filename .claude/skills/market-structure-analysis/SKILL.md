---
name: market-structure-analysis
description: Read and describe market structure on a chart or candle series — swing highs/lows, BOS/CHoCH, previous high/low, bullish/bearish/undefined state, multi-timeframe structure. Use when asked to analyze structure, describe trend/range state, or explain "where are we" before deeper supply/demand or liquidity analysis. Advisory only — does not decide trades.
---

# Market Structure Analysis

Foundation layer of the AG Profit Trading assistant pyramid (Structure → Supply/Demand →
Liquidity → Entry/Confirmation → Trade Management). Everything above this layer depends
on knowing where price is structurally.

## Scope

Deterministic, project-owned — see `market_structure/` (Phase 2, implemented
2026-08-26). Request analysis via `market_structure.analyze_structure(symbol,
timeframe, count=None)` or `python scripts/analyze_structure.py --symbol X --timeframe
Y [--json]` rather than eyeballing raw candles by hand — the deterministic analyzer
exists precisely so this skill doesn't have to manually reinterpret hundreds of bars.

A `StructureResult` carries: `state` (`BULLISH`/`BEARISH`/`STRUCTURE_STATE_UNDEFINED`),
`latest_swing_high`/`latest_swing_low`, `latest_bos`/`latest_choch`, `previous_high`/
`previous_low`, plus provenance (data range, candle count, config, smc version).

When asked for multiple timeframes, report each one separately before combining — don't
average timeframes into a single verdict; each is its own `analyze_structure()` call.

## How `state` is derived

Whichever of the latest confirmed BOS/CHOCH happened most recently (by confirmation
time, not swing-point time) sets `BULLISH`/`BEARISH`. If neither has confirmed yet,
`state` is `STRUCTURE_STATE_UNDEFINED` — report it as such, don't guess a direction from
raw swings alone. There is deliberately no `RANGE` state: nothing in this layer defines
one objectively, so inventing one would be discretionary bias, not a rule.

## External/internal tiers (additive, `market_structure/tiers.py`)

`analyze_structure_tiers(symbol, timeframe, count=None)` returns a `TieredStructureResult`
with independent `external` and `internal` `StructureTier`s — additive to
`analyze_structure()` above, which is unchanged and still the single-tier answer.
Frozen 2026-08-27: internal = `swing_length` 5 (identical detector/config to
`analyze_structure()`), external = `swing_length` 50 — matching the LuxAlgo Smart Money
Concepts reference indicator's own internal/swing defaults (`smartmoneyconcepts` is a
port of that indicator), not an arbitrary choice. Each tier carries its own full
`swings` sequence (labeled `HH`/`HL`/`LH`/`LL` — ties within
`config/liquidity.yaml`'s `equal_level_tolerance_points`, converted via tick size, label
toward continuation) and `events` (all confirmed BOS/CHOCH, chronological), not just the
latest of each. Report external and internal state **separately** — never average them
into one verdict; a market can be "external bullish, internal bearish" simultaneously
and both are correct.

## Rendering

`chart_renderer.render_chart(candles, structure=tier, zones=..., liquidity=...,
out_path=...)` draws exactly the coordinates a `StructureTier`/zone list/liquidity list
already contains — it never recomputes structure itself. Use it when asked to
visualize/plot structure rather than describing swing positions in prose only.

## Reuses / relationship to other classifiers

- `trend-range-classification` — canonical ER_ONLY_V2 TREND/RANGE call for a *frozen
  session-box* specifically (`strategy_engine.session.classifier`). This is a different,
  broader concept from this skill's general BULLISH/BEARISH/UNDEFINED state — both can
  be true at once (e.g. "H1 general structure = BULLISH" while "Asian session strategy
  regime = RANGE"). Name the source when reporting either; never substitute one for the
  other.
- Structure calculations delegate to the third-party `smartmoneyconcepts` package, but
  only inside `market_structure/smc_adapter.py` — that package's raw DataFrame/Series
  output never becomes this skill's answer directly; always relay the mapped
  `StructureResult` fields.

## Output shape

Report structurally: instrument, timeframe, state, last swing high/low, latest BOS,
latest CHoCH (or "None"), previous high/low, and the data status. Keep it compact —
see `scripts/analyze_structure.py`'s plain-text report for the target shape. Expand to
prose only when asked to explain further.

## Guardrails

- **Structure analysis does not authorize trades.** This skill may say "H1 structure is
  bullish." It may never say "therefore Strategy Engine must BUY" or phrase output as
  "therefore go long/short" — describe structure, let entry-confirmation-analysis and
  the strategy engine handle setup validity.
- This skill has no independent broker execution authority. It may return analysis,
  structured evidence, levels, trade candidates, and management recommendations. Actual
  broker execution is delegated to the central Trade Assistant execution layer
  (`execution/executor.py`, via `assistant/commands.py`) and requires explicit user
  authorization.
- If asked whether a specific registered strategy (e.g. `ST_ASIAN_SWEEP_5R_V1`) would
  trade here, say so explicitly and defer to `strategy_engine.evaluate()`'s actual
  output — do not substitute this skill's structural read for the engine's decision. A
  bullish general structure and a `NO_TRADE` session-strategy result can both be correct
  simultaneously; explain the difference rather than reconciling them into one verdict.
- If `status` isn't `VALID` (e.g. `MARKET_DATA_INVALID`, `INSUFFICIENT_STRUCTURE_HISTORY`,
  `STRUCTURE_LIBRARY_ERROR`), report that status and its reason code verbatim — don't
  fall back to a guess or stale memory of what structure "probably" looks like.
