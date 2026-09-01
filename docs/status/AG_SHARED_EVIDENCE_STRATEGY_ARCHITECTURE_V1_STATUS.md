# AG Shared Evidence + Multi-Strategy Engine Architecture V1 — Status (2026-09-01)

## Scope

Read-only architectural audit of the SKILLS -> EVIDENCE -> STRATEGY -> PORTFOLIO ->
RISK -> EXECUTION authority boundary, followed by the smallest necessary fix. No
strategy semantics were invented, no active strategy behavior changed, no execution
code was touched, and no Stage1/Stage2 replay contract was modified.

## Audit method

Three parallel read-only agents covered: (1) `strategies/registry.yaml` +
`strategy_manager/manager.py` + `strategy_engine/` dispatch, (2) the six shared skill
wrappers (`market-data`, `market-structure-analysis`, `supply-demand-analysis`,
`liquidity-analysis`, `entry-confirmation-analysis`, `trade-management-analysis`) and
their deterministic modules, (3) the Large-SMC workflow, evidence-envelope shape,
research-candidate persistence, replay/golden-slice location, and the
portfolio/risk/execution call graph.

## Findings

**Skills (PASS).** All six shared skills return typed, frozen dataclasses with explicit
status/reason codes and provenance (symbol/timeframe/timestamps). None import
`execution.*`, `mt5.management_gateway`, or risk-sizing modules. Strategy-shaped
verdicts (BUY/SELL/READY) are explicitly disclaimed in every `SKILL.md`.
`trade-management-analysis` is confirmed disjoint from `trade_management/manager.py`
(the separate, gateway-calling, execution-capable subsystem reached only via
`scripts/manage_positions.py`).

**Strategy registry/dispatch (PASS with one gap, now closed).**
`ST_LARGE_SMC_V1` has zero references anywhere under `src/` — nothing currently calls
it, so it structurally cannot reach READY, risk sizing, or execution.
`strategy_manager.manager.evaluate()` fail-closes correctly: unregistered, inactive, and
non-`SESSION_TRADE_V1` strategy ids are all rejected before any decision logic runs
(`strategy_manager/manager.py:88-95`).

Gap found: `scripts/run_strategy.py` (the `ST_ASIAN_SWEEP_5R_V1` ANALYSIS-mode CLI) took
an arbitrary `--strategy` argument and called `strategy_engine.evaluate()` with **no
registry/status check at all**. It was safe today only because `ST_LARGE_SMC_V1.yaml`'s
schema happens to mismatch what `load_strategy()` requires — an accident of the current
contract, not a designed gate. The script never sizes risk or sends orders, but it can
print a signal-shaped result (direction/entry/stop_loss), so a non-`ACTIVE` strategy
should not reach evaluation there either.

**Fix applied:** added `_check_registry_active()` to `scripts/run_strategy.py`, checked
before `load_strategy()`/`connect()`/`evaluate()`. Any strategy id that is unregistered
or not `active: true` in `strategies/registry.yaml` now returns `status=BLOCKED,
reason_code=STRATEGY_NOT_REGISTERED|STRATEGY_NOT_ACTIVE` before any MT5 connection or
strategy evaluation happens. `ST_ASIAN_SWEEP_5R_V1` (the only default/active caller) is
unaffected — same input still produces the same signal.

**Workflow/evidence (documented gaps, no action taken — out of scope for this phase).**
- No `LargeSMCWorkflow` orchestrator exists. This is consistent with `ST_LARGE_SMC_V1`
  being `RESEARCH_DRAFT`/`engine: NOT_IMPLEMENTED` with `UNSIGNED` entry/SL/target
  fields; building an orchestrator ahead of a frozen strategy contract would risk
  guessing at evidence shape the contract hasn't specified yet (forbidden by spec
  section 50). Deferred to `ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION`.
- No shared `SkillEvidence` envelope class exists; each skill has its own typed result
  (`StructureResult`, `ZoneResult`, `LiquidityResult`, `EntryConfirmationResult`,
  `TradeManagementResult`) that already carries status/provenance/symbol/timeframe.
  These are functionally equivalent to the envelope's intent; introducing a formal base
  class now would touch multiple proven, working modules for no behavior change — left
  as a documented option, not performed.
- No Large-SMC research-candidate ledger exists (`NOT_IMPLEMENTED`); nothing currently
  produces a candidate to persist.
- `ST_LIQUIDITY_SWEEP_RETEST_V1` has a real engine (`src/strategy_engine/sweep_retest/`)
  but no `strategies/registry.yaml` row — a registry-completeness/documentation gap,
  not an authority leak (nothing dispatches it without an explicit caller either).
  Left unresolved pending owner decision on registry schema (`family`/`role` fields
  don't exist in the current registry shape either).

**Portfolio/risk/execution (PASS).** `size_position()`/`order_check`/`order_send` are
reachable only through a validated `TradeProposal` plus an explicit, non-defaulted
`user_confirmed=True` supplied by `assistant.commands.execute_command()` in the same
turn as an explicit user execution instruction. No path from raw skill evidence or a
`RESEARCH_DRAFT` strategy result reaches these. Existing tests already assert this:
`tests/test_dual_workflow_boundaries.py`, `tests/test_large_smc_registration.py`,
`tests/test_execution_safety_v1.py`, `tests/test_execution_coordinator.py`.

**Replay (untouched).** Stage1/Stage2 (`src/historical_replay/`) and the golden vertical
slice (`artifacts/backtests/golden/two_stage_golden_fixture_v1.json`,
`tests/test_golden_vertical_slice.py`) were not modified and were not re-run (no change
in this phase touches that path).

## Tests

- `pytest tests/test_run_strategy_registry_gate.py` — 5 passed (new; proves the fix,
  including that `connect()` is never reached for a blocked strategy).
- `pytest tests/test_large_smc_registration.py tests/test_dual_workflow_boundaries.py
  tests/test_execution_safety_v1.py tests/test_execution_coordinator.py` — 44 passed
  (pre-existing boundary tests, unchanged).
- `pytest tests/ -k "strategy_engine or asian_sweep or session_workflow or
  run_strategy"` — 11 passed (confirms `ST_ASIAN_SWEEP_5R_V1` evaluation path
  unaffected).
- Full repo-wide suite and the golden replay slice were not re-run: the change is
  scoped to one CLI script's pre-evaluation gate and does not touch strategy engines,
  session semantics, evidence models, or replay code.

## Files changed

- `scripts/run_strategy.py` — added registry-active gate before strategy evaluation.
- `tests/test_run_strategy_registry_gate.py` — new, covers the gate.
- `docs/status/AG_SHARED_EVIDENCE_STRATEGY_ARCHITECTURE_V1_STATUS.md` — this document.

## Terminal state

`VERIFIED_WITH_NONBLOCKING_GAPS`. The authority boundary (skills=evidence,
strategies=decisions, portfolio/risk/execution=downstream, `RESEARCH_DRAFT`=fail-closed)
holds today. Remaining gaps (evidence envelope formalization, `LargeSMCWorkflow`,
research-candidate ledger, registry completeness for
`ST_LIQUIDITY_SWEEP_RETEST_V1`/`ST_HIGH_RR_LIQUIDITY_MSS_V1`) are documentation/
future-work items, not active leaks, and are correctly blocked by the current absence of
any caller into `ST_LARGE_SMC_V1`.

Next phase: `ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION` (freeze direction/location/
activation/confirmation/entry/SL/target/expiry) before any workflow/engine work begins.
