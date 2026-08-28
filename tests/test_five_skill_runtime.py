"""Tests for FIVE_SKILL_ASSISTANT_RUNTIME_V1 (assistant/five_skill_runtime.py,
analysis_models.py, assessment.py). Deterministic-fact tests: MT5-touching
collaborators (market_snapshot, analyze_structure, validated_order_blocks_for,
fair_value_gaps_for, liquidity_result) are monkeypatched at the seam
assistant.five_skill_runtime imports them at; entry_confirmation/trade_management run
for real (pure Python, no MT5 dependency) to get genuine integration coverage.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest

from assistant.analysis_models import (
    AssistantAnalysisRequest,
    SKILL_ENTRY_CONFIRMATION,
    SKILL_LIQUIDITY,
    SKILL_MARKET_STRUCTURE,
    SKILL_NOT_REQUESTED,
    SKILL_NO_CANDIDATE,
    SKILL_PARTIAL,
    SKILL_READY,
    SKILL_SUPPLY_DEMAND,
    SKILL_TRADE_MANAGEMENT,
    OVERALL_PARTIAL,
    OVERALL_READY,
    TradeCandidate,
)
from assistant.assessment import build_assistant_assessment
from assistant.five_skill_runtime import InvalidAnalysisRequest, analyze_market
from assistant.market_data import MarketSnapshot
from entry_confirmation import ALL_CONFIRMATIONS, DISPLACEMENT, LIQUIDITY_RECLAIM, STRUCTURE_SHIFT
from liquidity import LiquidityResult
from market_structure import STATE_BULLISH, StructureResult
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.session import Candle
from supply_demand import ZoneFamily, ZoneQueryResult

UTC = dt.timezone.utc


def _candle():
    return Candle(time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC), open=1.1700, high=1.1720, low=1.1690, close=1.1710, volume=1.0)


def _snapshot(status="OK", freshness="OK"):
    return MarketSnapshot(symbol="EURUSD", status=status, reason_codes=() if status == "OK" else (status,),
                           bid=1.17000, ask=1.17020, spread_points=2, tick_time_utc=dt.datetime.now(UTC),
                           freshness=freshness, latest_closed_candle=_candle(), recent_high=1.1750, recent_low=1.1650)


def _structure_result(status="VALID"):
    return StructureResult(symbol="EURUSD", timeframe="M15", status=status, reason_codes=(), state=STATE_BULLISH)


def _zone_query(status="OK"):
    return ZoneQueryResult(symbol="EURUSD", timeframe="M15", family=ZoneFamily.ORDER_BLOCK, status=status,
                            reason_codes=() if status == "OK" else (status,))


def _liquidity_result_fixture(status="LIQUIDITY_OK"):
    return LiquidityResult(symbol="EURUSD", timeframe="M15", status=status)


def _eurusd_meta():
    return SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                       volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=0.00001)


def _patch_common(monkeypatch, snapshot=None, structure=None, obs=None, fvgs=None, liquidity=None):
    snap_mock = MagicMock(return_value=snapshot or _snapshot())
    structure_mock = MagicMock(return_value=structure or _structure_result())
    obs_mock = MagicMock(return_value=obs if obs is not None else [])  # validated_order_blocks_for() -> plain list
    fvgs_mock = MagicMock(return_value=fvgs or _zone_query())
    liquidity_mock = MagicMock(return_value=liquidity or _liquidity_result_fixture())

    monkeypatch.setattr("assistant.five_skill_runtime.market_snapshot", snap_mock)
    monkeypatch.setattr("assistant.five_skill_runtime.analyze_structure", structure_mock)
    monkeypatch.setattr("assistant.five_skill_runtime.validated_order_blocks_for", obs_mock)
    monkeypatch.setattr("assistant.five_skill_runtime.fair_value_gaps_for", fvgs_mock)
    monkeypatch.setattr("assistant.five_skill_runtime._liquidity_result", liquidity_mock)
    return snap_mock, structure_mock, obs_mock, fvgs_mock, liquidity_mock


# --------------------------------------------------------------------------- selective invocation

def test_selective_invocation_market_structure_only(monkeypatch):
    snap, structure, obs, fvgs, liq = _patch_common(monkeypatch)
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(SKILL_MARKET_STRUCTURE,))
    result = analyze_market(req)

    assert snap.call_count == 1
    assert structure.call_count == 1
    assert obs.call_count == 0
    assert fvgs.call_count == 0
    assert liq.call_count == 0

    assert result.skill_statuses[SKILL_MARKET_STRUCTURE] == SKILL_READY
    assert result.skill_statuses[SKILL_SUPPLY_DEMAND] == SKILL_NOT_REQUESTED
    assert result.skill_statuses[SKILL_LIQUIDITY] == SKILL_NOT_REQUESTED
    assert result.skill_statuses[SKILL_ENTRY_CONFIRMATION] == SKILL_NOT_REQUESTED
    assert result.skill_statuses[SKILL_TRADE_MANAGEMENT] == SKILL_NO_CANDIDATE
    assert result.supply_demand is None
    assert result.liquidity is None


def test_selective_invocation_liquidity_only(monkeypatch):
    snap, structure, obs, fvgs, liq = _patch_common(monkeypatch)
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(SKILL_LIQUIDITY,))
    result = analyze_market(req)

    assert snap.call_count == 1
    assert liq.call_count == 1
    assert structure.call_count == 0
    assert obs.call_count == 0

    assert result.skill_statuses[SKILL_LIQUIDITY] == SKILL_READY
    assert result.skill_statuses[SKILL_MARKET_STRUCTURE] == SKILL_NOT_REQUESTED


def test_unknown_requested_skill_raises():
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=("not-a-real-skill",))
    with pytest.raises(InvalidAnalysisRequest):
        analyze_market(req)


# --------------------------------------------------------------------------- generic analysis (no strategy)

def test_generic_analysis_without_strategy_full_set(monkeypatch):
    _patch_common(monkeypatch)
    req = AssistantAnalysisRequest(symbol="EURUSD")  # default requested_skills = all four market skills
    result = analyze_market(req)

    assert result.structure is not None
    assert result.supply_demand is not None
    assert result.liquidity is not None
    assert result.entry_confirmation is not None
    assert result.trade_management is None
    assert result.skill_statuses[SKILL_TRADE_MANAGEMENT] == SKILL_NO_CANDIDATE


def test_entry_confirmation_auto_pulls_structure_and_liquidity(monkeypatch):
    snap, structure, obs, fvgs, liq = _patch_common(monkeypatch)
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(SKILL_ENTRY_CONFIRMATION,))
    result = analyze_market(req)

    assert structure.call_count == 1
    assert liq.call_count == 1
    assert obs.call_count == 0  # supply-demand is NOT an entry-confirmation dependency
    assert result.skill_statuses[SKILL_MARKET_STRUCTURE] == SKILL_READY
    assert result.skill_statuses[SKILL_LIQUIDITY] == SKILL_READY
    assert result.entry_confirmation.structure_shift.event_kind is None or result.structure is not None


# --------------------------------------------------------------------------- manual candidate (second acceptance test)

def test_manual_candidate_full_pipeline_no_strategy(monkeypatch):
    _patch_common(monkeypatch)
    candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750, take_profit=1.18000,
                                risk_percent=1.0, equity=10000.0, symbol_meta=_eurusd_meta())
    req = AssistantAnalysisRequest(symbol="EURUSD", candidate=candidate)
    result = analyze_market(req)

    assert result.trade_management is not None
    assert result.trade_management.overall_status == "READY"
    assert result.trade_management.geometry.rr_multiple == pytest.approx(4.0)
    assert result.trade_management.sizing.normalized_volume == pytest.approx(0.40)
    assert result.skill_statuses[SKILL_TRADE_MANAGEMENT] == SKILL_READY
    assert result.entry_confirmation.candidate_direction == "LONG"


def test_trade_management_runs_without_any_market_skill_requested(monkeypatch):
    _patch_common(monkeypatch)
    candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750,
                                risk_percent=1.0, equity=10000.0, symbol_meta=_eurusd_meta())
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(), candidate=candidate)
    result = analyze_market(req)

    assert result.trade_management is not None
    assert result.trade_management.overall_status == "READY"
    assert result.overall_status == OVERALL_READY


# --------------------------------------------------------------------------- trade management candidate/no-candidate

def test_no_candidate_mode_does_not_fail_analysis(monkeypatch):
    _patch_common(monkeypatch)
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(SKILL_MARKET_STRUCTURE,))
    result = analyze_market(req)
    assert result.trade_management is None
    assert result.skill_statuses[SKILL_TRADE_MANAGEMENT] == SKILL_NO_CANDIDATE
    assert result.overall_status == OVERALL_READY


# --------------------------------------------------------------------------- partial entry confirmation survives

def test_unsigned_displacement_survives_to_result_and_report(monkeypatch):
    _patch_common(monkeypatch)
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(SKILL_ENTRY_CONFIRMATION,),
                                    requested_confirmations=ALL_CONFIRMATIONS)
    result = analyze_market(req)

    assert result.entry_confirmation.displacement.status.value == "UNSIGNED_RULE"
    assert result.skill_statuses[SKILL_ENTRY_CONFIRMATION] == SKILL_PARTIAL
    assert result.overall_status == OVERALL_PARTIAL

    assessment = build_assistant_assessment(result)
    assert "UNSIGNED_RULE" in assessment.report_text
    assert "PASS" not in assessment.report_text.split("displacement")[1].split("\n")[0]


def test_narrowed_confirmations_avoid_unsigned_indeterminate(monkeypatch):
    from market_structure import StructurePoint, StructurePointKind

    choch = StructurePoint(time_utc=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), price=1.1690,
                            kind=StructurePointKind.BULLISH_CHOCH)
    structure = StructureResult(symbol="EURUSD", timeframe="M15", status="VALID", reason_codes=(),
                                 state=STATE_BULLISH, latest_choch=choch)

    from liquidity import LiquidityLevel, LiquiditySide, LiquidityStatus
    level = LiquidityLevel(symbol="EURUSD", timeframe="M15", side=LiquiditySide.SELL_SIDE,
                            source="SWING_LOW", price=1.1650, origin_time=None,
                            status=LiquidityStatus.RECLAIMED)
    liquidity = LiquidityResult(symbol="EURUSD", timeframe="M15", status="LIQUIDITY_OK",
                                 nearest_sell_side=level)

    _patch_common(monkeypatch, structure=structure, liquidity=liquidity)
    candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750)
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(SKILL_ENTRY_CONFIRMATION,),
                                    requested_confirmations=(STRUCTURE_SHIFT, LIQUIDITY_RECLAIM),
                                    candidate=candidate)
    result = analyze_market(req)
    assert result.entry_confirmation.structure_shift.status.value == "PASS"
    assert result.entry_confirmation.liquidity_reclaim.status.value == "PASS"
    assert result.skill_statuses[SKILL_ENTRY_CONFIRMATION] == SKILL_READY


# --------------------------------------------------------------------------- shared market context

def test_market_context_built_exactly_once_per_analysis(monkeypatch):
    snap, *_ = _patch_common(monkeypatch)
    candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750,
                                risk_percent=1.0, equity=10000.0, symbol_meta=_eurusd_meta())
    req = AssistantAnalysisRequest(symbol="EURUSD", candidate=candidate)  # all four market skills + candidate
    analyze_market(req)
    assert snap.call_count == 1


def test_no_candidate_current_price_defaults_from_shared_snapshot(monkeypatch):
    _patch_common(monkeypatch, snapshot=_snapshot())
    candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750,
                                risk_percent=1.0, equity=10000.0, symbol_meta=_eurusd_meta())
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(), candidate=candidate)
    result = analyze_market(req)
    # position_state advisory should have used the shared snapshot's bid (1.17000) as current_price
    assert result.trade_management.position_state.current_r is not None


# --------------------------------------------------------------------------- data quality gate

def test_context_unavailable_blocks_downstream_market_skills(monkeypatch):
    _patch_common(monkeypatch, snapshot=_snapshot(status="MT5_NOT_CONNECTED", freshness=None))
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(SKILL_MARKET_STRUCTURE, SKILL_LIQUIDITY))
    result = analyze_market(req)
    assert result.market_context_status == "MT5_NOT_CONNECTED"
    assert result.skill_statuses[SKILL_MARKET_STRUCTURE] == "UNAVAILABLE"
    assert result.skill_statuses[SKILL_LIQUIDITY] == "UNAVAILABLE"
    assert result.errors


def test_context_unavailable_does_not_block_trade_management(monkeypatch):
    _patch_common(monkeypatch, snapshot=_snapshot(status="MT5_NOT_CONNECTED", freshness=None))
    candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750,
                                risk_percent=1.0, equity=10000.0, symbol_meta=_eurusd_meta())
    req = AssistantAnalysisRequest(symbol="EURUSD", requested_skills=(), candidate=candidate)
    result = analyze_market(req)
    assert result.trade_management.overall_status == "READY"


# --------------------------------------------------------------------------- strategy independence

def test_five_skill_runtime_module_does_not_import_strategy_manager():
    import ast
    import pathlib

    for name in ("five_skill_runtime.py", "analysis_models.py", "assessment.py"):
        path = pathlib.Path(__file__).resolve().parent.parent / "src" / "assistant" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = {node.module.split(".")[0]}
            else:
                continue
            assert "strategy_manager" not in names, f"{path} imports strategy_manager"


# --------------------------------------------------------------------------- execution independence

def test_five_skill_runtime_module_has_no_execution_imports_or_broker_write_calls():
    import ast
    import pathlib

    forbidden_import = {"execution"}
    forbidden_calls = {"order_send", "order_check"}
    for name in ("five_skill_runtime.py", "analysis_models.py", "assessment.py"):
        path = pathlib.Path(__file__).resolve().parent.parent / "src" / "assistant" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                assert not (names & forbidden_import), f"{path} imports {names & forbidden_import}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = {node.module.split(".")[0]}
                assert not (names & forbidden_import), f"{path} imports {names & forbidden_import}"
            elif isinstance(node, ast.Call):
                func = node.func
                call_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                assert call_name not in forbidden_calls, f"{path} calls {call_name}(...)"


# --------------------------------------------------------------------------- live acceptance tests
# Mission sections 74/75's two product acceptance cases, run against a real MT5 terminal
# when available -- same skipif pattern as tests/test_assistant_market_data.py. Skipped
# (not failed) when no terminal is connected in this environment.

def _mt5_available():
    import MetaTrader5 as mt5
    return mt5.initialize()


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_acceptance_analyze_eurusd_m15_without_strategy_live():
    from mt5.connection import connect

    connect()
    req = AssistantAnalysisRequest(symbol="EURUSD", timeframe="M15")
    result = analyze_market(req)

    assert result.overall_status in ("READY", "PARTIAL", "BLOCKED")
    assert result.trade_management is None
    assert result.skill_statuses[SKILL_TRADE_MANAGEMENT] == SKILL_NO_CANDIDATE
    build_assistant_assessment(result)  # must not raise


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_acceptance_manual_candidate_evaluation_live():
    from mt5.connection import connect

    connect()
    candidate = TradeCandidate(direction="LONG", entry_price=1.17000, stop_loss=1.16750, take_profit=1.18000,
                                risk_percent=1.0, equity=10000.0, symbol_meta=_eurusd_meta())
    req = AssistantAnalysisRequest(symbol="EURUSD", candidate=candidate)
    result = analyze_market(req)

    assert result.trade_management is not None
    assert result.trade_management.geometry.rr_multiple == pytest.approx(4.0)
    build_assistant_assessment(result)  # must not raise
