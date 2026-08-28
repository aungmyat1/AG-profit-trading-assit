"""Tests for chart_renderer.render_chart: proves the renderer draws exactly the given
annotations (artist-count assertions), never recomputing them, and produces a real PNG
file. No live MT5/matplotlib GUI needed (Agg backend, offscreen)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from chart_renderer import render_chart
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure.models import STATE_BULLISH, StructurePoint, StructurePointKind, StructureTier
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candles(n=20):
    out = []
    price = 1.1000
    for i in range(n):
        price += 0.0002 if i % 2 == 0 else -0.0001
        out.append(Candle(time=START + timedelta(hours=i), open=price, high=price + 0.0003,
                           low=price - 0.0003, close=price + 0.0001, volume=1.0))
    return out


def _tier():
    swings = (
        StructurePoint(time_utc=START + timedelta(hours=2), price=1.1050, kind=StructurePointKind.HH),
        StructurePoint(time_utc=START + timedelta(hours=5), price=1.1020, kind=StructurePointKind.HL),
    )
    events = (
        StructurePoint(time_utc=START + timedelta(hours=6), price=1.1055, kind=StructurePointKind.BULLISH_BOS),
    )
    return StructureTier(tier="INTERNAL", swing_length=5, direction=STATE_BULLISH, swings=swings, events=events,
                          latest_swing_high=swings[0], latest_swing_low=swings[1], latest_bos=events[0], latest_choch=None)


def _zones():
    return [
        ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                   direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="smc.ob",
                   low=1.0990, high=1.1010, origin_time=START + timedelta(hours=3)),
        ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.SUPPLY,
                   direction=ZoneDirection.BEARISH, status=ZoneStatus.MITIGATED, source="smc.ob",
                   low=1.1080, high=1.1100, origin_time=START + timedelta(hours=8)),
    ]


def _liquidity_levels():
    return [
        LiquidityLevel(symbol="EURUSD", timeframe="H1", side=LiquiditySide.BUY_SIDE, source="EQUAL_HIGHS",
                        price=1.1090, origin_time=START, status=LiquidityStatus.UNSWEPT),
        LiquidityLevel(symbol="EURUSD", timeframe="H1", side=LiquiditySide.SELL_SIDE, source="SWING_LOW",
                        price=1.0980, origin_time=START, status=LiquidityStatus.SWEPT, sweep_time=START + timedelta(hours=10)),
    ]


def test_render_candles_only(tmp_path):
    candles = _candles(20)
    out_path = str(tmp_path / "candles.png")
    result = render_chart(candles, out_path)
    assert result.candle_count == 20
    assert result.swing_label_count == 0 and result.event_marker_count == 0
    assert result.zone_rect_count == 0 and result.liquidity_line_count == 0
    assert os.path.exists(out_path) and os.path.getsize(out_path) > 0


def test_render_structure_layer_matches_input_counts(tmp_path):
    candles = _candles(20)
    tier = _tier()
    result = render_chart(candles, str(tmp_path / "structure.png"), structure=tier)
    assert result.swing_label_count == len(tier.swings) == 2
    assert result.event_marker_count == len(tier.events) == 1


def test_render_zones_layer_matches_input_count(tmp_path):
    candles = _candles(20)
    result = render_chart(candles, str(tmp_path / "zones.png"), zones=_zones())
    assert result.zone_rect_count == 2


def test_render_liquidity_layer_matches_input_count(tmp_path):
    candles = _candles(20)
    result = render_chart(candles, str(tmp_path / "liquidity.png"), liquidity=_liquidity_levels())
    assert result.liquidity_line_count == 2


def test_render_combined_chart_draws_all_layers(tmp_path):
    candles = _candles(20)
    result = render_chart(
        candles, str(tmp_path / "combined.png"), structure=_tier(), zones=_zones(), liquidity=_liquidity_levels(),
        title="EURUSD H1 combined",
    )
    assert result.candle_count == 20
    assert result.swing_label_count == 2
    assert result.event_marker_count == 1
    assert result.zone_rect_count == 2
    assert result.liquidity_line_count == 2
    assert os.path.exists(result.out_path)


def test_render_liquidity_roles_label_lookup(tmp_path):
    from liquidity.hierarchy import level_id

    levels = _liquidity_levels()
    roles = {level_id(levels[0]): "TARGET"}
    result = render_chart(_candles(20), str(tmp_path / "roles.png"), liquidity=levels, liquidity_roles=roles)
    assert result.liquidity_line_count == 2  # still draws exactly the given levels, role is label-only


def test_render_zone_without_origin_time_is_skipped_not_guessed(tmp_path):
    candles = _candles(20)
    zone = ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="smc.ob",
                       low=1.0990, high=1.1010, origin_time=None)
    result = render_chart(candles, str(tmp_path / "no_origin.png"), zones=[zone])
    assert result.zone_rect_count == 0
