"""Tests for historical_replay.fill_simulator (historical-validation continuation spec
sections 30-38, 57): READY != FILLED, invalidation-before-fill, same-bar ambiguity, and
the honest UNFILLED_AS_OF_DATA_END outcome (no invented entry-expiry rule).
"""
from __future__ import annotations

import datetime as dt

from historical_replay.fill_simulator import (
    STATUS_FILLED,
    STATUS_INTRABAR_AMBIGUOUS,
    STATUS_INVALIDATED_BEFORE_FILL,
    STATUS_NO_ENTRY_CONTRACT,
    STATUS_UNFILLED_AS_OF_DATA_END,
    simulate_fill,
)
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _candle(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c)


READY_TIME = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


def test_ready_but_never_filled_reports_unfilled_as_of_data_end():
    """The exact scenario from spec section 33: setup becomes READY, price never
    returns to the entry array -- must NOT be counted as a trade."""
    candles = [
        _candle(READY_TIME + dt.timedelta(minutes=5 * i), 1.20, 1.201, 1.199, 1.2005)
        for i in range(10)
    ]  # price stays at 1.20, entry zone is far away at 1.10-1.11
    result = simulate_fill(
        "SETUP-1", "E2M1", "LONG", READY_TIME,
        entry_low=1.10, entry_high=1.11, entry_reference=None, invalidation_price=1.05,
        forward_candles=candles,
    )
    assert result.status == STATUS_UNFILLED_AS_OF_DATA_END
    assert result.fill_time is None


def test_price_returns_to_entry_zone_fills():
    candles = [
        _candle(READY_TIME, 1.20, 1.201, 1.199, 1.2005),
        _candle(READY_TIME + dt.timedelta(minutes=5), 1.15, 1.151, 1.105, 1.108),  # dips into 1.10-1.11 zone
    ]
    result = simulate_fill(
        "SETUP-2", "E2M1", "LONG", READY_TIME,
        entry_low=1.10, entry_high=1.11, entry_reference=None, invalidation_price=1.05,
        forward_candles=candles,
    )
    assert result.status == STATUS_FILLED
    assert result.fill_time == candles[1].time


def test_invalidated_before_fill():
    """Spec section 34: setup invalidates while still waiting for entry -- never filled."""
    candles = [
        _candle(READY_TIME, 1.20, 1.201, 1.199, 1.2005),
        _candle(READY_TIME + dt.timedelta(minutes=5), 1.06, 1.065, 1.04, 1.05),  # gaps below entry zone, crashes through invalidation (1.05) for LONG
    ]
    result = simulate_fill(
        "SETUP-3", "E2M1", "LONG", READY_TIME,
        entry_low=1.10, entry_high=1.11, entry_reference=None, invalidation_price=1.05,
        forward_candles=candles,
    )
    assert result.status == STATUS_INVALIDATED_BEFORE_FILL
    assert result.invalidation_time == candles[1].time


def test_same_bar_entry_and_invalidation_is_ambiguous():
    """Spec sections 36/58: one bar's OHLC contains both entry and invalidation --
    ordering unknown from M5 OHLC alone -- must be classified AMBIGUOUS, never assumed
    favorable."""
    candles = [
        _candle(READY_TIME, 1.20, 1.201, 1.199, 1.2005),
        _candle(READY_TIME + dt.timedelta(minutes=5), 1.108, 1.15, 1.04, 1.06),  # wick touches both 1.10-1.11 entry AND below 1.05 invalidation
    ]
    result = simulate_fill(
        "SETUP-4", "E2M1", "LONG", READY_TIME,
        entry_low=1.10, entry_high=1.11, entry_reference=None, invalidation_price=1.05,
        forward_candles=candles,
    )
    assert result.status == STATUS_INTRABAR_AMBIGUOUS


def test_missing_entry_contract_reports_no_entry_contract():
    result = simulate_fill(
        "SETUP-5", "E3M3", "SHORT", READY_TIME,
        entry_low=None, entry_high=None, entry_reference=None, invalidation_price=1.20,
        forward_candles=[],
    )
    assert result.status == STATUS_NO_ENTRY_CONTRACT


def test_single_price_entry_reference_for_m3_style_entries():
    """M3 exposes only a single entry_level, no range (see proposals.gate._entry_range's
    own documented limitation) -- fill simulation must still work off that single
    price."""
    candles = [
        _candle(READY_TIME, 1.20, 1.205, 1.199, 1.2005),
        _candle(READY_TIME + dt.timedelta(minutes=5), 1.195, 1.20, 1.15, 1.16),  # wick touches 1.18 exactly
    ]
    result = simulate_fill(
        "SETUP-6", "E3M3", "SHORT", READY_TIME,
        entry_low=None, entry_high=None, entry_reference=1.18, invalidation_price=1.25,
        forward_candles=candles,
    )
    assert result.status == STATUS_FILLED
    assert result.fill_price == 1.18


def test_short_direction_invalidation_is_above_not_below():
    candles = [
        _candle(READY_TIME, 1.20, 1.201, 1.199, 1.2005),
        _candle(READY_TIME + dt.timedelta(minutes=5), 1.24, 1.26, 1.23, 1.25),  # spikes above invalidation for SHORT
    ]
    result = simulate_fill(
        "SETUP-7", "E3M3", "SHORT", READY_TIME,
        entry_low=1.10, entry_high=1.11, entry_reference=None, invalidation_price=1.22,
        forward_candles=candles,
    )
    assert result.status == STATUS_INVALIDATED_BEFORE_FILL
