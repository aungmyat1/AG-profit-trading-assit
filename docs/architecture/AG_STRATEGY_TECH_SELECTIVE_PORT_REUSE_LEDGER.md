# AG_STRATEGY_TECH_SELECTIVE_PORT_REUSE_LEDGER

Produced by AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_V1 (2026-09-06). Records the
discovery pass and reuse classification for each of the four proposed phases (Strategy
contract / Runtime controller / Evaluation record / Lookahead guard), performed BEFORE
implementation, per the task's discovery-first requirement. See
`docs/status/AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_STATUS.md` for the final report,
files changed, and test results.

Related prior ledgers (not modified, referenced only):
- `docs/architecture/AG_MULTI_MARKET_OS_REUSE_LEDGER.md`
- `docs/architecture/AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md`

## AG_STRATEGY_TECH_REUSE_DISCOVERY

### PHASE_1_STRATEGY_CONTRACT
- AG_existing: Three independently-signed, strategy-native decision shapes already exist
  and were verified on disk:
  - `src/post_asian_pilot/decision.py::PostAsianDecision` (FX / ST_ASIAN_SWEEP_5R_V1) --
    already carries strategy_id/strategy_version/symbol/status/reason_codes/
    evaluation_time/ready_at, plus an optional `signal: TradeSignal` (direction/entry/
    stop_loss) once READY.
  - `src/strategy_engine/sweep_retest/models.py::SetupState` (BTC /
    ST_LIQUIDITY_SWEEP_RETEST_V1) -- state machine snapshot; carries strategy_id/symbol/
    direction/entry/stop_loss/tp1/tp2 but deliberately NOT strategy_version (versioning
    lives in strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml, read by the caller).
  - `src/large_smc_research/decision.py::LargeSMCResearchDecision` (Large-SMC /
    ST_LARGE_SMC_V1) -- carries strategy_id/strategy_version/symbol/direction/
    evaluation_timestamp/candidate identity; `simulated_broker_stop` is always None this
    phase because C10 (broker stop) is UNSIGNED, by explicit, documented design.
  - Separately, `src/assistant/models.py::StrategyResult`/`AssistantDecision` is a
    DIFFERENT, already-normalized contract, but scoped to SESSION_TRADE_V1 only (a
    fourth, external-engine strategy) -- not reused here, since extending it to FX/BTC/
    Large-SMC would require changing its own documented scope and status vocabulary.
  A prior discovery pass (`AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md`) already found these
  three shapes distinct and explicitly declined to force-unify them without an owner
  decision. This pass revisited that finding under the LEAN AlphaModel->Insight lens and
  reached the SAME semantic-risk conclusion for touching the native shapes themselves, but
  found a safe, additive alternative below.
- LEAN_pattern_reference: AlphaModel emits `Insight` (symbol, direction, confidence,
  period, magnitude) separately from `PortfolioConstructionModel`'s sizing -- i.e.
  Insight never carries account/order fields. AG's three native decisions already
  respect an equivalent split (no lot size/margin/account field exists in any of the
  three) -- this pattern was already present, not newly borrowed.
- reuse_decision: SMALL_ADAPTER. Do not touch, wrap, or version-bump any of the three
  native decision modules. Add a pure, read-only, one-way projection module
  (`src/strategy_contract/decision.py::StrategyDecision` +
  `from_fx_decision`/`from_btc_setup_state`/`from_large_smc_decision`) that copies fields
  out of an already-produced native decision. Large-SMC's stop is copied as None with its
  UNSIGNED_CONTRACT:C10_BROKER_STOP reason code preserved under
  `setup_properties["blockers"]` -- never fabricated. BTC's missing strategy_version is
  required as an explicit caller-supplied parameter, never invented.
- new_code_required: YES (the adapter module above), but no change to any native engine,
  output, authority, or version.

### PHASE_2_RUNTIME
- AG_existing: `src/daytrading_runtime/coordinator.py::RuntimeCoordinator` already
  orchestrates SESSION + SMC workflows in one `run_cycle()` (READ_ONLY,
  execution_submission=DISABLED), pulling from MT5 candles / market bias / session
  windows. BTC has its own orchestration (`src/btc_sweep_research/pipeline.py` ->
  `daily_report.py`) and Large-SMC has its own (`src/large_smc_research/engine.py`),
  each with independent cadence (BTC: daily report window; Large-SMC: per-replay-call;
  FX/SMC: per RuntimeCoordinator cycle) -- exactly the "don't force one evaluation
  cadence" requirement the task itself anticipates.
  Per the prior boundary-classification pass
  (`AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md`), `strategy_engine.sweep_retest.engine`
  and `post_asian_pilot` already import `execution.daily_loss_guard`/`position_guard`
  directly for pre-flight checks -- a real, intentional, bidirectional pattern, not a
  violation. A naive "strategy never imports execution" boundary test would false-
  positive against this and was NOT added.
- Hummingbot_pattern_reference: `MarketDataProvider -> ControllerBase -> ExecutorActions`.
  AG's target pattern differs at the last step: Controller must terminate at
  StrategyDecision, never an ExecutorAction/order.
- reuse_decision: EXISTING RUNTIME SUFFICIENT + interface-only. No new controller
  framework, no wiring into RuntimeCoordinator or either pipeline. Added
  `src/strategy_contract/controller.py::StrategyController`, a `typing.Protocol` with
  exactly `strategy_id` (property) and `evaluate(market_context) -> Optional[
  StrategyDecision]`. No `place_order`/`cancel_order`/`close_position`/`account`/`broker`
  member exists on it (verified by `tests/test_strategy_controller_protocol.py`, which
  asserts the Protocol's public surface is exactly `{strategy_id, evaluate}`). Nothing in
  the repository is required to implement it.
- new_code_required: YES (the Protocol only), zero behavioral change anywhere else.

### PHASE_3_EVALUATION
- AG_existing: repo-wide search for expectancy/win_rate/profit_factor/sharpe/sortino/
  max_drawdown found matches only in `.claude/skills/performance-analysis/scripts/
  metrics.py` and its `.agents/skills` mirror -- these are user-facing ADVISORY SKILL
  scripts (loaded on demand for analyst commentary), not production strategy-evaluation
  infrastructure consumed by any strategy engine, registry, or report. No production
  StrategyEvaluationRecord-equivalent exists.
- Jesse_pattern_reference: a standardized per-strategy metrics report (win-rate,
  expectancy, Sharpe, Sortino, max drawdown) computed once per backtest/live run. AG has
  no equivalent production module; the concept (not Jesse's exchange runtime or code) is
  what was ported.
  metric formulas). No existing calculation was reused verbatim (none existed in
  production code); the formula documentation prevents future silent-formula drift.
  historical evidence rewritten; raw evidence stores (FX shadow series, BTC ledger,
  Large-SMC candidate rows) are untouched. execution_drag_ratio keeps `ideal_r`/
  `realized_r` provenance separate and never overwrites either.
- new_code_required: YES -- this is the one phase genuinely NEW_MINIMAL_IMPLEMENTATION,
  as the task itself anticipated as a likely outcome.

### PHASE_4_LOOKAHEAD
- AG_existing: `tests/test_historical_replay_no_lookahead.py` (backed by
  `historical_replay.HistoricalCandleStore`/`historical_data_context`) already enforces
  the prefix/sliced-replay invariant at the actual point of risk -- candle/tick access
  inside native engines (bar-closure enforcement for H1/D1, live-analyzer reuse under
  replay, MT5-access-forbidden guard during replay). This is a sufficiently general
  harness; the task does not require and this pass did NOT build a duplicate one.
- Freqtrade_pattern_reference: sliced-data / prefix-invariance backtesting validation
  (bars[0:N] must match a live run at time N). AG's existing harness already implements
  the equivalent invariant for its own multi-timeframe/session-bucketing semantics
  (confirmed via `test_m5_1035_cannot_consume_the_1000_1100_h1_bar`, matching the task's
  own canonical example) -- REFERENCE_ONLY, no Freqtrade code or license question
  involved.
- reuse_decision: EXTEND, not duplicate. This task's own new code
  (`src/strategy_contract/decision.py`'s adapters) needed its OWN small, targeted
  regression rather than reuse of the candle-level harness, because it operates one
  layer up (already-produced native decisions, not candles). Added
  `tests/test_strategy_decision_no_lookahead.py`: proves each adapter's
  `decision_timestamp` equals the native decision's own authoritative timestamp (never a
  later evaluation/wall-clock time) and that the adapters are pure, deterministic
  functions of their input (no hidden clock/state dependency). This does not claim
  whole-repository no-lookahead proof -- only that the new adapter layer introduces no
  additional lookahead risk beyond what the existing engine-level harness already
  covers.
- new_code_required: YES (targeted adapter-purity tests only), existing harness
  unmodified.

## External source use policy (as required by the task)
| Framework | Local clone verified? | Reuse classification | License note |
|---|---|---|---|
| QuantConnect LEAN | No | CONCEPTUAL_PORT (Insight/AlphaModel separation concept only) | Apache-2.0 (not verified locally; conceptual use only, no code copied) |
| Hummingbot V2 | No | CONCEPTUAL_PORT (Controller->output separation concept only) | Apache-2.0 (not verified locally; conceptual use only, no code copied) |
| Jesse | No | CONCEPTUAL_PORT (standardized metrics-report concept only) | Not verified locally; no source copied, formulas independently defined and documented above |
| Freqtrade | No | REFERENCE_ONLY (sliced-replay/no-lookahead concept only) | GPL-3.0 -- no code copied, no obligations triggered |

No local clone of any of the four frameworks exists on this machine (confirmed by the
prior two discovery passes and re-confirmed here); all four rows above are therefore
capped at CONCEPTUAL_PORT/REFERENCE_ONLY, never DIRECT_REUSE or ADAPTED_REUSE, per the
task's own stop condition.

## Files added (all new, additive; nothing existing was modified except this ledger and
the sibling status document)
- `src/strategy_contract/__init__.py`
- `src/strategy_contract/decision.py`
- `src/strategy_contract/controller.py`
- `src/strategy_contract/evaluation.py`
- `tests/test_strategy_decision_contract.py`
- `tests/test_strategy_controller_protocol.py`
- `tests/test_strategy_evaluation_record.py`
- `tests/test_strategy_decision_no_lookahead.py`
