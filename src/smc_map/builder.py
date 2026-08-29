"""build_smc_market_map() -- the single builder function for SMCMarketMap (spec sections
17-19). Calls each already-frozen analyzer exactly once per requested timeframe; never
re-derives structure/zones/liquidity itself. Fails closed per timeframe/component: a
MarketDataError or a non-OK analyzer status degrades that ONE piece to absence (empty
tuple / None) plus a warning, it never raises out of this function and never fabricates
a snapshot from partial data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

from liquidity.analyzer import liquidity_result
from liquidity.models import LiquidityLevel
from market_structure.tiers import analyze_structure_tiers
from mt5.market_data import MarketDataError, get_tick
from supply_demand.analyzer import fair_value_gaps_for, order_blocks_for
from supply_demand.models import ZoneResult
from supply_demand.native_zones import premium_discount_from_previous_day

from .evidence import evidence_id
from .models import DEFAULT_TIMEFRAMES, SMCMarketMap, TimeframeMap


def _zone_evidence(kind: str, symbol: str, timeframe: str, zones: Sequence[ZoneResult]) -> Dict[str, object]:
    index: Dict[str, object] = {}
    for z in zones:
        eid = evidence_id(kind, symbol, timeframe, z.origin_time, z.low)
        index[eid] = z
    return index


def _liquidity_evidence(symbol: str, timeframe: str, levels: Sequence[LiquidityLevel]) -> Dict[str, object]:
    index: Dict[str, object] = {}
    for lvl in levels:
        eid = evidence_id("LIQ", symbol, timeframe, lvl.origin_time, lvl.price)
        index[eid] = lvl
    return index


def _structure_evidence(symbol: str, timeframe: str, structure) -> Dict[str, object]:
    index: Dict[str, object] = {}
    if structure is None or structure.status != "VALID":
        return index
    for tier in (structure.external, structure.internal):
        if tier is None:
            continue
        for point in (tier.latest_swing_high, tier.latest_swing_low, tier.latest_bos, tier.latest_choch):
            if point is None:
                continue
            eid = evidence_id(f"STRUCT-{tier.tier}", symbol, timeframe, point.time_utc, point.price)
            index[eid] = point
    return index


def _build_timeframe_map(symbol: str, timeframe: str, warnings: list) -> TimeframeMap:
    structure = None
    try:
        structure = analyze_structure_tiers(symbol, timeframe)
        if structure.status != "VALID":
            warnings.append(f"STRUCTURE_{timeframe}_{structure.status}")
    except MarketDataError as exc:
        warnings.append(f"STRUCTURE_{timeframe}_FETCH_FAILED:{exc.reason_code}")

    order_blocks: tuple = ()
    try:
        ob_query = order_blocks_for(symbol, timeframe)
        if ob_query.status == "OK":
            order_blocks = ob_query.zones
        else:
            warnings.append(f"ORDER_BLOCKS_{timeframe}_{ob_query.status}")
    except MarketDataError as exc:
        warnings.append(f"ORDER_BLOCKS_{timeframe}_FETCH_FAILED:{exc.reason_code}")

    fvgs: tuple = ()
    try:
        fvg_query = fair_value_gaps_for(symbol, timeframe)
        if fvg_query.status == "OK":
            fvgs = fvg_query.zones
        else:
            warnings.append(f"FVG_{timeframe}_{fvg_query.status}")
    except MarketDataError as exc:
        warnings.append(f"FVG_{timeframe}_FETCH_FAILED:{exc.reason_code}")

    liquidity_levels: tuple = ()
    try:
        liq = liquidity_result(symbol, timeframe)
        if liq.status == "LIQUIDITY_OK":
            liquidity_levels = liq.levels
        elif liq.status != "NO_LIQUIDITY_LEVELS":
            warnings.append(f"LIQUIDITY_{timeframe}_{liq.status}")
    except MarketDataError as exc:
        warnings.append(f"LIQUIDITY_{timeframe}_FETCH_FAILED:{exc.reason_code}")

    evidence_index: Dict[str, object] = {}
    evidence_index.update(_zone_evidence("OB", symbol, timeframe, order_blocks))
    evidence_index.update(_zone_evidence("FVG", symbol, timeframe, fvgs))
    evidence_index.update(_liquidity_evidence(symbol, timeframe, liquidity_levels))
    evidence_index.update(_structure_evidence(symbol, timeframe, structure))

    return TimeframeMap(
        timeframe=timeframe, structure=structure, order_blocks=order_blocks,
        fair_value_gaps=fvgs, liquidity_levels=liquidity_levels, evidence_index=evidence_index,
    )


def build_smc_market_map(symbol: str, timeframes: Sequence[str] = DEFAULT_TIMEFRAMES,
                          snapshot_time: Optional[datetime] = None) -> SMCMarketMap:
    warnings: list = []
    tf_maps: Dict[str, TimeframeMap] = {}
    for tf in timeframes:
        tf_maps[tf] = _build_timeframe_map(symbol, tf, warnings)

    premium_discount = None
    try:
        premium_discount = premium_discount_from_previous_day(symbol)
        if premium_discount is None:
            warnings.append("PREMIUM_DISCOUNT_UNAVAILABLE")
    except MarketDataError as exc:
        warnings.append(f"PREMIUM_DISCOUNT_FETCH_FAILED:{exc.reason_code}")

    if snapshot_time is None:
        try:
            snapshot_time = get_tick(symbol).time_utc
        except MarketDataError:
            snapshot_time = datetime.now(timezone.utc)
            warnings.append("SNAPSHOT_TIME_FALLBACK_TO_WALL_CLOCK")

    any_data = any(
        tf_map.structure is not None or tf_map.order_blocks or tf_map.fair_value_gaps or tf_map.liquidity_levels
        for tf_map in tf_maps.values()
    )
    if not any_data:
        data_quality = "UNAVAILABLE"
    elif warnings:
        data_quality = "PARTIAL"
    else:
        data_quality = "OK"

    return SMCMarketMap(
        symbol=symbol, snapshot_time=snapshot_time, timeframes=tf_maps,
        premium_discount=premium_discount,
        premium_discount_source="previous_day" if premium_discount is not None else None,
        data_quality=data_quality, warnings=tuple(warnings),
    )
