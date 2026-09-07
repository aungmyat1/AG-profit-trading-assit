"""StrategyController -- a narrow, Strategy-side runtime interface
(AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_V1, Phase 2).

Discovery finding (see docs/architecture/AG_STRATEGY_TECH_SELECTIVE_PORT_REUSE_LEDGER.md):
AG already has a working multi-workflow runtime orchestrator,
`daytrading_runtime.coordinator.RuntimeCoordinator` (SESSION + SMC cycles, READ_ONLY,
execution_submission=DISABLED), plus separate per-strategy orchestration entry points for
BTC (`btc_sweep_research.pipeline`) and Large-SMC (`large_smc_research.engine`) that each
have their own cadence/data requirements/authority. None of the three is missing a
runtime; what does not exist is a common TYPE that all of them could structurally satisfy.

This module adds ONLY that type -- a `typing.Protocol`, not a base class, not a new
orchestration engine, and NOT wired into RuntimeCoordinator or any pipeline. Nothing in
this repository is required to implement it; it exists so a future caller (e.g. a
cross-strategy research dashboard) can type-check "does this look like a strategy
controller" without importing any one strategy's concrete engine.

Deliberately excluded (see AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md's bidirectional-
import finding): no `place_order`, `cancel_order`, `close_position`, `account`, `broker`,
or any Execution-side method or property. A StrategyController may itself import
Execution's guard/risk modules for pre-flight checks (AG's existing, intentional,
bidirectional pattern -- strategy_engine.sweep_retest.engine and post_asian_pilot.pipeline
already do this) but must never RETURN an execution command; it returns only
StrategyDecision.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .decision import StrategyDecision


@runtime_checkable
class StrategyController(Protocol):
    """Structural interface only. No AG strategy is required to inherit from this; any
    object with a matching `strategy_id` property and `evaluate` method already satisfies
    it (see `isinstance(..., StrategyController)` via `runtime_checkable`)."""

    @property
    def strategy_id(self) -> str: ...

    def evaluate(self, market_context: Any) -> Optional[StrategyDecision]:
        """Return the strategy's current StrategyDecision for the given market context,
        or None if there is nothing to report yet. MUST NEVER return, construct, or
        expose an execution command, broker order, or account object."""
        ...
