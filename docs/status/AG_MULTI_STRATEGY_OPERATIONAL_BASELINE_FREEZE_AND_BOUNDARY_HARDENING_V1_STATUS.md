# AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_FREEZE_AND_BOUNDARY_HARDENING_V1

Governance + invariant-hardening milestone. Adopts and freezes the multi-strategy
operational baseline established in
`AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_AND_VERSION_PROMOTION_V1_STATUS.md` (preserved
unchanged, not superseded or rewritten -- that document remains the historical record of
its own milestone) as the canonical current project state, and closes the one identified
coverage gap: Large-SMC had no dedicated execution-boundary regression test (BTC did).

No trading semantics, strategy version, or application release changed.

## Baseline

`branch=main`, `HEAD=218ed1ab02175370245d2f1ed8aac429fbe1f40c`,
`origin/main=218ed1ab...` (0 ahead/0 behind). Working tree carried two pre-existing
items before this task (`PROJECT_STATUS.md` modified, and the prior milestone's own new
status doc) -- both preserved untouched.

## Canonical baseline adopted (frozen)

```text
FINAL_CLASSIFICATION = AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_READY_WITH_GOVERNANCE_BLOCKS

APPLICATION_RELEASE: AG_TRADE_ASSISTANT_V1_0_3, RELEASE_CANDIDATE, NO_VERSION_PROMOTION_REQUIRED

FX:    ST_ASIAN_SWEEP_5R_V1 v1.1.1, OPERATIONAL_PROPOSAL_SHADOW_AUTHORITY,
       CANDIDATE_SL_PROMOTION_NOT_AUTHORIZED, HISTORICAL_v1.1.1_IMMUTABLE
BTC:   ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0, OPERATIONALLY_READY_FOR_FORWARD_RESEARCH,
       ACCRUING_FORWARD_OBSERVATIONS (0/30), BROKER_EXECUTION_DISABLED
LARGE_SMC: ST_LARGE_SMC_V1 v1.0.6, RESEARCH_RUNTIME_READY_WITH_GOVERNANCE_BLOCKS,
       C10_UNSIGNED, C14_PARTIALLY_RESOLVED, PROPOSAL_PROMOTION_BLOCKED,
       BROKER_EXECUTION_DISABLED
```

Re-verified against current repository authority this task, no discrepancy found:
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml` (version 1.1.1), `strategies/
ST_LIQUIDITY_SWEEP_RETEST_V1.yaml` (version 2.0.0), `strategies/ST_LARGE_SMC_V1.yaml`
(`proposal_generation_authorized: false`, `initial_stop: UNSIGNED`), `config/releases/`
(no `V1.0.4`+ manifest exists). None of the section-20 stop conditions were triggered.

## Implementation: Large-SMC execution-boundary test (the one required change)

Added `tests/test_large_smc_execution_boundary.py`, modeled directly on the existing,
proven convention in `tests/test_btc_proposal_execution_boundary.py`'s static
AST-import-scan test (reused pattern, not a new framework). Forbidden-module set:

```text
execution.executor       (BTC guard's own set)
execution.coordinator    (BTC guard's own set)
execution.adapter        (BTC guard's own set)
execution.mt5_gateway    (verified real: "the only module allowed to call
                           order_check/order_send for an EXISTING position",
                           execution/mt5_gateway.py's own docstring)
mt5.management_gateway   (BTC guard's own set)
mt5.deals                (verified real: mt5/deals.py, broker deal/position history)
```

`src.execution` was deliberately NOT included -- this repository's actual import
convention is `execution.<module>`, never `src.execution.<module>` (verified against
the BTC guard's own set); including a non-existent prefix would create false
confidence without protecting anything real.

Scans every `.py` file in `src/large_smc_research/` (5 files) plus both runner scripts
(`scripts/run_large_smc_discovery.py`, `scripts/run_large_smc_outcome_lifecycle_check.py`).
**Result: 7/7 passed, zero violations found** -- the boundary already held structurally
(no execution import existed anywhere in the research package); this test now pins that
invariant with a regression guard, closing the coverage gap without finding or fixing
any actual defect.

## Persistence / runtime isolation

```text
PERSISTENCE_NAMESPACE_ISOLATION = VERIFIED
  FX:         journal/post_asian_pilot/, journal/post_london_newyork_pilot/ (separate
              state_dir per cycle, by design -- see strategies/STRATEGY_LEDGER.md)
  BTC:        journal/btc_sweep_research/, journal/reports/btc/
  Large-SMC:  artifacts/backtests/ (read/write only via caller-specified out_json_path,
              never a fixed live path)
  No shared file/directory found across any pair of the three.

RUNTIME_MEMORY_ISOLATION = VERIFIED for the specific risks checked this task:
  - No module-level mutable singleton, global counter, shared cache, or sequential
    ID generator found anywhere in src/large_smc_research/ or src/btc_sweep_research/
    (grepped for common patterns; none found).
  - execution.daily_loss_guard.DailyLossGuard is keyed by
    "{strategy_id}:{trading_day}" -- even if a caller reused the same store file
    across strategies (none currently do), the key itself prevents cross-strategy
    contamination.
  - Each strategy is invoked as its own separate OS process via a distinct CLI script
    (scripts/run_post_asian_pilot.py / scripts/run_btc_daily_report.py /
    scripts/run_large_smc_discovery.py) -- none are imported into one shared,
    long-lived Python process in this repository's current architecture, so no
    in-process shared-object risk currently exists either.
  This is not an exhaustive whole-repository audit of every module; it covers the
  specific isolation risks named in the governing prompt (mutable singletons, global
  counters, shared caches, ID generators, cross-strategy claim stores), all of which
  were checked and none of which were found.

CROSS_STRATEGY_MUTABLE_STATE = NONE FOUND
```

## FX candidate isolation (re-verified, unchanged since the prior milestone)

`SESSION_RANGE_25` (`src/strategy_engine/session/candidate_stop_models.py`) remains a
pure function, not imported by `strategy_engine.engine.evaluate` or
`session.setups.entry_2_sweep`. Verified again this task: no import of
`candidate_stop_models` exists anywhere outside its own test file and the isolated
`scripts/replay_candidate_model_a_session_range_25.py`. Active SL calculation, runtime
proposal generation, risk sizing (`execution/risk.py`), and execution geometry are all
byte-unchanged. Historical `v1.1.1` evidence (`artifacts/outcome_resolution/records/`)
remains untouched.

## SESSION_RANGE_25 promotion gate (documented, not evaluated/decided this task)

Per the governing prompt's own contract, recorded verbatim as the minimum future gate:

```text
20-session forward shadow evaluation
AND zero sub-pip stop anomalies
AND zero execution/risk.py assertion breaches
AND explicit owner-approved promotion/configuration update
```

No repository-authoritative promotion contract conflicting with this wording was found
(no `v1.1.2` reference exists anywhere under `strategies/`); this gate is adopted as
stated. Historical `v1.1.1` records remain unchanged regardless of any future promotion.

## BTC forward campaign integrity (re-verified, unchanged)

`journal/btc_sweep_research/` and `journal/reports/btc/` remain absent on disk --
counter remains `0/30`. No manual run was performed to manufacture evidence this task.
Scheduler remains installed/enabled from the prior milestone (`State=Ready`, next run
2026-09-07T06:35Z, inside the frozen 06:30-06:45 UTC window). `daily_report.py`'s
fail-closed `DATA_ERROR` path (verified in a prior milestone this session, unchanged)
still applies independently of the execution boundary -- a Bybit CloudFront/HTTP denial
produces a non-counting `DATA_ERROR`, never a fabricated or substituted-provider result.

## Telegram authority presentation contract (documented only -- no Telegram code exists on `main` to change)

No Telegram renderer exists on `main` (`src/authorization/`, `src/notifications/` remain
absent per `PROJECT_STATUS.md`'s own Telegram section; the Phase A-D1 work lives only on
an isolated, paused feature branch). This section is therefore a **forward-looking
documentation contract**, not an implementation, per the governing prompt's own
allowance ("do not necessarily implement Telegram UI changes ... unless the relevant
presentation layer already exists"):

```text
FX:         [OPERATIONAL SHADOW]
BTC:        [FORWARD INCUBATION - DO NOT TRADE]
LARGE_SMC:  [OFFLINE RESEARCH EXPERIMENT]
```

Any future Telegram ticket/message renderer must visibly expose strategy ID, strategy
version, authority level, execution state, and proposal/research status, and must never
let a research ticket visually resemble an executable approved order without its
authority label attached.

## Future opportunity-ranking architecture (documented invariant only -- no allocator exists)

No portfolio allocator/opportunity-ranker exists anywhere in the repository (confirmed:
no such module was found in `src/` during this session's multiple resource-first
inspections). The following invariant is frozen for any future implementation:

```text
STRATEGY ENGINE
    +--> FX Proposal
    +--> BTC Research Proposal
    +--> Large-SMC Research Ticket
              |
              v
    Read-only opportunity consumer
              |
              v
      ranking / allocation advice
```

A future ranker may rank already-generated tickets by confidence, historical
expectancy/Sharpe, evidence maturity, risk-adjusted score, or capital availability. It
must never modify setup qualification, direction, entry/stop/target coordinates,
strategy-specific risk rules, strategy version, or historical records. Execution
authorization, if the ranking is ever used to inform it, remains a wholly separate
boundary.

## Tests

- `tests/test_large_smc_execution_boundary.py` (new): 7/7 passed.
- `tests/test_btc_proposal_execution_boundary.py` (re-verified, unchanged): 13/13 passed.
- `tests/test_large_smc_registration.py`, `test_large_smc_outcome_lifecycle_safety.py`,
  `test_historical_replay_no_lookahead.py` (re-verified, unchanged): 21/21 passed.
- Full suite: **NOT re-run.** Only a new, additive test file and two documentation
  files were added; no shared runtime, strategy-engine, or execution/lifecycle source
  changed. Most recent trustworthy full-suite evidence at this same `HEAD`'s lineage:
  1550 passed / 6 skipped / 0 failed (prior SL-geometry milestone, same session).

## Files changed by this task

- `tests/test_large_smc_execution_boundary.py` (new)
- `docs/status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_FREEZE_AND_BOUNDARY_HARDENING_V1_STATUS.md` (new, this document)

No strategy YAML, registry, release manifest, or active engine/execution source was
touched.

## Final classification

`AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_READY_WITH_GOVERNANCE_BLOCKS` (adopted and
reconfirmed; the Large-SMC execution-boundary coverage gap identified in the prior
milestone is now closed).
