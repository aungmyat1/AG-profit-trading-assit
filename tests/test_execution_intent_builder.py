"""Tests for execution.intent_builder / risk / validator: SIGNAL -> TradeIntent ->
READY_FOR_ORDER_CHECK, using deterministic mocked broker metadata (no MT5 connection
needed)."""
from __future__ import annotations

import datetime as dt

import pytest

from execution import STATUS_READY, build_intent
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.loader import load_strategy
from strategy_engine.models import RiskConfig, StrategyConfig, TargetLeg, TradeSignal

DAY = dt.date(2026, 1, 5)


def _strategy(entry_order_type="MARKET", target_type="OPPOSITE_SESSION_BOUNDARY") -> StrategyConfig:
    return StrategyConfig(
        strategy_id="TEST_STRAT", strategy_name="Test", strategy_family="Test", version="0.0.1",
        status="ACTIVE_INCUBATION", instruments=("EURUSD",), timeframe="M15", magic_number=777001,
        session_pairs=(),
        risk=RiskConfig("FIXED_PERCENT_OR_CONTRACT", "PERCENT_OF_SESSION_RANGE", 0.25, 2.0, 10),
        entry_order_type=entry_order_type, total_target_r=5.0,
        legs=(TargetLeg(leg_id=1, volume_pct=0.75, target_type=target_type),),
        max_range_pips_eurusd=25.0, time_invalidation="15:00 GMT", structural_invalidation="x",
        source_path="test",
    )


def _signal(direction="LONG", entry=1.1000, stop_loss=1.0990, box_high=1.1050, box_low=1.0950, status="SIGNAL"):
    return TradeSignal(
        signal_id="TEST_STRAT:P1:EURUSD:2026-01-05", strategy_id="TEST_STRAT", strategy_version="0.0.1",
        symbol="EURUSD", pair_id="P1", reference_session="Asian", session_date=DAY,
        box_high=box_high, box_low=box_low, box_mid=(box_high + box_low) / 2,
        regime="RANGE", setup="SWEEP", status=status, reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction=direction, entry=entry, stop_loss=stop_loss, risk_distance=abs(entry - stop_loss),
    )


def _symbol_meta(**overrides) -> SymbolMeta:
    defaults = dict(
        symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
        volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
    )
    defaults.update(overrides)
    return SymbolMeta(**defaults)


# --------------------------------------------------------------------------- happy path

def test_long_sizing_reaches_ready_for_order_check():
    result = build_intent(_signal(direction="LONG"), _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == STATUS_READY
    assert result.intent.volume == pytest.approx(1.00)
    assert result.intent.risk_amount == pytest.approx(100.0)
    assert result.intent.take_profit == pytest.approx(1.1050)  # box_high, OPPOSITE_SESSION_BOUNDARY
    assert result.intent.signal_id == "TEST_STRAT:P1:EURUSD:2026-01-05"


def test_short_sizing_reaches_ready_for_order_check():
    signal = _signal(direction="SHORT", entry=1.1000, stop_loss=1.1010)
    result = build_intent(signal, _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == STATUS_READY
    assert result.intent.direction == "SHORT"
    assert result.intent.take_profit == pytest.approx(1.0950)  # box_low


# --------------------------------------------------------------------------- rejections

def test_non_signal_status_rejected():
    result = build_intent(_signal(status="NO_TRADE"), _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == "NOT_A_SIGNAL"
    assert result.intent is None


def test_invalid_long_geometry_stop_above_entry_rejected():
    signal = _signal(direction="LONG", entry=1.1000, stop_loss=1.1010)  # wrong side for LONG
    result = build_intent(signal, _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == "INVALID_ENTRY_GEOMETRY"


def test_zero_stop_distance_rejected():
    signal = _signal(entry=1.1000, stop_loss=1.1000)
    result = build_intent(signal, _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == "INVALID_STOP_DISTANCE"


def test_ambiguous_entry_order_type_rejected():
    result = build_intent(_signal(), _strategy(entry_order_type="MARKET_OR_LIMIT"), equity=10_000.0,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == "ENTRY_EXECUTION_UNDEFINED"


def test_missing_account_equity_rejected():
    result = build_intent(_signal(), _strategy(), equity=None,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == "ACCOUNT_DATA_MISSING"


def test_missing_symbol_meta_rejected():
    result = build_intent(_signal(), _strategy(), equity=10_000.0,
                           symbol_meta=None, risk_per_trade_pct=1.0)
    assert result.status == "SYMBOL_METADATA_MISSING"


def test_invalid_symbol_meta_tick_value_rejected():
    result = build_intent(_signal(), _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(tick_value=0.0), risk_per_trade_pct=1.0)
    assert result.status == "SYMBOL_METADATA_MISSING"


def test_invalid_risk_config_rejected():
    result = build_intent(_signal(), _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(), risk_per_trade_pct=0.0)
    assert result.status == "INVALID_RISK_CONFIG"


# --------------------------------------------------------------------------- sizing math

def test_volume_step_normalization_rounds_down():
    # loss_per_lot = 0.0009 * 100000 = 90; budget = 10_000 * 1% = 100; raw = 1.1111...
    signal = _signal(entry=1.1000, stop_loss=1.0991)  # 0.0009 stop distance
    result = build_intent(signal, _strategy(), equity=10_000.0,
                           symbol_meta=_symbol_meta(volume_step=0.1), risk_per_trade_pct=1.0)
    assert result.status == STATUS_READY
    assert result.intent.volume == pytest.approx(1.1)  # floored from 1.1111... to the 0.1 step
    assert result.intent.risk_amount == pytest.approx(1.1 * 90.0)
    assert result.intent.risk_amount < 100.0  # never exceeds the risk budget


def test_risk_budget_too_small_for_minimum_volume_rejected():
    signal = _signal(entry=1.1000, stop_loss=1.0990)  # loss_per_lot = 100
    result = build_intent(signal, _strategy(), equity=10.0,  # budget = 0.10
                           symbol_meta=_symbol_meta(volume_min=0.01, volume_step=0.01), risk_per_trade_pct=1.0)
    assert result.status == "VOLUME_BELOW_MIN"


def test_volume_above_broker_max_rejected():
    signal = _signal(entry=1.1000, stop_loss=1.0999)  # tiny 0.0001 stop distance -> huge raw volume
    result = build_intent(signal, _strategy(), equity=1_000_000.0, symbol_meta=_symbol_meta(volume_max=5.0),
                           risk_per_trade_pct=5.0)
    assert result.status == "VOLUME_ABOVE_MAX"


# --------------------------------------------------------------------------- real registered strategy

def test_real_strategy_config_is_ambiguous_on_entry_order_type():
    """Documents a known gap (strategies/STRATEGY_LEDGER.md 'Open gaps'): the registered
    strategy declares entry_order_type: MARKET_OR_LIMIT, which is not a single
    executable order type, so it cannot reach READY_FOR_ORDER_CHECK until fixed."""
    strategy = load_strategy("strategies/ST_ASIAN_SWEEP_5R_V1.yaml")
    assert strategy.entry_order_type == "MARKET_OR_LIMIT"

    result = build_intent(_signal(), strategy, equity=10_000.0, symbol_meta=_symbol_meta(), risk_per_trade_pct=1.0)
    assert result.status == "ENTRY_EXECUTION_UNDEFINED"
