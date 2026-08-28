"""DAYTRADING_BASIC_SKILLS_ROUTER_V1 spec section 28: the same classifier/router path
must work for any currently-supported reference session pair, with session_name treated
as pure metadata -- no `if session_name == ...` branching in setup_router.py."""
from __future__ import annotations

import datetime as dt
import inspect

import daytrading.decision.setup_router as setup_router
from daytrading.decision.models import MarketBias, MarketBiasDirection
from daytrading.decision.setup_router import route_daytrading_setup
from strategy_engine.session import Candle, Direction, SetupType

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)


def _candle(hour, minute, o, h, l, c) -> Candle:
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _trend_session(n=20):
    candles = []
    price = 1.1000
    for i in range(n):
        o = price
        price += 0.0010
        c = price
        candles.append(_candle(*divmod(15 * i, 60), o, c, o, c))
    return candles


def test_no_session_name_branching_in_router_source():
    source = inspect.getsource(setup_router)
    assert "session_name ==" not in source
    assert 'if session_name' not in source


def test_router_produces_equivalent_result_for_two_different_session_pairs():
    bias = MarketBias(direction=MarketBiasDirection.BULLISH.value, timeframe="H1")

    asian = route_daytrading_setup("TEST", "EURUSD", "asian", DAY, _trend_session(n=24), 24, bias)
    london = route_daytrading_setup("TEST", "EURUSD", "london_am", DAY, _trend_session(n=20), 20, bias)

    assert asian.setup_type is SetupType.TREND is london.setup_type
    assert asian.direction is Direction.LONG is london.direction
    assert asian.decision_status == london.decision_status == "VALID"
    assert asian.session_decision.reference_session == "asian"
    assert london.session_decision.reference_session == "london_am"
