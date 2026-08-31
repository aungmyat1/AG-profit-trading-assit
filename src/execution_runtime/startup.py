"""AG_DAYTRADING_RUNTIME_V1 startup sequence (spec STARTUP):

  1. Construct ONE ExecutionRuntimeContext (the sole source of OpenPositionGuard/
     DailyLossGuard/CloseLedger/coordinator -- no second context, no duplicate guards).
  2. Reconcile existing MT5 AG positions (reconcile_open_positions(), via
     ExecutionRuntimeContext.coordinator.reconcile()) BEFORE allowing any new Forex
     submission.
  3. Load the enabled strategy/profile config (load_sweep_retest_strategy()).
  4. Restore persistent strategy/runtime state (SweepRetestRuntime/SweepRetestStateStore
     -- restart-safe by construction, nothing to do here beyond constructing it).
  5. Fail closed (raise, never silently proceed with unknown state) if authoritative
     execution state cannot be established -- reconcile() itself raising, or its own
     results reporting it could not even query the broker's full position list.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from execution.bar_tracker import LastClosedBarStore
from execution.runtime_context import ExecutionRuntimeContext
from strategy_engine.sweep_retest.config import SweepRetestStrategyConfig, load_sweep_retest_strategy
from strategy_engine.sweep_retest.engine import SweepRetestRuntime
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore

DEFAULT_STRATEGY_PATH = "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"

# Reconciliation outcomes that mean "authoritative broker state could NOT be established
# for at least part of the picture" -- these must block startup rather than let the
# runtime silently proceed believing no other AG position exists (spec: "fail closed").
_UNSAFE_RECONCILE_STATUSES = frozenset({"POSITION_QUERY_FAILED", "GLOBAL_POSITION_QUERY_FAILED"})


class StartupReconciliationFailed(RuntimeError):
    """Raised when startup reconciliation could not establish authoritative execution
    state -- the runtime must refuse to accept any new submission in this case."""


@dataclass(frozen=True)
class RuntimeStartup:
    ctx: ExecutionRuntimeContext
    strategy_config: SweepRetestStrategyConfig
    runtime: SweepRetestRuntime
    bar_tracker: LastClosedBarStore
    reconciliation_results: List[Dict[str, Any]]


def start(
    *,
    strategy_path: str = DEFAULT_STRATEGY_PATH,
    ctx: Optional[ExecutionRuntimeContext] = None,
    setup_state_store: Optional[SweepRetestStateStore] = None,
    bar_tracker: Optional[LastClosedBarStore] = None,
    positions_lookup=None,
    deals_lookup=None,
    now: Optional[datetime] = None,
) -> RuntimeStartup:
    """Runs the full ordered startup sequence and returns the composed runtime, or raises
    StartupReconciliationFailed / whatever load_sweep_retest_strategy raises on a config
    error -- either way, the caller (scripts/run_ag_execution_runtime.py) must not proceed
    to accept new submissions.

    ctx/positions_lookup/deals_lookup are injectable (tests: fakes/tmp_path-backed guards;
    production: ExecutionRuntimeContext.default() + real mt5.account.positions/
    mt5.deals.deals_for_position, the same defaults ExecutionCoordinator.reconcile()
    already falls back to)."""
    ctx = ctx or ExecutionRuntimeContext.default()

    # Step 2 -- BEFORE any new submission is allowed. Step ordering is the point (spec
    # test 3: "assert ordering, not just eventual consistency") -- reconcile() runs to
    # completion here, synchronously, before this function ever returns a usable context.
    try:
        reconcile_kwargs: Dict[str, Any] = {"now": now}
        if positions_lookup is not None:
            reconcile_kwargs["positions_lookup"] = positions_lookup
        if deals_lookup is not None:
            reconcile_kwargs["deals_lookup"] = deals_lookup
        results = ctx.coordinator.reconcile(**reconcile_kwargs)
    except Exception as exc:  # noqa: BLE001 -- ANY reconciliation failure blocks startup (spec)
        raise StartupReconciliationFailed(f"RECONCILIATION_ERRORED: {exc}") from exc

    unsafe = [r for r in results if r.get("status") in _UNSAFE_RECONCILE_STATUSES]
    if unsafe:
        raise StartupReconciliationFailed(
            f"RECONCILIATION_INCOMPLETE: authoritative broker state could not be established: {unsafe}"
        )

    # Step 3.
    strategy_config = load_sweep_retest_strategy(strategy_path)

    # Step 4 -- restart-safe by construction (SweepRetestStateStore reads back whatever a
    # prior process instance already persisted; nothing to "restore" beyond constructing it).
    runtime = SweepRetestRuntime(setup_state_store or SweepRetestStateStore())
    tracker = bar_tracker or LastClosedBarStore.default()

    return RuntimeStartup(
        ctx=ctx, strategy_config=strategy_config, runtime=runtime,
        bar_tracker=tracker, reconciliation_results=results,
    )
