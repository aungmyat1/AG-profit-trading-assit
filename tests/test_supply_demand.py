"""Tests for supply_demand: FVG mapping (real smc.fvg() on hand-built minimal gap
fixtures), order-block mapping/mitigation (smc.ob()'s own trigger conditions are too
stateful to hand-construct reliably, so its OUTPUT is mocked here -- this tests OUR
mapping, which is the boundary we own; smc.ob()'s own detection was verified separately
against live EURUSD data), session zones, previous-day high/low, and the pure
premium/equilibrium/discount calculation.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pandas as pd
import pytest

from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneRole, ZoneStatus
from supply_demand.native_zones import dealing_range_zones
from supply_demand.smc_adapter import fair_value_gaps, order_blocks

UTC = dt.timezone.utc


def _candle(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c, volume=1.0)


# --------------------------------------------------------------------------- FVG (real smc.fvg())

def test_bullish_fvg_maps_to_fresh_demand_zone():
    t0 = dt.datetime(2026, 1, 5, tzinfo=UTC)
    candles = [
        _candle(t0, 1.0980, 1.1000, 1.0975, 1.0990),
        _candle(t0 + dt.timedelta(minutes=15), 1.0990, 1.1060, 1.0985, 1.1055),  # bullish, leaves the gap
        _candle(t0 + dt.timedelta(minutes=30), 1.1055, 1.1080, 1.1050, 1.1075),
    ]
    zones = fair_value_gaps("EURUSD", "M15", candles)

    assert len(zones) == 1
    z = zones[0]
    assert z.family == ZoneFamily.FVG
    assert z.direction == ZoneDirection.BULLISH
    assert z.role == ZoneRole.DEMAND
    assert z.low == pytest.approx(1.1000)
    assert z.high == pytest.approx(1.1050)
    assert z.status == ZoneStatus.FRESH


def test_bearish_fvg_with_later_candle_maps_to_mitigated_supply_zone():
    t0 = dt.datetime(2026, 1, 5, tzinfo=UTC)
    candles = [
        _candle(t0, 1.1080, 1.1090, 1.1075, 1.1078),
        _candle(t0 + dt.timedelta(minutes=15), 1.1078, 1.1080, 1.1010, 1.1015),  # bearish, leaves the gap
        _candle(t0 + dt.timedelta(minutes=30), 1.1015, 1.1020, 1.1000, 1.1005),
        _candle(t0 + dt.timedelta(minutes=45), 1.1005, 1.1078, 1.1000, 1.1070),  # crosses back into the gap
    ]
    zones = fair_value_gaps("EURUSD", "M15", candles)

    assert len(zones) == 1
    z = zones[0]
    assert z.direction == ZoneDirection.BEARISH
    assert z.role == ZoneRole.SUPPLY
    assert z.low == pytest.approx(1.1020)
    assert z.high == pytest.approx(1.1075)
    assert z.status == ZoneStatus.MITIGATED


def test_no_gap_produces_no_fvg_zones():
    t0 = dt.datetime(2026, 1, 5, tzinfo=UTC)
    candles = [_candle(t0 + dt.timedelta(minutes=15 * i), 1.10, 1.1005, 1.0995, 1.10) for i in range(10)]
    assert fair_value_gaps("EURUSD", "M15", candles) == []


# --------------------------------------------------------------------------- Order Blocks (mocked smc.ob output)

def _fake_swings_and_ob_frames():
    swings = pd.DataFrame({"HighLow": [1.0, -1.0, 1.0], "Level": [1.20, 1.10, 1.25]})
    ob = pd.DataFrame({
        "OB": [1.0, None, -1.0],
        "Top": [1.1010, None, 1.2010],
        "Bottom": [1.1000, None, 1.2000],
        "OBVolume": [500.0, None, 800.0],
        "MitigatedIndex": [0.0, None, 5.0],   # index 0: fresh bullish; index 2: mitigated bearish
        "Percentage": [40.0, None, 60.0],
    })
    return swings, ob


def test_order_block_mapping_bullish_fresh_and_bearish_mitigated():
    t0 = dt.datetime(2026, 1, 5, tzinfo=UTC)
    candles = [_candle(t0 + dt.timedelta(minutes=15 * i), 1.1, 1.1005, 1.0995, 1.1) for i in range(3)]

    swings, ob_frame = _fake_swings_and_ob_frames()
    with patch("supply_demand.smc_adapter.smc.swing_highs_lows", return_value=swings), \
         patch("supply_demand.smc_adapter.smc.ob", return_value=ob_frame):
        zones = order_blocks("EURUSD", "M15", candles, swing_length=5)

    assert len(zones) == 2
    bullish, bearish = zones[0], zones[1]

    assert bullish.family == ZoneFamily.ORDER_BLOCK
    assert bullish.direction == ZoneDirection.BULLISH
    assert bullish.role == ZoneRole.DEMAND
    assert bullish.low == pytest.approx(1.1000)
    assert bullish.high == pytest.approx(1.1010)
    assert bullish.status == ZoneStatus.FRESH
    assert bullish.raw_strength_metric == pytest.approx(40.0)

    assert bearish.direction == ZoneDirection.BEARISH
    assert bearish.role == ZoneRole.SUPPLY
    assert bearish.status == ZoneStatus.MITIGATED


# --------------------------------------------------------------------------- Premium/Equilibrium/Discount (pure)

def test_dealing_range_zones_classifies_premium_discount_equilibrium():
    above = dealing_range_zones("EURUSD", low=1.1000, high=1.1100, source="test", current_price=1.1080)
    below = dealing_range_zones("EURUSD", low=1.1000, high=1.1100, source="test", current_price=1.1020)
    exact = dealing_range_zones("EURUSD", low=1.1000, high=1.1100, source="test", current_price=1.1050)

    assert above.equilibrium == pytest.approx(1.1050)
    assert above.current_zone == "PREMIUM"
    assert below.current_zone == "DISCOUNT"
    assert exact.current_zone == "EQUILIBRIUM"
    assert above.source == "test"  # never guessed -- caller-named source is preserved verbatim


# --------------------------------------------------------------------------- live verification

def _mt5_available():
    import MetaTrader5 as mt5
    return mt5.initialize()


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
@pytest.mark.parametrize("timeframe", ["H1", "M15"])
def test_order_blocks_and_fvg_live_eurusd(timeframe):
    from mt5.connection import connect
    from supply_demand import fair_value_gaps_for, order_blocks_for

    connect()
    obs = order_blocks_for("EURUSD", timeframe)
    fvgs = fair_value_gaps_for("EURUSD", timeframe)

    assert obs.status == "OK"
    assert fvgs.status == "OK"
    for z in obs.zones:
        assert z.high >= z.low
        assert z.status in (ZoneStatus.FRESH, ZoneStatus.MITIGATED)
    for z in fvgs.zones:
        assert z.high >= z.low


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_session_zone_and_previous_day_live():
    from mt5.connection import connect
    from supply_demand import previous_day_high_low, session_zone

    connect()
    prev = previous_day_high_low("EURUSD")
    assert prev.status in (ZoneStatus.FRESH, ZoneStatus.TOUCHED, ZoneStatus.UNKNOWN)
    if prev.low is not None:
        assert prev.high >= prev.low

    session = session_zone("EURUSD", "asian")
    if session.low is not None:
        assert session.high >= session.low
