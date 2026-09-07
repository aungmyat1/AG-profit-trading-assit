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

## AG_EGSVF_V1_STRATEGY_STAGE_CONTRACT_RECONCILIATION (2026-09-07)

`STAGE_PREREQUISITES[OPERATIONAL_SHADOW]` was hardcoded to the literal gate name
`NATURAL_CAMPAIGN_ACCRUAL` -- BTC's own forward-observation campaign gate, wrongly
treated as the universal definition of a lifecycle milestone every strategy family
shares. FX has no such campaign; cumulative inheritance was therefore permanently
blocking FX on a gate it can never satisfy and never should have to.

**Fix -- abstract milestone gates resolved per strategy family:**

1. **Foundational gates are universal.** `FOUNDATIONAL_INVARIANTS` is unchanged and
   still required for every promotion at or beyond `FORWARD_RESEARCH`, for every
   strategy, with no substitution mechanism reaching it.
2. **Lifecycle milestones may name an ABSTRACT evidence requirement.**
   `STAGE_PREREQUISITES[OPERATIONAL_SHADOW]` now names `SHADOW_ENTRY_EVIDENCE` --  a
   milestone concept ("sufficient evidence exists to enter operational shadow"), not a
   concrete gate. `ABSTRACT_MILESTONE_GATES` is the explicit, narrow allow-list of
   names that may ever be treated this way (currently just this one).
3. **Abstract requirements resolve to strategy-family-specific concrete gates.**
   `MILESTONE_GATE_MAP` maps `strategy_id -> {abstract_gate: concrete_gate}`:
   `ST_ASIAN_SWEEP_5R_V1 -> FX_SHADOW_ENTRY_PREFLIGHT_PASS` (sourced from
   `docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md`'s
   `shadow_entry_ready = YES` / `PREFLIGHT_PASS_SHADOW_READY` classification -- a real,
   dated governance event, deliberately NOT Series 001's non-counting evidence);
   `ST_LIQUIDITY_SWEEP_RETEST_V1 -> NATURAL_CAMPAIGN_ACCRUAL` (unchanged). Large-SMC has
   no entry: no repository governance defines its shadow-entry evidence, and its actual
   current transition never reaches this gate, so none is invented.
4. **A family mapping cannot replace a foundational gate.** `validate_family_gate_map`
   (run at import time against `MILESTONE_GATE_MAP`, and directly callable by tests
   against any other mapping) raises `ValueError` if a mapping ever targets a name
   outside `ABSTRACT_MILESTONE_GATES` -- this makes the invariant enforced, not a
   convention.
5. **Unresolved milestone mappings fail closed.** A strategy_id with no mapping entry
   for a needed abstract gate (or no strategy_id supplied at all) resolves to
   `f"{abstract_gate}_UNRESOLVED_FOR_STRATEGY"` -- a placeholder no adapter emits a
   GateResult for, so it always surfaces as a real `MISSING_GATE` blocker. It never
   silently borrows another strategy's concrete gate and is never treated as PASS.
6. **Lifecycle label alone is still never proof of a concrete gate** (unchanged from
   the promotion-invariant-hardening milestone above) -- resolution happens fresh on
   every `evaluate_transition()` call from the strategy's actual current evidence.
7. **Evaluator remains sole promotion authority.** `evaluate_transition(..., strategy_id=...)`
   is still the only place `promotion_eligible`/`promotion_blockers` are computed;
   adapters only supply `strategy_id` and, where legitimately needed, one concrete
   GateResult -- see `tests/test_validation_framework.py::test_fx_shadow_entry_uses_fx_specific_gate`,
   `test_btc_shadow_entry_uses_natural_campaign_accrual`,
   `test_family_gate_mapping_cannot_replace_foundational_invariant`, and
   `test_missing_abstract_gate_mapping_fails_closed`.

Net effect: FX's blocker list no longer contains `NATURAL_CAMPAIGN_ACCRUAL`. Its real
blockers are now exactly its own evidence gaps (`DETERMINISM`, `HISTORICAL_REPLAY`,
`SHADOW_SERIES_COMPLETION`, `FRICTION_STRESS_TEST`, `OOS_VALIDATION`); BTC and Large-SMC
blocker lists are unchanged.

## AG_EGSVF_V1_CROSS_STRATEGY_DETERMINISM_EVIDENCE_RECONCILIATION (2026-09-07)

All three strategies previously carried `DETERMINISM = PARTIAL`, each backed only by
unit-level evidence (one repeat-run of a *reporting* layer for FX; occurrence-identity
determinism alone for BTC/Large-SMC) -- never a proof that the actual versioned
semantic pipeline itself is repeat-run-stable end to end.

**DETERMINISM PASS requires repeated semantic-pipeline equality over identical
version-bound fixtures. Unit/helper determinism alone is insufficient.**

Each strategy's real, offline, no-network pipeline boundary was identified and driven
2-3 times over a fixed fixture, comparing the full canonical semantic payload (never
just an identity field):

- **FX:** `strategy_engine.engine.evaluate()` -> `TradeSignal` ->
  `post_asian_pilot.decision.map_trade_signal_to_decision()` -> `PostAsianDecision`.
  Both functions are pure given explicit candles/timestamps.
- **BTC:** `btc_sweep_research.pipeline.run_research_cycle()` against a cached,
  in-memory `CryptoCandleFeed` fixture (`tests/test_btc_sweep_research_pipeline.py`'s
  own `_FixtureFeed`/`_build_fixture`) -- no network, fresh tmp_path-isolated state
  each run.
- **Large-SMC:** `large_smc_research.engine.LargeSMCResearchEngine.evaluate()` against
  the frozen golden two-stage fixture (`artifacts/backtests/golden/
  two_stage_golden_fixture_v1.json` + cached historical CSV store) -- the actual
  research-decision boundary, one layer above the Stage1/Stage2 fingerprint tests that
  already existed.

Evidence is **immutable and version-bound**: `scripts/generate_determinism_evidence.py`
writes one JSON record per strategy under `artifacts/validation_evidence/determinism/`,
named `<strategy_id>_<semantic_version>_<timestamp>.json`, never overwritten. Each
record carries `strategy_id`, `strategy_version`, `evaluation_head`, `fixture_ref`,
`test_ref`, `runs`, `normalization_contract`, `result`, and `payload_digests` (SHA-256
of the canonical JSON payload via the existing `post_asian_pilot.fingerprint.fingerprint`
serializer -- no new serializer invented). Every adapter's `DETERMINISM` gate is now
derived by `validation_framework.adapters.determinism_evidence.load_determinism_evidence()`,
which reads the most recent record matching the strategy's *exact* current
`(strategy_id, semantic_version)` and reports its recorded `result` verbatim --
`NOT_VERIFIED` if no matching record exists (a record for any other version is never
read), `FAIL` if one exists but recorded a genuine digest mismatch, `PASS` only if it
recorded one. No adapter infers `PASS` from a test file merely existing.

Result: all three strategies' `DETERMINISM` gate is now `PASS`, backed by real evidence
generated this task. Every other gate/blocker is unchanged -- FX still blocks on
`HISTORICAL_REPLAY`/`SHADOW_SERIES_COMPLETION`/`FRICTION_STRESS_TEST`/`OOS_VALIDATION`;
BTC still blocks on `NO_LOOKAHEAD`/`HISTORICAL_REPLAY`/`NATURAL_CAMPAIGN_ACCRUAL`;
Large-SMC still blocks on `C10_STOP_POLICY` (C10 remains `UNSIGNED`,
`proposal_generation_authorized` remains `false` -- unchanged by this task).

## Lifecycle Authority (2026-09-07, P0 hardening)

Before this section, each adapter (`fx_adapter.py`/`btc_adapter.py`/
`large_smc_adapter.py`) hardcoded its own `lifecycle_stage` Python literal directly --
functional (it is exactly how Large-SMC's `OFFLINE_RESEARCH -> FORWARD_RESEARCH`
promotion was recorded one milestone earlier), but architecturally fragile: an adapter
that emits evidence should not also be the sole owner of a strategy's current lifecycle
state, and nothing prevented future drift between what different adapters/tools
believed a strategy's stage to be.

**One machine-readable governance source now owns lifecycle stage**:
`config/governance/strategy_lifecycle.yaml`, read exclusively through
`src/validation_framework/lifecycle_registry.py::get_lifecycle_stage()`. It
deliberately does **not** duplicate `proposal_generation_authorized`/
`demo_authorized`/`live_authorized` -- those already have a canonical home
(`strategies/registry.yaml`, `strategies/<ID>.yaml`) and remain read from there
unchanged; duplicating them into the lifecycle file would create a second,
divergence-prone source of truth in the opposite direction. This registry owns exactly
one fact per strategy: its current `lifecycle_stage`, version-bound to the exact
`semantic_version` it applies to.

```text
Adapters are readers only -- they no longer own lifecycle state.

get_lifecycle_stage(strategy_id, semantic_version, repo_root) fails closed
(LifecycleRegistryError) on: missing registry file, malformed registry, missing
strategy entry, missing/unknown lifecycle_stage, or a semantic_version mismatch
between the registry's recorded version and the caller's own -- never silently
defaults to a guessed stage.

get_next_stage(current_stage) derives the next adjacent stage from the single
canonical LIFECYCLE_ORDER tuple (models.py) -- adapters no longer separately
hardcode `next_transition` either.

PromotionEvaluator remains eligibility authority only -- it has no knowledge of, and
no dependency on, where lifecycle_stage came from.

Governance actions (lifecycle promotion) mutate config/governance/strategy_lifecycle.yaml
only after an evaluator PASS (promotion_eligible=True) plus explicit owner
authorization -- exactly the same sequence every prior AG-EGSVF promotion in this
repository's history already followed; this section only relocates WHERE that fact is
persisted, it does not change WHEN or HOW it may be changed.
```

## What this task did NOT do

- Did not create, promote, or version-bump any strategy.
- Did not touch `strategies/*.yaml`, any strategy engine, risk engine, execution engine,
  broker adapter, Telegram code, campaign state, or historical evidence.
- Did not run or schedule a campaign, backtest, or optimization to manufacture evidence.
- Did not implement `promote_strategy(...)` -- only `evaluate_transition(...)` exists.
- Did not change `PROJECT_STATUS.md` (see the final report for why: the reconciliation
  found no discrepancy needing a documentation edit this run).
- Did not invent a Large-SMC shadow-entry gate or otherwise assign speculative future
  evidence.
- Did not resolve C10, change Large-SMC's proposal authorization, or touch any strategy
  economics while establishing determinism evidence.
- Did not duplicate `proposal_generation_authorized`/`demo_authorized`/
  `live_authorized` into the new lifecycle registry -- those remain owned by their
  existing canonical sources.
