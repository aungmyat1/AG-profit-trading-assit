"""ExecutionRuntimeContext: ONE composition root for the shared GLOBAL execution guards
(AG_EXECUTION_RUNTIME_READINESS_V1, GAP 3).

Before this module, every caller that needed OpenPositionGuard/DailyLossGuard/CloseLedger/
ExecutionCoordinator constructed them by hand -- correctly, but repeatedly (see
ExecutionCoordinator.default(), and the .default()-then-manually-pass-guards pattern every
test file in this repo already uses, e.g. tests/test_execution_coordinator.py::_coordinator,
tests/test_execution_lifecycle.py::_coordinator, strategy_engine/sweep_retest/engine.py's
own optional daily_loss_guard/open_position_guard parameters). Nothing here is new
plumbing -- this is a strict superset convenience over that exact same manual-wiring
pattern, not a second competing way to build these objects: it does not rewrite
OpenPositionGuard/DailyLossGuard/CloseLedger/ExecutionCoordinator, and it does not
introduce module-level singleton state -- each ExecutionRuntimeContext instance owns its
own guard instances, exactly like today's manual construction does.

The point: a future runtime should construct exactly ONE ExecutionRuntimeContext and hand
its SAME guard instances to both call sites that need them --

  - the STRATEGY-EVALUATION side (e.g. strategy_engine.sweep_retest.engine.evaluate_setup's
    own daily_loss_guard=/open_position_guard= parameters, or ST_ASIAN_SWEEP_5R_V1's
    signal path if it is ever wired to read guard state advisorily) -- for ADVISORY/
    preliminary "would this be blocked" visibility only.
  - the COORDINATOR side (ExecutionCoordinator.submit()/.reconcile()) -- the SOLE
    AUTHORITATIVE decision-maker for whether a proposal may actually execute.

so there is no way to accidentally end up with two different OpenPositionGuard objects
pointed at different underlying JsonKeyValueStore files, which would let a strategy
"see" one guard state while the coordinator enforces another. See
tests/test_execution_runtime_readiness.py for a test proving exactly this: one context
used for both an evaluation-side call and a coordinator submission gives byte-identical
blocking behavior.
"""
from __future__ import annotations

from dataclasses import dataclass

from .close_ledger import CloseLedger
from .coordinator import GLOBAL_LEDGER_STRATEGY_ID, ExecutionCoordinator
from .daily_loss_guard import DailyLossGuard
from .position_guard import OpenPositionGuard


@dataclass(frozen=True)
class ExecutionRuntimeContext:
    """One coordinator instance = one shared triple of GLOBAL guards, exactly the
    invariant ExecutionCoordinator's own docstring already establishes -- this class just
    makes constructing the whole set together, from the same underlying stores, the
    single obvious thing to do."""

    open_position_guard: OpenPositionGuard
    daily_loss_guard: DailyLossGuard
    close_ledger: CloseLedger
    coordinator: ExecutionCoordinator

    @classmethod
    def default(cls) -> "ExecutionRuntimeContext":
        """The real, on-disk shared guards -- same paths OpenPositionGuard.default()/
        DailyLossGuard.default()/CloseLedger.default()/ExecutionCoordinator.default()
        already use individually; this just wires all four from the SAME instances in one
        call instead of leaving that up to each caller to get right independently."""
        open_position_guard = OpenPositionGuard.default()
        daily_loss_guard = DailyLossGuard.default(GLOBAL_LEDGER_STRATEGY_ID)
        close_ledger = CloseLedger.default()
        coordinator = ExecutionCoordinator(
            open_position_guard=open_position_guard,
            daily_loss_guard=daily_loss_guard,
            close_ledger=close_ledger,
        )
        return cls(open_position_guard, daily_loss_guard, close_ledger, coordinator)

    @classmethod
    def build(
        cls,
        open_position_guard: OpenPositionGuard,
        daily_loss_guard: DailyLossGuard,
        close_ledger: "CloseLedger | None" = None,
    ) -> "ExecutionRuntimeContext":
        """Explicit-construction path for tests (tmp_path-backed guards, same isolation
        idiom every existing execution test already uses) or any caller that already has
        its own guard instances to share. Builds the ONE ExecutionCoordinator from exactly
        these instances -- a caller cannot end up with a second ExecutionCoordinator
        pointed at different guards through this constructor."""
        close_ledger = close_ledger if close_ledger is not None else CloseLedger.default()
        coordinator = ExecutionCoordinator(
            open_position_guard=open_position_guard,
            daily_loss_guard=daily_loss_guard,
            close_ledger=close_ledger,
        )
        return cls(open_position_guard, daily_loss_guard, close_ledger, coordinator)
