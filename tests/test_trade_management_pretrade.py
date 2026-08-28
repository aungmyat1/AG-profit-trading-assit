"""Tests for TRADE_MANAGEMENT_V1 (geometry/sizing/position_state/pretrade_engine).
Deterministic-fact tests only. No MT5 connection needed -- SymbolMeta is hand-built."""
from __future__ import annotations

import pytest

from mt5.symbol_resolver import SymbolMeta
from trade_management.geometry import evaluate_geometry
from trade_management.models import (
    ADVISORY_BREAKEVEN_ELIGIBLE,
    ADVISORY_HOLD,
    ADVISORY_INSUFFICIENT_DATA,
    ADVISORY_NOT_REQUESTED,
    ADVISORY_TARGET_REACHED,
    GEOMETRY_INVALID_DIRECTION,
    GEOMETRY_INVALID_LONG_STOP,
    GEOMETRY_INVALID_LONG_TARGET,
    GEOMETRY_INVALID_SHORT_STOP,
    GEOMETRY_INVALID_SHORT_TARGET,
    GEOMETRY_VALID,
    GEOMETRY_ZERO_STOP_DISTANCE,
    OVERALL_BLOCKED,
    OVERALL_READY,
    SIZING_ACCOUNT_DATA_MISSING,
    SIZING_INVALID_RISK_CONFIG,
    SIZING_NOT_REQUESTED,
    SIZING_READY,
    SIZING_RISK_LIMIT_EXCEEDED,
    SIZING_SYMBOL_METADATA_MISSING,
    SIZING_VOLUME_ABOVE_MAX,
    SIZING_VOLUME_BELOW_MIN,
    ManagementPolicy,
    TradeManagementRequest,
)
from trade_management.position_state import evaluate_position_state
from trade_management.pretrade_engine import evaluate_trade_management
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


# --------------------------------------------------------------------------- geometry

def test_valid_long_geometry():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, 1.1800)
    assert g.status == GEOMETRY_VALID
    assert g.rr_multiple == pytest.approx(4.0)


def test_invalid_long_stop_above_entry():
    g = evaluate_geometry("LONG", 1.1700, 1.1725, 1.1800)
    assert g.status == GEOMETRY_INVALID_LONG_STOP


def test_invalid_long_target_below_entry():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, 1.1600)
    assert g.status == GEOMETRY_INVALID_LONG_TARGET


def test_valid_short_geometry():
    g = evaluate_geometry("SHORT", 1.1700, 1.1725, 1.1600)
    assert g.status == GEOMETRY_VALID
    assert g.rr_multiple == pytest.approx(4.0)


def test_invalid_short_stop_below_entry():
    g = evaluate_geometry("SHORT", 1.1700, 1.1675, 1.1600)
    assert g.status == GEOMETRY_INVALID_SHORT_STOP


def test_invalid_short_target_above_entry():
    g = evaluate_geometry("SHORT", 1.1700, 1.1725, 1.1800)
    assert g.status == GEOMETRY_INVALID_SHORT_TARGET


def test_zero_stop_distance():
    g = evaluate_geometry("LONG", 1.1700, 1.1700, 1.1800)
    assert g.status == GEOMETRY_ZERO_STOP_DISTANCE


def test_equal_entry_and_tp_is_invalid_target():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, 1.1700)
    assert g.status == GEOMETRY_INVALID_LONG_TARGET


def test_missing_tp_is_valid_geometry_without_rr():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, None)
    assert g.status == GEOMETRY_VALID
    assert g.rr_multiple is None
    assert g.reward_distance_price is None


def test_invalid_direction_string():
    g = evaluate_geometry("UP", 1.1700, 1.1675, 1.1800)
    assert g.status == GEOMETRY_INVALID_DIRECTION


# --------------------------------------------------------------------------- stop distance / conventions

def test_stop_distance_points_forex():
    g = evaluate_geometry("LONG", 1.17000, 1.16750, symbol_meta=_eurusd_meta())
    assert g.stop_distance_points == pytest.approx(250.0, rel=1e-6)


def test_stop_distance_points_jpy():
    g = evaluate_geometry("LONG", 150.000, 149.750, symbol_meta=_jpy_meta())
    assert g.stop_distance_points == pytest.approx(250.0, rel=1e-6)


def test_stop_distance_points_gold():
    g = evaluate_geometry("LONG", 2400.00, 2395.00, symbol_meta=_gold_meta())
    assert g.stop_distance_points == pytest.approx(500.0, rel=1e-6)


def test_stop_distance_points_none_without_symbol_meta():
    g = evaluate_geometry("LONG", 1.1700, 1.1675)
    assert g.stop_distance_points is None


# --------------------------------------------------------------------------- risk budget

def test_sizing_one_percent_of_equity():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, 1.0, None, _eurusd_meta())
    assert s.status == SIZING_READY
    assert s.requested_risk_amount == pytest.approx(100.0)


def test_sizing_fractional_risk_percent():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, 0.25, None, _eurusd_meta())
    assert s.requested_risk_amount == pytest.approx(25.0)


def test_sizing_explicit_risk_amount():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, None, 50.0, _eurusd_meta())
    assert s.status == SIZING_READY
    assert s.requested_risk_amount == pytest.approx(50.0)


def test_sizing_requested_risk_above_policy_is_rejected():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, 2.0, None, _eurusd_meta(), max_risk_percent=1.0)
    assert s.status == SIZING_RISK_LIMIT_EXCEEDED


def test_sizing_missing_equity_fails_closed():
    s = evaluate_sizing(1.17000, 1.16750, None, 1.0, None, _eurusd_meta())
    assert s.status == SIZING_ACCOUNT_DATA_MISSING


def test_sizing_zero_equity_fails_closed():
    s = evaluate_sizing(1.17000, 1.16750, 0.0, 1.0, None, _eurusd_meta())
    assert s.status == SIZING_ACCOUNT_DATA_MISSING


def test_sizing_negative_risk_percent_is_invalid():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, -1.0, None, _eurusd_meta())
    assert s.status == SIZING_INVALID_RISK_CONFIG


def test_sizing_no_risk_info_is_invalid_config():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, None, None, _eurusd_meta())
    assert s.status == SIZING_INVALID_RISK_CONFIG


# --------------------------------------------------------------------------- position sizing (tick-based)

def test_sizing_known_tick_value_and_size_raw_lot():
    # Matches the mission's own worked Example 1: risk $100, loss/lot $250 -> 0.40 lots.
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, 1.0, None, _eurusd_meta())
    assert s.loss_per_lot == pytest.approx(250.0, rel=1e-6)
    assert s.raw_volume == pytest.approx(0.40, rel=1e-6)
    assert s.normalized_volume == pytest.approx(0.40)


def test_sizing_small_stop_larger_volume():
    s = evaluate_sizing(1.17000, 1.16990, 10000.0, 1.0, None, _eurusd_meta())
    assert s.raw_volume > 0.40


def test_sizing_large_stop_smaller_volume():
    s = evaluate_sizing(1.17000, 1.15000, 10000.0, 1.0, None, _eurusd_meta())
    assert s.raw_volume < 0.40


def test_sizing_zero_stop_is_unavailable():
    s = evaluate_sizing(1.17000, 1.17000, 10000.0, 1.0, None, _eurusd_meta())
    assert s.status not in (SIZING_READY,)


def test_sizing_missing_symbol_meta_fails_closed():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, 1.0, None, None)
    assert s.status == SIZING_SYMBOL_METADATA_MISSING


def test_sizing_non_forex_symbol_gold():
    s = evaluate_sizing(2400.00, 2395.00, 10000.0, 1.0, None, _gold_meta())
    assert s.status == SIZING_READY
    assert s.loss_per_lot == pytest.approx(5.00 / 0.01 * 1.0, rel=1e-6)


# --------------------------------------------------------------------------- volume normalization

def test_normalization_exact_valid_step():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, 1.0, None, _eurusd_meta(volume_step=0.10))
    assert s.normalized_volume == pytest.approx(0.40)


def test_normalization_rounds_down_never_up():
    # raw_volume ~0.037 with volume_min 0.01, step 0.01 -> floors to 0.03, never 0.04.
    s = evaluate_sizing(1.17000, 1.16999625, 1000.0, 1.0, None, _eurusd_meta())
    assert s.status == SIZING_READY
    assert s.normalized_volume <= s.raw_volume + 1e-9


def test_normalization_below_min_is_size_unavailable():
    s = evaluate_sizing(1.17000, 1.16999, 0.5, 1.0, None, _eurusd_meta())
    assert s.status == SIZING_VOLUME_BELOW_MIN


def test_normalization_above_max_is_rejected_not_capped():
    s = evaluate_sizing(1.17000, 1.16999, 1_000_000.0, 100.0, None, _eurusd_meta(volume_max=1.0))
    assert s.status == SIZING_VOLUME_ABOVE_MAX


def test_normalization_actual_risk_after_rounding():
    s = evaluate_sizing(1.17000, 1.16750, 10000.0, 1.0, None, _eurusd_meta())
    assert s.actual_risk_amount == pytest.approx(100.0, rel=1e-6)
    assert s.actual_risk_percent == pytest.approx(1.0, rel=1e-6)


# --------------------------------------------------------------------------- RR geometry

def test_rr_long_1r():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, 1.1725)
    assert g.rr_multiple == pytest.approx(1.0)


def test_rr_long_4r():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, 1.1800)
    assert g.rr_multiple == pytest.approx(4.0)


def test_rr_short_1r():
    g = evaluate_geometry("SHORT", 1.1700, 1.1725, 1.1675)
    assert g.rr_multiple == pytest.approx(1.0)


def test_rr_short_4r():
    g = evaluate_geometry("SHORT", 1.1700, 1.1725, 1.1600)
    assert g.rr_multiple == pytest.approx(4.0)


def test_rr_tp_absent_is_none():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, None)
    assert g.rr_multiple is None


def test_rr_invalid_target_short_circuits_before_rr():
    g = evaluate_geometry("LONG", 1.1700, 1.1675, 1.1600)
    assert g.rr_multiple is None
    assert g.status == GEOMETRY_INVALID_LONG_TARGET


# --------------------------------------------------------------------------- position state advisory

def test_position_state_not_requested_without_current_price():
    p = evaluate_position_state("LONG", 1.1700, 1.1675, 1.1800, None, None)
    assert p.status == ADVISORY_NOT_REQUESTED


def test_position_state_hold_without_policy():
    p = evaluate_position_state("LONG", 1.1700, 1.1675, 1.1800, 1.1710, None)
    assert p.status == ADVISORY_HOLD
    assert p.current_r == pytest.approx(0.4, rel=1e-6)


def test_position_state_breakeven_eligible():
    policy = ManagementPolicy(breakeven_trigger_r=1.0)
    p = evaluate_position_state("LONG", 1.1700, 1.1675, 1.1800, 1.1725, policy)
    assert p.status == ADVISORY_BREAKEVEN_ELIGIBLE
    assert p.current_r == pytest.approx(1.0, rel=1e-6)


def test_position_state_target_reached():
    p = evaluate_position_state("LONG", 1.1700, 1.1675, 1.1800, 1.1800, None)
    assert p.status == ADVISORY_TARGET_REACHED


def test_position_state_insufficient_data_zero_stop():
    p = evaluate_position_state("LONG", 1.1700, 1.1700, 1.1800, 1.1710, None)
    assert p.status == ADVISORY_INSUFFICIENT_DATA


# --------------------------------------------------------------------------- engine / integration

def test_engine_manual_entry_no_strategy_required_example_1():
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.17000,
                                  stop_loss=1.16750, take_profit=1.18000, risk_percent=1.0,
                                  equity=10000.0, symbol_meta=_eurusd_meta())
    result = evaluate_trade_management(req)
    assert result.overall_status == OVERALL_READY
    assert result.geometry.rr_multiple == pytest.approx(4.0)
    assert result.sizing.normalized_volume == pytest.approx(0.40)
    assert result.sizing.actual_risk_amount == pytest.approx(100.0, rel=1e-6)


def test_engine_fail_closed_example_2_size_unavailable():
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.17000,
                                  stop_loss=1.16999, take_profit=1.18000, risk_percent=1.0,
                                  equity=0.5, symbol_meta=_eurusd_meta())
    result = evaluate_trade_management(req)
    assert result.sizing.status == SIZING_VOLUME_BELOW_MIN
    assert result.overall_status == OVERALL_BLOCKED


def test_engine_invalid_geometry_blocks_before_sizing():
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.17000,
                                  stop_loss=1.17250, take_profit=1.18000, risk_percent=1.0,
                                  equity=10000.0, symbol_meta=_eurusd_meta())
    result = evaluate_trade_management(req)
    assert result.overall_status == OVERALL_BLOCKED
    assert result.sizing.status == SIZING_NOT_REQUESTED


def test_engine_geometry_only_request_is_ready_without_sizing():
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.17000,
                                  stop_loss=1.16750, take_profit=1.18000)
    result = evaluate_trade_management(req)
    assert result.overall_status == OVERALL_READY
    assert result.sizing.status == SIZING_NOT_REQUESTED


def test_engine_strategy_supplied_policy_is_recorded_not_globalized():
    policy = ManagementPolicy(max_risk_percent=1.0, strategy_id="SESSION_TRADE_V1", policy_source="SESSION_TRADE_V1")
    req = TradeManagementRequest(symbol="EURUSD", direction="LONG", entry_price=1.17000,
                                  stop_loss=1.16750, take_profit=1.18000, risk_percent=2.0,
                                  equity=10000.0, symbol_meta=_eurusd_meta(), management_policy=policy)
    result = evaluate_trade_management(req)
    assert result.sizing.status == SIZING_RISK_LIMIT_EXCEEDED
    assert result.overall_status == OVERALL_BLOCKED


# --------------------------------------------------------------------------- execution independence

def test_trade_management_package_has_no_execution_imports():
    import ast
    import pathlib

    pkg_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "trade_management"
    forbidden = {"execution"}
    for path in pkg_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = {node.module.split(".")[0]}
            else:
                continue
            assert not (names & forbidden), f"{path} imports forbidden module(s): {names & forbidden}"


def test_trade_management_package_has_no_order_send_or_check_calls():
    """AST-based (not a raw text scan) so this doesn't trip on the package's own
    docstrings that describe the boundary in prose (e.g. models.py's "Nothing in this
    package calls order_send/order_check directly")."""
    import ast
    import pathlib

    pkg_dir = pathlib.Path(__file__).resolve().parent.parent / "src" / "trade_management"
    forbidden_calls = {"order_send", "order_check"}
    for path in pkg_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            assert name not in forbidden_calls, f"{path} calls {name}(...)"
