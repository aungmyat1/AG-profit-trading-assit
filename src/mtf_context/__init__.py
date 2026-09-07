"""multi-timeframe-market-context runtime: WRAPPER_ONLY orchestration over
market_structure/liquidity/supply_demand/entry_confirmation. ADVISORY_ONLY -- see
.agents/skills/multi-timeframe-market-context/SKILL.md for the authority contract this
package must never exceed. No import here may ever reach execution/, mt5.management_gateway,
or strategy_engine's decision path (enforced by tests/test_mtf_context_execution_guard.py).
"""
from .models import (
    ALL_ROLES,
    AUTHORITY,
    CONTEXT_READY,
    DATA_ERROR,
    INSUFFICIENT_DATA,
    INVALID_PROFILE,
    PARTIAL_CONTEXT,
    ROLE_BIAS,
    ROLE_EXECUTION,
    ROLE_MACRO,
    ROLE_MANAGEMENT,
    ROLE_SETUP,
    ROLE_WORKING,
    SKILL_ID,
    SKILL_VERSION,
    InvalidProfileError,
    LayerResult,
    MTFContext,
    MTFProfile,
)
from .orchestrator import analyze

__all__ = [
    "analyze", "MTFProfile", "MTFContext", "LayerResult", "InvalidProfileError",
    "SKILL_ID", "SKILL_VERSION", "AUTHORITY",
    "ROLE_MACRO", "ROLE_BIAS", "ROLE_WORKING", "ROLE_SETUP", "ROLE_EXECUTION", "ROLE_MANAGEMENT", "ALL_ROLES",
    "CONTEXT_READY", "PARTIAL_CONTEXT", "INSUFFICIENT_DATA", "DATA_ERROR", "INVALID_PROFILE",
]
