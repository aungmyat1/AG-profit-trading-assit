"""E2_H1_POI_REACTION_V1 tests -- location + reaction only (spec section 8). This file
was rewritten as part of the SMC_ENTRY_MODELS_V1 refactor: the sweep -> CHoCH ->
displacement -> FVG/OB pipeline that used to live here moved to M3
(m3_sweep_drop_pump.py, see test_m3_sweep_drop_pump.py) since that pipeline is HTF-
liquidity-sweep-driven, not H1-POI-reaction-driven. E2 now only asks: has price reached
the H1 POI, and has it produced a qualifying M5 reaction candle (AG_ENTRY_DISPLACEMENT_V1)?
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.e2_h1_poi_reaction import E2PoiReactionRequest, evaluate_e2_h1_poi_reaction
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc

_POI_TOUCH_TIME = dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC)


def _h1_candle(hour, o, h, l, c, day=5):
    return Candle(dt.datetime(2026, 1, day, hour, 0, tzinfo=UTC), o, h, l, c)


def _h1_poi_zone(status=ZoneStatus.TOUCHED, direction=ZoneDirection.BEARISH, low=1.1005, high=1.1015):
    return ZoneResult(
        symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.SUPPLY,
        direction=direction, status=status, source="test",
        low=low, high=high, origin_time=dt.datetime(2026, 1, 4, 10, 0, tzinfo=UTC),
    )


def _h1_candles_with_touch():
    return [
        _h1_candle(0, 1.0990, 1.0995, 1.0985, 1.0992),
        _h1_candle(1, 1.0992, 1.0998, 1.0988, 1.0995),
        _h1_candle(2, 1.0995, 1.1003, 1.0990, 1.1000),
        Candle(_POI_TOUCH_TIME, 1.1000, 1.1012, 1.0998, 1.1008),  # intersects [1.1005, 1.1015]
        _h1_candle(4, 1.1008, 1.1010, 1.1000, 1.1002),
    ]


def _displacement_history():
    base = _POI_TOUCH_TIME - dt.timedelta(hours=2)
    return [
        Candle(base + dt.timedelta(minutes=5 * i), 1.1000, 1.1002, 1.0999, 1.10005)
        for i in range(20)
    ]


def _strong_bearish_m5_candles():
    """A single large bearish candle strictly after POI touch, big enough (relative to
    the tiny _displacement_history bodies) to qualify AG_ENTRY_DISPLACEMENT_V1."""
    return [
        Candle(_POI_TOUCH_TIME + dt.timedelta(minutes=5), 1.1010, 1.1012, 1.0930, 1.0932),
    ]


def _weak_m5_candles():
    return [
        Candle(_POI_TOUCH_TIME + dt.timedelta(minutes=5), 1.1010, 1.1011, 1.1009, 1.10095),
    ]


def _base_request(**overrides):
    kwargs = dict(
        symbol="EURUSD", h1_poi_zone=_h1_poi_zone(), h1_candles=_h1_candles_with_touch(),
        m5_candles=_strong_bearish_m5_candles(), m5_displacement_history=_displacement_history(),
        evaluation_time=_POI_TOUCH_TIME + dt.timedelta(hours=1),
    )
    kwargs.update(overrides)
    return E2PoiReactionRequest(**kwargs)


def test_full_bearish_poi_reaction_confirms_eligible_for_confirmation():
    result = evaluate_e2_h1_poi_reaction(_base_request())
    assert result.touch_status == "POI_TOUCHED"
    assert result.reaction_status == "POI_REACTED"
    assert result.direction == "SHORT"
    assert result.eligible_for_confirmation is True
    assert result.poi_interaction_time == _POI_TOUCH_TIME
    assert result.reaction_time is not None


def test_full_bullish_poi_reaction_confirms_eligible_for_confirmation():
    poi = _h1_poi_zone(direction=ZoneDirection.BULLISH, low=1.0985, high=1.0995)
    h1_candles = [
        _h1_candle(0, 1.1000, 1.1005, 1.0995, 1.0998),
        Candle(_POI_TOUCH_TIME, 1.0998, 1.1000, 1.0990, 1.0993),  # intersects [1.0985, 1.0995]
    ]
    m5_candles = [Candle(_POI_TOUCH_TIME + dt.timedelta(minutes=5), 1.0993, 1.1075, 1.0991, 1.1072)]
    result = evaluate_e2_h1_poi_reaction(_base_request(h1_poi_zone=poi, h1_candles=h1_candles, m5_candles=m5_candles))
    assert result.direction == "LONG"
    assert result.reaction_status == "POI_REACTED"
    assert result.eligible_for_confirmation is True


def test_poi_touched_but_no_qualifying_reaction_waits():
    result = evaluate_e2_h1_poi_reaction(_base_request(m5_candles=_weak_m5_candles()))
    assert result.touch_status == "POI_TOUCHED"
    assert result.reaction_status == "WAITING_REACTION"
    assert result.eligible_for_confirmation is False


def test_poi_not_yet_reached_stays_dormant():
    fresh_poi = _h1_poi_zone(status=ZoneStatus.FRESH)
    result = evaluate_e2_h1_poi_reaction(_base_request(h1_poi_zone=fresh_poi))
    assert result.touch_status == "WAITING_POI"
    assert result.eligible_for_confirmation is False


def test_invalidated_poi_never_confirms():
    invalidated_poi = _h1_poi_zone(status=ZoneStatus.INVALIDATED)
    result = evaluate_e2_h1_poi_reaction(_base_request(h1_poi_zone=invalidated_poi))
    assert result.invalidation == "POI_INVALIDATED"
    assert result.eligible_for_confirmation is False


def test_missing_h1_poi_zone_is_dormant_not_fabricated():
    result = evaluate_e2_h1_poi_reaction(_base_request(h1_poi_zone=None))
    assert result.touch_status == "WAITING_POI"
    assert result.eligible_for_confirmation is False


def test_reaction_after_evaluation_time_is_not_used_lookahead_safe():
    late_result = evaluate_e2_h1_poi_reaction(_base_request(evaluation_time=_POI_TOUCH_TIME + dt.timedelta(minutes=1)))
    assert late_result.eligible_for_confirmation is False
    assert late_result.reaction_status == "WAITING_REACTION"


def test_zero_lookahead_future_mutation_does_not_change_past_result():
    request_t = _base_request()
    result_before = evaluate_e2_h1_poi_reaction(request_t)

    mutated_candles = list(request_t.m5_candles) + [
        Candle(_POI_TOUCH_TIME + dt.timedelta(hours=2), 1.0500, 1.0900, 1.0400, 1.0850),
    ]
    mutated_request = E2PoiReactionRequest(**{**request_t.__dict__, "m5_candles": mutated_candles})
    result_after = evaluate_e2_h1_poi_reaction(mutated_request)

    assert result_after.eligible_for_confirmation == result_before.eligible_for_confirmation
    assert result_after.reaction_time == result_before.reaction_time
