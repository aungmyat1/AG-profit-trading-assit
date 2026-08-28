# FIVE_SKILL_ASSISTANT_RUNTIME_V1 — Status / Evidence Report

2026-08-28. Evidence only — see `FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md` for
architecture/design and `SKILL_OPTIMIZATION_STATUS.md` /
`ENTRY_CONFIRMATION_V1_SPEC.md` / `TRADE_MANAGEMENT_V1_SPEC.md` for prior-phase context.

## Baseline (before this phase)

`pytest tests/ -q`: **362 passed, 1 skipped** (`test_market_data.py`'s
"today's Asian session has not completed yet" — a legitimate, time-of-day-dependent
skip, not a regression; the prompt's claimed "363 passed, 0 failed, 0 skipped" does not
match what was actually observed when this phase started — recorded per the mission's
own "do not trust these values merely because this prompt says so" instruction).

## Implementation inventory

| File | Status | Purpose |
|---|---|---|
| `assistant/analysis_models.py` | NEW | `AssistantAnalysisRequest`, `TradeCandidate`, `FiveSkillAnalysisResult`, `SupplyDemandBundle`, skill/status vocabulary |
| `assistant/five_skill_runtime.py` | NEW | `analyze_market()` — the generic runtime |
| `assistant/assessment.py` | NEW | `build_assistant_assessment()` — pure report formatting |
| `assistant/__init__.py` | UPDATED | Was stale ("scaffolding only, not yet implemented"); now documents and exports both public runtime entry points |
| `tests/test_five_skill_runtime.py` | NEW | 18 tests (16 mocked + 2 live-guarded acceptance) |
| `tests/test_trade_management_execution_conformance.py` | NEW | 15 conformance tests (sizing + geometry vs. `execution/`) |
| `TRADE_ASSISTANT_ARCHITECTURE.md` | UPDATED | New "Generic Trade Assistant runtime" section; test count refreshed |
| `.claude/skills/SKILL_REGISTRY.yaml`, `.agents/skills/SKILL_REGISTRY.yaml` | UPDATED | Note on the new runtime (mirrors kept identical) |
| `FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md` | NEW | Full contract |

No existing file's algorithm was changed. `assistant/runtime.py` (the strategy-execution
path) is untouched.

## Runtime architecture

```
AssistantAnalysisRequest -> market_snapshot() [built once] -> requested skills
    -> FiveSkillAnalysisResult -> build_assistant_assessment() -> report
```

See the spec's architecture diagram for the full data flow, including Entry
Confirmation's auto-inclusion of Structure+Liquidity as its own declared dependency.

## Request/result contracts

`AssistantAnalysisRequest` (symbol, timeframe, requested_skills, requested_confirmations,
candidate) and `FiveSkillAnalysisResult` (per-skill structured results + skill_statuses +
overall_status + limitations + errors) — both READY, fully exercised by tests.

## Shared context behavior

`market_snapshot()` proven called exactly once per `analyze_market()` call regardless of
how many skills/candidate are involved (`test_market_context_built_exactly_once_per_analysis`).
Structure/Supply-Demand/Liquidity each still perform their own internal MT5 candle fetch
(pre-existing, frozen behavior — see spec's "Known limitations" #2); this was verified,
not assumed, by reading `liquidity/analyzer.py` and `supply_demand/analyzer.py` directly.

## Selective invocation evidence

`test_selective_invocation_market_structure_only` and `..._liquidity_only`: requesting
one skill invokes only `market_snapshot` + that skill's function; the other three
skill-fetch mocks assert `call_count == 0`.

## Manual candidate evidence

`test_manual_candidate_full_pipeline_no_strategy` (mocked) and
`test_acceptance_manual_candidate_evaluation_live` (real MT5): LONG EURUSD, entry
1.17000/SL 1.16750/TP 1.18000/risk 1%/equity $10,000 -> `rr_multiple == 4.0`,
`normalized_volume == 0.40`, `overall_status == "READY"`, zero broker calls, no strategy
loaded.

## Partial skill behavior

Default `requested_confirmations` (includes `displacement`/`rejection`, both always
`UNSIGNED_RULE`) drives `entry_confirmation.overall_state = INDETERMINATE`,
`skill_statuses["entry-confirmation"] = "PARTIAL"`, `overall_status = "PARTIAL"` —
verified end-to-end into the rendered report text
(`test_unsigned_displacement_survives_to_result_and_report` asserts `"UNSIGNED_RULE"`
appears and is never rewritten to `PASS`/`FAIL`). Narrowing to the two signed
primitives yields `READY` (`test_narrowed_confirmations_avoid_unsigned_indeterminate`).

## Strategy independence

AST-verified: `assistant/five_skill_runtime.py`, `analysis_models.py`, `assessment.py`
import no `strategy_manager` module
(`test_five_skill_runtime_module_does_not_import_strategy_manager`). Live acceptance
test `test_acceptance_analyze_eurusd_m15_without_strategy_live` ran a real
`Analyze EURUSD M15` end-to-end with zero strategy registry lookups.

## Execution independence

AST-verified (import scan + call scan): no `execution` import, no `order_send`/
`order_check` call anywhere in the three new modules
(`test_five_skill_runtime_module_has_no_execution_imports_or_broker_write_calls`).

## Sizing conformance

`trade_management.sizing.evaluate_sizing()` vs. `execution.risk.size_position()` across
5 synthetic EURUSD/USDJPY/XAUUSD fixtures: normalized volume and actual risk amount
agree to `1e-9` relative tolerance on every READY case; `VOLUME_BELOW_MIN`/
`VOLUME_ABOVE_MAX` rejection agrees (neither silently caps or forces a minimum).
**Result: PASS, `IMPLEMENTATION_DRIFT = NONE`.**

## Geometry conformance

`trade_management.geometry.evaluate_geometry()` vs.
`execution.validator.validate_geometry()` (via synthetic `TradeSignal`/`StrategyConfig`
fixtures) across 6 LONG/SHORT valid/invalid-SL/invalid-target cases + zero-stop-distance:
both agree on PASS/FAIL classification in every case. Reason-code **strings** differ
(`INVALID_ENTRY_GEOMETRY` vs. `INVALID_LONG_STOP` etc.) — a documented, pre-existing
`SEMANTIC_DIFFERENCE` in naming only, not a classification disagreement. **Result:
PASS, `IMPLEMENTATION_DRIFT = NONE`.** No correction made to either implementation —
none was needed.

## A real bug the live acceptance tests caught (not the mocked unit tests)

`supply_demand.validated_order_blocks_for()` returns a plain `List[ValidatedOrderBlock]`,
**not** a `ZoneQueryResult` like its sibling `fair_value_gaps_for()` — confirmed by
reading `supply_demand/analyzer.py`'s actual return statement, not assumed from its
docstring or from `order_blocks_for()`'s shape. The first version of
`five_skill_runtime.py` assumed the `ZoneQueryResult` shape and passed the mocked-unit
tests fine, but crashed (`AttributeError: 'list' object has no attribute 'status'`)
against the real function during the live acceptance test. Fixed by changing
`SupplyDemandBundle.validated_order_blocks` to `Tuple[ValidatedOrderBlock, ...]` and
deriving the supply-demand `skill_statuses` READY/PARTIAL judgment from
`fair_value_gaps`'s own status instead (documented in the spec's "Known limitations").
This is exactly why the mission required live acceptance tests, not mocks alone.

## Tests

```
BASELINE (before this phase) = 362 passed, 1 skipped, 0 failed
NEW THIS PHASE                = 33  (18 in test_five_skill_runtime.py + 15 in
                                       test_trade_management_execution_conformance.py)
FINAL                          = 396 passed, 0 failed, 0 skipped
                                  (the earlier skip resolved itself once the Asian
                                  session completed during this session — not a fix)
```

## Session Trade Codex

```
STATUS = NOT_RE-RUN
REASON = No file under Session Trade Codex's own dependency surface
         (session_strategy/, execute_session_signal.py, or this repo's
         market_structure/ package which it cross-imports) was touched this phase.
         Only assistant/, a new tests/ file, and two markdown docs changed.
```

## Known gaps

1. `validated_order_blocks_for()`'s silent-empty-list-on-failure behavior (no
   status/reason_code) is a pre-existing `supply_demand/` characteristic, not fixed
   here (out of scope — frozen capability code).
2. Full candle-level MarketContext sharing across Structure/Supply-Demand/Liquidity
   is not implemented; each still performs its own internal MT5 fetch (their frozen
   internals do not accept a pre-fetched candle set).
3. Entry Confirmation's `displacement`/`rejection` qualification remains `UNSIGNED_RULE`
   (unchanged, per explicit mission scope).
4. Generic pip conversion remains unavailable in Trade Management (unchanged).
5. Strategy Manager integration was not deepened or re-verified this phase beyond
   confirming it remains untouched and independently importable.

---

```
AG_PROFIT_TRADING_ASSISTANT = PRESERVED

PRIMARY_OBJECTIVE
FIVE_SKILL_TRADE_ASSISTANT = PRESERVED

FIVE_SKILL_ASSISTANT_RUNTIME_V1
DETERMINISTIC_RUNTIME      = YES
ANALYSIS_ONLY              = YES

FOUNDATION
MARKET_CONTEXT             = READY
SHARED_CONTEXT             = VERIFIED
SINGLE_SNAPSHOT_REUSE      = VERIFIED (tick/quality layer); PARTIAL (candle-level reuse
                              across Structure/S-D/Liquidity blocked by frozen internals,
                              documented, not silently accepted)

CORE SKILL INTEGRATION
MARKET_STRUCTURE           = READY
SUPPLY_DEMAND              = READY
LIQUIDITY                  = READY
ENTRY_CONFIRMATION         = PARTIAL (unchanged -- displacement/rejection UNSIGNED_RULE)
TRADE_MANAGEMENT           = READY

RUNTIME
REQUEST_CONTRACT           = READY
RESULT_CONTRACT            = READY
SELECTIVE_INVOCATION       = VERIFIED
GENERIC_ANALYSIS           = VERIFIED (mocked + live)
MANUAL_CANDIDATE_ANALYSIS  = VERIFIED (mocked + live)
PARTIAL_SKILL_HANDLING     = VERIFIED
ASSESSMENT_LAYER           = READY

ENTRY_CONFIRMATION
STRUCTURE_SHIFT            = READY
LIQUIDITY_RECLAIM          = READY
DISPLACEMENT               = MEASUREMENT_ONLY / UNSIGNED
REJECTION                  = MEASUREMENT_ONLY / UNSIGNED
UNSIGNED_RULES_PRESERVED   = YES

TRADE_MANAGEMENT
NO_CANDIDATE_MODE          = VERIFIED
CANDIDATE_MODE             = VERIFIED
POSITION_SIZING            = READY
RR_GEOMETRY                = READY

CONFORMANCE
TM_VS_EXECUTION_SIZING     = PASS
TM_VS_EXECUTION_GEOMETRY   = PASS (reason-code strings differ by design, documented)
IMPLEMENTATION_DRIFT       = NONE

INDEPENDENCE
STRATEGY_REQUIRED          = NO
SESSION_TRADE_RULES_CHANGED = NO
EXECUTION_IMPORT           = NONE
EXECUTION_WRITE_PATH       = NONE

SESSION_TRADE_V1
REGISTERED                 = YES
ASIAN_LONDON               = ACTIVE (demo)
LONDON_NEWYORK             = UNSIGNED
RULES_CHANGED              = NO

EXECUTION
DEMO_AUTHORITY             = UNCHANGED
LIVE                       = HARD_BLOCKED

TESTS — AG PROFIT TRADING
BASELINE_PASSED            = 362 (1 skipped)
NEW_TESTS                  = 33
FINAL_PASSED               = 396
FAILED                     = 0
SKIPPED                    = 0

SESSION_TRADE_CODEX
STATUS                     = NOT_RE-RUN
REASON                     = No shared dependency touched this phase

KNOWN_GAPS
1. validated_order_blocks_for() has no status/reason_code of its own (pre-existing, not fixed)
2. Full candle-level MarketContext reuse across Structure/S-D/Liquidity not implemented
   (frozen internals don't accept a shared candle set)
3. Entry Confirmation displacement/rejection qualification remains UNSIGNED_RULE
4. Generic pip conversion remains unavailable
5. Strategy Manager path not re-verified beyond confirming independence

READY_FOR_FIVE_SKILL_ASSISTANT_RUNTIME = YES
```
