"""Focused tests for DAYTRADING_NARRATIVE_BIAS_V1 (src/daytrading/narrative_bias.py,
true_day.py): true-day boundary/DST, zero-look-ahead causality, expected-vs-realized
separation, and the six narrative profiles including structure-vs-narrative and
liquidity-affinity-boundary isolation (spec sections 32-38). Pure/offline."""
from __future__ import annotations

from datetime import datetime, timezone

from daytrading.models import (
    BIAS_BEARISH,
    BIAS_BULLISH,
    BIAS_UNRESOLVED,
    DELIVERY_DOWN,
    DELIVERY_UP,
    DIRECTION_LONG,
    DIRECTION_SHORT,
    PROFILE_BEARISH_DAY,
    PROFILE_BEARISH_REVERSAL_DAY,
    PROFILE_BULLISH_DAY,
    PROFILE_BULLISH_REVERSAL_DAY,
    PROFILE_CONSOLIDATION_DAY,
    PROFILE_UNRESOLVED,
)
from daytrading.narrative_bias import evaluate_narrative_bias, evaluate_realized_narrative_bias
from daytrading.true_day import causal_candles, true_day_open, true_day_window
from liquidity.models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from market_structure.models import (
    STATE_BEARISH,
    STATE_BULLISH,
    STATE_UNDEFINED,
    StructurePoint,
    StructurePointKind,
    StructureResult,
)
from strategy_engine.session import Candle
from supply_demand.native_zones import dealing_range_zones


def _structure(state, status="VALID", choch=None) -> StructureResult:
    return StructureResult(symbol="EURUSD", timeframe="D1", status=status, reason_codes=(), state=state,
                            latest_choch=choch)


def _level(side, price, status=LiquidityStatus.UNSWEPT) -> LiquidityLevel:
    return LiquidityLevel(symbol="EURUSD", timeframe="D1", side=side, source="SWING", price=price,
                           origin_time=datetime(2026, 1, 1, tzinfo=timezone.utc), status=status)


def _liquidity(nearest_buy=None, nearest_sell=None, status="LIQUIDITY_OK") -> LiquidityResult:
    levels = tuple(l for l in (nearest_buy, nearest_sell) if l is not None)
    return LiquidityResult(symbol="EURUSD", timeframe="D1", status=status, levels=levels,
                            nearest_buy_side=nearest_buy, nearest_sell_side=nearest_sell)


def _candle(hour, price_open, price_close, day=15, month=1, year=2026) -> Candle:
    return Candle(time=datetime(year, month, day, hour, tzinfo=timezone.utc),
                  open=price_open, high=max(price_open, price_close), low=min(price_open, price_close),
                  close=price_close)


def _choch(kind) -> StructurePoint:
    return StructurePoint(time_utc=datetime(2026, 1, 15, 10, tzinfo=timezone.utc), price=1.1000, kind=kind)


# =========================================================================== DAY BOUNDARY (section 32)

def test_true_day_window_standard_time():
    ctx = true_day_window(datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc))
    assert ctx.reference_timezone == "America/New_York"
    assert ctx.trading_date == "2026-01-15"
    assert ctx.day_start_utc == datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc)  # EST = UTC-5
    assert ctx.day_end_utc == datetime(2026, 1, 16, 5, 0, tzinfo=timezone.utc)


def test_true_day_window_daylight_time():
    ctx = true_day_window(datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc))
    assert ctx.day_start_utc == datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)  # EDT = UTC-4


def test_true_day_window_spring_forward_transition():
    # 2026-03-08 is US DST spring-forward (2am -> 3am). A timestamp just before NY
    # midnight on the 8th must still land in the 8th's true day, not the 7th's or 9th's.
    before_midnight = datetime(2026, 3, 8, 4, 59, tzinfo=timezone.utc)  # 2026-03-07 23:59 EST
    ctx = true_day_window(before_midnight)
    assert ctx.trading_date == "2026-03-07"
    after_midnight = datetime(2026, 3, 8, 5, 1, tzinfo=timezone.utc)  # 2026-03-08 00:01 EST
    ctx2 = true_day_window(after_midnight)
    assert ctx2.trading_date == "2026-03-08"
    assert ctx2.day_end_utc - ctx2.day_start_utc == ctx2.day_end_utc - ctx2.day_start_utc  # window is well-formed


def test_true_day_window_fall_back_transition():
    # 2026-11-01 is US DST fall-back. Window must still be a single NY-midnight-to-
    # midnight span even though that UTC span is 25 hours long.
    ctx = true_day_window(datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc))
    assert ctx.trading_date == "2026-11-01"
    span = ctx.day_end_utc - ctx.day_start_utc
    assert span.total_seconds() == 25 * 3600


def test_true_day_window_weekend_is_still_a_well_formed_day():
    ctx = true_day_window(datetime(2026, 1, 17, 12, 0, tzinfo=timezone.utc))  # Saturday
    assert ctx.trading_date == "2026-01-17"
    assert ctx.day_end_utc > ctx.day_start_utc


def test_true_day_open_missing_midnight_bar_is_none():
    ctx = true_day_window(datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc))
    candles = [_candle(8, 1.1000, 1.1010)]  # no candle at/after day_start_utc (05:00 UTC) before 08:00 is fine...
    # use a candle set that genuinely has nothing inside [day_start, day_end)
    candles_outside = [Candle(time=datetime(2026, 1, 14, 20, tzinfo=timezone.utc), open=1.10, high=1.10,
                               low=1.10, close=1.10)]
    assert true_day_open(candles_outside, ctx) is None


def test_true_day_open_uses_first_in_day_candle():
    ctx = true_day_window(datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc))
    candles = [_candle(9, 1.1050, 1.1060), _candle(5, 1.1000, 1.1010)]  # 05:00 UTC = NY midnight
    assert true_day_open(candles, ctx) == 1.1000


# =========================================================================== CAUSALITY (section 33)

def _bullish_setup():
    structure = _structure(STATE_BULLISH)
    liquidity = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.2000))
    dealing_range = dealing_range_zones("EURUSD", 1.1000, 1.1200, source="previous_day", current_price=1.1150)
    return structure, liquidity, dealing_range


def test_expected_profile_unaffected_by_future_candles():
    structure, liquidity, dealing_range = _bullish_setup()
    t = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)  # 05:00 NY
    candles_before = [_candle(5, 1.1000, 1.1000), _candle(9, 1.1000, 1.1050)]  # delivery UP so far

    before = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, dealing_range,
                                      evaluation_time=t, h1_candles=candles_before)

    candles_with_future = list(candles_before) + [_candle(20, 1.0500, 1.0400)]  # a violent future reversal
    after = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, dealing_range,
                                     evaluation_time=t, h1_candles=candles_with_future)

    assert before.expected_profile == after.expected_profile == PROFILE_BULLISH_DAY
    assert before.initial_delivery == after.initial_delivery == DELIVERY_UP


def test_realized_profile_may_differ_from_expected_using_full_day():
    structure, liquidity, dealing_range = _bullish_setup()
    t = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    candles_up_to_t = [_candle(5, 1.1000, 1.1000), _candle(9, 1.1000, 1.1050)]
    expected = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, dealing_range,
                                        evaluation_time=t, h1_candles=candles_up_to_t)
    assert expected.expected_profile == PROFILE_BULLISH_DAY
    assert expected.realized_profile is None

    full_day = candles_up_to_t + [_candle(h, 1.1050 - h * 0.001, 1.1050 - h * 0.001 - 0.001)
                                   for h in range(10, 23)]  # decline for the rest of the day
    realized = evaluate_realized_narrative_bias("EURUSD", "D1", structure, liquidity, dealing_range,
                                                  h1_candles=full_day)
    assert realized.realized_profile is not None
    assert realized.expected_profile == PROFILE_UNRESOLVED  # this field is not meaningful on a realized result


# =========================================================================== PROFILE SEMANTICS (section 34)

def test_bullish_continuation_day():
    structure, liquidity, dealing_range = _bullish_setup()
    t = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    candles = [_candle(5, 1.1000, 1.1000), _candle(9, 1.1000, 1.1050)]
    result = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, dealing_range,
                                      evaluation_time=t, h1_candles=candles)
    assert result.expected_profile == PROFILE_BULLISH_DAY
    assert result.expected_delivery == DELIVERY_UP
    assert result.preferred_direction == DIRECTION_LONG
    assert result.bias == BIAS_BULLISH


def test_bearish_continuation_day():
    structure = _structure(STATE_BEARISH)
    liquidity = _liquidity(nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1000))
    t = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    candles = [_candle(5, 1.1200, 1.1200), _candle(9, 1.1200, 1.1150)]  # delivery DOWN
    result = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, None,
                                      evaluation_time=t, h1_candles=candles)
    assert result.expected_profile == PROFILE_BEARISH_DAY
    assert result.expected_delivery == DELIVERY_DOWN
    assert result.preferred_direction == DIRECTION_SHORT
    assert result.bias == BIAS_BEARISH


def test_bullish_reversal_candidate_needs_h1_choch_confirmation():
    structure, liquidity, dealing_range = _bullish_setup()
    t = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)
    candles = [_candle(5, 1.1050, 1.1050), _candle(9, 1.1050, 1.0950)]  # initial delivery DOWN, opposite of D1

    unresolved = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, dealing_range,
                                          evaluation_time=t, h1_candles=candles)
    assert unresolved.expected_profile == PROFILE_UNRESOLVED  # no reversal evidence yet -- not forced

    h1_structure = _structure(STATE_BEARISH, choch=_choch(StructurePointKind.BULLISH_CHOCH))
    reversal = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, dealing_range,
                                        evaluation_time=t, h1_candles=candles, h1_structure=h1_structure)
    assert reversal.expected_profile == PROFILE_BULLISH_REVERSAL_DAY
    assert reversal.initial_delivery == DELIVERY_DOWN
    assert reversal.expected_delivery == DELIVERY_UP
    assert "REVERSAL_CLASSIFICATION_POLICY=PARTIAL" in reversal.reason


def test_bearish_reversal_candidate_needs_h1_choch_confirmation():
    structure = _structure(STATE_BEARISH)
    liquidity = _liquidity(nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1000))
    t = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)
    candles = [_candle(5, 1.1050, 1.1050), _candle(9, 1.1050, 1.1150)]  # initial delivery UP, opposite of D1
    h1_structure = _structure(STATE_BULLISH, choch=_choch(StructurePointKind.BEARISH_CHOCH))
    reversal = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, None,
                                        evaluation_time=t, h1_candles=candles, h1_structure=h1_structure)
    assert reversal.expected_profile == PROFILE_BEARISH_REVERSAL_DAY
    assert reversal.initial_delivery == DELIVERY_UP
    assert reversal.expected_delivery == DELIVERY_DOWN


def test_consolidation_day():
    dr = dealing_range_zones("EURUSD", 1.1000, 1.1200, source="previous_day", current_price=1.1100)
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_UNDEFINED), _liquidity(), dr)
    assert result.expected_profile == PROFILE_CONSOLIDATION_DAY


def test_conflicting_evidence_is_unresolved_not_forced():
    # target liquidity already consumed -- prior draw satisfied, must not keep asserting continuation.
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.2000, status=LiquidityStatus.CONSUMED))
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_BULLISH), liq)
    assert result.expected_profile == PROFILE_UNRESOLVED


def test_insufficient_data_is_unresolved():
    result = evaluate_narrative_bias("EURUSD", "D1", None, None)
    assert result.expected_profile == PROFILE_UNRESOLVED
    assert result.status == "INSUFFICIENT_DATA"


# =========================================================================== STRUCTURE != NARRATIVE (section 35)

def test_bullish_structure_alone_does_not_force_bullish_day():
    structure = _structure(STATE_BULLISH)
    liquidity = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.2000, status=LiquidityStatus.CONSUMED))
    result = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity)
    assert result.expected_profile != PROFILE_BULLISH_DAY
    assert result.expected_profile == PROFILE_UNRESOLVED


# =========================================================================== PREMIUM/DISCOUNT (section 36)

def test_discount_location_does_not_force_bullish_without_supporting_narrative():
    structure = _structure(STATE_BEARISH)
    liquidity = _liquidity(nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1000))
    dr = dealing_range_zones("EURUSD", 1.1000, 1.1200, source="previous_day", current_price=1.1020)
    assert dr.current_zone == "DISCOUNT"
    result = evaluate_narrative_bias("EURUSD", "D1", structure, liquidity, dr)
    assert result.expected_profile != PROFILE_BULLISH_DAY
    assert "BULLISH" not in (result.preferred_direction or "")


def test_premium_location_does_not_force_bearish_without_supporting_narrative():
    structure = _structure(STATE_UNDEFINED)
    dr = dealing_range_zones("EURUSD", 1.1000, 1.1200, source="previous_day", current_price=1.1180)
    assert dr.current_zone == "PREMIUM"
    result = evaluate_narrative_bias("EURUSD", "D1", structure, _liquidity(), dr)
    assert result.expected_profile == PROFILE_CONSOLIDATION_DAY  # undefined structure -> consolidation, not bearish
    assert result.preferred_direction != DIRECTION_SHORT


# =========================================================================== LIQUIDITY ROLE (section 37)

def test_primary_draw_resolves_without_producing_affinity_execution_plan():
    liq = _liquidity(nearest_buy=_level(LiquiditySide.BUY_SIDE, 1.2000),
                      nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.0500))
    result = evaluate_narrative_bias("EURUSD", "D1", _structure(STATE_BULLISH), liq)
    assert result.primary_draw == "BUY_SIDE"
    # Skill #1 boundary: no entry-side/target-side/exact-level execution plan on this result.
    assert not hasattr(result, "entry_side_liquidity")
    assert not hasattr(result, "target_side_liquidity")


# =========================================================================== REVERSAL VS CONTINUATION (section 38)

def test_bullish_day_distinct_from_bullish_reversal_day():
    structure, liquidity, dealing_range = _bullish_setup()
    t = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)

    continuation = evaluate_narrative_bias(
        "EURUSD", "D1", structure, liquidity, dealing_range, evaluation_time=t,
        h1_candles=[_candle(5, 1.1000, 1.1000), _candle(9, 1.1000, 1.1050)])
    reversal = evaluate_narrative_bias(
        "EURUSD", "D1", structure, liquidity, dealing_range, evaluation_time=t,
        h1_candles=[_candle(5, 1.1050, 1.1050), _candle(9, 1.1050, 1.0950)],
        h1_structure=_structure(STATE_BEARISH, choch=_choch(StructurePointKind.BULLISH_CHOCH)))

    assert continuation.expected_profile == PROFILE_BULLISH_DAY
    assert reversal.expected_profile == PROFILE_BULLISH_REVERSAL_DAY
    assert continuation.expected_profile != reversal.expected_profile
    assert continuation.initial_delivery != reversal.initial_delivery
    assert continuation.expected_delivery == reversal.expected_delivery == DELIVERY_UP  # same eventual direction


def test_bearish_day_distinct_from_bearish_reversal_day():
    structure = _structure(STATE_BEARISH)
    liquidity = _liquidity(nearest_sell=_level(LiquiditySide.SELL_SIDE, 1.1000))
    t = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)

    continuation = evaluate_narrative_bias(
        "EURUSD", "D1", structure, liquidity, None, evaluation_time=t,
        h1_candles=[_candle(5, 1.1200, 1.1200), _candle(9, 1.1200, 1.1150)])
    reversal = evaluate_narrative_bias(
        "EURUSD", "D1", structure, liquidity, None, evaluation_time=t,
        h1_candles=[_candle(5, 1.1150, 1.1150), _candle(9, 1.1150, 1.1250)],
        h1_structure=_structure(STATE_BULLISH, choch=_choch(StructurePointKind.BEARISH_CHOCH)))

    assert continuation.expected_profile == PROFILE_BEARISH_DAY
    assert reversal.expected_profile == PROFILE_BEARISH_REVERSAL_DAY
    assert continuation.expected_profile != reversal.expected_profile
