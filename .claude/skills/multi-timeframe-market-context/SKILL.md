---
name: multi-timeframe-market-context
description: Compose normalized higher-to-lower-timeframe market context (structure, zones, liquidity, entry evidence) across caller-defined timeframe roles for any strategy or ad hoc analysis. Use when asked for top-down / multi-timeframe / D1-H4-H1-M15-style context, HTF-to-LTF alignment, or "does the lower timeframe agree with the higher timeframe." Advisory only — produces context, never a trade decision.
---

# Multi-Timeframe Market Context

Cross-cutting *orchestration* skill sitting across the existing pyramid
(`market-structure-analysis` -> `supply-demand-analysis` -> `liquidity-analysis` ->
`entry-confirmation-analysis`). It adds no new detection logic; it composes calls into
those four skills' already-deterministic modules across more than one timeframe and
returns one normalized object. See
`docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md` workflow F.

## Provenance

Designed from a conversation-supplied conceptual specification (task-prompt prose
describing an `smc-topdown-analysis` reference design: role hierarchy, normalized
context shape, state-machine intent) — no literal source files (`SKILL.md`,
`mtf_smc_engine.py`, `smc_pinescript.pine`, `state_machine.json`) were ever present in
this repository or attached to the conversation, so none was copied verbatim. The
concepts were generalized and mapped onto existing AG capabilities (`market_structure`,
`supply_demand`, `liquidity`, `entry_confirmation`, `assistant.market_data`) per the
resource-first policy; no new detection algorithm was introduced.

## Authority

```
authority: ADVISORY_ONLY
strategy_authority: NONE
risk_authority: NONE
execution_authority: NONE
```

This skill DESCRIBES the market across timeframes. It never authorizes, executes,
changes risk, or promotes a strategy lifecycle state — same guardrail as every skill in
the pyramid (see `AGENTS.md` "Authority order" point 4). No state, field, or example in
this skill may resemble `EXECUTE_TRADE` / `PLACE_ORDER` / `SEND_ORDER`.

## Timeframe roles, not a fixed hierarchy

Do not assume D1 -> H4 -> H1 -> M15 as *the* hierarchy. The caller supplies a
**profile**: an ordered map of semantic roles to whatever timeframes the question
actually needs.

Canonical roles (all optional — evaluate only the roles a profile actually sets):

```
MACRO       - major structural boundaries / external liquidity
BIAS        - dominant structural direction (BOS/CHoCH-driven)
WORKING     - current retracement/alignment state relative to BIAS
SETUP       - zone/liquidity context where a setup may form
EXECUTION   - lower-timeframe confirmation evidence (sweep, CHoCH, displacement, rejection, FVG)
MANAGEMENT  - optional, advisory-only, open-position context (never mutates SL/TP itself
              — trade-management-analysis / trade_management/* own that, see Guardrails)
```

Example profiles (illustrative — not defaults this skill enforces):

```yaml
SMC_TOPDOWN_STANDARD: {macro: D1, bias: H4, working: H1, setup: M15, execution: M5}
BTC_INTRADAY:         {macro: H4, bias: H1, working: M15, setup: M5, execution: M1}
SWING:                {macro: W1, bias: D1, working: H4, setup: H1, execution: M15}
```

A profile with only `bias` and `execution` set is valid.

## Orchestration (what this skill actually calls)

`src/mtf_context/` (added 2026-09-07, `AG_UNIVERSAL_MTF_CONTEXT_OPERATIONAL_INTEGRATION_AND_VALIDATION_V1`)
is the real, thin runtime implementation of this skill: `mtf_context.analyze(symbol,
profile, evaluation_time=None, ...)` takes an `MTFProfile` (role -> timeframe map, any
subset of MACRO/BIAS/WORKING/SETUP/EXECUTION/MANAGEMENT) and returns one `MTFContext`.
For every role with a timeframe assigned:

1. **Structure** — `market_structure.analyze_structure(symbol, timeframe)` — closed-candle
   `StructureResult`, called for every role that has a timeframe (not a fixed
   D1/H4/H1/M15 list; `tests/test_mtf_context.py::test_role_timeframes_is_role_based_not_hardcoded_hierarchy`
   and its live counterpart prove two structurally different profiles run through the
   same code path).
2. **Liquidity** — `liquidity.liquidity_result(symbol, timeframe)`, every role.
3. **Zones** (SETUP/EXECUTION roles only) — `supply_demand.validated_order_blocks_for()`,
   `fair_value_gaps_for()`.
4. **Local confirmation** (EXECUTION role only, and only when the caller explicitly
   supplies `candidate_direction` + `candidate_candle` + `candle_history` — the
   orchestrator never invents a candidate) —
   `entry_confirmation.evaluate_entry_confirmation()`, passing the already-computed
   `structure_result` / `liquidity_result` from steps 1-2 — never fetched fresh inside
   that call, per that skill's own contract.

Each role's failures are isolated and non-fatal: an exception or a non-`VALID`
underlying status becomes that role's `reason_codes`/`status` (`VALID`/`PARTIAL`/
`DATA_ERROR`), never a crash — see `src/mtf_context/orchestrator.py::_evaluate_role()`.
Do not reimplement any of the above. `src/mtf_context/` must never import `execution/`,
`mt5.management_gateway`, or `trade_management.manager` — enforced by
`tests/test_mtf_context_execution_guard.py` (AST-based static scan, not a comment
promise).

**Not yet integrated** (deliberately deferred, not a defect): no strategy report or
Telegram ticket attaches `mtf_context` yet. `src/post_asian_pilot/report.py::cycle_to_dict()`
has a clean, safe extension point matching this need — it already takes optional
`ledger`/`release_fingerprint`/`strategy_fingerprint` parameters that, when omitted,
leave output byte-identical to before they existed; a future `mtf_context` parameter
following that exact pattern (opt-in, `None` by default, byte-identical output when
omitted) is the recommended next step, not implemented in this pass because
`AG_V1_0_3_FX_SHADOW_SERIES_002` evidence collection is active and touching that file
deserves its own scoped, tested change rather than bundling it with new orchestrator
code in the same pass. See `references/strategy_usage_contract.json` for the generic
per-field usage-mode vocabulary (`REQUIRED`/`OPTIONAL`/`SCORE_ONLY`/`OBSERVE_ONLY`/
`IGNORE`/`EXPECTED_CONFLICT`) any future strategy binding should use, defaulting to
`OBSERVE_ONLY`.

## No-lookahead / data quality

Verified by code inspection 2026-09-07 (`AG_UNIVERSAL_AGENT_SKILLS_PORTABILITY_REMEDIATION_V1`),
not merely assumed:

- **Closed-candle enforcement at the data layer** — `mt5.market_data.get_latest_candles()`
  (used, directly or transitively, by every module this skill orchestrates) calls
  `copy_rates_from_pos` starting at position 1: "position 1 = last fully closed bar;
  position 0 is the still-forming current bar and is deliberately excluded." This holds
  for every timeframe a role's profile can name — MACRO/BIAS/WORKING/SETUP/EXECUTION all
  go through the same function, so a role assigned H4 never sees a partially-formed H4
  candle merely because a lower-timeframe role's data has moved further forward in time.
  **VERIFIED.**
- **Pivot/BOS/CHoCH availability vs. event time** — `market_structure/models.py`'s
  `all_breaks()`/`latest_swings_and_breaks()` docstrings distinguish a broken swing
  point's own index from `BrokenIndex`, "the position of the candle that *confirmed* the
  break" — `market-structure-analysis`'s own skill doc already reports state by
  confirmation time, not swing-point time. The same module explicitly guards against
  `smartmoneyconcepts.swing_highs_lows()`'s own bookend artifact (it force-assigns a
  swing label to the first/last row of the window regardless of real confirmation) so
  that artifact is never reported as a genuine, already-confirmed swing. **VERIFIED**
  by code inspection; not re-exercised by a new test in this pass (see
  `tests/market_structure/` for the existing suite covering this behavior).
- **Session-dependent liquidity sources** (ASIAN/LONDON/NEW_YORK high/low) only appear
  once that session's calendar day has fully closed (`liquidity-analysis` skill doc,
  `liquidity/contract.py`) — an in-progress "today" session produces no candidate at all.
  **VERIFIED** (documented contract; not independently re-derived this pass).
- **Timezone handling** — this skill introduces no new timestamp conversion; every
  timestamp it reports is whatever the underlying `Candle`/`StructureResult`/
  `LiquidityResult` already carries from `mt5.market_data`. **NOT INDEPENDENTLY
  VERIFIED** in this pass beyond confirming no new conversion path was added — if a
  caller crosses broker-time and UTC-labeled sources in one profile, that mismatch is
  inherited from the underlying data layer, not introduced here.

This skill adds no new candle-fetching path and therefore inherits the guarantees above
— never bypass them by reading raw MT5 candles directly. If any role's underlying call
reports a non-`OK`/non-`VALID` status (`MARKET_DATA_INVALID`,
`INSUFFICIENT_STRUCTURE_HISTORY`, a liquidity `MarketDataError`, etc.), surface that
status verbatim for that role and set `data_quality.status` to `PARTIAL` (or
`MISSING`/`DATA_ERROR` if every role failed) — never synthesize a role's state from an
earlier read or a neighboring role.

## Normalized output contract

See `references/context_contract.json` for a full worked example and
`references/timeframe_roles.json` for the role/state vocabulary.
`context_contract.json` also shows each layer's `bar_close_time` / `data_cutoff` /
`forming_bar_used` fields (omitted from the abbreviated shape below for brevity) — carry
them in any real output so a reader can audit whether the context was actually valid
as of `evaluation_time` rather than trusting an unverifiable claim. Shape:

```json
{
  "skill_id": "multi-timeframe-market-context",
  "skill_version": "1.0.0",
  "authority": "ADVISORY_ONLY",
  "symbol": "EURUSD",
  "evaluation_time": "...",
  "profile": {"macro": "D1", "bias": "H4", "working": "H1", "setup": "M15", "execution": "M5"},
  "layers": {
    "macro":     {"role": "MACRO",     "timeframe": "D1", "structure": {}, "liquidity": [], "evidence": []},
    "bias":      {"role": "BIAS",      "timeframe": "H4", "structure": {}, "evidence": []},
    "working":   {"role": "WORKING",   "timeframe": "H1", "alignment_to_bias": "RETRACING", "evidence": []},
    "setup":     {"role": "SETUP",     "timeframe": "M15", "zones": [], "liquidity": [], "evidence": []},
    "execution": {"role": "EXECUTION", "timeframe": "M5", "confirmation": {}, "evidence": []}
  },
  "alignment": {"macro_to_bias": "ALIGNED", "bias_to_working": "CONFLICTED", "working_to_setup": "UNKNOWN"},
  "data_quality": {"status": "VALID", "closed_candle_only": true, "reason_codes": []},
  "authorization": {"may_create_trade": false, "may_reject_trade": false, "may_change_strategy_decision": false, "may_modify_risk": false, "may_execute": false}
}
```

`structure`/`liquidity`/`zones`/`confirmation` fields are the actual `StructureResult` /
`LiquidityResult` / `ZoneResult` / `EntryConfirmationResult` objects from the four
underlying skills, reported as-is — never re-derived or summarized into a new opaque
label. States for `bias`/`working` reuse `market_structure.StructureResult.state`
(`BULLISH`/`BEARISH`/`STRUCTURE_STATE_UNDEFINED`) verbatim; do not invent a `RANGE`
state at this layer, for the same reason `market-structure-analysis` doesn't.

`alignment.*` values: `ALIGNED`, `CONFLICTED`, `RETRACING`, `REALIGNING`, `INDEPENDENT`,
`UNKNOWN` (data missing for one side), `NOT_APPLICABLE` (one of the two roles absent
from the profile). Never collapse to a boolean — a boolean cannot distinguish a healthy
retracement from a genuine reversal or missing data.

## Strategy consumption policy (vocabulary only — not wired into any strategy)

A strategy YAML *may* eventually declare how it treats each layer:
`REQUIRED` / `OPTIONAL` / `SCORE_ONLY` / `OBSERVE_ONLY` / `IGNORE` / `EXPECTED_CONFLICT`.
`CONFLICTED` is not universally bad (a reversal strategy may set
`working: EXPECTED_CONFLICT`) and `ALIGNED` is not universally required. This skill
defines the vocabulary only — no current strategy contract (`ST_ASIAN_SWEEP_5R_V1`,
`ST_LARGE_SMC_V1`, `ST_LIQUIDITY_SWEEP_RETEST_V1`) declares a `multi_timeframe_context`
block today, and none is added by installing this skill. Attaching this skill's output
to an existing strategy's proposal/report as `mtf_context` metadata is allowed and must
never change that strategy's `READY`/`WATCH`/`NO_TRADE`, direction, entry, SL, TP, or
risk — those fields must be provably identical with or without the attached context.
Any future `REQUIRED`-mode consumption is a separate, explicitly versioned strategy
change with its own tests and governance review, not an effect of installing this skill.

## Versioning

Keep `skill_version` (this skill), a consuming strategy's own version, the application
release (e.g. `AG_TRADE_ASSISTANT_V1_0_3`), and any profile name/version distinct in any
report — never conflate "this skill said X" with "the strategy decided Y."

## Guardrails

- This skill has no independent broker execution authority, same as every skill in the
  pyramid. Actual execution is delegated to `execution/executor.py` via
  `assistant/commands.py` and requires a fresh, explicit user execution command that
  turn (`AGENTS.md` "Authority order" point 4) — this skill never approaches that path.
- Never report this skill's `alignment`/`layers` output as if it were a `TradeSignal` or
  a registered strategy's decision. If a registered strategy is in play, run/cite
  `strategy_engine.evaluate()` (via `strategy-management`) and lead with its result;
  offer this skill's cross-timeframe read as separate, clearly labeled context.
- Do not manufacture a role's state from incomplete history. `INSUFFICIENT_DATA` /
  `DATA_ERROR` are valid, expected terminal states for a role or the whole context —
  never silently promote them to `NEUTRAL`.
- Do not hardcode D1/H4/H1/M15 as *the* hierarchy anywhere this skill is invoked from —
  always take the profile the caller (or the consuming strategy, once one exists)
  actually needs.
- Never silently adopt a numeric assumption not already authoritative in this
  repository (e.g. "minimum 1:3 RR", "50% FVG entry", "mandatory H4/H1 alignment"). If
  asked to apply one, label it `UNSIGNED` / `RESEARCH_PARAMETER` and say which strategy
  (if any) would need to sign it — do not freeze it here.
- `MANAGEMENT`-role output is advisory context only; it must never move SL/TP,
  partial-close, or otherwise touch an open position — that remains
  `trade_management/*` via `trade_management.manager`, independently gated
  (`AGENTS.md` point 5).
