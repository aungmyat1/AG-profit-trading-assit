# AG_EGSVF_V1 -- Evidence-Gated Strategy Validation Framework: discovery + design ledger

This ledger records the resource-first discovery trail behind `src/validation_framework/`
and the design decisions made from it. It is documentation of how the framework was
built, not a new source of strategy truth -- every claim below is either a repository
fact (a path, a test name, a config value) or explicitly marked as a judgment call.

## Existing-capability search (AGENT PROMPT section 4)

Searched the repository for an existing equivalent of a lifecycle/gate/promotion
framework before writing anything: `strategy registry`, `strategy identity`, `validation`,
`evidence`, `promotion`, `authority`, `campaign`, `shadow`, `outcome`, `friction`,
`lookahead`, `replay`, `ledger`, `governance`, `execution boundary`.

Findings:

- `strategies/registry.yaml` + `strategies/STRATEGY_LEDGER.md` -- strategy
  identity/registration/authorization-flag authority. Reused as-is (read, never
  duplicated).
- `src/strategy_contract/` (this session's immediately prior milestone) -- a read-only
  `StrategyDecision` normalization layer and a `StrategyEvaluationRecord` metrics
  summarizer. Neither implements a lifecycle stage, a gate model, or a promotion
  evaluator; both are decision/metric *shape* normalizers, one layer below what EGSVF
  needs. No functional overlap requiring deduplication was found.
- `proposals/lifecycle.py` -- the only other `Lifecycle`-named module in the repo; it is
  Large-SMC's live candidate-occurrence lifecycle (pending/filled/expired), not a
  strategy-promotion lifecycle. Different concept, same word; not reused, not
  duplicated.
- No file anywhere combines gate statuses with a transition state machine, a
  promotion-eligibility evaluator, or a cross-strategy portfolio ledger.

**Classification: no existing AG-EGSVF-equivalent framework exists.**
`AG_EGSVF_V1_FOUNDATION_IMPLEMENTED` (new, additive package), not
`AG_EGSVF_V1_EXISTING_CAPABILITY_REUSED`.

## Evidence trail per strategy (see each adapter module's own docstring for the full,
current citation list -- this section summarizes only)

- **FX (`ST_ASIAN_SWEEP_5R_V1` v1.1.1):** `strategies/ST_ASIAN_SWEEP_5R_V1.yaml`,
  `strategies/registry.yaml`, `tests/test_strategy_decision_no_lookahead.py`,
  `tests/test_historical_replay_no_lookahead.py`,
  `artifacts/outcome_resolution/records/ST_ASIAN_SWEEP_5R_V1_*.json` (13 records, all
  `strategy_version: "1.1.1"`, all `cost_status: "NOT_INCLUDED"`),
  `docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md` /
  `..._DAY_002_STATUS.md`, `docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_RELEASE_IDENTITY_
  REMEDIATION_STATUS.md` (repeat-run determinism evidence).
- **BTC (`ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0):**
  `strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml`, `strategies/registry.yaml`,
  `tests/test_btc_occurrence_identity.py`, `src/btc_sweep_research/costs.py` (wired into
  `pipeline.py:164`), `tests/test_btc_costs.py`,
  `tests/test_btc_proposal_execution_boundary.py`. No `journal/reports/btc/` directory
  exists (the FX equivalent, `journal/reports/fx/`, does) -- read as 0 archived
  observations, not assumed.
- **Large-SMC (`ST_LARGE_SMC_V1` v1.0.6):** `strategies/ST_LARGE_SMC_V1.yaml` (line 561
  `initial_stop: UNSIGNED` = C10; line 101 `proposal_generation_authorized: false`),
  `strategies/registry.yaml`, `tests/test_large_smc_execution_boundary.py` (added the
  immediately prior milestone), `tests/test_historical_replay_no_lookahead.py`,
  `artifacts/backtests/golden/two_stage_golden_fixture_v1.json`,
  `artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json`.

## Judgment calls made (not derivable from a single file; recorded here for audit)

1. **Lifecycle-stage assignment is this task's classification, not a stored AG field.**
   AG has no existing per-strategy lifecycle-stage field; `evaluator.py`'s
   `LifecycleStage` enum and each adapter's `lifecycle_stage=` assignment are this
   task's own read of the evidence above (e.g. FX = `OPERATIONAL_SHADOW` because it is
   already running proposal-only daily cycles under an active shadow series; BTC =
   `FORWARD_RESEARCH` because its campaign is authorized but has not yet accrued an
   observation; Large-SMC = `OFFLINE_RESEARCH` because it has never produced a forward
   proposal). A future AG governance decision could define these stages differently;
   this mapping should be reconciled against it if one is adopted.
2. **`DETERMINISM` is PARTIAL, not PASS, for all three strategies.** Each has *some*
   determinism evidence (FX: one real repeat-run; BTC/Large-SMC: deterministic
   occurrence-identity unit tests) but none has a dedicated seeded/repeated full-pipeline
   determinism test. Reported as PARTIAL rather than inflated to PASS or deflated to
   NOT_VERIFIED.
3. **`C10_STOP_POLICY` is a Large-SMC-specific added gate**, not a global default gate --
   see `adapters/large_smc_adapter.STRATEGY_TRANSITION_OVERRIDES`. This follows AGENT
   PROMPT section 21 ("common default + strategy-specific stricter requirement") rather
   than folding C10 into `SPEC_FIDELITY` (which stays PASS; see section 40).
4. **`NATURAL_CAMPAIGN_ACCRUAL`'s observed-count is computed by walking
   `journal/reports/btc/`** the same way the FX adapter's directory-existence check
   works for `journal/reports/fx/` -- symmetrical, not BTC-specific special-casing.
5. **The PROJECT_STATUS discrepancy detector matches the LAST occurrence of a counter
   line, not the first.** `PROJECT_STATUS.md` is a chronological rolling log; an early
   dated milestone (Series 001, Day 001) legitimately contains different numbers than
   the current canonical summary further down the file. A first-match implementation
   was tried during this task, produced a false `SOURCE_CONFLICT` against a stale
   Series-001 number, and was corrected to last-match before being reported as a
   finding -- documented in `ledger.py::_last_match`'s own docstring.

## AG_EGSVF_V1_PROMOTION_INVARIANT_HARDENING (2026-09-07)

A review of the initial foundation found the required-gate/blocker computation was not
actually sourced from `evaluator.evaluate_transition()` anywhere outside tests: each
adapter (`fx_adapter.py`, `btc_adapter.py`, `large_smc_adapter.py`) independently
computed `promotion_eligible`/`promotion_blockers` by checking a hand-picked subset of
"this stage's own" gate names. Two consequences followed directly from that:

1. **Foundational gates could silently disappear.** FX (legacy-labeled
   `OPERATIONAL_SHADOW`) and BTC (legacy-labeled `FORWARD_RESEARCH`) both had real
   `DETERMINISM`/`HISTORICAL_REPLAY`/`NO_LOOKAHEAD` gates sitting at `PARTIAL` or
   `NOT_VERIFIED`, but neither adapter's blocker check ever looked at them, because
   those gate names were never in the small subset each adapter happened to check.
2. **A gate could over-block a transition it doesn't apply to.** Large-SMC's adapter
   included `FRICTION_STRESS_TEST`/`OOS_VALIDATION` in its `OFFLINE_RESEARCH ->
   FORWARD_RESEARCH` blocker check even though those gates belong to a much later
   transition (`DEMO_ELIGIBLE`) -- the opposite defect, but the same root cause: no
   single authoritative function decided what was actually required.

**Fix.** `evaluator.py` now defines `FOUNDATIONAL_INVARIANTS` (`SPEC_FIDELITY`,
`DETERMINISM`, `NO_LOOKAHEAD`, `HISTORICAL_REPLAY`) and `STAGE_PREREQUISITES` (each
lifecycle stage's own entry gates), and `get_cumulative_required_gates(target_stage)`
walks `STAGE_ORDER` from `FORWARD_RESEARCH` through `target_stage` inclusive,
concatenating every intervening stage's prerequisites. `required_gates_for()` is now
this cumulative set plus any strategy-specific additive requirement for the *exact*
transition being evaluated -- never a delta-only "just this stage's own gates" list.
Every adapter now calls `evaluator.evaluate_transition()` directly and copies
`evaluation.eligible` / `evaluation.blocking_gates` verbatim onto the record it returns;
none computes a second, independent blocker list. `ledger.py` was already a pure
pass-through (`serialize_record` copies `record.promotion_eligible`/
`promotion_blockers` unchanged) and needed no change to satisfy this.

**Consequence, by design, not a bug:** a strategy's current `lifecycle_stage` label is
not evidence that the gates required to reach that stage were ever evaluated -- all
three of AG's real strategies were assigned their current stage before AG-EGSVF
existed. FX and BTC therefore now correctly show `NATURAL_CAMPAIGN_ACCRUAL` as a
blocker even though neither is being evaluated for the `... -> OPERATIONAL_SHADOW`
transition literally -- it is inherited cumulatively into their actual next-transition
target. See `models.StrategyValidationRecord.details["stage_assignment_provenance"] =
"LEGACY_PRE_EGSVF"` on every current adapter output as an explicit, non-authoritative
marker of this fact (AGENT PROMPT section 27) -- it is documentation, not a gate, and
does not itself affect any evaluation.

Governing principle now enforced end-to-end and covered by
`tests/test_validation_framework.py::test_ledger_blockers_exactly_match_evaluator` and
`test_legacy_stage_assignment_does_not_imply_prior_gate_pass`:

```text
Adapters emit evidence (GateResults, identity, capability/authority facts, and at most
one strategy-specific additive gate requirement for a specific transition).

PromotionEvaluator alone determines promotion eligibility and the blocker list, via
cumulative prerequisite inheritance through the target stage.

The ledger records that judgment unchanged. It never invents a different one.
```

## What this task did NOT do

- Did not create, promote, or version-bump any strategy.
- Did not touch `strategies/*.yaml`, any strategy engine, risk engine, execution engine,
  broker adapter, Telegram code, campaign state, or historical evidence.
- Did not run or schedule a campaign, backtest, or optimization to manufacture evidence.
- Did not implement `promote_strategy(...)` -- only `evaluate_transition(...)` exists.
- Did not change `PROJECT_STATUS.md` (see the final report for why: the reconciliation
  found no discrepancy needing a documentation edit this run).
