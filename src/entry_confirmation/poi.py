"""POI (point-of-interest) context (A4 reference material) -- consumes a caller-supplied
supply_demand.ZoneResult (Order Block, FVG, or a generic supply/demand zone) verbatim,
plus an optional caller-supplied liquidity.LiquidityLevel it is associated with. Never
redetects OB/FVG/zone geometry, never redetects liquidity.

Mandatory (spec rule 14): PRICE_AT_POI != ENTRY_CONFIRMED. `status` here is drawn from
a vocabulary that never includes "CONFIRMED" -- the furthest this module goes is
POI_REACHED / WAITING_CONFIRMATION / WAITING_LIQUIDITY_EVENT. Turning a POI into an
entry is entry_geometry's job (route.py), driven by an actual LTF confirmation event,
never by POI proximity alone.
"""
from __future__ import annotations

from typing import Optional

from liquidity import LiquidityLevel, LiquidityStatus
from supply_demand import ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

from .models_v2 import POIContext


def _poi_type(zone: ZoneResult) -> str:
    if zone.family == ZoneFamily.ORDER_BLOCK:
        return "ORDER_BLOCK"
    if zone.family == ZoneFamily.FVG:
        return "FVG"
    if zone.role == ZoneRole.SUPPLY:
        return "SUPPLY_ZONE"
    if zone.role == ZoneRole.DEMAND:
        return "DEMAND_ZONE"
    return "COMPOSITE_POI"


def evaluate_poi_context(
    zone: Optional[ZoneResult],
    liquidity_level: Optional[LiquidityLevel] = None,
    liquidity_side: Optional[str] = None,  # "ABOVE" / "BELOW", caller-asserted relationship
    price_action_coverage_confirmed: Optional[bool] = None,
) -> POIContext:
    if zone is None:
        return POIContext(status="UNRESOLVED", reason="No candidate POI zone supplied.")

    poi_type = _poi_type(zone)
    midpoint = (zone.low + zone.high) / 2.0 if zone.low is not None and zone.high is not None else None

    if liquidity_level is not None and liquidity_side in ("ABOVE", "BELOW"):
        association = f"{poi_type}_WITH_LIQUIDITY_{liquidity_side}"
    else:
        association = "NONE"

    if price_action_coverage_confirmed is True:
        pac = "CONFIRMED"
    elif price_action_coverage_confirmed is False:
        pac = "NOT_CONFIRMED"
    else:
        pac = "UNRESOLVED"

    evidence = [f"zone.status={zone.status.value}", f"poi_type={poi_type}"]
    if liquidity_level is not None:
        evidence.append(f"liquidity_level.status={liquidity_level.status.value}")

    if zone.status == ZoneStatus.INVALIDATED:
        status = "INVALIDATED"
        reason = "Upstream supply_demand zone reports INVALIDATED."
    elif zone.status == ZoneStatus.MITIGATED:
        # "Filled OB -- wait for sweep" (spec rules 13, 60): a mitigated POI whose
        # associated liquidity has not yet been swept/reclaimed cannot be treated as
        # ready on its own.
        if liquidity_level is not None and liquidity_level.status in (
            LiquidityStatus.UNSWEPT, LiquidityStatus.UNKNOWN,
        ):
            status = "WAITING_LIQUIDITY_EVENT"
            reason = "POI mitigated but associated liquidity is not yet swept -- waiting for sweep."
        else:
            status = "WAITING_CONFIRMATION"
            reason = "POI mitigated -- price has interacted with the zone; awaiting LTF confirmation."
    elif zone.status == ZoneStatus.TOUCHED:
        status = "POI_REACHED"
        reason = "Price has touched the POI -- reaction/confirmation not yet evaluated (touch != reaction)."
    elif zone.status == ZoneStatus.FRESH:
        status = "WAITING_POI"
        reason = "POI has not yet been reached by price."
    else:  # UNKNOWN
        status = "UNRESOLVED"
        reason = "Upstream zone status could not be determined."

    return POIContext(
        status=status,
        poi_type=poi_type,
        poi_high=zone.high,
        poi_low=zone.low,
        poi_midpoint=midpoint,
        poi_direction=zone.direction.value if zone.direction else None,
        poi_timeframe=zone.timeframe,
        liquidity_association=association,
        structure_association=None,
        price_action_coverage=pac,
        mitigation_state=zone.status.value,
        invalidation_state="INVALIDATED" if zone.status == ZoneStatus.INVALIDATED else "VALID",
        evidence=tuple(evidence),
        reason=reason,
    )
