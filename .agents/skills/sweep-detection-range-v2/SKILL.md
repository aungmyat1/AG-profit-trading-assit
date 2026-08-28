---
name: sweep-detection-range-v2
description: Detect a qualified Sweep inside a completed frozen M15 reference session after ER_ONLY_V2 classifies it RANGE. Use for SESSION_FLOW_V2_SIMPLE routing only; never use later execution candles or assume an order or fill.
---

> **Ownership note (skill taxonomy pass, 2026-08-27):** This is `ST_ASIAN_SWEEP_5R_V1`'s
> qualified-Sweep rule (`strategy_engine/session/setups.py::entry_2_sweep`,
> `SESSION_FLOW_V2_SIMPLE` routing), not the generic Trade Assistant `liquidity` sweep
> fact. `SESSION_TRADE_V1` has its own, separately-thresholded sweep rule
> (`session_strategy/engine.py::detect_sweep()` in `Session Trade Codex`) — the two are
> not the same contract. Use the `liquidity` skill for generic sweep/reclaim facts; use
> this skill only when qualifying an `ST_ASIAN_SWEEP_5R_V1` RANGE setup. See
> `docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md`'s "Strategy-specific skill ownership" section.

# RANGE Reference-Session Sweep Detection V2 Simple

Preconditions, in order:

1. `session-box-drawing` returned `VALID_FROZEN_SESSION`.
2. `trend-range-classification` returned `classifier_id=ER_ONLY_V2`, `status=VALIDATED`, and `session_type=RANGE` for that same frozen window.
3. Inspect only the immutable candles already contained in that frozen reference session.

Fail closed if any precondition fails. Trend sessions must return `SWEEP_DETECTION_REQUIRES_RANGE_SESSION` rather than being inspected.

Post-session observation is disabled. Later candles cannot change Sweep/Range ownership or Entry 2/3 routing.

## Completed-box Sweep signal

Evaluate each reference candle chronologically against highs and lows formed strictly by earlier reference candles. Strict penetration plus a close back inside the prior level qualifies. A touch is not penetration and a close remaining outside is a breakout, not a Sweep.

High-side Sweep routes Short. Low-side Sweep routes Long. The first qualified reference candle owns the Sweep result. A same-candle dual-side Sweep retains `setup_type=SWEEP` but leaves direction unresolved so Entry 2 fails closed.

Return exactly one completed-box result: qualified Sweep or no Sweep. This skill selects only the setup family; Entry 2 price and execution require a separately validated contract. Sweep detection must not alter the frozen box or Trend/Range classification.
