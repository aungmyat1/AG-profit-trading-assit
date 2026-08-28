# ENTRY_CONFIRMATION_V1 Spec — 2026-08-27

Package: `entry_confirmation/`. Public entry point: `evaluate_entry_confirmation()`.
Agent skill: `.claude/skills/entry-confirmation-analysis/` (mirrored in
`.agents/skills/`). Registry entry: `.claude/skills/SKILL_REGISTRY.yaml`.

## Objective

Answer, deterministically: *given a proposed direction and requested confirmation
types, what confirmation evidence exists?*

## Non-objective

This capability never answers *"should I buy or sell?"* It never produces a trade
signal, never calls execution, and never invents a universal SMC entry formula (no
`sweep + CHoCH + FVG = BUY`, no confidence score, no `3 confirmations = valid`). The
caller — a human via the assistant, or a signed strategy — owns qualification of the
returned facts.

## Architecture boundary

```
Market Context
      |
      +-- Market Structure  --> StructureResult (caller already has this)
      +-- Liquidity          --> LiquidityResult (caller already has this)
              |
              v
      Entry & Confirmation  (entry_confirmation.evaluate_entry_confirmation)
              |
              v
      EntryConfirmationResult (structured facts)
              |
       +------+------+
       |             |
  Human Assistant   Signed Strategy
  (interprets)      (applies its own rules)
```

This package never fetches MT5 data, never re-detects swings/BOS/CHoCH, and never
re-detects sweeps/reclaims. `structure_shift` consumes
`market_structure.StructureResult.latest_choch` verbatim; `liquidity_reclaim` consumes
`liquidity.LiquidityResult.nearest_buy_side`/`nearest_sell_side` verbatim. Candle-level
primitives (`displacement`, `rejection`) receive a caller-supplied
`strategy_engine.session.Candle` — the same `Candle` dataclass `supply_demand` already
imports from `strategy_engine.session`, not a new candle model.

## Audit performed before coding

Searched `market_structure/`, `supply_demand/`, `liquidity/`, `strategy_engine/`,
`execution/`, `trade_management/`, every `config/*.yaml`, and every `SKILL.md` for
existing definitions of displacement, rejection/reversal candles, CHoCH/BOS
confirmation, liquidity reclaim, and FVG confirmation.

| Entry confirmation primitive | Current implementation found | Rule source | Owner | Status | Reusable? | Action |
|---|---|---|---|---|---|---|
| CHoCH event | `market_structure/analyzer.py` -> `StructureResult.latest_choch` | AG structure contract | `market-structure` | SIGNED | YES | CONSUME ONLY (`structure_alignment.py`) |
| Sweep/reclaim event (generic) | `liquidity/status.py` state machine -> `LiquidityResult` | `AG_LIQUIDITY_V1` | `liquidity` | SIGNED | YES | CONSUME ONLY (`liquidity_alignment.py`) |
| Session-level displacement, `efficiency_ratio` | `strategy_engine/session/reference_box.py` (`ER_ONLY_V2`) | Strategy config | `ST_ASIAN_SWEEP_5R_V1` | STRATEGY_SPECIFIC, SIGNED | NO (session-level, not candle-level; different question) | DO NOT GLOBALIZE |
| Range-boundary rejection candle | `strategy_engine/session/setups.py` (`upper_rejection`/`lower_rejection`) | Strategy config | `ST_ASIAN_SWEEP_5R_V1` | STRATEGY_SPECIFIC, SIGNED | NO (tied to that strategy's own session box boundaries) | DO NOT GLOBALIZE |
| Qualified RANGE sweep | `strategy_engine/session/setups.py::entry_2_sweep` | `SESSION_FLOW_V2_SIMPLE` | `ST_ASIAN_SWEEP_5R_V1` | STRATEGY_SPECIFIC, SIGNED | NO | DO NOT GLOBALIZE; generic `liquidity_reclaim` primitive used instead |
| Order-Block origin candle body-ratio (PIVOT vs SHADOW) | `supply_demand/ob_contract.py`, `config/ag_order_block_v1.yaml` (`pivot_shadow_body_ratio_threshold`) | `AG_ORDER_BLOCK_V1` | `supply-demand` | SIGNED, but answers a different question (zone family, not entry qualification) | NO (would silently globalize a supply-demand-specific number) | DO NOT REUSE AS A GENERIC THRESHOLD |
| Generic candle-level displacement qualification | — (searched, not found anywhere) | — | — | UNSIGNED | N/A | Implement MEASUREMENT only; report `UNSIGNED_RULE` for qualification |
| Generic candle-level rejection/reversal qualification | — (searched, not found anywhere) | — | — | UNSIGNED | N/A | Implement MEASUREMENT only; report `UNSIGNED_RULE` for qualification |
| FVG retest / OB reaction / breaker / mitigation-block confirmation | — (searched, not found as a confirmation rule; FVG/OB *creation* facts exist in `supply_demand/`) | — | — | RESEARCH_ONLY / UNSIGNED | N/A | NOT IN SCOPE for V1 (mission's explicit narrow-scope instruction) |

Full detail on the two signed-but-not-reusable body-ratio thresholds:
`entry_confirmation/contract.py`'s module docstring and
`ENTRY_CONFIRMATION_CONTRACT_GAPS`.

## Request contract — `EntryConfirmationRequest`

```python
EntryConfirmationRequest(
    symbol: str,
    timeframe: str,
    candidate_direction: CandidateDirection = NONE,   # LONG / SHORT / NONE
    requested_confirmations: Tuple[str, ...] = (),      # subset of ALL_CONFIRMATIONS
    reference_time: Optional[datetime] = None,          # optional staleness filter for structure_shift
    candidate_candle: Optional[Candle] = None,           # for displacement / rejection
    structure_result: Optional[StructureResult] = None,  # caller-supplied, never recomputed
    liquidity_result: Optional[LiquidityResult] = None,  # caller-supplied, never recomputed
)
```

`ALL_CONFIRMATIONS = ("displacement", "structure_shift", "liquidity_reclaim", "rejection")`.
Only requested primitives are evaluated; the rest report `NOT_REQUESTED`. Passing an
unknown key raises `ValueError` (fail loud on a caller bug, rather than silently
ignoring a typo'd confirmation type).

## Result contract — `EntryConfirmationResult`

```python
EntryConfirmationResult(
    symbol, timeframe, candidate_direction, status,   # status == "EVALUATED" always in V1
    displacement: DisplacementEvidence,
    structure_shift: StructureAlignment,
    liquidity_reclaim: LiquidityAlignment,
    rejection: RejectionEvidence,
    overall_state: OverallState,
    requested_confirmations, missing_requirements, rule_versions, contract_version,
)
```

## Status vocabulary (`ConfirmationState`, per-primitive)

```
PASS                evidence aligns with candidate_direction / measurement qualifies
FAIL                evidence contradicts candidate_direction / does not qualify
NOT_REQUESTED       caller did not request this primitive
UNAVAILABLE         no upstream result/candle was supplied, or upstream produced no event
INSUFFICIENT_DATA   upstream result exists but is not valid/complete enough to use
UNSIGNED_RULE       measurement computed, but no owner-signed qualifying threshold exists
ERROR               reserved, not currently produced (no exception path returns this in V1)
```

## Supported primitives

1. **`displacement`** — candle measurement (`body_size`, `range_size`, `body_ratio`,
   `close_location`, `direction`) from a caller-supplied `Candle`. Qualification:
   `UNSIGNED_RULE` (see contract gaps).
2. **`structure_shift`** — alignment of `StructureResult.latest_choch` with
   `candidate_direction`. `BULLISH_CHOCH` aligns with `LONG`, `BEARISH_CHOCH` with
   `SHORT`. An optional `reference_time` fails a CHoCH that predates it (stale
   evidence). Scoped to CHoCH only (SMC's "structure shift" term) — BOS is a different
   question and remains available directly from `StructureResult.latest_bos` for a
   future primitive if ever authorized.
3. **`liquidity_reclaim`** — alignment of the relevant-side nearest `LiquidityLevel`
   with `candidate_direction`: `LONG` needs `SELL_SIDE` `RECLAIMED`; `SHORT` needs
   `BUY_SIDE` `RECLAIMED`. `SWEPT` (live, unconfirmed) reports `INSUFFICIENT_DATA`;
   `UNSWEPT`/`CONSUMED` report `FAIL`; missing level reports `FAIL`; missing/invalid
   result reports `UNAVAILABLE`/`INSUFFICIENT_DATA`.
4. **`rejection`** — candle measurement (`body`, `range`, `upper_wick`, `lower_wick`,
   wick ratios, `close_location`, `direction`). Qualification: `UNSIGNED_RULE`.

Not implemented in V1 (per mission scope): FVG retest, order-block reaction, breaker/
mitigation-block confirmation, multi-timeframe confluence, any numeric score.

## Measurement vs. qualification

Every primitive's *measurement* (the arithmetic) is always computed and always
trustworthy. *Qualification* (does this measurement count as "confirmed") requires an
owner-signed threshold. For `displacement`/`rejection`, no such threshold exists
anywhere in this repo for a generic candle (the only body-ratio threshold found,
`config/ag_order_block_v1.yaml`'s `pivot_shadow_body_ratio_threshold`, is signed for a
different question — Order Block family classification — and reusing it here would
silently globalize a supply-demand-specific number). `structure_shift` and
`liquidity_reclaim` need no new threshold: they only check alignment of an
already-qualified event.

## Signed vs. unsigned rules

```
SIGNED   : structure_shift alignment (market_structure's own StructureResult)
           liquidity_reclaim alignment (liquidity's own LiquidityResult)
           all candle measurements (pure arithmetic)
UNSIGNED : displacement qualification threshold
           rejection/reversal qualification threshold
```

## Aggregation behavior — `overall_state`

```
no requested confirmations                                    -> INDETERMINATE
any requested confirmation is UNSIGNED_RULE / UNAVAILABLE /
    INSUFFICIENT_DATA / ERROR                                  -> INDETERMINATE
otherwise (all requested resolve to PASS/FAIL):
    all PASS                                                    -> CONFIRMED
    all FAIL                                                    -> NOT_CONFIRMED
    mixed                                                        -> PARTIAL
```

`overall_state` never implies `TRADE = VALID`. It only summarizes how much of the
*requested* evidence points the same way.

## Upstream dependencies

`market_structure.StructureResult`, `liquidity.LiquidityResult`,
`strategy_engine.session.Candle`. No dependency on `supply_demand`, `execution`, or
`trade_management` in V1.

## Strategy boundary

A future strategy may declare `entry_confirmation: {required: [...]}` in its own
contract and call `evaluate_entry_confirmation()` directly with its own
`candidate_direction`/candle/upstream results, then apply its own sufficiency rule to
the returned facts. This spec does not add any such requirement to
`SESSION_TRADE_V1`'s or `ST_ASIAN_SWEEP_5R_V1`'s existing signed contracts — neither
was touched by this pass.

## Examples

**Example 1 — full positive evidence (synthetic test data, not live market evidence):**

```
Candidate: LONG
Requested: structure_shift, liquidity_reclaim
Structure: latest_choch = BULLISH_CHOCH
Liquidity: nearest_sell_side.status = RECLAIMED

structure_shift    = PASS
liquidity_reclaim  = PASS
overall_state      = CONFIRMED
```

(See `tests/test_entry_confirmation.py::test_aggregation_all_pass_is_confirmed`.)

**Example 2 — mixed evidence:**

```
Candidate: SHORT
Requested: structure_shift, liquidity_reclaim
Structure: latest_choch = BEARISH_CHOCH        -> structure_shift = PASS
Liquidity: nearest_buy_side.status = UNSWEPT   -> liquidity_reclaim = FAIL

overall_state = PARTIAL
```

This demonstrates confirmation facts != an automatic SHORT signal — `PARTIAL` says
"some but not all requested evidence agrees," nothing more.

## Known gaps

1. `displacement` and `rejection` qualification thresholds are `UNSIGNED` — an owner
   needs to sign a generic candle-level threshold (or explicitly authorize reusing an
   existing strategy/capability-specific one) before these can report `PASS`/`FAIL`.
2. `structure_shift` is scoped to CHoCH only; BOS-based alignment is not implemented as
   its own primitive (available directly from `StructureResult.latest_bos` if needed later).
3. FVG/order-block/breaker/mitigation confirmation primitives are not implemented —
   no signed definition found, and out of the mission's V1 scope.
