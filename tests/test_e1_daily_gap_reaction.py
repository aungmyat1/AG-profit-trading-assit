"""E1_DAILY_GAP_REACTION_V1 tests. Thin wrapper over `gap.py::evaluate_gap_context`
(touch vs. fill vs. reaction, spec section 5) -- no new gap detection here."""
from __future__ import annotations

import datetime as dt

from entry_confirmation.e1_daily_gap_reaction import evaluate_e1_daily_gap_reaction
from entry_confirmation.models import CandidateDirection
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc
_ORIGIN = dt.datetime(2026, 1, 4, 0, 0, tzinfo=UTC)
_TOUCH_TIME = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
_REACTION_TIME = dt.datetime(2026, 1, 6, 0, 0, tzinfo=UTC)


def _gap_zone(status=ZoneStatus.TOUCHED, low=1.0980, high=1.1000):
    return ZoneResult(symbol="EURUSD", timeframe="D1", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.BULLISH, status=status, source="test",
                       low=low, high=high, origin_time=_ORIGIN)


def _touch_candle():
    return Candle(_TOUCH_TIME, 1.1005, 1.1010, 1.0985, 1.0990)  # intersects [1.0980, 1.1000]


def _reaction_candle():
    # Large bullish candle qualifying AG_ENTRY_DISPLACEMENT_V1 against the tiny history.
    return Candle(_REACTION_TIME, 1.0990, 1.1090, 1.0988, 1.1088)


def _reaction_history():
    base = _ORIGIN - dt.timedelta(days=25)
    return [Candle(base + dt.timedelta(days=i), 1.1000, 1.1002, 1.0999, 1.10005) for i in range(20)]


def test_no_gap_zone_supplied_is_not_eligible():
    result = evaluate_e1_daily_gap_reaction("EURUSD", None)
    assert result.eligible_for_confirmation is False


def test_invalidated_gap_is_not_eligible():
    result = evaluate_e1_daily_gap_reaction("EURUSD", _gap_zone(status=ZoneStatus.INVALIDATED))
    assert result.invalidation == "GAP_INVALIDATED"
    assert result.eligible_for_confirmation is False


def test_gap_touched_only_no_reaction_is_not_eligible():
    result = evaluate_e1_daily_gap_reaction(
        "EURUSD", _gap_zone(), candidate_direction=CandidateDirection.LONG, touch_candle=_touch_candle(),
    )
    assert result.fill_status in ("GAP_TOUCHED", "GAP_FILLED")
    assert result.reaction_status == "WAITING_REACTION"
    assert result.eligible_for_confirmation is False


def test_gap_filled_and_reacted_is_eligible_for_confirmation():
    result = evaluate_e1_daily_gap_reaction(
        "EURUSD", _gap_zone(), candidate_direction=CandidateDirection.LONG, touch_candle=_touch_candle(),
        reaction_candle=_reaction_candle(), reaction_history=_reaction_history(),
    )
    assert result.reaction_status == "GAP_REACTED"
    assert result.eligible_for_confirmation is True
    assert result.direction == "LONG"
