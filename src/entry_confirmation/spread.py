"""Spread-aware alert/invalidation geometry (A5 reference material). Never hard-codes a
spread value -- always caller-supplied (broker/symbol metadata or an explicit test
fixture). If unavailable, reports UNRESOLVED rather than assuming zero spread (spec
rules 15, 16, 55, 56, 71). This is alert/monitoring geometry only, never a broker fill
price and never position sizing.

    BUY  alert = price - spread
    SELL alert = price + spread

Invalidation adjustment pushes the structural stop further from price by one spread,
in the direction away from price, mirroring the same LONG/SHORT convention.
"""
from __future__ import annotations

from typing import Optional

from .models import CandidateDirection
from .models_v2 import SpreadContext


def evaluate_spread_context(
    price: Optional[float],
    spread: Optional[float],
    candidate_direction: CandidateDirection = CandidateDirection.NONE,
    invalidation_reference_price: Optional[float] = None,
) -> SpreadContext:
    if spread is None or price is None:
        return SpreadContext(
            status="UNRESOLVED",
            alert_reference_price=price,
            invalidation_reference_price=invalidation_reference_price,
            reason="SPREAD_ALERT = UNRESOLVED -- no spread/price supplied.",
        )
    if candidate_direction == CandidateDirection.NONE:
        return SpreadContext(
            status="UNRESOLVED", spread=spread, alert_reference_price=price,
            invalidation_reference_price=invalidation_reference_price,
            reason="candidate_direction is required to resolve spread-adjusted alert direction.",
        )

    if candidate_direction == CandidateDirection.LONG:
        alert_price = price - spread
        invalidation = (
            invalidation_reference_price - spread if invalidation_reference_price is not None else None
        )
    else:  # SHORT
        alert_price = price + spread
        invalidation = (
            invalidation_reference_price + spread if invalidation_reference_price is not None else None
        )

    return SpreadContext(
        status="RESOLVED",
        spread=spread,
        alert_reference_price=price,
        spread_adjusted_alert_price=alert_price,
        invalidation_reference_price=invalidation_reference_price,
        spread_adjusted_invalidation=invalidation,
    )
