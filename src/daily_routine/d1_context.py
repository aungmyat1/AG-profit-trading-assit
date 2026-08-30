"""build_d1_context() -- orchestration only. Calls existing market_structure/
liquidity/supply_demand capabilities; invents nothing (spec section 4)."""
from __future__ import annotations

from liquidity import liquidity_result
from market_structure import analyze_structure
from market_structure.models import STATE_BEARISH, STATE_BULLISH
from mt5.market_data import MarketDataError
from supply_demand import fair_value_gaps_for

from .models import (
    D1Context,
    DIRECTIONAL_PERMISSION_INDETERMINATE,
    DIRECTIONAL_PERMISSION_LONG_ONLY,
    DIRECTIONAL_PERMISSION_SHORT_ONLY,
    FundamentalContext,
)

_PERMISSION_FOR_STATE = {
    STATE_BULLISH: DIRECTIONAL_PERMISSION_LONG_ONLY,
    STATE_BEARISH: DIRECTIONAL_PERMISSION_SHORT_ONLY,
}


def build_d1_context(symbol: str) -> D1Context:
    reasoning: list = []
    evidence: dict = {}

    try:
        structure = analyze_structure(symbol, "D1")
    except MarketDataError as exc:
        return D1Context(symbol=symbol, as_of=None, status="UNAVAILABLE",
                         reasoning_codes=(f"D1_STRUCTURE_FETCH_FAILED:{exc.reason_code}",))

    if structure.status != "VALID":
        return D1Context(symbol=symbol, as_of=None, status="UNAVAILABLE",
                         reasoning_codes=(f"D1_STRUCTURE_{structure.status}",))

    structure_direction = structure.state
    permission = _PERMISSION_FOR_STATE.get(structure_direction, DIRECTIONAL_PERMISSION_INDETERMINATE)
    reasoning.append(f"D1_STRUCTURE={structure_direction}")
    evidence["structure"] = structure

    buy_side = sell_side = None
    internal_liquidity: tuple = ()
    try:
        liq = liquidity_result(symbol, "D1")
        if liq.status == "LIQUIDITY_OK":
            buy_side, sell_side = liq.nearest_buy_side, liq.nearest_sell_side
            evidence["liquidity"] = liq
        else:
            reasoning.append(f"D1_LIQUIDITY_{liq.status}")
    except MarketDataError as exc:
        reasoning.append(f"D1_LIQUIDITY_FETCH_FAILED:{exc.reason_code}")

    gap_liquidity: tuple = ()
    try:
        fvg = fair_value_gaps_for(symbol, "D1")
        if fvg.status == "OK":
            gap_liquidity = fvg.zones
        else:
            reasoning.append(f"D1_GAP_{fvg.status}")
    except MarketDataError as exc:
        reasoning.append(f"D1_GAP_FETCH_FAILED:{exc.reason_code}")

    status = "READY" if permission != DIRECTIONAL_PERMISSION_INDETERMINATE else "PARTIAL"

    return D1Context(
        symbol=symbol, as_of=None, market_data_freshness="OK",
        structure_direction=structure_direction,
        external_buy_side_liquidity=buy_side, external_sell_side_liquidity=sell_side,
        internal_liquidity=internal_liquidity, gap_liquidity=gap_liquidity,
        fundamental_context=FundamentalContext(status="UNAVAILABLE"),
        directional_permission=permission,
        reasoning_codes=tuple(reasoning), evidence=evidence, status=status,
    )
