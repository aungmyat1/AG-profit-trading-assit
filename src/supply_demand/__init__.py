"""Supply & Demand capability (Phase 3): Order Blocks and Fair Value Gaps via
smartmoneyconcepts (wrapped, never exposed raw -- see smc_adapter.py), plus native
(non-smc) session zones, previous-day high/low, and premium/equilibrium/discount from
an explicitly-named dealing range.

Order Block contract (AG_ORDER_BLOCK_V1, frozen by owner 2026-08-26): `order_blocks_for()`
still returns raw smc.ob() CANDIDATE zones unchanged (existing behavior preserved).
`validated_order_blocks_for()` additionally runs each candidate through the AG Order
Block Validator (ob_contract.py) -- PIVOT_OB/SHADOW_OB zone geometry, required matching
BOS/CHoCH, required same-direction FVG within 3 candles, WICK_TOUCH_BOUNDARY mitigation,
close-beyond-zone invalidation. See ob_contract.py for what's frozen vs. still an
interpretation, and ORDER_BLOCK_CONTRACT_GAPS for what's still unresolved (FLIP_OB
identification, L1/L2, inside-bar D2S/S2D -- all explicitly UNSIGNED).

Advisory only: no execution authority. See PROJECT_STATUS.md 'Authority order'.
"""
from .analyzer import fair_value_gaps_for, order_blocks_for, validated_order_blocks_for
from .models import ZoneDirection, ZoneFamily, ZoneQueryResult, ZoneResult, ZoneRole, ZoneStatus, zone_id
from .native_zones import (
    DealingRangeZones,
    dealing_range_zones,
    premium_discount_from_previous_day,
    premium_discount_from_session,
    previous_day_high_low,
    previous_week_high_low,
    session_zone,
)
from .ob_config import AGOrderBlockConfig, load_ag_order_block_config
from .ob_contract import (
    INSIDE_BAR_FLIP_RULE,
    L1_L2_CLASSIFICATION,
    MAX_CANDLES_TO_FVG,
    ORDER_BLOCK_CONTRACT_GAPS,
    OBFamily,
    OBValidationStatus,
    OrderBlockContractGap,
    ValidatedOrderBlock,
    validate_order_block,
    validate_order_blocks,
)

__all__ = [
    "order_blocks_for", "fair_value_gaps_for", "validated_order_blocks_for",
    "session_zone", "previous_day_high_low", "previous_week_high_low", "dealing_range_zones",
    "premium_discount_from_previous_day", "premium_discount_from_session",
    "DealingRangeZones",
    "ZoneResult", "ZoneQueryResult", "ZoneFamily", "ZoneRole", "ZoneDirection", "ZoneStatus", "zone_id",
    "ValidatedOrderBlock", "OBFamily", "OBValidationStatus",
    "validate_order_block", "validate_order_blocks",
    "OrderBlockContractGap", "ORDER_BLOCK_CONTRACT_GAPS",
    "MAX_CANDLES_TO_FVG", "L1_L2_CLASSIFICATION", "INSIDE_BAR_FLIP_RULE",
    "AGOrderBlockConfig", "load_ag_order_block_config",
]
