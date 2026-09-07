# AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_STATUS

2026-09-06. Full discovery doc: `docs/architecture/AG_STRATEGY_TECH_SELECTIVE_PORT_REUSE_LEDGER.md`.

## REPOSITORY
- branch: main
- HEAD (before this task): `218ed1ab02175370245d2f1ed8aac429fbe1f40c` ("Add forward shadow outcome resolver and candidate stop-loss model")
- origin_main: `https://github.com/aungmyat1/AG-profit-trading-assit.git` (fetch/push), no push performed this task
- working_tree_before: modified `PROJECT_STATUS.md`; untracked
  `docs/status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_AND_VERSION_PROMOTION_V1_STATUS.md`,
  `docs/status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_FREEZE_AND_BOUNDARY_HARDENING_V1_STATUS.md`,
  `tests/test_large_smc_execution_boundary.py`, plus four prior-pass ledger/status files
  (`AG_MULTI_MARKET_OS_REUSE_LEDGER.md`, `AG_MULTI_MARKET_STRATEGY_OS_RESOURCE_REUSE_DISCOVERY_V1_STATUS.md`,
  `AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md`, `AG_TWO_SYSTEM_ARCHITECTURE_AND_OPEN_SOURCE_REUSE_V1_STATUS.md`)
  -- all left untouched, per instruction.
- working_tree_after: same pre-existing files unchanged, plus 8 new files added by this
  task (2 docs, 4 `src/strategy_contract/` modules, 4 focused test files -- see FILES_CHANGED).

## BASELINE
- application: AG_TRADE_ASSISTANT_V1_0_3 = RELEASE_CANDIDATE (unchanged)
- application_state: no change to demo/live authorization anywhere
- FX: ST_ASIAN_SWEEP_5R_V1 v1.1.1, authority=OPERATIONAL_PROPOSAL_SHADOW_AUTHORITY (unchanged; registry.yaml confirms demo_authorized=false, live_authorized=false)
- BTC: ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0, research=true, active=false (Forex profile), Crypto profile proposal/observation-only; campaign confirmed 0/30 in PROJECT_STATUS.md (not advanced by this task)
- Large_SMC: ST_LARGE_SMC_V1 v1.0.6, research=true, active=false; C10 confirmed UNSIGNED (`REASON_UNSIGNED_C10_BROKER_STOP` still the only C10 reason code emitted by `engine.py`); proposal-promotion remains BLOCKED
- strategy_version_changes: NONE
- execution_changes: NONE (no broker execution code touched; no demo/live flag changed)

## PHASE_1_STRATEGY_CONTRACT
- AG_existing: YES -- three independently-signed native decision shapes already exist
  (`PostAsianDecision`, `SetupState`, `LargeSMCResearchDecision`); a prior pass already
  declined to force-unify them without an owner decision.
- LEAN_pattern: AlphaModel -> Insight separation (identity/direction/confidence, no
  account fields) -- conceptually already present in all three native shapes.
- implementation: SMALL_ADAPTER. Added `src/strategy_contract/decision.py`:
  `StrategyDecision` frozen dataclass + `from_fx_decision`/`from_btc_setup_state`/
  `from_large_smc_decision`, pure read-only projections. Native modules unchanged.
  Large-SMC's stop is preserved as `None` with `UNSIGNED_CONTRACT:C10_BROKER_STOP`
  surfaced under `setup_properties["blockers"]` -- never fabricated. BTC's
  `strategy_version` (absent from `SetupState`) is a required caller-supplied parameter.
- files: `src/strategy_contract/decision.py`, `src/strategy_contract/__init__.py`
- tests: `tests/test_strategy_decision_contract.py` (9 tests: immutability, FX
  READY/NO_TRADE mapping, BTC ENTRY_READY/WAITING mapping with explicit strategy_version,
  Large-SMC C10-unsigned-stop-preserved-as-None, Large-SMC WATCH-has-no-direction) -- all pass.
- semantic_change: NONE. No native output, economics, authority, or version changed.

## PHASE_2_RUNTIME_ORCHESTRATION
- AG_existing: YES -- `daytrading_runtime.coordinator.RuntimeCoordinator` (SESSION+SMC,
  READ_ONLY, execution_submission=DISABLED) plus independent BTC
  (`btc_sweep_research.pipeline`) and Large-SMC (`large_smc_research.engine`)
  orchestration, each with its own cadence -- sufficient; no new orchestration engine built.
- Hummingbot_pattern: MarketDataProvider -> Controller -> output; AG's variant terminates
  at StrategyDecision, never an ExecutorAction/order.
- implementation: interface-only. Added `src/strategy_contract/controller.py`:
  `StrategyController`, a `typing.Protocol` (`strategy_id` property, `evaluate(...) ->
  Optional[StrategyDecision]`). Not wired into RuntimeCoordinator or either pipeline;
  nothing in the repo is required to implement it.
- files: `src/strategy_contract/controller.py`
- tests: `tests/test_strategy_controller_protocol.py` (3 tests: Protocol's public
  surface is exactly `{strategy_id, evaluate}` with no broker/order/account member,
  duck-typed structural satisfaction works, a partial object correctly fails
  `isinstance`) -- all pass. No "strategy can never import execution" test was added --
  per the prior boundary-classification finding, `strategy_engine.sweep_retest.engine`
  and `post_asian_pilot` legitimately import `execution.daily_loss_guard`/
  `position_guard` today for pre-flight checks, and a naive import-boundary test would
  false-positive against that real, intentional pattern.
- execution_boundary_preserved: YES -- existing `tests/test_btc_proposal_execution_boundary.py`
  (17 tests) and `tests/test_large_smc_execution_boundary.py` (13 tests) both still pass
  unmodified against the current tree.

## PHASE_3_RESEARCH_EVALUATION
- AG_existing: NO production evaluation-record module found repo-wide (only advisory
  skill scripts under `.claude/skills/performance-analysis` and `.agents/skills/
  performance-analysis`, which are user-facing analyst tools, not production strategy
  infrastructure).
- Jesse_pattern: standardized per-strategy metrics report (expectancy/win-rate/Sharpe/
  Sortino/drawdown) -- concept only, no Jesse code/runtime adopted.
- metric_schema: `StrategyEvaluationRecord(strategy_id, strategy_version,
  evaluation_start, evaluation_end, sample_count, expectancy_r, win_rate,
  profit_factor, sharpe_r, sortino_r, max_drawdown_r, mae_mean_r, mfe_mean_r,
  execution_drag_ratio)` -- all metric fields Optional.
- formula_definition_source: documented in full in `src/strategy_contract/evaluation.py`'s
  module docstring (numerator/denominator, zero-loss handling for profit_factor -> None
  not +inf, empty/insufficient-sample handling -> None, explicit non-annualized
  Sharpe/Sortino with risk-free-rate=0 and the reasoning why, execution_drag_ratio's
  ideal_r/realized_r provenance split).
- implementation: `build_evaluation_record(strategy_id, strategy_version, samples, ...)`
  -- a pure function over caller-supplied `TradeOutcomeSample` values; never reads or
  overwrites any raw evidence store itself.
- files: `src/strategy_contract/evaluation.py`
- tests: `tests/test_strategy_evaluation_record.py` (7 tests: empty-set all-None,
  single-sample dispersion-metrics-None, known expectancy/win-rate/profit-factor values,
  known max-drawdown on a constructed equity curve, known Sharpe/Sortino values,
  MAE/MFE averaged only over supplying samples, execution_drag_ratio provenance and
  None-when-missing) -- all pass.

## PHASE_4_LOOKAHEAD_PROTECTION
- AG_existing: YES -- `tests/test_historical_replay_no_lookahead.py` (16 tests, backed by
  `historical_replay.HistoricalCandleStore`/`historical_data_context`) already enforces
  the prefix/sliced-replay invariant at the point of actual risk (candle/tick access
  inside native engines); confirmed still passing unmodified (16/16).
- Freqtrade_pattern: sliced-data/prefix-invariance validation -- REFERENCE_ONLY, no code
  or license obligation involved (GPL-3.0 noted, nothing copied).
- test_method: extended, not duplicated -- added a separate small file targeting the
  ONE piece of new code this task introduces (the Phase-1 adapters), one layer above
  candle access.
- scope: `src/strategy_contract/decision.py`'s three adapter functions only. Does not
  claim whole-repository no-lookahead proof.
- implementation: `tests/test_strategy_decision_no_lookahead.py` (3 tests: FX adapter's
  `decision_timestamp` equals the native `ready_at`, never the later `evaluation_time`;
  adapter output is a deterministic pure function of its input (same call twice ->
  equal result); Large-SMC adapter never widens `evaluation_timestamp`) -- all pass.
- files: `tests/test_strategy_decision_no_lookahead.py`

## REUSE
- AG_exact_reuse: `PostAsianDecision`, `SetupState`, `LargeSMCResearchDecision`,
  `RuntimeCoordinator` -- all read, none modified.
- local_reuse: existing test fixture conventions (frozen dataclasses, explicit UTC
  datetimes) mirrored from `tests/test_historical_replay_no_lookahead.py`.
- external_direct_reuse: NONE (no external framework code copied).
- conceptual_ports: LEAN Insight/AlphaModel separation (Phase 1), Hummingbot
  Controller->output separation (Phase 2), Jesse standardized-metrics concept (Phase 3),
  Freqtrade sliced-replay concept (Phase 4).
- new_code: `src/strategy_contract/` (decision.py, controller.py, evaluation.py,
  __init__.py) + 4 focused test files.

## LICENSE
- LEAN: Apache-2.0 (not verified locally; conceptual reference only, no source read)
- Hummingbot: Apache-2.0 (not verified locally; conceptual reference only, no source read)
- Jesse: not verified locally; no source referenced or copied
- Freqtrade: GPL-3.0 (not verified locally; REFERENCE_ONLY, no source copied, no obligation triggered)

## BOUNDARY
- Strategy_can_call_broker: NO (unchanged) -- `StrategyController` Protocol has no
  broker/order/account member (verified by test)
- Strategy_can_read_credentials: NO (unchanged; no credential-adjacent code touched)
- ExecutionCommand_emitted_by_Strategy: NO -- `StrategyDecision`/`StrategyController`
  carry no execution-command type or method
- BTC_execution_boundary: UNCHANGED -- `tests/test_btc_proposal_execution_boundary.py`
  (17/17) still passes
- Large_SMC_execution_boundary: UNCHANGED -- `tests/test_large_smc_execution_boundary.py`
  (13/13) still passes

## EVIDENCE
- historical_attribution_changed: NO
- forward_campaigns_modified: NO (BTC 0/30, FX shadow series untouched; no counters advanced)
- raw_research_artifacts_changed: NO (StrategyEvaluationRecord only ever consumes
  caller-supplied samples; it reads/writes nothing in any evidence store)

## TESTS
- focused: 20 new tests across 4 new files, all passing:
  - `tests/test_strategy_decision_contract.py` -- 9 passed
  - `tests/test_strategy_controller_protocol.py` -- 3 passed
  - `tests/test_strategy_evaluation_record.py` -- 7 passed
  - `tests/test_strategy_decision_no_lookahead.py` -- 3 passed
  Plus regression confirmation (unmodified, still green):
  - `tests/test_historical_replay_no_lookahead.py` -- 16 passed
  - `tests/test_large_smc_execution_boundary.py` -- 13 passed
  - `tests/test_btc_proposal_execution_boundary.py` -- 17 passed
  (36 passed when run together with the two boundary files.)
- full_suite: NOT run
- full_suite_reason: no shared production behavior changed -- every change this task
  made is new, additive code under a new package (`src/strategy_contract/`) that no
  existing module imports or calls; the three native strategy engines, RuntimeCoordinator,
  and all execution modules are byte-for-byte unmodified. A full-suite rerun would not
  exercise any changed code path beyond what the focused + regression tests above already
  cover, and the task's own constraints ask to avoid full historical/backtest reruns
  unless materially necessary.

## FILES_CHANGED
New files only (nothing existing modified):
- `docs/architecture/AG_STRATEGY_TECH_SELECTIVE_PORT_REUSE_LEDGER.md`
- `docs/status/AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_STATUS.md` (this file)
- `src/strategy_contract/__init__.py`
- `src/strategy_contract/decision.py`
- `src/strategy_contract/controller.py`
- `src/strategy_contract/evaluation.py`
- `tests/test_strategy_decision_contract.py`
- `tests/test_strategy_controller_protocol.py`
- `tests/test_strategy_evaluation_record.py`
- `tests/test_strategy_decision_no_lookahead.py`

## NEXT_RECOMMENDATION
3 -- `src/strategy_contract/` exists now as optional, additive infrastructure. No caller
currently depends on it (by design, to avoid premature wiring). A natural next step,
only if an owner decides it is wanted, is a single real caller (e.g. a read-only
cross-strategy research summary command) that uses the Phase-1 adapters +
Phase-3 evaluation record together against one strategy's already-existing evidence
store, still without touching execution or any native engine.

## FINAL_CLASSIFICATION
AG_STRATEGY_TECH_PARTIAL_IMPLEMENTATION_COMPLETE

Rationale: Phases 1, 2, and 4 found sufficient existing AG infrastructure and needed only
small, additive interface/adapter/test code (no native behavior change); Phase 3 required
genuinely new minimal implementation (no prior production evaluation-record module
existed). All four phases are now covered, but none required or received a rewrite of
existing strategy logic, authority, or versioning -- exactly the "partial, minimal
footprint" outcome the task anticipated as the likely result.
