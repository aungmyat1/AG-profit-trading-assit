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
from .topdown_contracts import (
    ALL_CANONICAL_TIMEFRAMES,
    ALLOWED_STRUCTURE_DEFINITION_IDS,
    DATA_QUALITY_DATA_ERROR,
    DATA_QUALITY_MISSING,
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_H4,
    TIMEFRAME_M1,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
    TOPDOWN_TIMEFRAMES,
    DailyContext,
    H1Context,
    H4Context,
    InvalidDataQualityStatusError,
    InvalidStructureDefinitionError,
    InvalidTimeframeError,
    M5Context,
    M15Context,
    StructureFact,
    TimeframeRequirement,
    TopDownContext,
    WeeklyContext,
    compute_context_id,
)

__all__ = [
    "analyze", "MTFProfile", "MTFContext", "LayerResult", "InvalidProfileError",
    "SKILL_ID", "SKILL_VERSION", "AUTHORITY",
    "ROLE_MACRO", "ROLE_BIAS", "ROLE_WORKING", "ROLE_SETUP", "ROLE_EXECUTION", "ROLE_MANAGEMENT", "ALL_ROLES",
    "CONTEXT_READY", "PARTIAL_CONTEXT", "INSUFFICIENT_DATA", "DATA_ERROR", "INVALID_PROFILE",
    # TD-1 top-down context contracts (additive; see topdown_contracts.py)
    "TIMEFRAME_W1", "TIMEFRAME_D1", "TIMEFRAME_H4", "TIMEFRAME_H1", "TIMEFRAME_M15", "TIMEFRAME_M5", "TIMEFRAME_M1",
    "TOPDOWN_TIMEFRAMES", "ALL_CANONICAL_TIMEFRAMES",
    "DATA_QUALITY_VALID", "DATA_QUALITY_PARTIAL", "DATA_QUALITY_MISSING", "DATA_QUALITY_DATA_ERROR",
    "STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1", "ALLOWED_STRUCTURE_DEFINITION_IDS",
    "InvalidTimeframeError", "InvalidDataQualityStatusError", "InvalidStructureDefinitionError",
    "StructureFact", "TimeframeRequirement", "compute_context_id",
    "WeeklyContext", "DailyContext", "H4Context", "H1Context", "M15Context", "M5Context", "TopDownContext",
]
