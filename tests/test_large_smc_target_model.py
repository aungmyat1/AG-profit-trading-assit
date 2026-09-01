"""ST_LARGE_SMC_V1 C11 target-model wiring (large_smc_research/target_model.py).

Exercises `select_target` -- the thin adapter implementing the yaml's frozen
HYBRID_WITH_STRUCTURAL_FALLBACK contract -- entirely with synthetic
`market_structure.models.StructureTier`/`Candle` fixtures. No MT5, no historical
replay store: `select_target` takes its structure/candle evidence as plain arguments,
so this is a pure unit test of the primary/fallback/no-target/tie-break logic.
"""
from __future__ import annotations

import datetime as dt

from large_smc_research.target_model import TARGET_TIER_FALLBACK, TARGET_TIER_PRIMARY, select_target
from market_structure.models import StructurePoint, StructurePointKind, StructureTier
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _tier(swings, latest_high=None, latest_low=None):
    return StructureTier(tier="EXTERNAL", swing_length=50, direction="STRUCTURE_STATE_UNDEFINED",
                          swings=tuple(swings), events=(), latest_swing_high=latest_high, latest_swing_low=latest_low)


def _pt(t, price, kind):
    return StructurePoint(time_utc=t, price=price, kind=kind)


def _candle(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c, volume=1.0)


T0 = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)


def test_primary_tier_selects_nearest_unswept_above_anchor_long():
    high = _pt(T0, 1.1100, StructurePointKind.SWING_HIGH)
    low = _pt(T0, 1.0900, StructurePointKind.SWING_LOW)
    tier = _tier([high, low], latest_high=high, latest_low=low)
    result = select_target("LONG", anchor_price=1.1000, symbol="EURUSD", timeframe="M5",
                            external_tier=tier, m5_candles=())
    assert result.found is True
    assert result.target_tier == TARGET_TIER_PRIMARY
    assert result.target_price == 1.1100
    assert result.target_side == "BUY_SIDE"


def test_primary_tier_mirrors_for_short_direction():
    high = _pt(T0, 1.1100, StructurePointKind.SWING_HIGH)
    low = _pt(T0, 1.0900, StructurePointKind.SWING_LOW)
    tier = _tier([high, low], latest_high=high, latest_low=low)
    result = select_target("SHORT", anchor_price=1.1000, symbol="EURUSD", timeframe="M5",
                            external_tier=tier, m5_candles=())
    assert result.found is True
    assert result.target_tier == TARGET_TIER_PRIMARY
    assert result.target_price == 1.0900
    assert result.target_side == "SELL_SIDE"


def test_fallback_tier_used_when_primary_swept():
    # Latest swing high (primary candidate) gets swept by a later candle closing above
    # it -- CONSUMED, not UNSWEPT -- so the primary tier finds nothing and falls back
    # to the older, still-unswept external swing high.
    older_high = _pt(T0, 1.1150, StructurePointKind.SWING_HIGH)
    latest_high = _pt(T0 + dt.timedelta(hours=1), 1.1100, StructurePointKind.SWING_HIGH)
    low = _pt(T0, 1.0900, StructurePointKind.SWING_LOW)
    tier = _tier([older_high, latest_high, low], latest_high=latest_high, latest_low=low)
    sweep_candle = _candle(latest_high.time_utc + dt.timedelta(minutes=5), 1.1101, 1.1120, 1.1099, 1.1115)
    result = select_target("LONG", anchor_price=1.1000, symbol="EURUSD", timeframe="M5",
                            external_tier=tier, m5_candles=(sweep_candle,))
    assert result.found is True
    assert result.target_tier == TARGET_TIER_FALLBACK
    assert result.target_price == 1.1150


def test_no_target_reject_when_neither_tier_qualifies():
    tier = _tier([], latest_high=None, latest_low=None)
    result = select_target("LONG", anchor_price=1.1000, symbol="EURUSD", timeframe="M5",
                            external_tier=tier, m5_candles=())
    assert result.found is False
    assert result.reason == "REJECT_NO_TARGET"


def test_fallback_tie_break_most_recent_origin_time_wins():
    # The primary candidate (latest_swing_high) is the NEAREST level and gets swept by
    # a candle that breaches it without reaching the two farther fallback candidates --
    # forcing fallback. Those two fallback candidates then sit at the SAME price
    # distance from anchor: the more recent origin time must win per
    # MOST_RECENT_ORIGIN_TIME_WINS.
    excluded_latest = _pt(T0 + dt.timedelta(hours=5), 1.1050, StructurePointKind.SWING_HIGH)
    older = _pt(T0, 1.1200, StructurePointKind.SWING_HIGH)
    more_recent = _pt(T0 + dt.timedelta(hours=1), 1.1200, StructurePointKind.HH)
    low = _pt(T0, 1.0900, StructurePointKind.SWING_LOW)
    tier = _tier([older, more_recent, excluded_latest, low], latest_high=excluded_latest, latest_low=low)
    sweep_candle = _candle(excluded_latest.time_utc + dt.timedelta(minutes=5), 1.1051, 1.1060, 1.1049, 1.1055)
    result = select_target("LONG", anchor_price=1.1000, symbol="EURUSD", timeframe="M5",
                            external_tier=tier, m5_candles=(sweep_candle,))
    assert result.found is True
    assert result.target_tier == TARGET_TIER_FALLBACK
    assert result.target_evidence_timestamp == more_recent.time_utc


def test_static_selection_is_deterministic_across_repeated_calls():
    high = _pt(T0, 1.1100, StructurePointKind.SWING_HIGH)
    low = _pt(T0, 1.0900, StructurePointKind.SWING_LOW)
    tier = _tier([high, low], latest_high=high, latest_low=low)
    r1 = select_target("LONG", anchor_price=1.1000, symbol="EURUSD", timeframe="M5", external_tier=tier, m5_candles=())
    r2 = select_target("LONG", anchor_price=1.1000, symbol="EURUSD", timeframe="M5", external_tier=tier, m5_candles=())
    assert r1.target_price == r2.target_price
    assert r1.target_tier == r2.target_tier


def test_missing_structure_tier_fails_closed():
    result = select_target("LONG", anchor_price=1.1000, symbol="EURUSD", timeframe="M5",
                            external_tier=None, m5_candles=())
    assert result.found is False
