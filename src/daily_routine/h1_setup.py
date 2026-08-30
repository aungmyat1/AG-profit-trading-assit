"""build_h1_setup_context() -- orchestration only. Consumes D1Context; calls existing
market_structure/liquidity/supply_demand capabilities for H1 location (spec section
5). Midnight Open and the alert/breathing-room zone are documented GAPs (models.py) --
never approximated here."""
from __future__ import annotations

from liquidity import liquidity_result
from market_structure import analyze_structure
from mt5.market_data import MarketDataError, get_tick
from supply_demand import validated_order_blocks_for
from supply_demand.models import ZoneRole
from supply_demand.native_zones import session_zone

from .models import (
    D1Context,
    DIRECTIONAL_PERMISSION_LONG_ONLY,
    DIRECTIONAL_PERMISSION_SHORT_ONLY,
    H1_INDETERMINATE,
    H1_POI_IDENTIFIED,
    H1_POI_REACHED,
    H1_WAITING_CONTEXT,
    H1_WAITING_LOCATION,
    AlertZone,
    H1SetupContext,
    MidnightOpen,
)

_ROLE_FOR_PERMISSION = {
    DIRECTIONAL_PERMISSION_LONG_ONLY: ZoneRole.DEMAND,
    DIRECTIONAL_PERMISSION_SHORT_ONLY: ZoneRole.SUPPLY,
}


def build_h1_setup_context(symbol: str, d1: D1Context) -> H1SetupContext:
    if d1.status == "UNAVAILABLE":
        return H1SetupContext(symbol=symbol, as_of=None, d1_directional_permission=d1.directional_permission,
                              status=H1_WAITING_CONTEXT, reasoning_codes=("D1_CONTEXT_UNAVAILABLE",))

    reasoning: list = []
    evidence: dict = {}

    try:
        structure = analyze_structure(symbol, "H1")
        structure_direction = structure.state if structure.status == "VALID" else None
    except MarketDataError as exc:
        structure_direction = None
        reasoning.append(f"H1_STRUCTURE_FETCH_FAILED:{exc.reason_code}")

    external_liquidity: tuple = ()
    try:
        liq = liquidity_result(symbol, "H1")
        if liq.status == "LIQUIDITY_OK":
            external_liquidity = liq.levels
            evidence["liquidity"] = liq
    except MarketDataError as exc:
        reasoning.append(f"H1_LIQUIDITY_FETCH_FAILED:{exc.reason_code}")

    asian_high = asian_low = None
    try:
        asian = session_zone(symbol, "asian")
        if asian.low is not None and asian.high is not None:
            asian_high, asian_low = asian.high, asian.low
        else:
            reasoning.append(f"ASIAN_SESSION_{asian.reason_codes[0] if asian.reason_codes else 'UNAVAILABLE'}")
    except MarketDataError as exc:
        reasoning.append(f"ASIAN_SESSION_FETCH_FAILED:{exc.reason_code}")

    role = _ROLE_FOR_PERMISSION.get(d1.directional_permission)
    poi_candidates: tuple = ()
    selected_poi = None
    if role is not None:
        try:
            obs = tuple(validated_order_blocks_for(symbol, "H1"))
            poi_candidates = tuple(v.candidate for v in obs if v.candidate is not None and v.candidate.role == role)
            selected_poi = max(poi_candidates, key=lambda z: z.origin_time or __import__("datetime").datetime.min,
                               default=None)
        except MarketDataError as exc:
            reasoning.append(f"H1_POI_FETCH_FAILED:{exc.reason_code}")
    else:
        reasoning.append("D1_PERMISSION_NOT_DIRECTIONAL")

    current_location = None
    current_price = None
    try:
        current_price = get_tick(symbol).bid
    except MarketDataError:
        pass
    if selected_poi is not None and current_price is not None and selected_poi.low is not None and selected_poi.high is not None:
        if selected_poi.low <= current_price <= selected_poi.high:
            current_location = "INSIDE_POI"
        elif current_price > selected_poi.high:
            current_location = "ABOVE_POI"
        else:
            current_location = "BELOW_POI"

    if selected_poi is None:
        status = H1_WAITING_LOCATION if role is not None else H1_INDETERMINATE
    elif current_location == "INSIDE_POI":
        status = H1_POI_REACHED
    else:
        status = H1_POI_IDENTIFIED

    return H1SetupContext(
        symbol=symbol, as_of=None, d1_directional_permission=d1.directional_permission,
        structure_direction=structure_direction,
        external_liquidity=external_liquidity, internal_liquidity=(),
        asian_session_high=asian_high, asian_session_low=asian_low,
        poi_candidates=poi_candidates, selected_poi=selected_poi,
        midnight_open=MidnightOpen(), current_location=current_location,
        alert_zone=AlertZone(target_zone=selected_poi),
        reasoning_codes=tuple(reasoning), evidence=evidence, status=status,
    )
