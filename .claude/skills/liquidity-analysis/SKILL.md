---
name: liquidity-analysis
description: Map buy-side/sell-side liquidity, equal highs/lows, and liquidity sweeps/grabs/reclaims around structural, session, and previous-day levels. Use when asked where liquidity sits, whether a level was swept/reclaimed, or to explain a sweep-based setup. Advisory only — does not decide trades.
---

# Liquidity Analysis

Fourth layer of the AG Profit Trading assistant pyramid, built on
`market-structure-analysis` and `supply-demand-analysis`. Relevant both generally and,
specifically, to the registered `ST_ASIAN_SWEEP_5R_V1` strategy family.

## Scope

Deterministic, project-owned — see `liquidity/` (Phase 4, implemented 2026-08-26).
Request analysis via `liquidity.liquidity_result(symbol, timeframe, count=None)` rather
than manually scanning raw candles for sweeps — the deterministic analyzer exists
precisely so this skill doesn't have to reinterpret price history by hand.

A `LiquidityResult` carries a `levels` list (each a `LiquidityLevel`: `side`
BUY_SIDE/SELL_SIDE, `source` — SWING_HIGH/SWING_LOW, ASIAN/LONDON/NEW_YORK_HIGH/LOW,
PDH/PDL, EQUAL_HIGHS/EQUAL_LOWS — `price`, `status`, and `sources`, the full tuple of
every source that agreed on this price after cross-source deduplication), plus
`nearest_buy_side` and `nearest_sell_side` (the nearest still-`UNSWEPT` level per side,
falling back to nearest overall if none are unswept).

Session-dependent sources (ASIAN/LONDON/NEW_YORK_HIGH/LOW) only appear once that
session's calendar day has fully closed — an in-progress session for "today" produces
no candidate for it at all, never a guessed or partial value. See `liquidity/contract.py`
(`AG_LIQUIDITY_V1`) for the full frozen-from-implementation contract, including which
sources are session-dependent vs. always available, and what deduplication does.

## Status semantics (defined once, in `liquidity/status.py`)

- `UNSWEPT` — no candle has traded through the level, and it isn't being traded through
  live right now either.
- `SWEPT` — the **current live tick** is trading through the level; not yet confirmed by
  a closed candle. This is the only situation `SWEPT` is reported — once a candle
  closes, the outcome always resolves to `RECLAIMED` or `CONSUMED`.
- `RECLAIMED` — a closed candle penetrated the level, and the market has since closed
  back on the origin side (the classic "sweep and reverse").
- `CONSUMED` — a closed candle penetrated **and closed beyond** the level, with no
  reclaim since (the level has been broken through, not swept-and-reversed).
- `UNKNOWN` — status couldn't be determined (no data).

## Equal highs / equal lows

Deterministic tolerance-based clustering of raw candle extremes — see
`liquidity/equal_levels.py` and `config/liquidity.yaml`'s `equal_level_tolerance_points`
(currently 5 points, converted via the symbol's own tick size — an explicit, documented
default, not derived from any prior project authority). Report the tolerance used when
asked "are these really equal" — don't imply exact-price equality.

## External/internal liquidity + Inducement Candidate (additive, `liquidity/hierarchy.py`)

Scope freeze (2026-08-27, documented not silently assumed): **EXTERNAL** = swing
liquidity built from `market_structure.tiers`' EXTERNAL tier (`swing_length` 50) via
`external_swing_liquidity()` — the one new detector this adds, reusing the same
`liquidity/status.py` sweep state machine as every other source. **INTERNAL** = every
level `liquidity_result()` already produces (its existing swing-sourced levels already
use `swing_length` 5, identical to the INTERNAL tier; EQUAL_HIGHS/EQUAL_LOWS, PDH/PDL,
and session H/L are internal per this freeze). `scope_liquidity_levels()` tags each.

An **Inducement Candidate** (`find_inducement_candidates()`) is a deterministic
*relationship*, never a standalone label: an UNSWEPT INTERNAL level strictly between
current price and an UNSWEPT EXTERNAL level on the same side (nearer to price than that
target). `classify_roles()` gives every scoped level a role — `TARGET`,
`INDUCEMENT_CANDIDATE`, or `NONE` (internal liquidity with no valid target stays `NONE`,
never forced). Multiple valid candidates are all returned, unranked — do not pick one as
"the" inducement unless a ranking rule gets separately frozen. A swept candidate or
swept target immediately drops out (`ACTIVE_INDUCEMENT = NO`) on the very next read; report
this as a status change, not a re-interpretation of the past — the earlier classification
was correct at its own `as_of` time (see no-hindsight guardrail below).

## Engineered / retail liquidity (`liquidity/proxies.py`)

`retail_liquidity_proxies()` relabels existing objective sources (EQUAL_HIGHS/LOWS,
SWING_HIGH/LOW, PDH/PDL, session H/L) — **VALIDATED**, not new detection.
`engineered_liquidity_candidates()` is explicitly **RESEARCH_ONLY**: a 0-3 evidence count
(repeated minor-level cluster, a same-side major objective present, and — the closest
defensible proxy for "inducement" available from status data alone — the minor level
already swept while the major one remains unswept). Never present an engineered-liquidity
score as certainty or a probability; report the evidence flags, not a confidence number.

## Rendering

`chart_renderer.render_chart(..., liquidity=levels, liquidity_roles=roles)` draws the
given `LiquidityLevel`s; `liquidity_roles` (from `classify_roles()`) only adds a label
suffix (`[TARGET]`/`[INDUCEMENT_CANDIDATE]`) — it never changes what's drawn.

## Relationship to `ST_ASIAN_SWEEP_5R_V1`'s own sweep logic

`sweep-detection-range-v2` / `strategy_engine.session.setups.entry_2_sweep` is a
**separate, frozen, strategy-specific** sweep contract for that one strategy's own
session box (strict penetration against a completed reference-session box only). This
skill's general liquidity read is independent and may legitimately disagree with it on
the same market moment — e.g. general liquidity can say "Asian High RECLAIMED" while the
strategy's own frozen rule says `NO_SETUP` for an unrelated reason. When the question
concerns a registered strategy specifically, defer to that strategy's own engine result
for what counts as "qualified" for trading purposes; use this skill's read for general
context. Don't invent a looser or stricter sweep definition ad hoc for either.

## Output shape

Report: instrument, timeframe, nearest buy-side and sell-side liquidity (source, price,
status), and any specifically-asked-about level's full detail (source, price, status,
sweep_time, reclaim_time). Keep it compact; expand to prose only when asked to explain
further.

## Guardrails

- "A level was swept/reclaimed" is an observation, not authorization to trade. Whether a
  registered strategy produces a `TradeSignal` is decided by
  `strategy_engine.session.setups.entry_2_sweep` / `strategy_engine.evaluate()`, using
  only that session's own candles up to the qualifying one — never later candles (no
  lookahead).
- This skill has no independent broker execution authority. It may return analysis,
  structured evidence, levels, trade candidates, and management recommendations. Actual
  broker execution is delegated to the central Trade Assistant execution layer
  (`execution/executor.py`, via `assistant/commands.py`) and requires explicit user
  authorization.
- If this skill's read of a sweep disagrees with what `strategy_engine.evaluate()`
  actually returned for a registered strategy, report the engine's result as authoritative
  and explain the discrepancy — do not present this skill's read as the trade outcome.
- If `status` isn't `LIQUIDITY_OK` (e.g. a `MarketDataError`-equivalent reason code, or
  `NO_LIQUIDITY_LEVELS`), report that status verbatim — don't fall back to a guess.
- Never phrase an inducement candidate or engineered-liquidity evidence score as trader
  intent ("smart money is manipulating retail before taking the highs"). Report the
  relationship/evidence only: "internal BSL at X is unswept, structurally confirmed, and
  lies between current price and external BSL at Y" — that is the complete claim.
- A classification is only valid as of the `current_price`/candle set it was computed
  from. Do not use later price movement to retroactively decide an earlier level "was"
  or "wasn't" inducement — recompute at the new `as_of` point and report the change.
