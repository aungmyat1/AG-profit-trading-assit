"""Raw-evidence annotation builders (spec sections 17-21): SMCMarketMap -> Annotation.
Each function only reads objects already normalized by `smc_map` (structure tiers,
order blocks, FVGs, liquidity levels) and looks up the SAME evidence_id `smc_map`
already assigned them -- never redetects, never assigns a new id. Distinct from
`builder.py`'s `build_visual_explanation()`, which annotates ONE composed E/M
combination; these functions annotate the broader chart-wide picture a symbol's full
market map carries, independent of any particular combination.

Protected High/Low is deliberately NOT annotated here: no detector for it exists
anywhere in this repo (see docs/status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md's
conformance matrix) -- inventing one to fill an annotation slot would violate "no new
SMC primitives" for this phase. `PROTECTED_HIGH`/`PROTECTED_LOW` remain valid
`semantic_role` values in the annotation model for when/if that primitive is ever
frozen; this builder simply never emits them.
"""
from __future__ import annotations

from typing import Tuple

from liquidity.models import LiquidityStatus
from market_structure.models import StructurePoint, StructurePointKind
from smc_map.evidence import evidence_id
from smc_map.models import SMCMarketMap
from supply_demand.models import ZoneResult, ZoneStatus

from .models import ANNOTATION_BOX, ANNOTATION_LINE, ANNOTATION_MARKER, Annotation

_SWING_ROLE = {
    StructurePointKind.HH: "BOS_MARKER", StructurePointKind.HL: "BOS_MARKER",
    StructurePointKind.LH: "BOS_MARKER", StructurePointKind.LL: "BOS_MARKER",
    StructurePointKind.SWING_HIGH: "STRUCTURE_LEVEL", StructurePointKind.SWING_LOW: "STRUCTURE_LEVEL",
}
_EVENT_LABEL = {
    StructurePointKind.BULLISH_BOS: "BOS+", StructurePointKind.BEARISH_BOS: "BOS-",
    StructurePointKind.BULLISH_CHOCH: "CHOCH+", StructurePointKind.BEARISH_CHOCH: "CHOCH-",
}
_SWING_LABEL = {
    StructurePointKind.HH: "HH", StructurePointKind.HL: "HL", StructurePointKind.LH: "LH", StructurePointKind.LL: "LL",
    StructurePointKind.SWING_HIGH: "H", StructurePointKind.SWING_LOW: "L",
}

_LIQUIDITY_ROLE = {
    LiquidityStatus.UNSWEPT: "LIQUIDITY_LEVEL", LiquidityStatus.SWEPT: "LIQUIDITY_SWEEP",
    LiquidityStatus.RECLAIMED: "LIQUIDITY_RECLAIM", LiquidityStatus.CONSUMED: "LIQUIDITY_LEVEL",
    LiquidityStatus.UNKNOWN: "LIQUIDITY_LEVEL",
}
_LIQUIDITY_DEVELOPING = {
    LiquidityStatus.UNSWEPT: True, LiquidityStatus.SWEPT: True,
    LiquidityStatus.RECLAIMED: False, LiquidityStatus.CONSUMED: False, LiquidityStatus.UNKNOWN: True,
}


def _point_annotation(symbol: str, timeframe: str, point: StructurePoint, kind_prefix: str) -> Annotation:
    role = _EVENT_LABEL.get(point.kind)
    if role is not None:
        semantic_role, label = "CHOCH_MARKER" if "CHOCH" in point.kind.value else "BOS_MARKER", role
    else:
        semantic_role, label = _SWING_ROLE.get(point.kind, "STRUCTURE_LEVEL"), _SWING_LABEL.get(point.kind, point.kind.value)
    return Annotation(
        type=ANNOTATION_MARKER, timeframe=timeframe, timestamp=point.time_utc.isoformat(), price=point.price,
        label=label, semantic_role=semantic_role,
        source_id=evidence_id(kind_prefix, symbol, timeframe, point.time_utc, point.price),
        developing=False,  # market_structure only ever exposes CONFIRMED (closed-candle) points
    )


def build_structure_annotations(market_map: SMCMarketMap, timeframe: str) -> Tuple[Annotation, ...]:
    tf_map = market_map.timeframe_map(timeframe)
    if tf_map is None or tf_map.structure is None or tf_map.structure.status != "VALID":
        return ()
    annotations = []
    for tier in (tf_map.structure.external, tf_map.structure.internal):
        if tier is None:
            continue
        kind_prefix = f"STRUCT-{tier.tier}"
        for point in (*tier.swings, *tier.events):
            annotations.append(_point_annotation(market_map.symbol, timeframe, point, kind_prefix))
    return tuple(annotations)


def build_liquidity_annotations(market_map: SMCMarketMap, timeframe: str) -> Tuple[Annotation, ...]:
    tf_map = market_map.timeframe_map(timeframe)
    if tf_map is None:
        return ()
    annotations = []
    for level in tf_map.liquidity_levels:
        semantic_role = _LIQUIDITY_ROLE.get(level.status, "LIQUIDITY_LEVEL")
        annotations.append(Annotation(
            type=ANNOTATION_LINE, timeframe=timeframe,
            timestamp=level.origin_time.isoformat() if level.origin_time is not None else None,
            price=level.price, label=f"{level.source} ({level.status.value})", semantic_role=semantic_role,
            source_id=evidence_id("LIQ", market_map.symbol, timeframe, level.origin_time, level.price),
            developing=_LIQUIDITY_DEVELOPING.get(level.status, True),
        ))
    return tuple(annotations)


def _zone_annotation(symbol: str, timeframe: str, zone: ZoneResult, kind_prefix: str) -> Annotation:
    return Annotation(
        type=ANNOTATION_BOX, timeframe=timeframe,
        time_start=zone.origin_time.isoformat() if zone.origin_time is not None else None,
        low=zone.low, high=zone.high, label=f"{zone.family.value} {zone.role.value} ({zone.status.value})",
        semantic_role=zone.role.value,
        source_id=evidence_id(kind_prefix, symbol, timeframe, zone.origin_time, zone.low),
        developing=zone.status not in (ZoneStatus.FRESH, ZoneStatus.TOUCHED, ZoneStatus.MITIGATED, ZoneStatus.INVALIDATED),
    )


def build_supply_demand_annotations(market_map: SMCMarketMap, timeframe: str) -> Tuple[Annotation, ...]:
    """Order Blocks / Supply / Demand zones -- NOT FVGs (see build_fvg_annotations for
    those, which also need a midpoint/CE line FVGs don't share with OB zones)."""
    tf_map = market_map.timeframe_map(timeframe)
    if tf_map is None:
        return ()
    return tuple(_zone_annotation(market_map.symbol, timeframe, z, "OB") for z in tf_map.order_blocks)


def build_fvg_annotations(market_map: SMCMarketMap, timeframe: str) -> Tuple[Annotation, ...]:
    tf_map = market_map.timeframe_map(timeframe)
    if tf_map is None:
        return ()
    annotations = []
    for fvg in tf_map.fair_value_gaps:
        annotations.append(_zone_annotation(market_map.symbol, timeframe, fvg, "FVG"))
        if fvg.low is not None and fvg.high is not None:
            midpoint = (fvg.low + fvg.high) / 2.0  # same equilibrium-style midpoint arithmetic native_zones.py uses
            annotations.append(Annotation(
                type=ANNOTATION_LINE, timeframe=timeframe,
                timestamp=fvg.origin_time.isoformat() if fvg.origin_time is not None else None,
                price=midpoint, label="CE (50%)", semantic_role="FVG_MIDPOINT",
                source_id=evidence_id("FVG", market_map.symbol, timeframe, fvg.origin_time, fvg.low),
                developing=fvg.status not in (ZoneStatus.FRESH, ZoneStatus.TOUCHED, ZoneStatus.MITIGATED, ZoneStatus.INVALIDATED),
            ))
    return tuple(annotations)


def build_raw_evidence_annotations(market_map: SMCMarketMap, timeframe: str) -> Tuple[Annotation, ...]:
    """Convenience: all four raw-evidence builders for one timeframe, concatenated."""
    return (
        build_structure_annotations(market_map, timeframe)
        + build_liquidity_annotations(market_map, timeframe)
        + build_supply_demand_annotations(market_map, timeframe)
        + build_fvg_annotations(market_map, timeframe)
    )
