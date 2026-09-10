"""Authority boundary (spec section 0). READY != AUTHORIZED_FOR_EXECUTION. This module
is the single place that states the scheduler's lifecycle facts and refuses execution
outright -- nothing else in this package may import an execution/order-submission
module, and this guard exists so that stays true even under future modification.
"""
from __future__ import annotations

LIFECYCLE_STAGE = "OFFLINE_RESEARCH"
DEMO_ELIGIBLE = False
DEMO_AUTHORIZED = False
EXECUTION_ENABLED = False


class ExecutionNotAuthorized(RuntimeError):
    """Raised by guard_no_execution() -- AG_DAILY_OPPORTUNITY_SCHEDULER_V2 has no path
    that is allowed to reach this call."""


def guard_no_execution(*_args, **_kwargs) -> None:
    """Any code path that would submit a demo/live order must call this first (or,
    better, must simply not exist in this package). Kept as a defense-in-depth
    trip-wire, not because a real call site is expected to reach it."""
    raise ExecutionNotAuthorized(
        "AG_DAILY_OPPORTUNITY_SCHEDULER_V2 is OFFLINE_RESEARCH: demo_eligible=False, "
        "demo_authorized=False. READY != AUTHORIZED_FOR_EXECUTION."
    )
