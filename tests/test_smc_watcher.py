"""DUAL_DAYTRADING_WORKFLOW_V1 spec sections 36-40: E1/E2/E3 condition adapters,
OR-routing/consolidation, deduplication, and the M5 handoff. Builds real GapContext/
POIContext/LiquidityLevel evidence via the existing entry_confirmation.gap/poi and
liquidity primitives (same discipline as test_entry_confirmation_v2.py) -- only the
supply_demand ZoneResult / liquidity LiquidityLevel inputs are hand-built fixtures.
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.gap import evaluate_gap_context
from entry_confirmation.models import CandidateDirection
from entry_confirmation.poi import evaluate_poi_context
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from smc_watcher.conditions import evaluate_e1_condition, evaluate_e2_condition, evaluate_e3_condition
from smc_watcher.models import (
    ALERT_STATE_WAITING_M5_CONFIRMATION,
    STATE_INVALIDATED,
    STATE_POI_TOUCHED,
    STATE_REACTED,
    STATE_RECLAIMED,
    STATE_WATCHING,
)
from smc_watcher.watcher import SMCConditionWatcher
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc


def _candle(hour, minute, o, h, l, c):
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _gap_zone(status=ZoneStatus.FRESH, low=1.0950, high=1.1000):
    return ZoneResult(
        symbol="EURUSD", timeframe="D1", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
        direction=ZoneDirection.BULLISH, status=status, source="test", low=low, high=high,
    )


def _strong_bull_reaction_candle():
    return _candle(11, 0, 1.0975, 1.1030, 1.0973, 1.1028)


def _flat_reaction_history():
    # 20 flat prior candles -> tiny median body, so the reaction candle above qualifies
    # easily under AG_ENTRY_DISPLACEMENT_V1 (same fixture discipline as
    # test_entry_confirmation_v2.py::test_gap_reacted_requires_qualifying_displacement).
    return tuple(
        _candle(9, m, 1.0975, 1.0977, 1.0974, 1.09755) for m in range(20)
    )


# ------------------------------------------------------------------------------------ E1


def test_e1_no_gap_is_watching():
    result = evaluate_e1_condition(None)
    assert result.state == STATE_WATCHING
    assert result.triggered is False


def test_e1_untouched_gap_is_watching():
    gap_context = evaluate_gap_context(_gap_zone())
    result = evaluate_e1_condition(gap_context)
    assert result.state == STATE_WATCHING
    assert result.triggered is False


def test_e1_touch_without_reaction_does_not_trigger():
    zone = _gap_zone()
    touch = _candle(6, 0, 1.0975, 1.0980, 1.0970, 1.0978)  # intersects [1.0950, 1.1000], no reaction supplied
    gap_context = evaluate_gap_context(zone, touch_candle=touch)
    result = evaluate_e1_condition(gap_context)
    assert result.triggered is False
    assert result.state in ("TOUCHED", "FILLED")


def test_e1_gap_fill_and_reaction_triggers():
    zone = _gap_zone()
    touch = _candle(6, 0, 1.0975, 1.0980, 1.0970, 1.0978)
    reaction = _strong_bull_reaction_candle()
    gap_context = evaluate_gap_context(
        zone, touch_candle=touch, reaction_candle=reaction, reaction_history=_flat_reaction_history(),
        candidate_direction=CandidateDirection.LONG,
    )
    result = evaluate_e1_condition(gap_context)
    assert result.state == STATE_REACTED
    assert result.triggered is True


def test_e1_same_condition_polled_twice_via_watcher_yields_one_alert():
    zone = _gap_zone()
    touch = _candle(6, 0, 1.0975, 1.0980, 1.0970, 1.0978)
    reaction = _strong_bull_reaction_candle()
    gap_context = evaluate_gap_context(
        zone, touch_candle=touch, reaction_candle=reaction, reaction_history=_flat_reaction_history(),
        candidate_direction=CandidateDirection.LONG,
    )
    e1_result = evaluate_e1_condition(gap_context)

    watcher = SMCConditionWatcher()
    first = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e1_result=e1_result)
    second = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e1_result=e1_result)
    assert first is not None
    assert second is None


# ------------------------------------------------------------------------------------ E2


def _poi_zone(status=ZoneStatus.TOUCHED):
    return ZoneResult(
        symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
        direction=ZoneDirection.BULLISH, status=status, source="test", low=1.0900, high=1.0950,
    )


def test_e2_no_poi_is_watching():
    result = evaluate_e2_condition(None)
    assert result.state == STATE_WATCHING


def test_e2_fresh_poi_is_watching():
    poi_context = evaluate_poi_context(_poi_zone(ZoneStatus.FRESH))
    result = evaluate_e2_condition(poi_context)
    assert result.state == STATE_WATCHING


def test_e2_touched_without_caller_assertion_fails_closed():
    poi_context = evaluate_poi_context(_poi_zone(ZoneStatus.TOUCHED))
    result = evaluate_e2_condition(poi_context)
    assert result.state == STATE_POI_TOUCHED
    assert result.triggered is False
    assert "E2_REACTION_RULE_UNDEFINED" in result.reason_codes


def test_e2_touched_with_caller_asserted_reaction_triggers():
    poi_context = evaluate_poi_context(_poi_zone(ZoneStatus.TOUCHED))
    reaction_time = dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC)
    result = evaluate_e2_condition(poi_context, poi_reaction_time=reaction_time, poi_reacted=True)
    assert result.state == STATE_REACTED
    assert result.triggered is True
    assert "CALLER_ASSERTED_POI_REACTION" in result.reason_codes


def test_e2_invalidated_poi_never_alerts():
    poi_context = evaluate_poi_context(_poi_zone(ZoneStatus.INVALIDATED))
    result = evaluate_e2_condition(poi_context, poi_reaction_time=dt.datetime(2026, 1, 5, tzinfo=UTC), poi_reacted=True)
    assert result.state == STATE_INVALIDATED
    assert result.triggered is False


# ------------------------------------------------------------------------------------ E3


def _sweep_level(status=LiquidityStatus.UNSWEPT, side=LiquiditySide.SELL_SIDE, sweep_time=None):
    return LiquidityLevel(
        symbol="EURUSD", timeframe="M15", side=side, source="ASIAN_LOW", price=1.1000,
        origin_time=dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), status=status, sweep_time=sweep_time,
    )


def test_e3_no_level_is_watching():
    result = evaluate_e3_condition(None)
    assert result.state == STATE_WATCHING


def test_e3_unswept_is_watching():
    result = evaluate_e3_condition(_sweep_level())
    assert result.state == STATE_WATCHING
    assert result.triggered is False


def test_e3_sell_side_sweep_triggers_long_implication():
    sweep_time = dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)
    level = _sweep_level(status=LiquidityStatus.RECLAIMED, side=LiquiditySide.SELL_SIDE, sweep_time=sweep_time)
    result = evaluate_e3_condition(level)
    assert result.state == STATE_RECLAIMED
    assert result.triggered is True
    assert result.directional_implication == "LONG"


def test_e3_buy_side_sweep_triggers_short_implication():
    sweep_time = dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)
    level = _sweep_level(status=LiquidityStatus.RECLAIMED, side=LiquiditySide.BUY_SIDE, sweep_time=sweep_time)
    result = evaluate_e3_condition(level)
    assert result.triggered is True
    assert result.directional_implication == "SHORT"


def test_e3_repeated_same_sweep_via_watcher_yields_one_alert():
    sweep_time = dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)
    level = _sweep_level(status=LiquidityStatus.RECLAIMED, side=LiquiditySide.SELL_SIDE, sweep_time=sweep_time)
    e3_result = evaluate_e3_condition(level)

    watcher = SMCConditionWatcher()
    first = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e3_result=e3_result)
    second = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e3_result=e3_result)
    assert first is not None
    assert second is None


# -------------------------------------------------------------------------- OR routing


def test_all_false_yields_no_alert():
    watcher = SMCConditionWatcher()
    e1 = evaluate_e1_condition(None)
    e2 = evaluate_e2_condition(None)
    e3 = evaluate_e3_condition(None)
    alert = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e1_result=e1, e2_result=e2, e3_result=e3)
    assert alert is None


def test_e3_only_triggers_alert():
    sweep_time = dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)
    level = _sweep_level(status=LiquidityStatus.RECLAIMED, side=LiquiditySide.SELL_SIDE, sweep_time=sweep_time)
    e3 = evaluate_e3_condition(level)
    watcher = SMCConditionWatcher()
    alert = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert alert is not None
    assert alert.triggered_conditions == ("E3",)
    assert alert.execution_eligible is False
    assert alert.alert_state == ALERT_STATE_WAITING_M5_CONFIRMATION


def test_e1_and_e3_simultaneously_gives_one_consolidated_alert():
    zone = _gap_zone()
    touch = _candle(6, 0, 1.0975, 1.0980, 1.0970, 1.0978)
    reaction = _strong_bull_reaction_candle()
    gap_context = evaluate_gap_context(
        zone, touch_candle=touch, reaction_candle=reaction, reaction_history=_flat_reaction_history(),
        candidate_direction=CandidateDirection.LONG,
    )
    e1 = evaluate_e1_condition(gap_context)

    sweep_time = dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)
    level = _sweep_level(status=LiquidityStatus.RECLAIMED, side=LiquiditySide.SELL_SIDE, sweep_time=sweep_time)
    e3 = evaluate_e3_condition(level)

    watcher = SMCConditionWatcher()
    alert = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e1_result=e1, e3_result=e3)
    assert alert is not None
    assert set(alert.triggered_conditions) == {"E1", "E3"}
    assert alert.execution_eligible is False


# -------------------------------------------------------------------------- M5 handoff


def test_m5_unavailable_stays_waiting_and_never_fabricates_confirmation():
    from entry_confirmation.models import EntryConfirmationRequest

    sweep_time = dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)
    level = _sweep_level(status=LiquidityStatus.RECLAIMED, side=LiquiditySide.SELL_SIDE, sweep_time=sweep_time)
    e3 = evaluate_e3_condition(level)
    watcher = SMCConditionWatcher()
    alert = watcher.evaluate("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    m5_request = EntryConfirmationRequest(symbol="EURUSD", timeframe="M5")  # no confirmations requested
    advanced = SMCConditionWatcher.advance_with_m5_confirmation(alert, m5_request)
    assert advanced.confirmation_state == "INDETERMINATE"
    assert advanced.execution_eligible is False
