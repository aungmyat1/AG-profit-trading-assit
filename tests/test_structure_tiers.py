"""Tests for market_structure.tiers: HH/HL/LH/LL labeling (pure), the tie rule, and the
independent external(50)/internal(5) two-tier read. No live MT5 connection needed --
get_latest_candles/get_symbol_meta are monkeypatched with synthetic, deterministic
candle series.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_structure import tiers
from market_structure.models import StructurePoint, StructurePointKind
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.session import Candle

TOLERANCE = 5 * 0.00001  # equal_level_tolerance_points(5) * EURUSD tick_size, matching config/liquidity.yaml


def _point(price: float, kind: StructurePointKind, minute: int = 0) -> StructurePoint:
    return StructurePoint(time_utc=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute), price=price, kind=kind)


# --------------------------------------------------------------------------- label_swings

def test_label_swings_classifies_hh_hl_lh_ll():
    swings = [
        _point(1.1000, StructurePointKind.SWING_LOW, 0),
        _point(1.1100, StructurePointKind.SWING_HIGH, 1),
        _point(1.1050, StructurePointKind.SWING_LOW, 2),   # higher than 1.1000 -> HL
        _point(1.1200, StructurePointKind.SWING_HIGH, 3),  # higher than 1.1100 -> HH
        _point(1.0900, StructurePointKind.SWING_LOW, 4),   # lower than 1.1050 -> LL
        _point(1.1150, StructurePointKind.SWING_HIGH, 5),  # lower than 1.1200 -> LH
    ]
    labeled = tiers.label_swings(swings, TOLERANCE)
    kinds = [p.kind for p in labeled]
    assert kinds == [
        StructurePointKind.SWING_LOW,  # first low: unclassified
        StructurePointKind.SWING_HIGH,  # first high: unclassified
        StructurePointKind.HL,
        StructurePointKind.HH,
        StructurePointKind.LL,
        StructurePointKind.LH,
    ]


def test_label_swings_tie_within_tolerance_labels_as_continuation():
    swings = [
        _point(1.1000, StructurePointKind.SWING_HIGH, 0),
        _point(1.1000 + TOLERANCE / 2, StructurePointKind.SWING_HIGH, 1),  # within tolerance -> HH (tie)
        _point(1.1000, StructurePointKind.SWING_LOW, 2),
        _point(1.1000 - TOLERANCE / 2, StructurePointKind.SWING_LOW, 3),  # within tolerance -> LL (tie)
    ]
    labeled = tiers.label_swings(swings, TOLERANCE)
    assert labeled[1].kind == StructurePointKind.HH
    assert labeled[3].kind == StructurePointKind.LL


def test_label_swings_prices_and_times_preserved():
    swings = [_point(1.1000, StructurePointKind.SWING_HIGH, 0), _point(1.1200, StructurePointKind.SWING_HIGH, 1)]
    labeled = tiers.label_swings(swings, TOLERANCE)
    assert labeled[1].price == pytest.approx(1.1200)
    assert labeled[1].time_utc == swings[1].time_utc


# --------------------------------------------------------------------------- analyze_structure_tiers

def _zigzag_candles(n: int, start_price: float = 1.10000, amplitude: float = 0.00500, period: int = 20) -> list:
    """Deterministic synthetic OHLC: a repeating up/down zigzag, one bar per hour."""
    import math
    candles = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        mid = start_price + amplitude * math.sin(2 * math.pi * i / period)
        o = mid
        c = mid + amplitude * 0.05
        h = max(o, c) + amplitude * 0.1
        l = min(o, c) - amplitude * 0.1
        candles.append(Candle(time=start + timedelta(hours=i), open=o, high=h, low=l, close=c, volume=1.0))
    return candles


_SYMBOL_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
)


def test_analyze_structure_tiers_computes_both_tiers_independently(monkeypatch):
    candles = _zigzag_candles(1100)
    monkeypatch.setattr(tiers, "get_latest_candles", lambda symbol, timeframe, count: candles[-count:])
    monkeypatch.setattr(tiers, "get_symbol_meta", lambda symbol: _SYMBOL_META)

    result = tiers.analyze_structure_tiers("EURUSD", "H1")

    assert result.status == "VALID"
    assert result.internal is not None and result.external is not None
    assert result.internal.tier == "INTERNAL" and result.internal.swing_length == 5
    assert result.external.tier == "EXTERNAL" and result.external.swing_length == tiers.EXTERNAL_SWING_LENGTH
    # Independently computed -- internal (short lookback) finds far more swings on a
    # zigzag than external (long lookback), proving they aren't the same computation.
    assert len(result.internal.swings) > len(result.external.swings)


def test_analyze_structure_tiers_insufficient_history(monkeypatch):
    candles = _zigzag_candles(50)
    monkeypatch.setattr(tiers, "get_latest_candles", lambda symbol, timeframe, count: candles[-count:] if count <= len(candles) else candles)
    monkeypatch.setattr(tiers, "get_symbol_meta", lambda symbol: _SYMBOL_META)

    result = tiers.analyze_structure_tiers("EURUSD", "H1")

    assert result.status == "INSUFFICIENT_STRUCTURE_HISTORY"
    assert result.external is None and result.internal is None
