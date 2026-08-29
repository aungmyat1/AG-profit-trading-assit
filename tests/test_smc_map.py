"""Tests for smc_map: single-snapshot reuse (each analyzer called exactly once per
timeframe), evidence ID stability/uniqueness, and fail-closed behavior on missing data.
All dependencies of smc_map.builder are monkeypatched -- this tests OUR normalization/
stitching boundary, not market_structure/supply_demand/liquidity's own detection (those
have their own test suites).
"""
from __future__ import annotations

import datetime as dt

import pytest

import smc_map.builder as builder_mod
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityResult, LiquidityStatus
from market_structure.models import (
    STATE_BULLISH,
    StructurePoint,
    StructurePointKind,
    StructureTier,
    TieredStructureResult,
)
from mt5.market_data import MarketDataError, Tick
from smc_map.evidence import evidence_id
from smc_map.models import DEFAULT_TIMEFRAMES
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneQueryResult, ZoneResult, ZoneRole, ZoneStatus
from supply_demand.native_zones import DealingRangeZones

UTC = dt.timezone.utc


def _tier(tier_name, swing_length, bos_price=1.1100, bos_time=dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC)):
    bos = StructurePoint(bos_time, bos_price, StructurePointKind.BULLISH_BOS)
    return StructureTier(tier=tier_name, swing_length=swing_length, direction=STATE_BULLISH,
                          swings=(), events=(bos,), latest_bos=bos)


def _structure(symbol, timeframe):
    return TieredStructureResult(symbol=symbol, timeframe=timeframe, status="VALID", reason_codes=(),
                                  external=_tier("EXTERNAL", 50), internal=_tier("INTERNAL", 5))


def _zone(symbol, timeframe, family, low, high, origin):
    return ZoneResult(symbol=symbol, timeframe=timeframe, family=family, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="test",
                       low=low, high=high, origin_time=origin)


def _liquidity_level(symbol, timeframe, price, origin):
    return LiquidityLevel(symbol=symbol, timeframe=timeframe, side=LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                           price=price, origin_time=origin, status=LiquidityStatus.UNSWEPT)


@pytest.fixture(autouse=True)
def _patch_all(monkeypatch):
    calls = {"structure": 0, "ob": 0, "fvg": 0, "liq": 0, "pd": 0}

    def fake_structure(symbol, timeframe):
        calls["structure"] += 1
        return _structure(symbol, timeframe)

    def fake_ob(symbol, timeframe, count=None, close_mitigation=False):
        calls["ob"] += 1
        origin = dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC)
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.ORDER_BLOCK, status="OK",
                                zones=(_zone(symbol, timeframe, ZoneFamily.ORDER_BLOCK, 1.0990, 1.1010, origin),))

    def fake_fvg(symbol, timeframe, count=None, join_consecutive=False):
        calls["fvg"] += 1
        origin = dt.datetime(2026, 1, 5, 2, 0, tzinfo=UTC)
        return ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.FVG, status="OK",
                                zones=(_zone(symbol, timeframe, ZoneFamily.FVG, 1.1020, 1.1030, origin),))

    def fake_liquidity(symbol, timeframe, count=None):
        calls["liq"] += 1
        origin = dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC)
        level = _liquidity_level(symbol, timeframe, 1.1200, origin)
        return LiquidityResult(symbol=symbol, timeframe=timeframe, status="LIQUIDITY_OK", levels=(level,),
                                nearest_buy_side=level)

    def fake_premium_discount(symbol):
        calls["pd"] += 1
        return DealingRangeZones(symbol=symbol, source="previous_day", low=1.0800, high=1.1200,
                                  equilibrium=1.1000, premium_low=1.1000, premium_high=1.1200,
                                  discount_low=1.0800, discount_high=1.1000, current_price=1.1050,
                                  current_zone="PREMIUM")

    def fake_tick(symbol):
        return Tick(symbol=symbol, time_utc=dt.datetime(2026, 1, 5, 4, 0, tzinfo=UTC), bid=1.1050, ask=1.1052)

    monkeypatch.setattr(builder_mod, "analyze_structure_tiers", fake_structure)
    monkeypatch.setattr(builder_mod, "order_blocks_for", fake_ob)
    monkeypatch.setattr(builder_mod, "fair_value_gaps_for", fake_fvg)
    monkeypatch.setattr(builder_mod, "liquidity_result", fake_liquidity)
    monkeypatch.setattr(builder_mod, "premium_discount_from_previous_day", fake_premium_discount)
    monkeypatch.setattr(builder_mod, "get_tick", fake_tick)
    return calls


# --------------------------------------------------------------------------- single-snapshot reuse

def test_each_analyzer_called_exactly_once_per_timeframe(_patch_all):
    builder_mod.build_smc_market_map("EURUSD", timeframes=("H1", "M5"))
    assert _patch_all["structure"] == 2  # once per timeframe, not once per E/M/consumer
    assert _patch_all["ob"] == 2
    assert _patch_all["fvg"] == 2
    assert _patch_all["liq"] == 2
    assert _patch_all["pd"] == 1  # premium/discount is symbol-scoped, not per-timeframe


def test_default_timeframes_used_when_unspecified():
    result = builder_mod.build_smc_market_map("EURUSD")
    assert set(result.timeframes.keys()) == set(DEFAULT_TIMEFRAMES)


# --------------------------------------------------------------------------- content / data quality

def test_market_map_is_ok_when_everything_available():
    result = builder_mod.build_smc_market_map("EURUSD", timeframes=("H1",))
    assert result.data_quality == "OK"
    assert result.symbol == "EURUSD"
    h1 = result.timeframe_map("H1")
    assert h1.structure.status == "VALID"
    assert len(h1.order_blocks) == 1
    assert len(h1.fair_value_gaps) == 1
    assert len(h1.liquidity_levels) == 1
    assert result.premium_discount.current_zone == "PREMIUM"


# --------------------------------------------------------------------------- evidence IDs

def test_evidence_ids_are_stable_and_resolve_back_to_the_same_object():
    result = builder_mod.build_smc_market_map("EURUSD", timeframes=("H1",))
    h1 = result.timeframe_map("H1")
    ob = h1.order_blocks[0]
    eid = evidence_id("OB", "EURUSD", "H1", ob.origin_time, ob.low)
    assert eid in h1.evidence_index
    assert h1.evidence_index[eid] is ob
    assert result.resolve_evidence(eid) is ob


def test_evidence_ids_differ_for_different_objects():
    result = builder_mod.build_smc_market_map("EURUSD", timeframes=("H1",))
    h1 = result.timeframe_map("H1")
    ob = h1.order_blocks[0]
    fvg = h1.fair_value_gaps[0]
    ob_id = evidence_id("OB", "EURUSD", "H1", ob.origin_time, ob.low)
    fvg_id = evidence_id("FVG", "EURUSD", "H1", fvg.origin_time, fvg.low)
    assert ob_id != fvg_id


def test_evidence_id_is_deterministic_across_calls():
    t = dt.datetime(2026, 1, 5, tzinfo=UTC)
    assert evidence_id("OB", "EURUSD", "H1", t, 1.1000) == evidence_id("OB", "EURUSD", "H1", t, 1.1000)


def test_unresolvable_evidence_id_returns_none():
    result = builder_mod.build_smc_market_map("EURUSD", timeframes=("H1",))
    assert result.resolve_evidence("OB-H1-doesnotexist") is None


# --------------------------------------------------------------------------- fail-closed

def test_structure_fetch_failure_degrades_that_component_only(monkeypatch):
    def fail(symbol, timeframe):
        raise MarketDataError("DATA_MISSING", "no candles in this deterministic test")

    monkeypatch.setattr(builder_mod, "analyze_structure_tiers", fail)
    result = builder_mod.build_smc_market_map("EURUSD", timeframes=("H1",))

    h1 = result.timeframe_map("H1")
    assert h1.structure is None
    assert len(h1.order_blocks) == 1  # other components still populated
    assert any("STRUCTURE_H1_FETCH_FAILED" in w for w in result.warnings)
    assert result.data_quality == "PARTIAL"


def test_all_components_unavailable_is_unavailable_not_fabricated(monkeypatch):
    def fail_structure(symbol, timeframe):
        raise MarketDataError("DATA_MISSING", "x")

    def fail_query(symbol, timeframe, count=None, **kwargs):
        raise MarketDataError("DATA_MISSING", "x")

    def fail_liq(symbol, timeframe, count=None):
        raise MarketDataError("DATA_MISSING", "x")

    monkeypatch.setattr(builder_mod, "analyze_structure_tiers", fail_structure)
    monkeypatch.setattr(builder_mod, "order_blocks_for", fail_query)
    monkeypatch.setattr(builder_mod, "fair_value_gaps_for", fail_query)
    monkeypatch.setattr(builder_mod, "liquidity_result", fail_liq)
    monkeypatch.setattr(builder_mod, "premium_discount_from_previous_day",
                         lambda symbol: (_ for _ in ()).throw(MarketDataError("DATA_MISSING", "x")))

    result = builder_mod.build_smc_market_map("EURUSD", timeframes=("H1",))
    assert result.data_quality == "UNAVAILABLE"
    h1 = result.timeframe_map("H1")
    assert h1.structure is None and h1.order_blocks == () and h1.fair_value_gaps == () and h1.liquidity_levels == ()
