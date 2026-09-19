"""TD-3: adapter tests for translating existing D1/H1/M5 market-context facts into
the frozen TD-1 tier-context contracts. All deterministic/unit -- no live MT5 needed;
fake source objects are hand-built the same way tests/test_mt5_market_data_guards.py
hand-builds Candle lists. See docs/status/TD3_EXISTING_CONTEXT_ADAPTERS_STATUS.md.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

from daily_routine.models import D1Context, DIRECTIONAL_PERMISSION_LONG_ONLY, H1SetupContext, H1_POI_IDENTIFIED
from market_structure.models import StructurePoint, StructurePointKind, StructureResult
from mtf_context.topdown_contracts import (
    DATA_QUALITY_DATA_ERROR,
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_M5,
)
from mtf_context.topdown_context_adapters import (
    D1_CONTEXT_SOURCE,
    H1_CONTEXT_SOURCE,
    M5_CONTEXT_SOURCE,
    build_daily_context,
    build_h1_context,
    build_m5_context,
    daily_context_from_d1,
    h1_context_from_sources,
    m5_context_from_structure,
)

UTC = dt.timezone.utc
_BAR_CLOSE = dt.datetime(2026, 9, 17, 21, 0, tzinfo=UTC)


def _bos_point(price=1.0950, time=_BAR_CLOSE) -> StructurePoint:
    return StructurePoint(time_utc=time, price=price, kind=StructurePointKind.BULLISH_BOS)


def _choch_point(price=1.0900, time=_BAR_CLOSE - dt.timedelta(hours=1)) -> StructurePoint:
    return StructurePoint(time_utc=time, price=price, kind=StructurePointKind.BEARISH_CHOCH)


def _structure_result(
    symbol="EURUSD", timeframe="D1", status="VALID", smc_version="1.2.3",
    latest_bos=None, latest_choch=None, data_end_utc=_BAR_CLOSE,
) -> StructureResult:
    return StructureResult(
        symbol=symbol, timeframe=timeframe, status=status, reason_codes=(),
        state="BULLISH", latest_bos=latest_bos, latest_choch=latest_choch,
        data_start_utc=(data_end_utc - dt.timedelta(days=30)) if data_end_utc else None,
        data_end_utc=data_end_utc,
        closed_candle_count=200, smc_version=smc_version,
    )


def _d1_context(structure: StructureResult, status="READY") -> D1Context:
    return D1Context(
        symbol=structure.symbol, as_of=None, status=status,
        structure_direction=structure.state,
        directional_permission=DIRECTIONAL_PERMISSION_LONG_ONLY,
        evidence={"structure": structure},
    )


def _h1_setup_context(symbol="EURUSD", status=H1_POI_IDENTIFIED) -> H1SetupContext:
    return H1SetupContext(symbol=symbol, as_of=None, status=status)


# --------------------------------------------------------------------------- D1

def test_d1_existing_facts_map_to_daily_context():
    structure = _structure_result(timeframe="D1", latest_bos=_bos_point())
    d1 = _d1_context(structure)

    ctx = daily_context_from_d1(d1)

    assert ctx is not None
    assert ctx.symbol == "EURUSD"
    assert ctx.timeframe == TIMEFRAME_D1
    assert ctx.source == D1_CONTEXT_SOURCE
    assert ctx.bar_close_time == structure.data_end_utc
    assert ctx.data_quality_status == DATA_QUALITY_VALID
    assert len(ctx.structure_facts) == 1
    assert ctx.structure_facts[0].event_type == "BOS"
    assert ctx.structure_facts[0].direction == "BULLISH"
    assert ctx.structure_facts[0].level == 1.0950


def test_d1_unavailable_status_yields_no_context():
    """No evidence["structure"] means no closed-bar timestamp -- DailyContext.
    bar_close_time is mandatory, so nothing honest can be constructed."""
    d1 = D1Context(symbol="EURUSD", as_of=None, status="UNAVAILABLE")
    assert daily_context_from_d1(d1) is None


def test_d1_structure_fetch_failure_yields_no_context():
    structure = _structure_result(status="MARKET_DATA_INVALID", smc_version=None, data_end_utc=None)
    d1 = D1Context(symbol="EURUSD", as_of=None, status="UNAVAILABLE", evidence={"structure": structure})
    assert daily_context_from_d1(d1) is None


def test_d1_missing_smc_version_yields_partial_quality_with_no_facts():
    structure = _structure_result(smc_version=None, latest_bos=_bos_point())
    d1 = _d1_context(structure)

    ctx = daily_context_from_d1(d1)

    assert ctx is not None
    assert ctx.data_quality_status == DATA_QUALITY_PARTIAL
    assert ctx.structure_facts == ()


def test_build_daily_context_calls_existing_d1_authority_only():
    """No-redetection proof: build_daily_context must call daily_routine.d1_context.
    build_d1_context exactly once and use its result verbatim -- it must never call
    market_structure/liquidity/supply_demand functions directly itself."""
    structure = _structure_result(latest_bos=_bos_point())
    fake_d1 = _d1_context(structure)

    with patch("mtf_context.topdown_context_adapters.build_d1_context", return_value=fake_d1) as mock_build:
        ctx = build_daily_context("EURUSD")

    mock_build.assert_called_once_with("EURUSD")
    assert ctx is not None
    assert ctx.structure_facts[0].level == structure.latest_bos.price


# --------------------------------------------------------------------------- H1

def test_h1_existing_facts_map_to_h1_context():
    structure = _structure_result(timeframe="H1", latest_choch=_choch_point())
    h1_setup = _h1_setup_context()

    ctx = h1_context_from_sources(h1_setup, structure)

    assert ctx is not None
    assert ctx.timeframe == TIMEFRAME_H1
    assert ctx.source == H1_CONTEXT_SOURCE
    assert ctx.bar_close_time == structure.data_end_utc
    assert len(ctx.structure_facts) == 1
    assert ctx.structure_facts[0].event_type == "CHOCH"
    assert ctx.structure_facts[0].direction == "BEARISH"


def test_h1_context_excludes_strategy_owned_poi_interpretation():
    """H1SetupContext's own selected_poi/current_location/alert_zone/midnight_open/
    asian-session fields must never appear on H1Context -- confirmed structurally:
    H1Context (TD-1's frozen contract) has no such field at all."""
    from dataclasses import fields
    from mtf_context.topdown_contracts import H1Context

    field_names = {f.name for f in fields(H1Context)}
    assert not (field_names & {
        "selected_poi", "current_location", "alert_zone", "midnight_open",
        "asian_session_high", "asian_session_low", "poi_candidates",
    })


def test_h1_symbol_mismatch_between_sources_rejected():
    structure = _structure_result(symbol="GBPUSD", timeframe="H1")
    h1_setup = _h1_setup_context(symbol="EURUSD")
    with pytest.raises(ValueError):
        h1_context_from_sources(h1_setup, structure)


def test_build_h1_context_calls_existing_h1_and_d1_authorities_only():
    structure = _structure_result(timeframe="H1", latest_bos=_bos_point())
    fake_d1 = _d1_context(_structure_result(timeframe="D1"))
    fake_h1_setup = _h1_setup_context()

    with patch("mtf_context.topdown_context_adapters.build_d1_context", return_value=fake_d1) as mock_d1, \
         patch("mtf_context.topdown_context_adapters.build_h1_setup_context", return_value=fake_h1_setup) as mock_h1, \
         patch("mtf_context.topdown_context_adapters.analyze_structure", return_value=structure) as mock_structure:
        ctx = build_h1_context("EURUSD")

    mock_d1.assert_called_once_with("EURUSD")
    mock_h1.assert_called_once_with("EURUSD", fake_d1)
    mock_structure.assert_called_once_with("EURUSD", TIMEFRAME_H1)
    assert ctx is not None
    assert ctx.structure_facts[0].level == structure.latest_bos.price


# --------------------------------------------------------------------------- M5

def test_m5_existing_facts_map_to_m5_context():
    structure = _structure_result(timeframe="M5", latest_bos=_bos_point(), latest_choch=_choch_point())

    ctx = m5_context_from_structure(structure)

    assert ctx is not None
    assert ctx.timeframe == TIMEFRAME_M5
    assert ctx.source == M5_CONTEXT_SOURCE
    assert len(ctx.structure_facts) == 2


def test_build_m5_context_calls_existing_structure_authority_only():
    structure = _structure_result(timeframe="M5", latest_bos=_bos_point())
    with patch("mtf_context.topdown_context_adapters.analyze_structure", return_value=structure) as mock_structure:
        ctx = build_m5_context("EURUSD")

    mock_structure.assert_called_once_with("EURUSD", TIMEFRAME_M5)
    assert ctx is not None


def test_m5_structure_fetch_failure_yields_no_context():
    structure = _structure_result(timeframe="M5", status="INSUFFICIENT_STRUCTURE_HISTORY", smc_version=None)
    assert m5_context_from_structure(structure) is None


# --------------------------------------------------------------------------- 4. Deterministic mapping

def test_mapping_is_deterministic():
    structure_a = _structure_result(latest_bos=_bos_point())
    structure_b = _structure_result(latest_bos=_bos_point())  # same values, different object
    ctx_a = daily_context_from_d1(_d1_context(structure_a))
    ctx_b = daily_context_from_d1(_d1_context(structure_b))

    assert ctx_a.context_id == ctx_b.context_id
    assert ctx_a.structure_facts == ctx_b.structure_facts


# --------------------------------------------------------------------------- 5. Provenance retained

def test_provenance_fields_all_populated():
    structure = _structure_result(latest_bos=_bos_point())
    ctx = daily_context_from_d1(_d1_context(structure))

    assert ctx.context_id
    assert ctx.symbol == structure.symbol
    assert ctx.timeframe == TIMEFRAME_D1
    assert ctx.source == D1_CONTEXT_SOURCE
    assert ctx.bar_close_time == structure.data_end_utc
    assert ctx.feature_version
    assert ctx.structure_facts[0].feature_version == structure.smc_version
    assert ctx.structure_facts[0].confirmation_bar_time == structure.latest_bos.time_utc


# --------------------------------------------------------------------------- 6. Partial parent lineage

def test_daily_context_without_parent_weekly_id_is_valid():
    structure = _structure_result(latest_bos=_bos_point())
    ctx = daily_context_from_d1(_d1_context(structure), parent_weekly_context_id=None)
    assert ctx.parent_weekly_context_id is None


def test_daily_context_with_parent_weekly_id_retains_it():
    structure = _structure_result(latest_bos=_bos_point())
    ctx = daily_context_from_d1(_d1_context(structure), parent_weekly_context_id="TDCTX-W1-abc")
    assert ctx.parent_weekly_context_id == "TDCTX-W1-abc"


# --------------------------------------------------------------------------- 7. structure_definition_id retained

def test_structure_definition_id_retained_on_every_fact():
    structure = _structure_result(latest_bos=_bos_point(), latest_choch=_choch_point())
    ctx = m5_context_from_structure(structure)
    for fact in ctx.structure_facts:
        assert fact.structure_definition_id == STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1


# --------------------------------------------------------------------------- 10. No trade-decision authority

def test_no_context_dataclass_carries_a_trade_decision_field():
    from dataclasses import fields
    from mtf_context.topdown_contracts import DailyContext, H1Context, M5Context

    forbidden = {"direction", "decision", "signal", "buy", "sell", "ready_for_trade",
                 "position_size", "risk_amount", "permission", "poi", "location"}
    for cls in (DailyContext, H1Context, M5Context):
        field_names = {f.name for f in fields(cls)}
        assert not (field_names & forbidden), f"{cls.__name__} leaked a decision-shaped field"
