"""DUAL_DAYTRADING_WORKFLOW_V1 spec section 35: SESSION_TRADE completion dispatch --
once-per-(strategy_id, symbol, reference_session, trading_date), NO_SETUP as a valid
result, and no duplicate evaluation on repeated dispatch. Drives the real
route_daytrading_setup/route_completed_session engine with hand-built Candle sequences
(same discipline as test_daytrading_setup_router.py) -- only MarketBias is a fixture.
"""
from __future__ import annotations

import datetime as dt

from daytrading.decision.models import MarketBias, MarketBiasDirection
from daytrading_workflow.models import (
    PROPOSAL_CONFLICT,
    PROPOSAL_NO_SETUP,
    PROPOSAL_VALID,
    PROPOSAL_WAITING_CONFIRMATION,
)
from daytrading_workflow.session_workflow import SessionCompletionDispatcher, evaluate_session_completion
from daytrading_workflow.universe import load_session_universe
from strategy_engine.session import Direction, SetupType

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)
DAY_2 = dt.date(2026, 1, 6)


def _candle(hour, minute, o, h, l, c):
    from strategy_engine.session import Candle
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _bias(direction):
    return MarketBias(direction=direction, timeframe="H1")


def _range_session_flat(n=24, price=1.1000):
    return [_candle(*divmod(15 * i, 60), price, price, price, price) for i in range(n)]


def _sell_side_sweep_candle():
    return _candle(6, 15, 1.0999, 1.0999, 1.0995, 1.1002)


# --------------------------------------------------------------- evaluate_session_completion


def test_evaluate_session_completion_projects_valid_sweep_proposal():
    proposal = evaluate_session_completion(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
        entry_confirmation_state="CONFIRMED",
    )
    assert proposal.proposal_status == PROPOSAL_VALID
    assert proposal.setup_type == SetupType.SWEEP.value
    assert proposal.direction == Direction.LONG.value
    assert proposal.sweep_detected is True
    assert proposal.sweep_side == "SELL_SIDE"
    assert proposal.reference_high == 1.1000
    assert proposal.reference_low == 1.1000
    assert proposal.entry_reference is not None  # sourced from SetupDecision, never fabricated


def test_evaluate_session_completion_no_confirmation_is_waiting_confirmation():
    proposal = evaluate_session_completion(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert proposal.proposal_status == PROPOSAL_WAITING_CONFIRMATION


def test_evaluate_session_completion_no_setup_is_valid_result():
    proposal = evaluate_session_completion(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value),
    )
    assert proposal.proposal_status == PROPOSAL_NO_SETUP
    assert proposal.entry_reference is None
    assert proposal.stop_reference is None


def test_evaluate_session_completion_conflict_status():
    rejection = _candle(6, 15, 1.1000, 1.1000, 1.0997, 1.0998)
    proposal = evaluate_session_completion(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[rejection],
    )
    assert proposal.proposal_status == PROPOSAL_CONFLICT


# --------------------------------------------------------------------- dispatcher (spec 35)


def test_incomplete_session_produces_no_dispatch_cycle():
    dispatcher = SessionCompletionDispatcher()
    result = dispatcher.process_one(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(n=5), 24,
        _bias(MarketBiasDirection.BULLISH.value),
    )
    assert result is None


def test_completed_session_dispatches_once():
    dispatcher = SessionCompletionDispatcher()
    result = dispatcher.process_one(
        "TEST", "GBPUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert result is not None
    assert result.proposal_status == PROPOSAL_WAITING_CONFIRMATION


def test_repeated_dispatch_for_same_key_does_not_duplicate():
    dispatcher = SessionCompletionDispatcher()
    first = dispatcher.process_one(
        "TEST", "USDJPY", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    second = dispatcher.process_one(
        "TEST", "USDJPY", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert first is not None
    assert second is None  # already processed -- no duplicate proposal


def test_second_reference_session_is_an_independent_cycle():
    dispatcher = SessionCompletionDispatcher()
    asian = dispatcher.process_one(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    london = dispatcher.process_one(
        "TEST", "EURUSD", "london", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert asian is not None
    assert london is not None  # different reference_session -- independent key


def test_next_trading_date_allows_a_new_event():
    dispatcher = SessionCompletionDispatcher()
    day_1 = dispatcher.process_one(
        "TEST", "EURUSD", "asian", DAY, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    day_2 = dispatcher.process_one(
        "TEST", "EURUSD", "asian", DAY_2, _range_session_flat(), 24,
        _bias(MarketBiasDirection.BULLISH.value), post_session_candles=[_sell_side_sweep_candle()],
    )
    assert day_1 is not None
    assert day_2 is not None


def test_process_universe_allows_no_setup_for_some_symbols_and_setup_for_others():
    dispatcher = SessionCompletionDispatcher()
    common = dict(strategy_id="TEST", session_candles=_range_session_flat(), expected_bar_count=24)
    sessions_by_symbol = {
        "EURUSD": dict(**common, market_bias=_bias(MarketBiasDirection.BULLISH.value)),
        "GBPUSD": dict(**common, market_bias=_bias(MarketBiasDirection.BULLISH.value),
                       post_session_candles=[_sell_side_sweep_candle()], entry_confirmation_state="CONFIRMED"),
    }
    results = dispatcher.process_universe(
        ["EURUSD", "GBPUSD"], "asian", DAY, sessions_by_symbol,
    )
    assert results["EURUSD"].proposal_status == PROPOSAL_NO_SETUP
    assert results["GBPUSD"].proposal_status == PROPOSAL_VALID


def test_process_universe_skips_symbols_without_session_data():
    dispatcher = SessionCompletionDispatcher()
    results = dispatcher.process_universe(["EURUSD", "XAUUSD.crp"], "asian", DAY, {})
    assert results == {}


# --------------------------------------------------------------------------- universe (spec 7)


def test_session_universe_loads_configured_symbols_from_strategy_yaml():
    universe = load_session_universe()
    assert universe.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert "EURUSD" in universe.configured_symbols
    assert len(universe.configured_symbols) == len(set(universe.configured_symbols))
