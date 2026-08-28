"""DAYTRADING_BASIC_SKILLS_ROUTER_V1 -- a deterministic setup router: Market Structure
gives market bias, strategy_engine.session gives session-box RANGE/TREND regime and
(for RANGE) a boundary-liquidity-sweep check, and this package's own setup_router.py
combines the two into SWEEP_SETUP / RANGE_SETUP / TREND_SETUP / NO_SETUP with a
fail-closed bias-alignment gate. See docs/architecture and this package's own module
docstrings for the exact division of responsibility.

Deliberately reuses strategy_engine.session.classify()/route_completed_session() and
its 0.40 ER threshold / strict-penetration sweep rule verbatim -- this package adds the
market-bias gate that was missing, never a second regime/sweep engine.
"""
from .market_bias import derive_market_bias, derive_market_bias_from_tiers
from .models import (
    DaytradingSetupDecision,
    DirectionAlignment,
    MarketBias,
    MarketBiasDirection,
)
from .setup_router import route_daytrading_setup

__all__ = [
    "derive_market_bias", "derive_market_bias_from_tiers",
    "DaytradingSetupDecision", "DirectionAlignment", "MarketBias", "MarketBiasDirection",
    "route_daytrading_setup",
]
