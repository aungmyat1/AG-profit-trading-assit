"""AG_STRATEGY_DIRECTION_CONTRACT_V1 -- Layer 1 (Market Intelligence).

M1 (canonical contract) + M2/M3 (daytrading.decision.market_bias converted to a thin
adapter over resolve_from_structure_tiers -- see that module's docstring). No further
strategy migration happens in this milestone -- see
docs/architecture/AG_UNIVERSAL_STRATEGY_DIRECTION_ARCHITECTURE_V1.md for the full staged
plan (M0-M6) and docs/status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M2_M3_STATUS.md
for what this milestone did and explicitly did not do.
"""
from __future__ import annotations

from .models import Bias, MarketBiasResult
from .bias_resolver import (
    resolve_from_daytrading_market_bias,
    resolve_from_structure_tiers,
    resolve_unavailable,
)

__all__ = [
    "Bias", "MarketBiasResult",
    "resolve_from_daytrading_market_bias", "resolve_from_structure_tiers", "resolve_unavailable",
]
