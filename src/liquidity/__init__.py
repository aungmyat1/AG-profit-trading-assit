"""Liquidity capability (Phase 4): structural swings, session/PDH-PDL liquidity, and
equal-highs/equal-lows, each tracked through a sweep/reclaim state machine (status.py).

Reuses market_structure.analyze_structure(), supply_demand.session_zone(), and
supply_demand.previous_day_high_low() rather than recalculating them -- see
analyzer.py's module docstring.

Deliberately independent of strategy_engine.session.setups.entry_2_sweep: that is the
frozen, strategy-specific sweep contract for ST_ASIAN_SWEEP_5R_V1's own session box; this
is a general-purpose liquidity read usable for any level, any symbol, any timeframe.
Both may disagree on the same market moment and that is expected -- see the
liquidity-analysis skill for how to report that without either overriding the other.

Advisory only: no execution authority. See PROJECT_STATUS.md 'Authority order'.

Contract: AG_LIQUIDITY_V1 (contract.py) -- documents which sources are session-dependent,
structure-dependent, or always-available, and records the cross-source deduplication
(dedup.py) added to preserve source provenance when multiple detectors agree on one price.
"""
from .affinity import (
    AFFINITY_INVALIDATED,
    AFFINITY_RULE_VERSION,
    BEARISH_INTERNAL_TO_EXTERNAL,
    BULLISH_INTERNAL_TO_EXTERNAL,
    EXTERNAL_LIQUIDITY_REACHED,
    EXTERNAL_TO_INTERNAL,
    INDETERMINATE as AFFINITY_INDETERMINATE,
    INTERNAL_REBALANCING,
    LiquidityAffinityResult,
    evaluate_liquidity_affinity,
    liquidity_affinity_result,
)
from .analyzer import liquidity_result
from .contract import CONTRACT_VERSION, LIQUIDITY_CONTRACT_GAPS, LiquidityContractGap
from .hierarchy import (
    SCOPE_EXTERNAL,
    SCOPE_INTERNAL,
    InducementCandidate,
    ScopedLiquidityLevel,
    classify_roles,
    external_swing_liquidity,
    find_inducement_candidates,
    level_id,
    scope_liquidity_levels,
)
from .models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus

__all__ = [
    "liquidity_result", "LiquidityLevel", "LiquidityResult", "LiquiditySide", "LiquidityStatus",
    "CONTRACT_VERSION", "LIQUIDITY_CONTRACT_GAPS", "LiquidityContractGap",
    "SCOPE_EXTERNAL", "SCOPE_INTERNAL", "ScopedLiquidityLevel", "InducementCandidate",
    "external_swing_liquidity", "scope_liquidity_levels", "find_inducement_candidates",
    "classify_roles", "level_id",
    "LiquidityAffinityResult", "evaluate_liquidity_affinity", "liquidity_affinity_result",
    "AFFINITY_RULE_VERSION", "BULLISH_INTERNAL_TO_EXTERNAL", "BEARISH_INTERNAL_TO_EXTERNAL",
    "EXTERNAL_TO_INTERNAL", "INTERNAL_REBALANCING", "EXTERNAL_LIQUIDITY_REACHED",
    "AFFINITY_INVALIDATED", "AFFINITY_INDETERMINATE",
]
