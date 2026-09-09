"""Active dealing range derivation (P16) -- WHICH swing pair defines premium/discount,
not just "the most recent arbitrary high and low".

Reuses supply_demand.native_zones.dealing_range_zones(symbol, low, high, source,
current_price) verbatim for the actual premium/equilibrium/discount arithmetic (never
reimplemented here) -- this module's only job is picking the swing pair to feed it: the
canonical market_structure engine's own latest CONFIRMED swing high and swing low on a
caller-named timeframe. If either confirmed swing is missing, or the high/low pair is
degenerate (high <= low), this fails closed to None (P16: "If the active dealing range
cannot be established: active_dealing_range = null").
"""
from __future__ import annotations

from typing import Optional

from market_structure.models import StructureResult
from supply_demand.native_zones import dealing_range_zones

from .models import DealingRangeSnapshot


def active_dealing_range_from_structure(
    structure_result: StructureResult,
    current_price: Optional[float] = None,
) -> Optional[DealingRangeSnapshot]:
    high_point = structure_result.latest_swing_high
    low_point = structure_result.latest_swing_low
    if high_point is None or low_point is None:
        return None
    if high_point.price <= low_point.price:
        # Degenerate/stale pair (e.g. a swing_high below the swing_low from an older
        # structural regime) -- do not report a range that cannot be a real dealing
        # range. Fail closed rather than silently swapping high/low.
        return None

    zone = dealing_range_zones(
        symbol=structure_result.symbol,
        low=low_point.price,
        high=high_point.price,
        source=f"structure:{structure_result.timeframe}:latest_confirmed_swing_pair",
        current_price=current_price,
    )
    return DealingRangeSnapshot(
        swing_high=zone.high,
        swing_low=zone.low,
        equilibrium=zone.equilibrium,
        current_zone=zone.current_zone,
        defining_timeframe=structure_result.timeframe,
        source=zone.source,
    )
