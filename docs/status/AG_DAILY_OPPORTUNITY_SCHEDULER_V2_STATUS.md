# AG_DAILY_OPPORTUNITY_SCHEDULER_V2 -- Implementation Status

Package: `src/ag_scheduler_v2/`
Config: `config/ag_scheduler_v2.yaml`
Tests: `tests/test_ag_scheduler_v2_*.py`

## Scope

Orchestration layer for market observation and research workloads. Not a strategy,
not lifecycle authority, not trade authorization. Coordinates the canonical daily
schedule (PRE_FLIGHT through P1_RESEARCH), M15 exactly-once evaluation, catch-up
recovery, economic-news-risk tagging, and advisory rolling-expectancy ranking, and
calls the existing `strategy_manager.manager.evaluate()` entry point for all signal
semantics rather than duplicating strategy rules.

## Strategy-integration reconciliation

The task naming this scheduler's strategy-integration target used the identifier
`ST_SESSION_SWEEP_CONTINUATION_V1`. Repository reconciliation (2026-09-10) found no
registry entry, adapter, contract, or test referencing that identifier anywhere in
this repository. Per explicit owner direction, `SESSION_TRADE_V1` -- the existing
registered strategy with S1/S2/S3-shaped session sweep/continuation logic, a SIGNED
ASIAN_LONDON cycle, and `demo_authorized: true` for that cycle only -- is used as the
working target. `config/ag_scheduler_v2.yaml`'s `strategy_integration` block records
both the real `strategy_id` (`SESSION_TRADE_V1`) and the task's naming alias
(`strategy_id_alias: ST_SESSION_SWEEP_CONTINUATION_V1`) so this mapping is auditable
rather than silent. If a strategy actually named `ST_SESSION_SWEEP_CONTINUATION_V1` is
registered later, this scheduler's config and evidence-identity fields are the only
places that need to change.

## Lifecycle

`lifecycle.py` states the authority boundary as data: `LIFECYCLE_STAGE =
"OFFLINE_RESEARCH"`, `DEMO_ELIGIBLE = False`, `DEMO_AUTHORIZED = False`,
`EXECUTION_ENABLED = False`. No module in this package imports an execution/order
submission path. Ranking output is always `WOULD_PRIORITIZE`, never `EXECUTE`. A
`READY` strategy result is evidence, not authorization.

## Known gaps / deferred (owner-directed, not implemented here)

- No `EconomicCalendarProvider` implementation is wired to a real data source --
  the interface and fail-closed UNAVAILABLE handling exist; a concrete provider is a
  separate task.
- M1 fill/slippage fetch is flagged (`pipeline.requires_m1_fetch`) but no concrete M1
  adapter call is wired -- the project's existing M1 fetch/spread-snapshot capability
  was not identified during reconciliation as a single reusable call site.
- `BarSettlementPolicy`/news-risk-window/rolling-sample-size values in
  `config/ag_scheduler_v2.yaml` are the owner-specified Phase-1 hypotheses from the
  task, not tuned or optimized (per the task's explicit "do not optimize" instruction).
- The real M15 sleep/wake loop (`scheduler.py`'s `tick()` is the pure per-instant
  function) is not wired to a live process/OS scheduler entry point -- that follows the
  repository's existing convention of a thin `scripts/run_*.py` CLI invoked by an
  external OS scheduler, which is a separate, smaller follow-up task once this package
  is reviewed.
