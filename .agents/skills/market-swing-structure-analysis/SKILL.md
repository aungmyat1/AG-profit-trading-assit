---
name: market-swing-structure-analysis
description: Compose a normalized, MTF-aware swing-structure snapshot (confirmed swings with explicit confirmation timestamps, BOS/CHoCH, active dealing range, liquidity/imbalance context, HTF-to-LTF alignment) by orchestrating existing canonical AG engines. Use when asked for swing structure, pivot confirmation timing, premium/discount context, or "where is the active dealing range" in one composed object. Advisory only — never decides trades.
---

# Market Swing Structure Analysis

This is a universal AG project skill, usable from any agent ecosystem — it names no
vendor or tool. It is an **analytical composition layer**, not a new market-structure
engine: it discovers, reuses, and normalizes output from the existing canonical
capabilities (`market-structure-analysis`, `liquidity-analysis`, `supply-demand-analysis`,
`multi-timeframe-market-context`) into one schema-versioned snapshot. It contains no
independent BOS/CHoCH/FVG detector and must never disagree with the engine it read from.

## Scope

```
Market Structure Engine (market_structure/)
Liquidity Engine        (liquidity/)
Supply/Demand Engine    (supply_demand/)
        |
Market Swing Structure  (src/market_swing_structure/, this skill's runtime)
        |
normalized MARKET_SWING_STRUCTURE_V1 snapshot
        |
Strategy-specific bias (e.g. SESSION_BIAS_V1) / Session Strategy / Large-SMC
```

Request analysis via `market_swing_structure.analyze(symbol, timeframes,
evaluation_time=None)` — `timeframes` is an ordered HTF-first, LTF-last sequence (e.g.
`("H4", "H1", "M15")`); there is no fixed hierarchy, the caller supplies it (see
`multi-timeframe-market-context`'s own role-profile convention, which this skill does
not duplicate — it takes a plain ordered timeframe sequence, one call per symbol).

## Authority

```
authority: ADVISORY_CONTEXT_ONLY
strategy_authority: NONE
lifecycle_authority: NONE
risk_authority: NONE
execution_authority: NONE
```

`STRUCTURE_CONTEXT_IS_NOT_ENTRY`. This skill may read confirmed swings, BOS/CHoCH,
liquidity events, FVG/zone information, and construct dealing-range/MTF context. It may
NOT change strategy configuration, change lifecycle state, create a trade signal,
authorize a proposal/Demo/Live, submit an order, rewrite historical evidence, or
override any existing structure engine's own output.

## Workflow

```
1. Identify available structure authority (market_structure.analyze_structure per
   timeframe — never a skill-local reimplementation).
2. Retrieve confirmed swings and attach an explicit confirmed_time_utc
   (market_swing_structure.confirmation — a pure derivation, not re-detection).
3. Retrieve BOS/CHoCH events (relayed verbatim from StructureResult.latest_bos/
   latest_choch — already confirmation-timestamped by the canonical engine).
4. Retrieve liquidity context (liquidity.liquidity_result — EQH/EQL, PDH/PDL, session
   levels, symbol-aware tolerance already built in).
5. Retrieve imbalance/zone context (supply_demand.fair_value_gaps_for —
   mitigation-tracked FVGs).
6. Build the active dealing range from the canonical structure engine's own latest
   CONFIRMED swing pair on the LTF timeframe (market_swing_structure.dealing_range) —
   never "the most recent arbitrary high and low"; null if either swing is missing or
   the pair is degenerate.
7. Map timeframes: compute an mtf_alignment LABEL (market_swing_structure.alignment)
   over already-computed structure_state values — never a bias decision.
8. Return one normalized MARKET_SWING_STRUCTURE_V1 snapshot.
9. Never generate trading authorization.
```

## Mandatory rules

```
use confirmed information only
respect confirmation timestamps (confirmed_time_utc >= pivot_time_utc, always)
never backdate pivots — a swing is only usable strategy-side after its confirmed_time_utc
reuse canonical engines — no skill-local BOS/CHoCH/FVG/swing detector
bias is not entry
liquidity event is not entry
LTF cannot silently override HTF — CONFLICT is reported, never silently resolved
strategy rules remain authoritative
unconfirmed_swing_cannot_create_structure_event (SMC_TRAP_GUARD_V1-compatible, see Compatibility)
```

## What is genuinely new here (and only this)

Two pure, narrow derivations — everything else is a direct read of an existing engine:

- **`confirmation.py`** — `market_structure.StructurePoint`'s `time_utc` for a
  SWING_HIGH/SWING_LOW is the pivot bar's own time, not a confirmation time (unlike
  BOS/CHoCH points, whose `time_utc` already is the confirmation time via smc_adapter's
  `BrokenIndex`). This module derives `confirmed_time_utc = pivot_time_utc +
  swing_length bars of that timeframe's own duration` — arithmetic over already-known
  quantities (timeframe bar duration reused from
  `historical_replay.candle_store.TIMEFRAME_MINUTES`), never a second pivot detector.
  Because `analyze_structure()` only ever returns a swing whose full confirmation window
  already existed in the fetched candle range, every swing this module normalizes was
  already, structurally, confirmed — `assert_confirmed_as_of()` is an explicit, testable
  safety net for that invariant, not a claim this module could otherwise emit an
  unconfirmed swing.
- **`alignment.py`** — turns an ordered HTF-to-LTF list of already-computed
  `structure_state` values into one label (`ALIGNED_<STATE>` /
  `HTF_<X>_LTF_TRANSITION` / `HTF_<X>_LTF_CONFLICT` / `UNKNOWN`). Never resolves a
  CONFLICT into a single winning direction — the consuming strategy decides what
  conflict means (P18).

Everything else (swing detection, BOS/CHoCH, EQH/EQL, FVG detection/mitigation, premium/
equilibrium/discount arithmetic) is called through unchanged from `market_structure`,
`liquidity`, and `supply_demand` — see `src/market_swing_structure/orchestrator.py`.

## Dealing range: WHICH swing pair, not just "the latest high and low"

`active_dealing_range` is derived from the canonical structure engine's own
`latest_swing_high`/`latest_swing_low` on the LTF timeframe (documented, not the most
recent arbitrary extremes) — see `dealing_range.active_dealing_range_from_structure()`,
which calls `supply_demand.native_zones.dealing_range_zones()` unchanged for the actual
premium/equilibrium/discount arithmetic. If either confirmed swing is missing, or
`swing_high <= swing_low` (a degenerate/stale pair), this fails closed to `null` — never
guesses or swaps values to produce a range.

## Output shape

See `references/market_swing_structure_contract.json` for a full worked example. Top
level fields: `schema_version` (`MARKET_SWING_STRUCTURE_V1`), `symbol`,
`analysis_time_utc`, `authority` (`ADVISORY_CONTEXT_ONLY`), `timeframes` (ordered
HTF→LTF, each a `TimeframeStructureSnapshot`), `active_dealing_range` (or `null`),
`liquidity_context`, `imbalance_context`, `structure_events`, `mtf_alignment`,
`provenance` (skill_version, schema_version, timeframes_requested, which timeframe
defines the dealing range/liquidity/imbalance context), `status`, `reason_codes`.

Do not report `current_bias` as a primary field — `structure_state` and `mtf_alignment`
are the outputs this skill owns; a dedicated bias module (e.g. `SESSION_BIAS_V1`) owns
the BULLISH/BEARISH/NEUTRAL trade-bias decision, not this skill (P19/P20).

## Integration

```
Market Swing Structure Skill
        |
normalized context (structure_state, mtf_alignment, active_dealing_range, ...)
        |
Strategy-specific Bias (e.g. SESSION_BIAS_V1)
        |
Session Strategy / Large-SMC setup validation
```

Never reverse this — the skill does not create Session Trade entries, does not
determine bias itself, and never changes Large-SMC's own E/M models or C10 invalidation.
Large-SMC's existing authorities remain authoritative; this skill's snapshot may be
consumed by it later if compatible, never the other way around.

## Compatibility with SMC_TRAP_GUARD_V1

Verified compatible: `liquidity_event_is_not_trade_signal`, `bias_is_not_entry`,
`future_evidence_cannot_create_past_qualification` (this is exactly what
`confirmation.py`'s explicit `confirmed_time_utc` exists to make auditable),
`lower_timeframe_cannot_override_higher_timeframe` (`alignment.py` never resolves
CONFLICT to one side), `silent_rule_changes_prohibited` (no signed contract was
modified by adding this skill). Adds one new, compatible invariant this skill
introduces and enforces for its own outputs:
`unconfirmed_swing_cannot_create_structure_event` — this skill never emits a
`NormalizedSwing` or `StructureEvent` whose underlying canonical engine hadn't already
confirmed it.

## Guardrails

- This skill has no independent broker execution authority, same as every skill in the
  pyramid. Actual execution is delegated to `execution/executor.py` via
  `assistant/commands.py` and requires a fresh, explicit user execution command that
  turn.
- Do not silently pick a fixed D1/H4/H1/M15 hierarchy — always take the ordered
  timeframe sequence the caller (or consuming strategy) actually needs.
- If a role's underlying call reports a non-`VALID`/non-`OK` status
  (`MARKET_DATA_INVALID`, `INSUFFICIENT_STRUCTURE_HISTORY`, a liquidity/zone error),
  surface that status verbatim for that timeframe and set the snapshot's own `status` to
  `PARTIAL` — never synthesize a timeframe's state from an earlier read or a neighbor.
- Never report this skill's output as a `TradeSignal` or a registered strategy's
  decision. If a registered strategy is in play, run/cite `strategy_engine.evaluate()`
  and lead with its result; offer this skill's structural read as separate, clearly
  labeled context.
- Do not use a `CANDIDATE`-status swing (none exist yet from the current canonical
  engine, but the schema reserves the state) as confirmed historical structure.
