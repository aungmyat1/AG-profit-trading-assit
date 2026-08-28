"""Walk-forward (no-hindsight) and repeatability validation for the three foundational
skills (spec sections 15, 16, 41). All synthetic/offline -- no live MT5 connection.

Scope note: Structure and Supply & Demand are validated end-to-end
(analyze_structure_tiers()/order_blocks_for(), each needing only one
get_latest_candles monkeypatch). Liquidity's full liquidity_result() orchestrates
session/PDH lookups through several other modules' own get_latest_candles imports, so
this file validates its two deterministic cores directly instead
(liquidity.equal_levels clustering + liquidity.status sweep state machine, both pure,
no monkeypatch needed) -- the full liquidity_result() call path is already covered by
the existing live-guarded tests/test_liquidity.py, not re-proven here.

"No retroactive change" is checked as: once a candle window confirms an annotation
(swing/event/zone by identifying time+price+kind), computing again over a LONGER window
that still includes that candle must reproduce the identical annotation -- new bars may
ADD annotations but must never CHANGE or REMOVE an already-confirmed one.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from market_structure import tiers
from market_structure.models import StructurePointKind
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.session import Candle
from supply_demand import analyzer as sd_analyzer
from liquidity.equal_levels import detect_equal_highs
from liquidity.status import compute_status
from liquidity.models import LiquiditySide

_SYMBOL_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
)
_ZONE_ORDINAL = {"FRESH": 0, "TOUCHED": 1, "MITIGATED": 2, "INVALIDATED": 3}


def _zigzag_candles(n: int, start_price: float = 1.10000, amplitude: float = 0.00500, period: int = 20) -> list:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        mid = start_price + amplitude * math.sin(2 * math.pi * i / period)
        o, c = mid, mid + amplitude * 0.05
        h, l = max(o, c) + amplitude * 0.1, min(o, c) - amplitude * 0.1
        out.append(Candle(time=start + timedelta(hours=i), open=o, high=h, low=l, close=c, volume=1.0))
    return out


# --------------------------------------------------------------------------- structure

def test_structure_repeatability():
    candles = _zigzag_candles(1100)
    df = tiers.candles_to_dataframe(candles)
    tier_a = tiers._build_tier(df, "INTERNAL", 5, True, 5 * 0.00001)
    tier_b = tiers._build_tier(df, "INTERNAL", 5, True, 5 * 0.00001)
    assert tier_a == tier_b


def test_structure_walkforward_no_retroactive_change(monkeypatch):
    candles = _zigzag_candles(1300)
    monkeypatch.setattr(tiers, "get_symbol_meta", lambda symbol: _SYMBOL_META)

    monkeypatch.setattr(tiers, "get_latest_candles", lambda s, tf, count: candles[:1100])
    result_k = tiers.analyze_structure_tiers("EURUSD", "H1")
    assert result_k.status == "VALID"

    monkeypatch.setattr(tiers, "get_latest_candles", lambda s, tf, count: candles[:1300])
    result_k_plus = tiers.analyze_structure_tiers("EURUSD", "H1")
    assert result_k_plus.status == "VALID"

    swings_plus_by_time = {p.time_utc: p for p in result_k_plus.internal.swings}
    for point in result_k.internal.swings:
        assert point.time_utc in swings_plus_by_time
        matched = swings_plus_by_time[point.time_utc]
        assert matched.price == point.price and matched.kind == point.kind

    events_plus_by_time = {p.time_utc: p for p in result_k_plus.internal.events}
    for point in result_k.internal.events:
        assert point.time_utc in events_plus_by_time
        matched = events_plus_by_time[point.time_utc]
        assert matched.price == point.price and matched.kind == point.kind


# --------------------------------------------------------------------------- supply & demand

def test_order_blocks_repeatability(monkeypatch):
    candles = _zigzag_candles(300)
    monkeypatch.setattr(sd_analyzer, "get_latest_candles", lambda s, tf, count: candles)
    result_a = sd_analyzer.order_blocks_for("EURUSD", "H1", count=200)
    result_b = sd_analyzer.order_blocks_for("EURUSD", "H1", count=200)
    assert result_a.status == "OK" and result_b.status == "OK"
    assert result_a.zones == result_b.zones


def test_order_blocks_walkforward_no_retroactive_change(monkeypatch):
    candles = _zigzag_candles(400)

    monkeypatch.setattr(sd_analyzer, "get_latest_candles", lambda s, tf, count: candles[:250])
    result_k = sd_analyzer.order_blocks_for("EURUSD", "H1", count=150)
    assert result_k.status == "OK"

    monkeypatch.setattr(sd_analyzer, "get_latest_candles", lambda s, tf, count: candles[:400])
    result_k_plus = sd_analyzer.order_blocks_for("EURUSD", "H1", count=300)
    assert result_k_plus.status == "OK"

    zones_plus_by_origin = {z.origin_time: z for z in result_k_plus.zones}
    for zone in result_k.zones:
        assert zone.origin_time in zones_plus_by_origin, "zone disappeared on a longer window"
        matched = zones_plus_by_origin[zone.origin_time]
        assert matched.low == zone.low and matched.high == zone.high and matched.direction == zone.direction
        # Lifecycle only advances forward (FRESH -> ... -> INVALIDATED), never backward.
        if zone.status.value in _ZONE_ORDINAL and matched.status.value in _ZONE_ORDINAL:
            assert _ZONE_ORDINAL[matched.status.value] >= _ZONE_ORDINAL[zone.status.value]


# --------------------------------------------------------------------------- liquidity (core, pure functions)

def test_liquidity_equal_highs_repeatability():
    candles = _zigzag_candles(300)
    levels_a = detect_equal_highs("EURUSD", "H1", candles, tolerance_price=5 * 0.00001, extremum_window=2)
    levels_b = detect_equal_highs("EURUSD", "H1", candles, tolerance_price=5 * 0.00001, extremum_window=2)
    assert levels_a == levels_b


def test_liquidity_equal_highs_walkforward_geometry_unchanged():
    # NOTE: a cluster's origin_time is its LATEST member touch (liquidity/equal_levels.py
    # _cluster()), which legitimately advances as a longer window accrues more touches at
    # the same price -- that's new information, not a hindsight leak. The invariant to
    # check is the cluster's PRICE (its representative level), matched by price rather
    # than by origin_time.
    candles = _zigzag_candles(300)
    levels_k = detect_equal_highs("EURUSD", "H1", candles[:200], tolerance_price=5 * 0.00001, extremum_window=2)
    levels_k_plus = detect_equal_highs("EURUSD", "H1", candles[:300], tolerance_price=5 * 0.00001, extremum_window=2)

    plus_prices = {round(lvl.price, 8) for lvl in levels_k_plus}
    for lvl in levels_k:
        assert round(lvl.price, 8) in plus_prices  # same cluster level still reported in the longer window
        matched = next(l for l in levels_k_plus if round(l.price, 8) == round(lvl.price, 8))
        assert matched.origin_time >= lvl.origin_time  # origin_time only advances forward, never back


def test_liquidity_sweep_time_immutable_once_set():
    candles = _zigzag_candles(60)
    level_price = candles[10].high
    status_k, sweep_k, reclaim_k, _ = compute_status(LiquiditySide.BUY_SIDE, level_price, candles[11:40], None, None)
    status_k_plus, sweep_k_plus, reclaim_k_plus, _ = compute_status(LiquiditySide.BUY_SIDE, level_price, candles[11:60], None, None)

    if sweep_k is not None:
        assert sweep_k_plus == sweep_k  # the sweep EVENT's time is historical fact, must not move
