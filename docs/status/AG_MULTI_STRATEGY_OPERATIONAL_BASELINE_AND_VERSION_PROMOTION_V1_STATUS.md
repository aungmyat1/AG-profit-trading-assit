# AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_AND_VERSION_PROMOTION_V1

Verification-only milestone. Confirms all three strategy workstreams
(`ST_ASIAN_SWEEP_5R_V1`, `ST_LIQUIDITY_SWEEP_RETEST_V1`, `ST_LARGE_SMC_V1`) can produce
their maximum-authorized deterministic decision/ticket output, and makes an explicit,
evidence-based governance decision on application-release and strategy-version
promotion. No source code was changed by this task.

## Baseline

`branch=main`, `HEAD=218ed1ab02175370245d2f1ed8aac429fbe1f40c`,
`origin/main=218ed1ab...` (0 ahead/0 behind), working tree carried one pre-existing
modified file (`PROJECT_STATUS.md`, from the immediately prior BTC-documentation
milestone, untouched further here).

## Application release decision: NO NEW RELEASE MANIFEST CREATED

`config/releases/` contains `AG_TRADE_ASSISTANT_V1_0` / `_V1_0_1` / `_V1_0_2` /
`_V1_0_3` only -- `V1.0.3` (`RELEASE_CANDIDATE`, unchanged status) is confirmed the
current, unsuperseded application release.

`docs/VERSION_HISTORY.md`'s own "Versioning boundary" section is authoritative and
explicit: *"Application/release version changes ... do NOT imply a strategy semantics
change, and vice versa ... never for logging, reporting, persistence, restart recovery,
CLI changes, journal hygiene, or release manifests."* The same document's "Required
upgrades" roadmap names the next real application releases as `V1.1.0` (crypto demo
execution) and `V1.2.0` (Large-SMC proposal readiness) -- there is no `V1.0.4` concept
anywhere in the authoritative history, and V1.0.3's own "Complete `AG_TRADE_ASSISTANT_
V1_0_3`" checklist (FX 20-day shadow, BTC 30-day observation, credential rotation) is
still open, not superseded.

Everything accomplished across this session's prior milestones -- BTC skill
registration, BTC scheduler installation, BTC campaign authorization reconciliation, FX
dual-cycle architecture verification, README/PROJECT_STATUS documentation reconciliation
-- falls squarely into the categories this rule says must NOT trigger a new release
number (reporting, CLI, journal hygiene, documentation, operational readiness). No
runtime, broker-adapter, or operating-control capability was added that V1.0.3 didn't
already describe.

**Decision: `config/releases/AG_TRADE_ASSISTANT_V1_0_4.yaml` was NOT created.** V1.0.3
remains the current `RELEASE_CANDIDATE`; this milestone's work is qualification-gate
progress toward completing it, not a new release. Creating a new manifest here would
have fragmented the qualification lineage the last ~10 commits have deliberately kept
inside V1.0.3, for zero underlying strategy-version delta -- exactly the kind of
change-for-its-own-sake this repository's own conventions warn against.

## Strategy version decisions (each independent, none bumped)

| Strategy | Current version | Decision | Reason |
|---|---|---|---|
| `ST_ASIAN_SWEEP_5R_V1` | 1.1.1 (active) | `NO_VERSION_CHANGE_REQUIRED` | The `SESSION_RANGE_25` candidate (self-labeled `1.1.2-RC1` only inside its own research artifacts, never in `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` or `strategies/registry.yaml`) was classified `MODEL_A_SUFFICIENT_FOR_CANDIDATE_RECONCILIATION` in the prior SL-geometry milestone, but no owner promotion decision was recorded anywhere in the repository (verified: no `v1.1.2` string exists in `strategies/`). Per this task's own section 10 fallback, it remains `CANDIDATE / NOT ACTIVE`. |
| `ST_LIQUIDITY_SWEEP_RETEST_V1` | 2.0.0 | `NO_VERSION_CHANGE_REQUIRED` | No signal/entry/stop/target/session/risk semantic change was made to either profile this session; only orchestration-adjacent documentation/scheduler/skill artifacts changed. |
| `ST_LARGE_SMC_V1` | 1.0.6 | `NO_VERSION_CHANGE_REQUIRED` | C10 (`AG_NATIVE_INVALIDATION`) remains `UNSIGNED`/`BLOCKED` (verified: `strategies/ST_LARGE_SMC_V1.yaml` `initial_stop: UNSIGNED`, `strategies/registry.yaml` unchanged). No implemented semantic change exists to justify `v1.0.7`. |

## Multi-strategy runtime/decision/ticket proof (re-verified from existing evidence and source, no new runs against protected surfaces)

**FX** -- `scripts/scheduled/run_asian_london_once.bat` and `run_london_newyork_once.bat`
both confirmed routing to the identical `scripts/run_post_asian_pilot.py` (the latter via
`--pilot-config`), which calls `strategy_engine.engine.evaluate()` identically for both
`pair_id`s. Decision + proposal generation already proven by real, persisted evidence:
`journal/post_asian_pilot/decision.json` and `journal/post_london_newyork_pilot/
decision.json` both contain real READY/WATCH/EXPIRED/DATA_ERROR records for both cycles;
`artifacts/outcome_resolution/records/*.json` (13 records, `strategy_version="1.1.1"`)
prove end-to-end decision -> proposal -> outcome for both cycles and both symbols. No
new run was triggered this task (2026-09-06 UTC is outside/between both cycles' windows
at audit time; existing evidence was sufficient and reuse-first policy applies).

**BTC** -- `scripts/run_btc_daily_report.py` confirmed callable (`--help` inspected,
flags match documented contract exactly: `--date`, `--json`, `--allow-outside-window`,
`--no-archive`). `report_window_status()`/`build_btc_daily_report()` source-verified to
fail closed to a non-counting `DATA_ERROR` on any feed/data-quality exception, entirely
independent of the execution-boundary mechanism (`tests/test_btc_proposal_execution_
boundary.py`, 13/13, verified this session). Scheduler confirmed installed/enabled
(`State=Ready`, next run 2026-09-07T06:35Z). Campaign counter confirmed still `0/30`
(`journal/btc_sweep_research/` and `journal/reports/btc/` do not yet exist on disk) --
scheduler installation and campaign authorization are both necessary but neither is
sufficient on its own, per the observation contract's own definition.

**Large-SMC** -- `scripts/run_large_smc_discovery.py` confirmed to take a positional
`<csv_path> <symbol> <start_iso> <end_iso> <out_json_path> [manifest_path]` CLI (no
`--dry-run` flag exists; none was invented). Confirmed via source that it imports
`historical_replay.orchestrator.run_replay` and `large_smc_research.engine`, which
consume the shared E1/E2/E3/M1/M2/M3 detection modules verbatim -- no duplicate detector
exists. `large_smc_research.decision.LargeSMCResearchDecision` already exposes a
complete research-ticket shape (event/occurrence identity, E/M combination, entry
array, structural-invalidation anchor, target, state, reason_codes) with
`simulated_broker_stop` always `None` and `reason_codes` carrying
`UNSIGNED_CONTRACT:C10_BROKER_STOP` whenever a candidate would otherwise need a stop --
confirmed fail-closed, never fabricated. No new discovery run was executed this task (a
full-month replay is ~90 minutes of compute for zero new governance information, since
C10 already deterministically blocks final resolution); existing `artifacts/backtests/`
evidence from prior phases already demonstrates the pipeline runs end-to-end to
`RESEARCH_QUALIFIED`/`BLOCKED`.

## Execution boundary (all three, independently)

- FX: `demo_authorized: false`, `live_authorized: false` (registry, unchanged).
- BTC: `execution_domain=CRYPTO_RESEARCH`/`execution_authority=DISABLED`; zero
  `execution.executor`/`execution.coordinator`/`mt5.management_gateway` imports anywhere
  in `src/btc_sweep_research/`; 13/13 boundary tests pass.
- Large-SMC: `proposal_generation_authorized: false`; zero `execution.*` imports
  anywhere in `src/large_smc_research/` (no dedicated boundary test file exists for this
  strategy, unlike BTC -- noted as a minor test-coverage gap, not a defect, since
  nothing currently violates the boundary).

No path from any of the three strategies to `execution.executor`/broker order placement
was found. `UNAUTHORIZED_EXECUTION_PATH_DEFECT` does NOT apply.

## Tests

Focused only (no code changed, so no full-suite justification exists per this task's own
policy): `tests/test_btc_proposal_execution_boundary.py` (13/13, re-verified),
`tests/test_large_smc_outcome_lifecycle_safety.py` + `test_large_smc_registration.py` +
`test_historical_replay_no_lookahead.py` (21/21, re-verified this session), FX candidate
`tests/test_candidate_sl_model_session_range_25.py` (14/14, from the prior SL-geometry
milestone, not re-run since no related code changed). Full suite last confirmed clean at
this same `HEAD` in the prior SL-geometry milestone: 1550 passed / 6 skipped / 0 failed.

## Files changed by this task

None (verification/governance-decision only). This status document is the sole new
artifact.

## Final classification

`AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_READY_WITH_GOVERNANCE_BLOCKS`

All three strategy pipelines are demonstrably able to produce their authorized
decision/ticket output, remain correctly isolated from each other and from broker
execution, and preserve historical attribution. The application release and the FX
v1.1.2 candidate promotion are both correctly and deliberately blocked by existing,
cited governance evidence (no `V1.0.4` warranted per `docs/VERSION_HISTORY.md`'s own
versioning-boundary rule; no owner promotion decision recorded for `SESSION_RANGE_25`)
-- these are governance holds, not defects.
