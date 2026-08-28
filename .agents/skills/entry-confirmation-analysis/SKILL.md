---
name: entry-confirmation-analysis
description: Judge whether structure + zone + liquidity context adds up to a valid-looking entry — rejection/engulfing candles, displacement, break-and-retest, sweep-and-reclaim, structure shift, SL geometry, RR. Use when asked "is this a valid setup" or to explain entry logic. Advisory only — cannot itself produce a TradeSignal.
---

# Entry & Confirmation Analysis

Fourth layer of the AG Profit Trading assistant pyramid, sitting on top of
`market-structure-analysis`, `supply-demand-analysis`, and `liquidity-analysis`. Answers
a different question than the layers below it: not "where are we" but "is there
actually a valid trade here."

## Scope

- Confirmation candle read: rejection wicks, engulfing, strong directional close.
- Displacement: an unusually forceful move away from a zone/level.
- Break-and-retest and sweep-and-reclaim patterns.
- Structure shift immediately following a liquidity event.
- Entry location, stop-loss geometry, and resulting risk:reward, given a proposed entry
  and stop.

## Deterministic capability (ENTRY_CONFIRMATION_V1, added 2026-08-27)

`entry_confirmation/` (`evaluate_entry_confirmation()`) is the deterministic backing for
this skill's structure-shift, liquidity-reclaim, displacement, and rejection-candle
claims. Full contract: `ENTRY_CONFIRMATION_V1_SPEC.md`. Use it whenever a claim in this
skill's scope needs to be traceable to a fact rather than a qualitative read.

Call shape: build an `EntryConfirmationRequest` (symbol, timeframe, `candidate_direction`
[`LONG`/`SHORT`/`NONE`], `requested_confirmations` [any of `displacement`,
`structure_shift`, `liquidity_reclaim`, `rejection`], and the already-computed
`candidate_candle` / `structure_result` / `liquidity_result` this skill already has from
`market-structure-analysis` / `liquidity-analysis` -- never fetched fresh here). Pass it
to `evaluate_entry_confirmation()` and report the returned `EntryConfirmationResult`
as-is: `displacement`, `structure_shift`, `liquidity_reclaim`, `rejection` (each a
`PASS` / `FAIL` / `NOT_REQUESTED` / `UNAVAILABLE` / `INSUFFICIENT_DATA` /
`UNSIGNED_RULE` fact) and `overall_state` (`CONFIRMED` / `PARTIAL` / `NOT_CONFIRMED` /
`INDETERMINATE` -- an evidence summary, never a trade decision).

`displacement` and `rejection` currently report `UNSIGNED_RULE`: the underlying
candle measurements (body/range/wick ratios, close_location) are always computed, but no
owner has signed a generic qualifying threshold yet (see `entry_confirmation/contract.py`).
Report the measurements and say so plainly -- do not round `UNSIGNED_RULE` up to a
qualitative "looks like displacement" judgment when this deterministic path is in use.

## Reuses

- `risk-position-sizing` — for the mechanics of translating a stop distance into position
  size once an entry is deemed worth costing out (sizing itself remains
  `execution/risk.py`'s job once implemented; this skill and `risk-position-sizing` only
  describe/estimate, they do not size a live order).
- Draws on `market-structure-analysis`, `supply-demand-analysis`, and
  `liquidity-analysis` outputs as its inputs rather than re-deriving structure/zones/
  liquidity itself. The deterministic path above formalizes this for structure_shift
  (`market_structure.StructureResult.latest_choch`) and liquidity_reclaim
  (`liquidity.LiquidityResult`) specifically.

## The critical distinction

This skill may say: *"there appears to be a high-quality bullish confirmation."*

Only `strategy_engine.evaluate()` (via `strategy_engine.session.setups`) can say:
`ENTRY_VALID` / produce a `TradeSignal` with `status: SIGNAL`. Those are different
claims and must not be conflated in a report. When a registered strategy is in play,
always run or cite the engine's actual result alongside this skill's qualitative read,
and lead with the engine's result if the two differ.

## Guardrails

- This skill has no independent broker execution authority. It may return analysis,
  structured evidence, levels, trade candidates, and management recommendations. Actual
  broker execution is delegated to the central Trade Assistant execution layer
  (`execution/executor.py`, via `assistant/commands.py`) and requires explicit user
  authorization.
- Never state or imply that this skill's judgment *is* a `TradeSignal`. If the user asks
  "should I take this trade," reframe: report what the engine's registered rules say
  (or that no registered strategy covers this setup), then offer this skill's contextual
  read as separate, clearly-labeled color commentary.
- Do not fabricate confirmation where the data doesn't show it just because the lower
  layers looked favorable — a good structure/zone/liquidity read with no confirming
  candle is "no confirmation yet," not a soft yes.
- Never invent a displacement/rejection qualifying threshold (e.g. "body_ratio >= 0.6 =
  displacement") on this skill's own authority. Report `UNSIGNED_RULE` and the raw
  measurement instead, until an owner signs a generic threshold.
- Never reuse a strategy-specific rule (e.g. `ER_ONLY_V2`'s session-level displacement,
  or `sweep-detection-range-v2`'s qualified sweep) as if it were this capability's
  generic answer — those stay owned by `ST_ASIAN_SWEEP_5R_V1`.
