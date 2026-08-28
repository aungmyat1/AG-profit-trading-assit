"""DAYTRADING_BASIC_SKILLS_ROUTER_V1 spec section 23: market-bias derivation from
market_structure.tiers.TieredStructureResult.external -- evidence, not just a label,
fail-closed on conflict/insufficient data (no invented bias)."""
from __future__ import annotations

from datetime import datetime, timezone

from daytrading.decision.market_bias import derive_market_bias_from_tiers
from daytrading.decision.models import MarketBiasDirection
from market_structure.models import (
    STATE_BEARISH,
    STATE_BULLISH,
    STATE_UNDEFINED,
    StructurePoint,
    StructurePointKind,
    StructureTier,
    TieredStructureResult,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _tiers(direction, latest_swing_high=None, latest_swing_low=None, latest_bos=None, latest_choch=None, status="VALID"):
    external = StructureTier(tier="EXTERNAL", swing_length=50, direction=direction, swings=(), events=(),
                              latest_swing_high=latest_swing_high, latest_swing_low=latest_swing_low,
                              latest_bos=latest_bos, latest_choch=latest_choch)
    return TieredStructureResult(symbol="EURUSD", timeframe="H1", status=status, reason_codes=(), external=external)


def test_bullish_external_structure_with_protected_low_is_bullish():
    protected_low = StructurePoint(time_utc=T0, price=1.1500, kind=StructurePointKind.SWING_LOW)
    bos = StructurePoint(time_utc=T0, price=1.1650, kind=StructurePointKind.BULLISH_BOS)
    tiers = _tiers(STATE_BULLISH, latest_swing_low=protected_low, latest_bos=bos)

    bias = derive_market_bias_from_tiers(tiers, "H1")

    assert bias.direction == MarketBiasDirection.BULLISH.value
    assert bias.protected_level_type == "PROTECTED_LOW"
    assert bias.protected_level == 1.1500
    assert bias.latest_break == "BULLISH_BOS"
    assert "EXTERNAL_STRUCTURE_BULLISH" in bias.reasons
    assert "PROTECTED_LOW_INTACT" in bias.reasons


def test_bearish_external_structure_with_protected_high_is_bearish():
    protected_high = StructurePoint(time_utc=T0, price=1.1700, kind=StructurePointKind.SWING_HIGH)
    choch = StructurePoint(time_utc=T0, price=1.1600, kind=StructurePointKind.BEARISH_CHOCH)
    tiers = _tiers(STATE_BEARISH, latest_swing_high=protected_high, latest_choch=choch)

    bias = derive_market_bias_from_tiers(tiers, "H1")

    assert bias.direction == MarketBiasDirection.BEARISH.value
    assert bias.protected_level_type == "PROTECTED_HIGH"
    assert bias.protected_level == 1.1700
    assert bias.latest_break == "BEARISH_CHOCH"


def test_undefined_structure_is_neutral():
    tiers = _tiers(STATE_UNDEFINED)

    bias = derive_market_bias_from_tiers(tiers, "H1")

    assert bias.direction == MarketBiasDirection.NEUTRAL.value
    assert "EXTERNAL_STRUCTURE_UNDEFINED" in bias.reasons


def test_invalid_tiers_status_is_indeterminate_fail_closed():
    tiers = _tiers(STATE_BULLISH, status="INSUFFICIENT_STRUCTURE_HISTORY")

    bias = derive_market_bias_from_tiers(tiers, "H1")

    assert bias.direction == MarketBiasDirection.INDETERMINATE.value
    assert any("INSUFFICIENT_STRUCTURE_HISTORY" in r for r in bias.reasons)


def test_missing_protected_level_is_still_bullish_but_flagged():
    bos = StructurePoint(time_utc=T0, price=1.1650, kind=StructurePointKind.BULLISH_BOS)
    tiers = _tiers(STATE_BULLISH, latest_bos=bos)  # no latest_swing_low supplied

    bias = derive_market_bias_from_tiers(tiers, "H1")

    assert bias.direction == MarketBiasDirection.BULLISH.value
    assert bias.protected_level is None
    assert "PROTECTED_LOW_UNAVAILABLE" in bias.reasons
