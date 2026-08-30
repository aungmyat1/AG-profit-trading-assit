"""AG_DAILY_ROUTINE_V1 -- D1 (direction) -> H1 (location) -> M5 (execution)
orchestrator over the existing five skills. See docs/specs/AG_DAILY_ROUTINE_V1_SPEC.md.
"""
from .d1_context import build_d1_context
from .h1_setup import build_h1_setup_context
from .m5_execution import evaluate_m5_execution
from .models import (
    AlertZone,
    D1Context,
    DailyRoutineResult,
    DIRECTIONAL_PERMISSION_BOTH,
    DIRECTIONAL_PERMISSION_INDETERMINATE,
    DIRECTIONAL_PERMISSION_LONG_ONLY,
    DIRECTIONAL_PERMISSION_NO_TRADE,
    DIRECTIONAL_PERMISSION_SHORT_ONLY,
    FundamentalContext,
    H1SetupContext,
    M5ExecutionContext,
    MidnightOpen,
    TP2_POLICY_REQUIRED,
)
from .orchestrator import run_daily_routine

__all__ = [
    "run_daily_routine", "build_d1_context", "build_h1_setup_context", "evaluate_m5_execution",
    "D1Context", "H1SetupContext", "M5ExecutionContext", "DailyRoutineResult",
    "FundamentalContext", "MidnightOpen", "AlertZone", "TP2_POLICY_REQUIRED",
    "DIRECTIONAL_PERMISSION_LONG_ONLY", "DIRECTIONAL_PERMISSION_SHORT_ONLY",
    "DIRECTIONAL_PERMISSION_BOTH", "DIRECTIONAL_PERMISSION_NO_TRADE", "DIRECTIONAL_PERMISSION_INDETERMINATE",
]
