"""Tests for visual_explanation.raw_builders: structure/liquidity/S&D/OB/FVG annotation
builders over an SMCMarketMap. Every annotation's source_id must resolve back to a real
object in the market map (no orphan annotations, spec section 27); no protected-high/low
annotation is ever emitted (undefined primitive, spec section 38 -- no new primitives).
"""
from __future__ import annotations

import datetime as dt

from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure.models import STATE_BULLISH, StructurePoint, StructurePointKind, StructureTier, TieredStructureResult
from smc_map.models import SMCMarketMap, TimeframeMap
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
from visual_explanation import (
    build_fvg_annotations,
    build_liquidity_annotations,
    build_raw_evidence_annotations,
    build_structure_annotations,
    build_supply_demand_annotations,
)
from smc_map.builder import _liquidity_evidence, _structure_evidence, _zone_evidence

UTC = dt.timezone.utc


def _market_map_from(symbol="EURUSD", timeframe="H1", structure=None, order_blocks=(), fvgs=(), liquidity_levels=()):
    evidence_index = {}
    evidence_index.update(_zone_evidence("OB", symbol, timeframe, order_blocks))
    evidence_index.update(_zone_evidence("FVG", symbol, timeframe, fvgs))
    evidence_index.update(_liquidity_evidence(symbol, timeframe, liquidity_levels))
    evidence_index.update(_structure_evidence(symbol, timeframe, structure))
    tf_map = TimeframeMap(timeframe=timeframe, structure=structure, order_blocks=tuple(order_blocks),
                           fair_value_gaps=tuple(fvgs), liquidity_levels=tuple(liquidity_levels),
                           evidence_index=evidence_index)
    return SMCMarketMap(symbol=symbol, snapshot_time=dt.datetime(2026, 1, 5, tzinfo=UTC), timeframes={timeframe: tf_map})


def _structure_result(symbol, timeframe):
    bos = StructurePoint(dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC), 1.1100, StructurePointKind.BULLISH_BOS)
    swing = StructurePoint(dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC), 1.1050, StructurePointKind.HH)
    tier = StructureTier(tier="INTERNAL", swing_length=5, direction=STATE_BULLISH, swings=(swing,), events=(bos,))
    return TieredStructureResult(symbol=symbol, timeframe=timeframe, status="VALID", reason_codes=(), internal=tier)


def _ob(origin=dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC)):
    return ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="test",
                       low=1.0990, high=1.1010, origin_time=origin)


def _fvg(origin=dt.datetime(2026, 1, 5, 2, 0, tzinfo=UTC)):
    return ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="test",
                       low=1.1020, high=1.1030, origin_time=origin)


def _liq(status=LiquidityStatus.UNSWEPT, origin=dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC)):
    return LiquidityLevel(symbol="EURUSD", timeframe="H1", side=LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                           price=1.1200, origin_time=origin, status=status)


# --------------------------------------------------------------------------- structure

def test_structure_annotations_traceable_and_labeled():
    structure = _structure_result("EURUSD", "H1")
    market_map = _market_map_from(structure=structure)
    annotations = build_structure_annotations(market_map, "H1")

    assert len(annotations) == 2
    labels = {a.label for a in annotations}
    assert "HH" in labels
    assert "BOS+" in labels
    for a in annotations:
        assert a.source_id is not None
        assert market_map.resolve_evidence(a.source_id) is not None


def test_structure_annotations_empty_when_no_structure():
    market_map = _market_map_from()
    assert build_structure_annotations(market_map, "H1") == ()


def test_no_protected_high_low_annotation_ever_emitted():
    structure = _structure_result("EURUSD", "H1")
    market_map = _market_map_from(structure=structure)
    annotations = build_structure_annotations(market_map, "H1")
    assert all(a.semantic_role not in ("PROTECTED_HIGH", "PROTECTED_LOW") for a in annotations)


# --------------------------------------------------------------------------- liquidity

def test_liquidity_annotation_touch_sweep_reclaim_semantic_roles():
    unswept = _liq(LiquidityStatus.UNSWEPT)
    swept = _liq(LiquidityStatus.SWEPT, origin=dt.datetime(2026, 1, 5, 4, 0, tzinfo=UTC))
    reclaimed = _liq(LiquidityStatus.RECLAIMED, origin=dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC))
    market_map = _market_map_from(liquidity_levels=(unswept, swept, reclaimed))
    annotations = build_liquidity_annotations(market_map, "H1")

    roles = {a.semantic_role for a in annotations}
    assert "LIQUIDITY_LEVEL" in roles
    assert "LIQUIDITY_SWEEP" in roles
    assert "LIQUIDITY_RECLAIM" in roles
    for a in annotations:
        assert market_map.resolve_evidence(a.source_id) is not None


# --------------------------------------------------------------------------- supply/demand + OB

def test_supply_demand_annotation_has_lifecycle_in_label():
    market_map = _market_map_from(order_blocks=(_ob(),))
    annotations = build_supply_demand_annotations(market_map, "H1")
    assert len(annotations) == 1
    a = annotations[0]
    assert a.semantic_role == "DEMAND"
    assert "FRESH" in a.label
    assert a.low == 1.0990 and a.high == 1.1010
    assert market_map.resolve_evidence(a.source_id) is not None


# --------------------------------------------------------------------------- FVG

def test_fvg_annotation_includes_box_and_midpoint_line():
    market_map = _market_map_from(fvgs=(_fvg(),))
    annotations = build_fvg_annotations(market_map, "H1")
    assert len(annotations) == 2
    box = next(a for a in annotations if a.semantic_role == "REFERENCE")
    midpoint = next(a for a in annotations if a.semantic_role == "FVG_MIDPOINT")
    assert box.low == 1.1020 and box.high == 1.1030
    assert midpoint.price == 1.1025
    assert midpoint.label == "CE (50%)"
    for a in annotations:
        assert market_map.resolve_evidence(a.source_id) is not None


# --------------------------------------------------------------------------- combined

def test_build_raw_evidence_annotations_concatenates_all_four():
    structure = _structure_result("EURUSD", "H1")
    market_map = _market_map_from(structure=structure, order_blocks=(_ob(),), fvgs=(_fvg(),),
                                   liquidity_levels=(_liq(),))
    combined = build_raw_evidence_annotations(market_map, "H1")
    assert len(combined) == 2 + 1 + 1 + 2  # structure(2) + liquidity(1) + OB(1) + FVG(box+midpoint=2)
    assert all(a.source_id is not None and market_map.resolve_evidence(a.source_id) is not None for a in combined)
