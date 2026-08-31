# AG_POST_ASIAN_LONDON_PILOT_V1 / AG_TRADE_ASSISTANT_V1_0 Status (2026-09-01)

Scope: turn `ST_ASIAN_SWEEP_5R_V1` into a daily, read-only, PROPOSAL_ONLY trading
assistant for EURUSD+GBPUSD, wrapped in an application-level release manifest
(`AG_TRADE_ASSISTANT_V1_0`). Builds on the frozen two-stage replay architecture
(`docs/status/AG_TWO_STAGE_GOLDEN_VERTICAL_SLICE_V1_STATUS.md`, untouched by this pass)
and does not modify it.

## 1. Architecture

New package `src/post_asian_pilot/` -- thin orchestration only; every computation
delegates to an existing, already-verified module: `session_clock` (canonical Asian
window), `strategy_engine.evaluate()` (the strategy's own unmodified sweep/regime/exit
logic -- no bias overlay, chosen over the parallel bias-gated `daytrading_workflow` path
specifically to avoid importing an unrelated alignment rule into this strategy's frozen
contract), `execution.intent_builder.build_intent()` + `execution.adapter.TradeProposal`
(risk-sized proposal construction), `execution.position_guard.OpenPositionGuard` /
`execution.daily_loss_guard.DailyLossGuard` (existing, unmodified project-wide guards),
and `runtime_state.store.JsonKeyValueStore` (atomic persistence, same convention as every
other `journal/*` store).

**Scope decision** (`src/post_asian_pilot/decision.py` docstring): `ST_ASIAN_SWEEP_5R_V1`'s
own `entry_rules` (`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`) define ONLY sweep triggers --
no trend or range-boundary-rejection formulas. `strategy_engine.session.route_completed_session`
is a generic TREND/SWEEP/RANGE router shared by other session strategies, so a `TradeSignal`
whose `setup` is `TREND` or `RANGE` is deliberately mapped to `NO_TRADE`
(`NON_SWEEP_SETUP_OUT_OF_SCOPE`) rather than promoted to `READY` -- this preserves the
strategy's own sweep-only contract exactly, without modifying the shared, frozen router.

**Risk authority**: `ST_ASIAN_SWEEP_5R_V1.yaml` has no signed `risk_per_trade_pct`
(confirmed open gap, `PROJECT_STATUS.md`). Per explicit user decision, `0.5%` is
pilot-level runtime policy (`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1.yaml`), not a
retroactive edit to the strategy's own signed contract.

## 2. Files

```
config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1.yaml   pilot universe/window/risk overlay
config/releases/AG_TRADE_ASSISTANT_V1_0.yaml       application release manifest
src/post_asian_pilot/snapshot.py                   AsianSessionSnapshot + candle-array validator
src/post_asian_pilot/decision.py                   PostAsianDecision (WATCH/READY/NO_TRADE/DATA_ERROR/EXPIRED)
src/post_asian_pilot/proposal.py                    risk-sized Entry Proposal (TP1 via existing leg1_take_profit, TP2 computed)
src/post_asian_pilot/governor.py                    daily governor (guards reused + new -1R lock + new trade-slot)
src/post_asian_pilot/tiebreak.py                     simultaneous-READY fail-closed policy
src/post_asian_pilot/store.py                        persistence + idempotent signature-diff dedup
src/post_asian_pilot/pipeline.py                     one evaluation cycle
src/post_asian_pilot/report.py                       JSON + human-readable report, release fingerprints
src/post_asian_pilot/fingerprint.py                  canonical SHA-256 (same technique as historical_replay.stage1)
scripts/run_post_asian_pilot.py                      CLI (--once/--watch/--status), read-only
tests/test_post_asian_pilot.py                        26 focused tests
```

## 3. Tests

```
new focused (tests/test_post_asian_pilot.py)                          = 26 passed
existing regression (test_strategy_engine/test_execution_intent_builder/
                     test_execution_coordinator/test_execution_safety_v1)  = 57 passed, unmodified
broader repository suite (run once)                                    = 1156 passed, 0 new failures
                                                                          (1130 baseline + 26 new)
```

## 4. Live read-only validation

`python scripts/run_post_asian_pilot.py --status` against real MT5 data (2026-08-31,
09:37 UTC evaluation) produced a genuine real-world exercise of the fail-closed
tie-break: **both EURUSD (LOWER_SWEEP_STRICT_PENETRATION, LONG) and GBPUSD
(UPPER_SWEEP_STRICT_PENETRATION, SHORT) reached `strategy_state=READY` on the same
closed-M15 timestamp.** With no existing cross-symbol priority policy, the pilot
correctly returned `portfolio_state=BLOCKED` /
`SIMULTANEOUS_READY_POLICY_UNRESOLVED` for both, per spec, instead of arbitrarily
picking one. `order_check`/`order_send` calls: 0 (the package never imports
`execution.executor`/`execution.mt5_gateway`, verified both by test and by grep).
Output persisted under `journal/post_asian_pilot/` (decision + session snapshot; no
proposal was built since neither candidate was promoted to actionable).

## 5. Acceptance

```
AG_POST_ASIAN_LONDON_PILOT_V1_STATUS

STRATEGY
strategy_id = ST_ASIAN_SWEEP_5R_V1        version = 1.1.1        authority = SOLE_DAY_TRADING_STRATEGY (pilot-scoped)
contract_match = MATCHES (sweep semantics, exit legs, session windows -- all verified against source)

UNIVERSE
EURUSD = ENABLED   GBPUSD = ENABLED   other_symbols = DISABLED_FOR_PILOT

SESSION
canonical_source = config/canonical_sessions.yaml (VERIFIED)   Asian_window = 00:00-06:00 UTC
expected_M15 = 24   snapshot = VERIFIED (immutable, fingerprinted, gap/duplicate/monotonic/forming-bar checked)
execution_window = 07:00-11:00 UTC   LONDON_NEWYORK = DISABLED (inactive_cycle)

DECISION
WATCH = VERIFIED   READY = VERIFIED (live)   NO_TRADE = VERIFIED   DATA_ERROR = VERIFIED (tested)
EXPIRED = VERIFIED   BLOCKED = VERIFIED (live)

RISK
risk_per_trade = 0.5% (pilot policy)   max_new_trades_per_day = 1   max_open_positions = 1
strategy_loss_lock = -1R (new, layered alongside the existing unmodified -2R project guard)
volume_normalization = VERIFIED (floor-only, execution.risk.size_position, unmodified)
risk_overshoot = IMPOSSIBLE (tested: minimum-lot-exceeds-budget -> BLOCKED)

EXIT
TP1_allocation = 75%   TP1_target = opposing session boundary (existing leg1_take_profit, unmodified)
runner_allocation = 25%   runner_target = 5R (computed from strategy's own signed total_target_r)
breakeven_policy = PRESERVED (strategy's own MOVE_RUNNER_SL_TO_BREAKEVEN, untouched -- not re-implemented here)

PROPOSAL
existing_model_reused = execution.adapter.TradeProposal (via TradeProposal.from_trade_intent)
proposal_identity = PROPOSAL-<setup_id>   expiration = one M15 bar / window close

PORTFOLIO
daily_trade_slot = VERIFIED (new)   pair_correlation_control = VERIFIED (shared one-slot-across-universe)
simultaneous_READY_policy = FAIL_CLOSED (SIMULTANEOUS_READY_POLICY_UNRESOLVED, exercised live)

PERSISTENCE
session_snapshot = VERIFIED   decision = VERIFIED   proposal = VERIFIED   restart = idempotent by design
                                                                          (signature-diff dedup, tested)
duplicate_suppression = VERIFIED

EXECUTION
mode = PROPOSAL_ONLY   order_check_calls = 0   order_send_calls = 0
automatic_execution = DISABLED   explicit_confirmation = REQUIRED   live_execution = DISABLED

REGRESSION
two_stage_changed = NO   strategy_semantics_changed = NO   High_RR_rules_imported = NO
Large_SMC_execution_added = NO   crypto_changed = NO

TESTS
new_focused = 26   existing_focused = 57   broader = 1156 (0 new failures)   live_read_only = VERIFIED

PILOT_READINESS
post_Asian_decision = READY_FOR_READ_ONLY_PILOT
READY_proposal_if_qualified = READY (subject to tie-break/governor gates, all verified)
forced_trade = NEVER   automatic_execution = DISABLED

PROMOTION
historical_100_instances = NOT_STARTED   forward_30_sessions = NOT_STARTED   demo_eligible = NO_UNTIL_VALIDATION_GATES_PASS
```

```
AG_TRADE_ASSISTANT_V1_0_STATUS

RELEASE
release_id = AG_TRADE_ASSISTANT_V1_0   status = PILOT
release/strategy/session/risk fingerprints = VERIFIED (deterministic, SHA-256, distinct per-artifact)

Everything else identical to AG_POST_ASIAN_LONDON_PILOT_V1_STATUS above -- this release
manifest wraps that pilot without redefining any of its behavior.
```

## 6. Not implemented in this pass (deferred, per spec)

SMC advisory upgrade, tick-volume/CVD/footprint, Large-SMC execution, `ST_HIGH_RR_LIQUIDITY_MSS_V1`,
New York trading cycle, crypto, automatic/demo execution. `ST_HIGH_RR_LIQUIDITY_MSS_V1` and
`LARGE_SMC` (as named in the originating spec) do not exist anywhere in this repository --
confirmed by audit, not assumed.

## 7. First unresolved requirement

None blocking this pilot. Open items for the next phase: (a) the bias-gated
`daytrading_workflow`/`daytrading_runtime.coordinator` path continues running independently
and is unrelated to this pilot -- worth a future decision on whether the two should ever
converge; (b) demo/historical promotion evidence (100 historical instances, 30 forward
sessions) has not been collected -- tracked separately from this pilot's own readiness.

NEXT_PHASE = PILOT_OBSERVATION_AND_HISTORICAL_VALIDATION
