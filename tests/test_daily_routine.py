"""Focused tests for AG_DAILY_ROUTINE_V1 (spec source Phase 16). Mocks the existing
skill functions daily_routine calls -- proves orchestration/gating behavior without
depending on a live MT5 terminal or real market data."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from daily_routine.d1_context import build_d1_context
from daily_routine.h1_setup import build_h1_setup_context
from daily_routine.models import (
    DIRECTIONAL_PERMISSION_INDETERMINATE,
    DIRECTIONAL_PERMISSION_LONG_ONLY,
    DIRECTIONAL_PERMISSION_SHORT_ONLY,
    H1_INDETERMINATE,
    H1_POI_IDENTIFIED,
    H1_WAITING_LOCATION,
    M5_NO_TRADE,
    M5_WAITING_H1_LOCATION,
    D1Context,
    H1SetupContext,
)
from daily_routine.orchestrator import run_daily_routine
from market_structure.models import STATE_BEARISH, STATE_BULLISH, STATE_UNDEFINED, StructureResult
from mt5.market_data import MarketDataError


def _structure(state):
    return StructureResult(symbol="EURUSD", timeframe="D1", status="VALID", reason_codes=(), state=state)


# --------------------------------------------------------------------------- D1

def test_d1_bullish_structure_grants_long_only():
    with patch("daily_routine.d1_context.analyze_structure", return_value=_structure(STATE_BULLISH)), \
         patch("daily_routine.d1_context.liquidity_result", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.d1_context.fair_value_gaps_for", side_effect=MarketDataError("X", "x")):
        d1 = build_d1_context("EURUSD")
    assert d1.directional_permission == DIRECTIONAL_PERMISSION_LONG_ONLY
    assert d1.structure_direction == STATE_BULLISH


def test_d1_bearish_structure_grants_short_only():
    with patch("daily_routine.d1_context.analyze_structure", return_value=_structure(STATE_BEARISH)), \
         patch("daily_routine.d1_context.liquidity_result", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.d1_context.fair_value_gaps_for", side_effect=MarketDataError("X", "x")):
        d1 = build_d1_context("EURUSD")
    assert d1.directional_permission == DIRECTIONAL_PERMISSION_SHORT_ONLY


def test_d1_undefined_structure_is_indeterminate_never_fabricated():
    with patch("daily_routine.d1_context.analyze_structure", return_value=_structure(STATE_UNDEFINED)), \
         patch("daily_routine.d1_context.liquidity_result", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.d1_context.fair_value_gaps_for", side_effect=MarketDataError("X", "x")):
        d1 = build_d1_context("EURUSD")
    assert d1.directional_permission == DIRECTIONAL_PERMISSION_INDETERMINATE


def test_d1_missing_evidence_is_unavailable_not_fabricated():
    with patch("daily_routine.d1_context.analyze_structure", side_effect=MarketDataError("MT5_NOT_CONNECTED", "x")):
        d1 = build_d1_context("EURUSD")
    assert d1.status == "UNAVAILABLE"
    assert d1.directional_permission == DIRECTIONAL_PERMISSION_INDETERMINATE


# --------------------------------------------------------------------------- H1

def test_h1_no_poi_is_waiting_location():
    d1 = D1Context(symbol="EURUSD", as_of=None, directional_permission=DIRECTIONAL_PERMISSION_LONG_ONLY, status="READY")
    with patch("daily_routine.h1_setup.analyze_structure", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.liquidity_result", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.session_zone", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.validated_order_blocks_for", return_value=()), \
         patch("daily_routine.h1_setup.get_tick", side_effect=MarketDataError("X", "x")):
        h1 = build_h1_setup_context("EURUSD", d1)
    assert h1.status == H1_WAITING_LOCATION
    assert h1.selected_poi is None


def test_h1_poi_identified_when_candidate_present_and_price_outside():
    from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
    from supply_demand.ob_contract import OBValidationStatus
    import datetime as dt

    class _VOB:
        def __init__(self, candidate, status):
            self.candidate = candidate
            self.status = status

    zone = ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, low=1.10, high=1.101, status=ZoneStatus.FRESH,
                       origin_time=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), source="test")

    d1 = D1Context(symbol="EURUSD", as_of=None, directional_permission=DIRECTIONAL_PERMISSION_LONG_ONLY, status="READY")
    with patch("daily_routine.h1_setup.analyze_structure", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.liquidity_result", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.session_zone", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.validated_order_blocks_for", return_value=(_VOB(zone, OBValidationStatus.VALID),)), \
         patch("daily_routine.h1_setup.get_tick") as mock_tick:
        mock_tick.return_value.bid = 1.20  # well outside the zone
        h1 = build_h1_setup_context("EURUSD", d1)
    assert h1.status == H1_POI_IDENTIFIED
    assert h1.selected_poi is zone
    assert h1.current_location == "ABOVE_POI"


def test_h1_indeterminate_when_d1_permission_not_directional():
    d1 = D1Context(symbol="EURUSD", as_of=None, directional_permission=DIRECTIONAL_PERMISSION_INDETERMINATE, status="PARTIAL")
    with patch("daily_routine.h1_setup.analyze_structure", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.liquidity_result", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.session_zone", side_effect=MarketDataError("X", "x")), \
         patch("daily_routine.h1_setup.get_tick", side_effect=MarketDataError("X", "x")):
        h1 = build_h1_setup_context("EURUSD", d1)
    assert h1.status == H1_INDETERMINATE


# --------------------------------------------------------------------------- gates (no direct transitions)

def test_orchestrator_no_direct_d1_to_proposal_when_h1_not_ready():
    """D1 alone (bullish, LONG_ONLY) must never produce a proposal without H1/M5."""
    with patch("daily_routine.orchestrator.build_d1_context") as mock_d1, \
         patch("daily_routine.orchestrator.build_h1_setup_context") as mock_h1:
        mock_d1.return_value = D1Context(symbol="EURUSD", as_of=None,
                                          directional_permission=DIRECTIONAL_PERMISSION_LONG_ONLY, status="READY")
        mock_h1.return_value = H1SetupContext(symbol="EURUSD", as_of=None,
                                              d1_directional_permission=DIRECTIONAL_PERMISSION_LONG_ONLY,
                                              selected_poi=None, status=H1_WAITING_LOCATION)
        result = run_daily_routine("EURUSD")

    assert result.proposal_id is None
    assert result.overall_status == "WAITING"
    assert result.m5.status == M5_WAITING_H1_LOCATION  # M5 never actually ran


def test_orchestrator_no_direct_h1_to_execute_without_m5_ready():
    """H1 POI identified alone must never produce a proposal without M5 confirming READY."""
    import datetime as dt
    from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

    zone = ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, low=1.10, high=1.101, status=ZoneStatus.FRESH,
                       origin_time=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), source="test")

    with patch("daily_routine.orchestrator.build_d1_context") as mock_d1, \
         patch("daily_routine.orchestrator.build_h1_setup_context") as mock_h1, \
         patch("daily_routine.orchestrator.evaluate_m5_execution") as mock_m5:
        mock_d1.return_value = D1Context(symbol="EURUSD", as_of=None,
                                          directional_permission=DIRECTIONAL_PERMISSION_LONG_ONLY, status="READY")
        mock_h1.return_value = H1SetupContext(symbol="EURUSD", as_of=None,
                                              d1_directional_permission=DIRECTIONAL_PERMISSION_LONG_ONLY,
                                              selected_poi=zone, status=H1_POI_IDENTIFIED)
        from daily_routine.models import M5ExecutionContext
        mock_m5.return_value = M5ExecutionContext(symbol="EURUSD", as_of=None,
                                                   d1_permission=DIRECTIONAL_PERMISSION_LONG_ONLY,
                                                   h1_location=H1_POI_IDENTIFIED, status=M5_NO_TRADE)
        result = run_daily_routine("EURUSD")

    assert result.proposal_id is None
    assert result.overall_status == "NO_TRADE"
    mock_m5.assert_called_once()  # M5 DID run (unlike the previous test) since H1 had a POI


def test_stale_d1_data_fails_closed():
    with patch("daily_routine.orchestrator.build_d1_context") as mock_d1, \
         patch("daily_routine.orchestrator.build_h1_setup_context") as mock_h1:
        mock_d1.return_value = D1Context(symbol="EURUSD", as_of=None, status="UNAVAILABLE")
        mock_h1.return_value = H1SetupContext(symbol="EURUSD", as_of=None, status="WAITING_CONTEXT")
        result = run_daily_routine("EURUSD")
    assert result.overall_status == "STALE_DATA"
    assert result.proposal_id is None
