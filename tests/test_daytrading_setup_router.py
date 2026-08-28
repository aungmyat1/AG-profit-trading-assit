"""DAYTRADING_BASIC_SKILLS_ROUTER_V1 spec sections 26-27: the full SWEEP/RANGE/TREND/
NO_SETUP routing matrix and cross-skill isolation. Drives real
strategy_engine.session.route_completed_session() (0.40 ER threshold, strict-penetration
sweep) with hand-built Candle sequences -- the regime/sweep engine itself stays exercised
for real, never monkeypatched; only MarketBias is a direct fixture."""
from __future__ import annotations

import datetime as dt

from daytrading.decision.models import DirectionAlignment, MarketBias, MarketBiasDirection
from daytrading.decision.setup_router import route_daytrading_setup
from strategy_engine.session import Candle, Direction, SetupType

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)


def _candle(hour, minute, o, h, l, c) -> Candle:
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _bias(direction) -> MarketBias:
    return MarketBias(direction=direction, timeframe="H1")


# ---- TREND sessions (ER >= 0.40): a monotonically-walking session with no retracement ----

def _trend_session(long=True, n=24):
    """path_length == displacement (pure directional walk) => efficiency_ratio == 1.0."""
    candles = []
    price = 1.1000
    step = 0.0010 if long else -0.0010
    for i in range(n):
        o = price
        price += step
        c = price
        h, l = (max(o, c), min(o, c))
        candles.append(_candle(*divmod(15 * i, 60), o, h, l, c))
    return candles


def _range_session_flat(n=24, price=1.1000):
    """path_length == 0 => RANGE by construction (matches test_session_router.py's own
    zero-path-length RANGE fixture)."""
    return [_candle(*divmod(15 * i, 60), price, price, price, price) for i in range(n)]


REFERENCE_LOW = 1.1000
REFERENCE_HIGH = 1.1000  # flat box: session_high == session_low == price


def _sell_side_sweep_candle():
    return _candle(6, 15, 1.0999, 1.0999, 1.0995, 1.1002)  # low < ref_low, close > ref_low


def _buy_side_sweep_candle():
    return _candle(6, 15, 1.1001, 1.1005, 1.1001, 1.0998)  # high > ref_high, close < ref_high


def test_bullish_range_sell_side_sweep_gives_sweep_long(monkeypatch=None):
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert result.setup_type is SetupType.SWEEP
    assert result.direction is Direction.LONG
    assert result.direction_alignment is DirectionAlignment.ALIGNED
    assert result.decision_status == "VALID"
    assert result.sweep_detected is True
    assert result.sweep_side == "SELL_SIDE"


def test_bearish_range_buy_side_sweep_gives_sweep_short():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BEARISH.value), post_session_candles=[_buy_side_sweep_candle()],
    )
    assert result.setup_type is SetupType.SWEEP
    assert result.direction is Direction.SHORT
    assert result.direction_alignment is DirectionAlignment.ALIGNED
    assert result.decision_status == "VALID"


def test_bullish_range_no_sweep_falls_through_to_range_setup_if_rejection_found():
    # An upper-boundary rejection candle (RANGE via entry_3) that closes SHORT would
    # CONFLICT with a BULLISH bias -- assert the router reports CONFLICT, not a
    # fabricated LONG.
    # high==session_high (touch, not strict penetration -- fails entry_2_sweep's strict
    # `>`), close<session_high and close<open (qualifies entry_3_range's rejection).
    rejection = _candle(6, 15, 1.1000, 1.1000, 1.0997, 1.0998)
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[rejection],
    )
    assert result.setup_type is SetupType.RANGE
    assert result.direction is Direction.SHORT
    assert result.direction_alignment is DirectionAlignment.CONFLICT
    assert result.decision_status == "CONFLICT"
    assert result.execution_eligible is False


def test_range_with_no_sweep_and_no_rejection_is_no_setup():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[],
    )
    assert result.setup_type is SetupType.NONE
    assert result.decision_status == "NO_SETUP"
    assert result.execution_eligible is False


def test_bullish_trend_long_is_aligned_trend_setup():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _trend_session(long=True), 24,
        _bias(MarketBiasDirection.BULLISH.value),
    )
    assert result.setup_type is SetupType.TREND
    assert result.direction is Direction.LONG
    assert result.session_trend_direction is Direction.LONG
    assert result.direction_alignment is DirectionAlignment.ALIGNED
    assert result.decision_status == "VALID"


def test_bearish_trend_short_is_aligned_trend_setup():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _trend_session(long=False), 24,
        _bias(MarketBiasDirection.BEARISH.value),
    )
    assert result.setup_type is SetupType.TREND
    assert result.direction is Direction.SHORT
    assert result.direction_alignment is DirectionAlignment.ALIGNED
    assert result.decision_status == "VALID"


def test_bullish_bias_trend_short_is_conflict_no_execution():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _trend_session(long=False), 24,
        _bias(MarketBiasDirection.BULLISH.value),
    )
    assert result.setup_type is SetupType.TREND
    assert result.direction_alignment is DirectionAlignment.CONFLICT
    assert result.decision_status == "CONFLICT"
    assert result.execution_eligible is False
    assert "BIAS_TREND_CONFLICT" in result.reason_codes


def test_bearish_bias_trend_long_is_conflict_no_execution():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _trend_session(long=True), 24,
        _bias(MarketBiasDirection.BEARISH.value),
    )
    assert result.direction_alignment is DirectionAlignment.CONFLICT
    assert result.decision_status == "CONFLICT"
    assert result.execution_eligible is False


def test_trend_regime_never_becomes_sweep_even_with_sweep_shaped_post_session_candles():
    """Sweep must never override TREND classification (spec section 7/21) -- post_session
    candles that WOULD qualify as a sweep are irrelevant once regime==TREND, because
    route_completed_session only calls entry_2_sweep when regime is RANGE."""
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _trend_session(long=True), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert result.setup_type is SetupType.TREND
    assert result.regime.value == "TREND"


def test_neutral_bias_range_no_sweep_is_no_setup():
    rejection = _candle(6, 15, 1.1000, 1.1003, 1.0998, 1.0999)
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.NEUTRAL.value), post_session_candles=[rejection],
    )
    assert result.decision_status == "NO_SETUP"
    assert result.execution_eligible is False
    assert "NO_DIRECTION" in result.reason_codes


def test_incomplete_session_is_waiting_reference():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(n=5), 24,  # only 5 of 24 expected bars
        _bias(MarketBiasDirection.BULLISH.value),
    )
    assert result.decision_status == "WAITING_REFERENCE"
    assert result.setup_type is SetupType.NONE
    assert result.execution_eligible is False


# ---------------------------------------------------------------- skill-separation (22-26)

def test_supply_demand_context_never_changes_setup_selection():
    r1 = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
        supply_demand_context={"nearest_supply": 1.1200},
    )
    r2 = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
        supply_demand_context={"nearest_supply": 1.0500},  # different context
    )
    assert r1.setup_type == r2.setup_type
    assert r1.direction == r2.direction
    assert r1.decision_status == r2.decision_status
    assert r1.supply_demand_context != r2.supply_demand_context  # context itself does differ/pass through


def test_entry_confirmation_state_gates_execution_only_not_setup_selection():
    base_kwargs = dict(
        strategy_id="TEST", symbol="EURUSD", session_name="asian", session_date=DAY,
        session_candles=_range_session_flat(), expected_bar_count=24,
        market_bias=_bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    not_confirmed = route_daytrading_setup(**base_kwargs, entry_confirmation_state="WAITING")
    confirmed = route_daytrading_setup(**base_kwargs, entry_confirmation_state="CONFIRMED")

    assert not_confirmed.setup_type == confirmed.setup_type == SetupType.SWEEP
    assert not_confirmed.direction == confirmed.direction == Direction.LONG
    assert not_confirmed.execution_eligible is False
    assert confirmed.execution_eligible is True


def test_no_entry_confirmation_state_defaults_execution_ineligible():
    result = route_daytrading_setup(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert result.decision_status == "VALID"
    assert result.execution_eligible is False
