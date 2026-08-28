"""Tests for liquidity.affinity: AG_LIQUIDITY_AFFINITY_V1 (spec sections 19-24). Pure/
offline -- no MT5 connection, no candle fetch; every input is hand-built."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from liquidity.affinity import (
    AFFINITY_INVALIDATED,
    BEARISH_INTERNAL_TO_EXTERNAL,
    BULLISH_INTERNAL_TO_EXTERNAL,
    EXTERNAL_TO_INTERNAL,
    INTERNAL_REBALANCING,
    evaluate_liquidity_affinity,
)
from liquidity.hierarchy import SCOPE_EXTERNAL, SCOPE_INTERNAL, ScopedLiquidityLevel, level_id
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure.models import (
    STATE_BEARISH,
    STATE_BULLISH,
    StructurePoint,
    StructurePointKind,
    StructureTier,
    TieredStructureResult,
)
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
from supply_demand.native_zones import dealing_range_zones

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _scoped(source, side, price, scope, status=LiquidityStatus.UNSWEPT, sweep_time=None) -> ScopedLiquidityLevel:
    lvl = LiquidityLevel(symbol="EURUSD", timeframe="H1", side=side, source=source, price=price,
                          origin_time=NOW, status=status, sweep_time=sweep_time)
    return ScopedLiquidityLevel(level=lvl, scope=scope, level_id=level_id(lvl))


def _fvg(direction, low, high, status=ZoneStatus.FRESH, origin_time=NOW) -> ZoneResult:
    return ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.FVG,
                       role=ZoneRole.DEMAND if direction == ZoneDirection.BULLISH else ZoneRole.SUPPLY,
                       direction=direction, status=status, source="smc.fvg", low=low, high=high, origin_time=origin_time)


def _tier(tier_name, direction, swing_length=50, latest_bos=None, latest_choch=None) -> StructureTier:
    return StructureTier(tier=tier_name, swing_length=swing_length, direction=direction, swings=(), events=(),
                          latest_bos=latest_bos, latest_choch=latest_choch)


def _tiers(symbol, timeframe, external: StructureTier, internal: StructureTier) -> TieredStructureResult:
    return TieredStructureResult(symbol=symbol, timeframe=timeframe, status="VALID", reason_codes=(),
                                  external=external, internal=internal)


# --------------------------------------------------------------------------- section 19: bullish

def test_bullish_internal_to_external():
    external = _tier("EXTERNAL", STATE_BULLISH)
    internal = _tier("INTERNAL", STATE_BEARISH)  # opposing external bias -> CORRECTIVE
    tiers = _tiers("EURUSD", "H1", external, internal)

    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    fvg = _fvg(ZoneDirection.BULLISH, 1.1740, 1.1770)
    dealing_range = dealing_range_zones("EURUSD", 1.1700, 1.1900, source="external_tier_swing_range", current_price=1.1780)

    result = evaluate_liquidity_affinity("EURUSD", "H1", tiers, scoped, (fvg,), dealing_range, current_price=1.1780)

    assert result.structural_bias == STATE_BULLISH
    assert result.market_phase == "CORRECTIVE"
    assert result.affinity == BULLISH_INTERNAL_TO_EXTERNAL
    assert result.external_liquidity_type == "EXTERNAL_BSL"
    assert result.imbalance_candidate == "FVG"
    assert result.premium_discount_location == "DISCOUNT"
    assert result.trade_signal == "NONE"


# --------------------------------------------------------------------------- section 20: bearish

def test_bearish_internal_to_external():
    external = _tier("EXTERNAL", STATE_BEARISH)
    internal = _tier("INTERNAL", STATE_BULLISH)  # opposing -> CORRECTIVE
    tiers = _tiers("EURUSD", "H1", external, internal)

    scoped = [_scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1700, SCOPE_EXTERNAL)]
    fvg = _fvg(ZoneDirection.BEARISH, 1.1830, 1.1860)
    dealing_range = dealing_range_zones("EURUSD", 1.1700, 1.1900, source="external_tier_swing_range", current_price=1.1820)

    result = evaluate_liquidity_affinity("EURUSD", "H1", tiers, scoped, (fvg,), dealing_range, current_price=1.1820)

    assert result.structural_bias == STATE_BEARISH
    assert result.market_phase == "CORRECTIVE"
    assert result.affinity == BEARISH_INTERNAL_TO_EXTERNAL
    assert result.external_liquidity_type == "EXTERNAL_SSL"
    assert result.imbalance_candidate == "FVG"
    assert result.premium_discount_location == "PREMIUM"
    assert result.trade_signal == "NONE"


# --------------------------------------------------------------------------- section 21: external -> internal

def test_external_to_internal_does_not_force_an_external_objective():
    external = _tier("EXTERNAL", STATE_BULLISH)
    internal = _tier("INTERNAL", STATE_BULLISH)
    tiers = _tiers("EURUSD", "H1", external, internal)

    sweep_time = NOW
    scoped = [_scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1650, SCOPE_EXTERNAL,
                       status=LiquidityStatus.RECLAIMED, sweep_time=sweep_time)]
    fvg = _fvg(ZoneDirection.BULLISH, 1.1700, 1.1730, origin_time=sweep_time + timedelta(hours=1))

    result = evaluate_liquidity_affinity("EURUSD", "H1", tiers, scoped, (fvg,), None, current_price=1.1750)

    assert result.affinity == EXTERNAL_TO_INTERNAL
    assert result.latest_liquidity_event == "SELL_SIDE_SWEEP"
    assert result.imbalance_candidate == "FVG"
    assert result.trade_signal == "NONE"


# --------------------------------------------------------------------------- section 22: invalidation

def test_affinity_invalidated_on_opposing_structural_break():
    external_bull = _tier("EXTERNAL", STATE_BULLISH)
    internal_bear = _tier("INTERNAL", STATE_BEARISH)
    tiers_bull = _tiers("EURUSD", "H1", external_bull, internal_bear)
    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    fvg = _fvg(ZoneDirection.BULLISH, 1.1740, 1.1770)
    first = evaluate_liquidity_affinity("EURUSD", "H1", tiers_bull, scoped, (fvg,), None, current_price=1.1780)
    assert first.affinity == BULLISH_INTERNAL_TO_EXTERNAL

    external_bear = _tier("EXTERNAL", STATE_BEARISH)
    internal_bear2 = _tier("INTERNAL", STATE_BEARISH)
    tiers_bear = _tiers("EURUSD", "H1", external_bear, internal_bear2)
    second = evaluate_liquidity_affinity("EURUSD", "H1", tiers_bear, scoped, (fvg,), None,
                                          current_price=1.1780, previous_affinity=first.affinity)

    assert second.affinity == AFFINITY_INVALIDATED
    assert second.affinity_invalidated is True
    assert second.trade_signal == "NONE"


# --------------------------------------------------------------------------- section 23: FVG != liquidity pool

def test_fvg_is_not_collapsed_into_internal_liquidity_candidate():
    external = _tier("EXTERNAL", STATE_BULLISH)
    internal = _tier("INTERNAL", STATE_BEARISH)
    tiers = _tiers("EURUSD", "H1", external, internal)

    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]  # no internal pool at all
    fvg = _fvg(ZoneDirection.BULLISH, 1.1740, 1.1770)

    result = evaluate_liquidity_affinity("EURUSD", "H1", tiers, scoped, (fvg,), None, current_price=1.1780)

    assert result.imbalance_candidate == "FVG"
    assert result.internal_liquidity_candidate is None
    assert result.affinity == BULLISH_INTERNAL_TO_EXTERNAL


# --------------------------------------------------------------------------- section 24: multi-timeframe

def test_h1_and_m15_are_not_forced_to_the_same_bias():
    h1_external = _tier("EXTERNAL", STATE_BULLISH)
    h1_internal = _tier("INTERNAL", STATE_BEARISH)
    h1_tiers = _tiers("EURUSD", "H1", h1_external, h1_internal)
    h1_scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    h1_fvg = _fvg(ZoneDirection.BULLISH, 1.1740, 1.1770)
    h1_result = evaluate_liquidity_affinity("EURUSD", "H1", h1_tiers, h1_scoped, (h1_fvg,), None, current_price=1.1780)
    assert h1_result.affinity == BULLISH_INTERNAL_TO_EXTERNAL

    m15_external = _tier("EXTERNAL", STATE_BEARISH)
    m15_internal = _tier("INTERNAL", STATE_BULLISH)  # corrective bullish leg inside a bearish external tier
    m15_tiers = _tiers("EURUSD", "M15", m15_external, m15_internal)
    m15_scoped = [_scoped("INTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1850, SCOPE_INTERNAL)]  # no external SSL
    m15_result = evaluate_liquidity_affinity("EURUSD", "M15", m15_tiers, m15_scoped, (), None, current_price=1.1800)

    assert m15_result.affinity != h1_result.affinity
    assert m15_result.affinity == INTERNAL_REBALANCING
