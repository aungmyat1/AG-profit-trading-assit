"""TRADE_MANAGEMENT_V1 vs execution/ conformance tests (FIVE_SKILL_ASSISTANT_RUNTIME_V1
mission section 40-45). trade_management/ deliberately reimplements (does not import)
execution/risk.py::size_position() and overlaps with execution/validator.py's geometry
sign checks -- see trade_management/sizing.py's and TRADE_MANAGEMENT_V1_SPEC.md's own
audit table for why. These tests prove the two implementations have not silently
drifted apart. All synthetic data -- no live MT5/terminal/account required.
"""
from __future__ import annotations

from datetime import date

import pytest

from execution.risk import size_position
from execution.validator import validate_geometry
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.models import RiskConfig, StrategyConfig, TargetLeg, TradeSignal
from trade_management.geometry import evaluate_geometry
from trade_management.models import (
    GEOMETRY_INVALID_LONG_STOP,
    GEOMETRY_INVALID_LONG_TARGET,
    GEOMETRY_INVALID_SHORT_STOP,
    GEOMETRY_INVALID_SHORT_TARGET,
    GEOMETRY_VALID,
    GEOMETRY_ZERO_STOP_DISTANCE,
)
from trade_management.sizing import evaluate_sizing


def _eurusd_meta(**overrides):
    defaults = dict(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                     volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=0.00001)
    defaults.update(overrides)
    return SymbolMeta(**defaults)


def _jpy_meta(**overrides):
    defaults = dict(symbol="USDJPY", tick_size=0.001, tick_value=0.0091, contract_size=100000,
                     volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=3, point=0.001)
    defaults.update(overrides)
    return SymbolMeta(**defaults)


def _gold_meta(**overrides):
    defaults = dict(symbol="XAUUSD", tick_size=0.01, tick_value=1.0, contract_size=100,
                     volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=2, point=0.01)
    defaults.update(overrides)
    return SymbolMeta(**defaults)


# --------------------------------------------------------------------------- sizing conformance

@pytest.mark.parametrize("meta,entry,stop_loss,equity,risk_pct", [
    (_eurusd_meta(), 1.17000, 1.16750, 10000.0, 1.0),
    (_eurusd_meta(), 1.17000, 1.16990, 5000.0, 0.5),
    (_jpy_meta(), 150.000, 149.750, 10000.0, 1.0),
    (_gold_meta(), 2400.00, 2395.00, 10000.0, 1.0),
    (_gold_meta(), 2400.00, 2350.00, 25000.0, 2.0),
])
def test_sizing_conformance_ready_cases(meta, entry, stop_loss, equity, risk_pct):
    exec_volume, exec_risk_amount, exec_reason = size_position(entry, stop_loss, equity, risk_pct, meta)
    tm_result = evaluate_sizing(entry, stop_loss, equity, risk_pct, None, meta)

    assert exec_reason is None
    assert tm_result.status == "READY"
    assert tm_result.normalized_volume == pytest.approx(exec_volume, rel=1e-9)
    assert tm_result.actual_risk_amount == pytest.approx(exec_risk_amount, rel=1e-9)


def test_sizing_conformance_volume_below_min():
    meta = _eurusd_meta()
    entry, stop_loss, equity, risk_pct = 1.17000, 1.16999, 0.5, 1.0
    exec_volume, exec_risk_amount, exec_reason = size_position(entry, stop_loss, equity, risk_pct, meta)
    tm_result = evaluate_sizing(entry, stop_loss, equity, risk_pct, None, meta)

    assert exec_volume is None and exec_reason == "VOLUME_BELOW_MIN"
    assert tm_result.status == "VOLUME_BELOW_MIN"


def test_sizing_conformance_volume_above_max():
    meta = _eurusd_meta(volume_max=1.0)
    entry, stop_loss, equity, risk_pct = 1.17000, 1.16999, 1_000_000.0, 100.0
    exec_volume, exec_risk_amount, exec_reason = size_position(entry, stop_loss, equity, risk_pct, meta)
    tm_result = evaluate_sizing(entry, stop_loss, equity, risk_pct, None, meta)

    assert exec_volume is None and exec_reason == "VOLUME_ABOVE_MAX"
    assert tm_result.status == "VOLUME_ABOVE_MAX"


def test_sizing_conformance_invalid_stop_distance():
    meta = _eurusd_meta()
    exec_volume, exec_risk_amount, exec_reason = size_position(1.17000, 1.17000, 10000.0, 1.0, meta)
    assert exec_reason == "INVALID_STOP_DISTANCE"
    # trade_management's own geometry layer catches this before sizing is ever attempted --
    # semantic difference documented in TRADE_MANAGEMENT_V1_SPEC.md's audit table, not drift.


# --------------------------------------------------------------------------- geometry conformance

def _signal_and_strategy(direction: str, entry: float, stop_loss: float, take_profit: float = None):
    legs = ()
    box_high = box_low = None
    if take_profit is not None:
        legs = (TargetLeg(leg_id=1, volume_pct=1.0, target_type="OPPOSITE_SESSION_BOUNDARY"),)
        if direction == "LONG":
            box_high = take_profit
        else:
            box_low = take_profit

    signal = TradeSignal(
        signal_id="sig1", strategy_id="TEST", strategy_version="1.0", symbol="EURUSD",
        pair_id="ASIAN_LONDON", reference_session="Asian", session_date=date(2026, 1, 5),
        box_high=box_high if box_high is not None else 1.99,
        box_low=box_low if box_low is not None else 0.01,
        box_mid=1.0, regime="TREND", setup="entry_1_trend", status="SIGNAL", reason_code="OK",
        direction=direction, entry=entry, stop_loss=stop_loss, risk_distance=abs(entry - stop_loss),
    )
    strategy = StrategyConfig(
        strategy_id="TEST", strategy_name="Test", strategy_family="Test", version="1.0", status="ACTIVE",
        instruments=["EURUSD"], timeframe="M15", magic_number=1, session_pairs=(),
        risk=RiskConfig(risk_mode="FIXED_PERCENT", stop_loss_mode="FIXED", stop_loss_range_pct=0.25,
                         max_spread_allowed_pips=2.0, slippage_limit_points=10),
        entry_order_type="MARKET", total_target_r=4.0, legs=legs, max_range_pips_eurusd=25.0,
        time_invalidation="15:00", structural_invalidation="none", source_path="test",
    )
    return signal, strategy


@pytest.mark.parametrize("direction,entry,stop_loss,take_profit,expect_valid", [
    ("LONG", 1.1700, 1.1675, 1.1800, True),
    ("LONG", 1.1700, 1.1725, 1.1800, False),   # SL above entry
    ("LONG", 1.1700, 1.1675, 1.1600, False),   # target below entry
    ("SHORT", 1.1700, 1.1725, 1.1600, True),
    ("SHORT", 1.1700, 1.1675, 1.1600, False),  # SL below entry
    ("SHORT", 1.1700, 1.1725, 1.1800, False),  # target above entry
])
def test_geometry_conformance_pass_fail_classification_agrees(direction, entry, stop_loss, take_profit, expect_valid):
    signal, strategy = _signal_and_strategy(direction, entry, stop_loss, take_profit)
    exec_reason = validate_geometry(signal, strategy)
    tm_result = evaluate_geometry(direction, entry, stop_loss, take_profit)

    exec_valid = exec_reason is None
    tm_valid = tm_result.status == GEOMETRY_VALID
    assert exec_valid == expect_valid
    assert tm_valid == expect_valid
    # Both implementations must agree on PASS/FAIL classification even though their
    # reason-code vocabularies differ by design (execution/'s predates trade_management/'s
    # more granular LONG/SHORT-specific codes) -- see TRADE_MANAGEMENT_V1_SPEC.md.
    assert exec_valid == tm_valid


def test_geometry_conformance_zero_stop_distance():
    signal, strategy = _signal_and_strategy("LONG", 1.1700, 1.1700, None)
    exec_reason = validate_geometry(signal, strategy)
    tm_result = evaluate_geometry("LONG", 1.1700, 1.1700, None)

    assert exec_reason == "INVALID_STOP_DISTANCE"
    assert tm_result.status == GEOMETRY_ZERO_STOP_DISTANCE
    # Same fact (zero risk distance), different code strings -- SEMANTIC_DIFFERENCE in
    # naming only, not a classification disagreement (both reject).
