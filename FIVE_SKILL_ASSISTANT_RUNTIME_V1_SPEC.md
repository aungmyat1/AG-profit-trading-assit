# FIVE_SKILL_ASSISTANT_RUNTIME_V1 Spec — 2026-08-28

Package: `assistant/` (new modules: `analysis_models.py`, `five_skill_runtime.py`,
`assessment.py`; `__init__.py` updated to export the new public surface).
Public entry points: `assistant.analyze_market()`, `assistant.build_assistant_assessment()`.

## Objective

Integrate the five existing deterministic capabilities into one usable runtime:

```
request -> Market Context -> requested skills -> structured facts -> assessment/report
```

READ, ANALYZE, SYNTHESIZE, REPORT. Not an execution runtime.

## Non-objectives

- Does not implement new trading intelligence: no new displacement/rejection
  thresholds, no new BOS/CHoCH/Order Block/liquidity/Trend-Range/Sweep rules, no new
  SL/TP/risk-percent defaults, no AI confidence score, no automatic BUY/SELL logic.
- Does not call `order_send`/`order_check`/position-modify (verified by AST tests).
- Does not require a registered strategy (`strategy_id` is never a field on
  `AssistantAnalysisRequest`).
- Does not redesign `assistant.runtime.evaluate()` (the existing strategy-execution
  path, `ASSISTANT_RUNTIME_V1`) -- both coexist as separate public functions in the
  same package. See "Strategy independence" below.

## Audit performed before coding

Inspected `assistant/` (`runtime.py` already existed -- ASSISTANT_RUNTIME_V1, strategy-
execution path, requires `strategy_id`; kept untouched), `market_structure/`,
`supply_demand/`, `liquidity/`, `entry_confirmation/`, `trade_management/`,
`strategy_manager/`, `execution/`, `mt5/`. No competing generic runtime existed --
`assistant/market_data.py`'s five functions (`market_snapshot`, `historical_candles`,
`session_snapshot`, `data_health`, `multi_timeframe_snapshot`) are foundation-layer
utilities, not an orchestrator across the five core skills.

| Component | Current implementation | Input | Output | Authority | Action |
|---|---|---|---|---|---|
| Market context / tick+quality snapshot | `assistant.market_data.market_snapshot()` | symbol, timeframe | `MarketSnapshot` (bid/ask/freshness/latest candle) | Foundation, READY | REUSE_DIRECTLY -- this IS the shared context builder |
| Market Structure | `market_structure.analyze_structure(symbol, timeframe)` | symbol, timeframe | `StructureResult` | Core, frozen | REUSE_DIRECTLY |
| Supply & Demand (validated OBs) | `supply_demand.validated_order_blocks_for(symbol, timeframe)` | symbol, timeframe | `List[ValidatedOrderBlock]` (**not** `ZoneQueryResult` -- verified, not assumed; see "Known limitations") | Core, frozen (`AG_ORDER_BLOCK_V1`) | REUSE_DIRECTLY |
| Supply & Demand (FVG) | `supply_demand.fair_value_gaps_for(symbol, timeframe)` | symbol, timeframe | `ZoneQueryResult` | Core, frozen | REUSE_DIRECTLY |
| Liquidity | `liquidity.liquidity_result(symbol, timeframe)` | symbol, timeframe | `LiquidityResult` | Core, frozen | REUSE_DIRECTLY |
| Entry & Confirmation | `entry_confirmation.evaluate_entry_confirmation()` | `EntryConfirmationRequest` | `EntryConfirmationResult` | Core, PARTIAL (2 of 4 primitives UNSIGNED) | REUSE_DIRECTLY |
| Trade Management | `trade_management.evaluate_trade_management()` | `TradeManagementRequest` | `TradeManagementResult` | Core, READY | REUSE_DIRECTLY |
| Strategy dispatch | `assistant.runtime.evaluate()` + `strategy_manager.manager` | strategy_id, symbol, cycle, mode | `AssistantDecision` | Optional use case, unchanged | LEGACY (relative to this task) -- preserved as-is, not touched |
| Execution | `execution/` | -- | -- | Paused, unchanged | Not imported anywhere in the new modules (AST-verified) |

## Architecture boundary

```
AssistantAnalysisRequest
        |
        v
assistant.market_data.market_snapshot()  <- built exactly once per analyze_market() call
        |
    +---+---+-------+
    v       v       v
Structure  S/D  Liquidity   (each requested independently; see "Skill dependencies")
    +-------+-------+
            v
   Entry & Confirmation   (auto-includes Structure+Liquidity as its own declared
                            upstream dependencies when requested -- see below)
            |
            v
   Trade Management        (gated purely by `request.candidate` presence, independent
                             of requested_skills)
            |
            v
   FiveSkillAnalysisResult -> build_assistant_assessment() -> AssistantAssessment
```

## Request model — `AssistantAnalysisRequest`

```python
AssistantAnalysisRequest(
    symbol: str, timeframe: str = "M15",
    requested_skills: Tuple[str, ...] = REQUESTABLE_MARKET_SKILLS,   # any of the four below
    requested_confirmations: Tuple[str, ...] = entry_confirmation.ALL_CONFIRMATIONS,
    candidate: Optional[TradeCandidate] = None,
)
```

`REQUESTABLE_MARKET_SKILLS = ("market-structure", "supply-demand", "liquidity",
"entry-confirmation")` -- the same string identifiers as
`.claude/skills/SKILL_REGISTRY.yaml` and `TRADE_ASSISTANT_ARCHITECTURE.md`'s taxonomy.
`trade-management` is deliberately **not** a member: it activates purely from
`request.candidate` being supplied (mission section 9/20/21), never from
`requested_skills`. An unknown skill name raises `InvalidAnalysisRequest`. No field
requires a strategy.

`TradeCandidate` carries the manually- or strategy-supplied proposed trade
(`direction`, `entry_price`, `stop_loss`, `take_profit`, `risk_percent`/`risk_amount`,
`equity`, `symbol_meta`, `current_price`, `management_policy`) -- identical fields to
`trade_management.TradeManagementRequest` minus `symbol` (taken from the parent
request).

## Result model — `FiveSkillAnalysisResult`

```python
FiveSkillAnalysisResult(
    symbol, timeframe, timestamp_utc, market_context_status,
    structure: Optional[StructureResult],
    supply_demand: Optional[SupplyDemandBundle],
    liquidity: Optional[LiquidityResult],
    entry_confirmation: Optional[EntryConfirmationResult],
    trade_management: Optional[TradeManagementResult],
    skill_statuses: Dict[str, str], overall_status: str,
    limitations: Tuple[str, ...], errors: Tuple[str, ...],
)
```

Each field is the capability's own structured result, unmodified -- never flattened
into a shared schema. `SupplyDemandBundle` (new, thin) composes
`validated_order_blocks: Tuple[ValidatedOrderBlock, ...]` and
`fair_value_gaps: ZoneQueryResult` -- see "Known limitations" for why these two have
different shapes.

## MarketContext lifecycle ("build once")

`market_snapshot(symbol, timeframe)` is called exactly once per `analyze_market()`
call, regardless of how many skills are requested (proven by
`test_market_context_built_exactly_once_per_analysis`, mocking the call and asserting
`call_count == 1`). Its result is reused for: (1) the data-quality gate below, (2) the
`candidate_candle` fed to Entry Confirmation's displacement/rejection primitives, and
(3) the default `current_price` for Trade Management's position-state advisory when the
caller didn't supply one.

**Known, pre-existing limitation, not introduced by this phase:** `analyze_structure()`,
`liquidity_result()`, `validated_order_blocks_for()`, and `fair_value_gaps_for()` each
independently fetch their own candles from MT5 internally (different warmup/count
requirements per frozen algorithm -- e.g. Structure needs `swing_length * 20` warmup
bars; `liquidity_result()` even calls `analyze_structure()` internally a second time,
per its own docstring: "Reuses StructureResult... rather than recalculating"). None of
these four functions accept a pre-fetched candle set as a parameter. Changing that would
mean altering frozen capability module signatures/internals, which the mission
explicitly prohibits ("do not change Market Structure/Supply-Demand/Liquidity
algorithms"). This phase does not attempt it. The runtime-level "one snapshot" guarantee
above covers everything that is actually shareable without touching frozen internals;
full candle-level snapshot reuse across all three core skills remains a future
capability-layer change, not a runtime plumbing change.

## Data quality gate

`context_ready = snapshot.status == "OK" and snapshot.freshness in (None, "OK")`.
`market_context_status` reuses `mt5.market_data`'s own existing vocabulary verbatim
(`MT5_NOT_CONNECTED`, `SYMBOL_NOT_FOUND`, `INSUFFICIENT_CANDLES`, `STALE_DATA`, etc. --
no new codes invented) rather than the mission's suggested-but-unverified
`SYMBOL_UNRESOLVED`/`DATA_GAPPED`. When not ready, Structure/Supply-Demand/Liquidity/
Entry-Confirmation report `UNAVAILABLE` without being invoked -- no silent fallback to a
"normal" analysis. Trade Management is **not** gated by this (see below).

## Skill dependencies

```
market_snapshot
    -> market-structure
    -> supply-demand
    -> liquidity

market-structure + liquidity + optional candidate direction
    -> entry-confirmation   (auto-requested when entry-confirmation itself is requested)

TradeCandidate + (equity, symbol_meta)
    -> trade-management     (independent of market_snapshot readiness -- pure geometry/
                              sizing math over caller-supplied prices)
```

Requesting `entry-confirmation` automatically resolves `market-structure` and
`liquidity` as its own declared upstream dependencies (verified:
`test_entry_confirmation_auto_pulls_structure_and_liquidity`) -- this is closing a
declared dependency edge, not "running everything": `supply-demand` is **not**
auto-included (Entry Confirmation V1 does not consume it). No dependency was invented
from Supply-Demand toward Structure or Liquidity toward Supply-Demand at the runtime
level, per the mission's explicit instruction.

## Selective skill invocation

Verified by `test_selective_invocation_market_structure_only` and
`test_selective_invocation_liquidity_only`: requesting one skill invokes only
`market_snapshot` + that skill's own function; the other three skill-fetch functions
are asserted to have `call_count == 0`.

## Entry Confirmation partial semantics (preserved, not solved)

`ec_request.candidate_candle` = the shared snapshot's `latest_closed_candle`;
`candidate_direction` = `request.candidate.direction` if a `TradeCandidate` is supplied,
else `CandidateDirection.NONE`; `structure_result`/`liquidity_result` are whatever was
computed above (`None` if not requested, in which case those two primitives report
`UNAVAILABLE`, never fabricated). The default `requested_confirmations` includes
`displacement`/`rejection`, both always `UNSIGNED_RULE` -- so a default-configuration
call's `entry_confirmation.overall_state` is `INDETERMINATE`, mapped to
`skill_statuses["entry-confirmation"] = "PARTIAL"`. This survives unmodified into
`FiveSkillAnalysisResult` and the rendered report (verified:
`test_unsigned_displacement_survives_to_result_and_report`, which asserts
`"UNSIGNED_RULE"` appears in the report text and is never rewritten to `PASS`). A
caller can narrow `requested_confirmations` to only the two signed primitives
(`structure_shift`, `liquidity_reclaim`) to get a definitive `READY` status
(`test_narrowed_confirmations_avoid_unsigned_indeterminate`).

## Trade Management candidate/no-candidate semantics

`request.candidate is None` -> `trade_management = None`,
`skill_statuses["trade-management"] = "NO_CANDIDATE"` -- this never counts as a failure
in `overall_status` aggregation (`test_no_candidate_mode_does_not_fail_analysis`).
Supplying a `TradeCandidate` always attempts `evaluate_trade_management()`, entirely
independent of `market_context_status` or `requested_skills`
(`test_trade_management_runs_without_any_market_skill_requested`,
`test_context_unavailable_does_not_block_trade_management`) -- Trade Management's
geometry/sizing math needs only caller-supplied prices/equity/symbol metadata, not live
market data.

## Assessment layer

`build_assistant_assessment(result) -> AssistantAssessment(report_text, evidence_summary)`
is pure formatting over `FiveSkillAnalysisResult`'s already-computed fields (same
discipline as `assistant/report.py`). It never states BUY/SELL/ENTER-NOW, never invents
a numeric confidence score -- `evidence_summary` is a `Tuple[str, ...]` of
`"<skill>: <status>"` lines instead, the auditable "evidence completeness" record the
mission requires in place of a fake probability.

## Overall status aggregation

```python
considered = {skill: status for skill, status in skill_statuses.items()
              if status not in (NOT_REQUESTED, NO_CANDIDATE)}
if not considered: READY
elif all considered == READY: READY
elif all considered in (UNAVAILABLE, BLOCKED): BLOCKED
else: PARTIAL
```

One unavailable/partial optional skill downgrades to `PARTIAL`, never destroys the
whole analysis (mission section 58) -- verified across every scenario test above.

## Strategy independence

`assistant.five_skill_runtime`, `assistant.analysis_models`, and `assistant.assessment`
import neither `strategy_manager` nor any strategy-specific module (verified by an AST
import scan, `test_five_skill_runtime_module_does_not_import_strategy_manager`).
`assistant.runtime.evaluate()` (the pre-existing strategy path) is untouched and
remains importable/usable independently -- `Analyze EURUSD` never touches
`strategies/registry.yaml` or any adapter.

## Execution independence

Verified by AST import + call scans across the same three modules
(`test_five_skill_runtime_module_has_no_execution_imports_or_broker_write_calls`): no
`execution` import, no literal `order_send`/`order_check` call anywhere in the generic
runtime path.

## Conformance requirements (`trade_management` vs. `execution/`)

`trade_management/sizing.py` reimplements (does not import) `execution/risk.py`'s
formula; `trade_management/geometry.py` overlaps with
`execution/validator.py::validate_geometry()`'s sign checks. `tests/
test_trade_management_execution_conformance.py`:

- **Sizing**: parametrized across synthetic EURUSD/USDJPY/XAUUSD fixtures, comparing
  `execution.risk.size_position()` against `trade_management.sizing.evaluate_sizing()`
  for identical inputs -- normalized volume and actual risk amount agree to `1e-9`
  relative tolerance on every READY case, and both agree on `VOLUME_BELOW_MIN`/
  `VOLUME_ABOVE_MAX` rejection (never a silent cap). **Result: PASS, no drift.**
- **Geometry**: six parametrized LONG/SHORT valid/invalid-SL/invalid-target cases plus
  zero-stop-distance, comparing `execution.validator.validate_geometry()` (via
  synthetic `TradeSignal`/`StrategyConfig` fixtures) against
  `trade_management.geometry.evaluate_geometry()`. Both agree on PASS/FAIL
  classification in every case. Reason-code **strings** differ by design
  (`INVALID_ENTRY_GEOMETRY`/`INVALID_STOP_DISTANCE` in `execution/`, predating this
  phase, vs. trade_management's more granular `INVALID_LONG_STOP`/
  `GEOMETRY_ZERO_STOP_DISTANCE` etc.) -- documented as `SEMANTIC_DIFFERENCE` in naming
  only, not a classification disagreement. **Result: PASS, no drift**, no correction made
  to either implementation (per the mission's "do not silently patch one implementation
  just to pass the test" instruction -- there was nothing to patch).

## Error handling

Structured statuses throughout (`MARKET_CONTEXT_UNAVAILABLE` recorded in `errors`,
per-skill `UNAVAILABLE`/`PARTIAL`/`BLOCKED`, `INDETERMINATE` at the Entry Confirmation
level) -- no swallowed exceptions. An unknown `requested_skills` entry raises
`InvalidAnalysisRequest` (programmer error, not a runtime data condition). Unexpected
programming errors inside a capability still propagate, matching existing project
convention (no blanket `except Exception` anywhere in the new modules).

## Examples

Both are exercised end-to-end against a live MT5 terminal in
`tests/test_five_skill_runtime.py` (skipif-guarded, matching
`tests/test_assistant_market_data.py`'s pattern) — a real bug (see "Known limitations"
below) was caught only by running these live, not by the mocked unit tests alone.

**Generic analysis, no strategy** (`test_acceptance_analyze_eurusd_m15_without_strategy_live`):

```python
result = analyze_market(AssistantAnalysisRequest(symbol="EURUSD", timeframe="M15"))
# result.trade_management is None; skill_statuses["trade-management"] == "NO_CANDIDATE"
```

**Manual candidate, no strategy** (`test_acceptance_manual_candidate_evaluation_live`):

```python
candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750,
                            take_profit=1.18000, risk_percent=1.0, equity=10000.0,
                            symbol_meta=<EURUSD SymbolMeta>)
result = analyze_market(AssistantAnalysisRequest(symbol="EURUSD", candidate=candidate))
# result.trade_management.geometry.rr_multiple == 4.0
```

## Known limitations

1. **`validated_order_blocks_for()` returns `List[ValidatedOrderBlock]`, not
   `ZoneQueryResult`** -- unlike its sibling `order_blocks_for()`/`fair_value_gaps_for()`.
   It fails silently to `[]` on a `MarketDataError`, with no status/reason_code of its
   own. Discovered only by the live acceptance test (the mocked unit tests had
   assumed the wrong shape and would not have caught this). `SupplyDemandBundle` now
   reflects the real shape; `skill_statuses["supply-demand"]`'s READY/PARTIAL judgment
   is driven by `fair_value_gaps`'s own status instead, since `validated_order_blocks`
   carries no status of its own. Not fixed inside `supply_demand/` (frozen, out of
   scope) -- only the runtime's own assumption was corrected.
2. Full candle-level MarketContext sharing across Structure/Supply-Demand/Liquidity is
   not implemented -- see "MarketContext lifecycle" above. Each still performs its own
   internal MT5 fetch, a pre-existing characteristic of frozen capability code.
3. Entry Confirmation's `displacement`/`rejection` qualification remains `UNSIGNED_RULE`
   (unchanged, not solved this phase, per explicit mission instruction).
4. Generic pip conversion remains unavailable in Trade Management (unchanged, not
   solved this phase).
5. Strategy Manager integration (`assistant.runtime.evaluate()`) was not touched or
   deepened this phase -- it remains available as a fully separate, optional path.
