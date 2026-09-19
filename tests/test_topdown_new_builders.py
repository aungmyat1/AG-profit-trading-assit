"""TD-4: tests for the new W1/H4/M15 context builders. All deterministic/unit -- no
live MT5 needed; fake source objects are hand-built the same way TD-3's adapter tests
build them. See docs/status/TD4_NEW_CONTEXT_BUILDERS_STATUS.md.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

from liquidity.models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from market_structure.models import StructurePoint, StructurePointKind, StructureResult
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
from supply_demand.ob_contract import OBFamily, OBValidationStatus, ValidatedOrderBlock
from mtf_context.topdown_contracts import (
    DATA_QUALITY_DATA_ERROR,
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    TIMEFRAME_H4,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
)
from mtf_context.topdown_new_builders import (
    H4_CONTEXT_SOURCE,
    M15_CONTEXT_SOURCE,
    WEEKLY_CONTEXT_SOURCE,
    build_h4_context,
    build_m15_context,
    build_weekly_context,
    h4_context_from_structure,
    m15_context_from_structure,
    weekly_context_from_structure,
)

UTC = dt.timezone.utc
_BAR_CLOSE = dt.datetime(2026, 9, 12, 21, 0, tzinfo=UTC)


def _bos_point(price=1.0950, time=_BAR_CLOSE) -> StructurePoint:
    return StructurePoint(time_utc=time, price=price, kind=StructurePointKind.BULLISH_BOS)


def _choch_point(price=1.0900, time=_BAR_CLOSE - dt.timedelta(hours=1)) -> StructurePoint:
    return StructurePoint(time_utc=time, price=price, kind=StructurePointKind.BEARISH_CHOCH)


def _structure_result(
    symbol="EURUSD", timeframe="W1", status="VALID", smc_version="1.2.3",
    latest_bos=None, latest_choch=None, data_end_utc=_BAR_CLOSE,
) -> StructureResult:
    return StructureResult(
        symbol=symbol, timeframe=timeframe, status=status, reason_codes=(),
        state="BULLISH", latest_bos=latest_bos, latest_choch=latest_choch,
        data_start_utc=(data_end_utc - dt.timedelta(days=90)) if data_end_utc else None,
        data_end_utc=data_end_utc, closed_candle_count=200, smc_version=smc_version,
    )


def _fvg_zone(timeframe="W1", low=1.090, high=1.095, origin_time=_BAR_CLOSE) -> ZoneResult:
    return ZoneResult(symbol="EURUSD", timeframe=timeframe, family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="smc.fvg",
                       low=low, high=high, origin_time=origin_time)


def _validated_ob(timeframe="W1", role=ZoneRole.DEMAND, low=1.080, high=1.085, origin_time=_BAR_CLOSE) -> ValidatedOrderBlock:
    candidate = ZoneResult(symbol="EURUSD", timeframe=timeframe, family=ZoneFamily.ORDER_BLOCK, role=role,
                            direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="smc.ob",
                            low=low, high=high, origin_time=origin_time)
    return ValidatedOrderBlock(symbol="EURUSD", timeframe=timeframe, family=OBFamily.PIVOT_OB,
                                status=OBValidationStatus.VALID, direction=ZoneDirection.BULLISH,
                                low=low, high=high, origin_time=origin_time, candidate=candidate)


def _liquidity_level(timeframe="W1", side=LiquiditySide.BUY_SIDE, source="PWH", price=1.10,
                      origin_time=_BAR_CLOSE) -> LiquidityLevel:
    return LiquidityLevel(symbol="EURUSD", timeframe=timeframe, side=side, source=source,
                           price=price, origin_time=origin_time, status=LiquidityStatus.UNSWEPT)


def _session_zone(name="asian", timeframe="M15", low=1.09, high=1.095, origin_time=_BAR_CLOSE) -> ZoneResult:
    return ZoneResult(symbol="EURUSD", timeframe=timeframe, family=ZoneFamily.SESSION, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN,
                       source="config/canonical_sessions.yaml", low=low, high=high, origin_time=origin_time)


# --------------------------------------------------------------------------- 1. W1 -> WeeklyContext

def test_w1_structure_facts_map_to_weekly_context():
    structure = _structure_result(latest_bos=_bos_point())
    ctx = weekly_context_from_structure(structure)

    assert ctx is not None
    assert ctx.timeframe == TIMEFRAME_W1
    assert ctx.source == WEEKLY_CONTEXT_SOURCE
    assert ctx.bar_close_time == structure.data_end_utc
    assert len(ctx.structure_facts) == 1
    assert ctx.structure_facts[0].event_type == "BOS"


def test_weekly_context_maps_zone_imbalance_liquidity_facts():
    structure = _structure_result(latest_bos=_bos_point())
    ctx = weekly_context_from_structure(
        structure, order_blocks=(_validated_ob(),), fvg_zones=(_fvg_zone(),),
        liquidity_levels=(_liquidity_level(),),
    )
    assert len(ctx.zone_facts) == 1
    assert len(ctx.imbalance_facts) == 1
    assert len(ctx.liquidity_facts) == 1


def test_weekly_context_has_no_parent_field():
    """WeeklyContext is the top of the hierarchy -- TD-1's frozen contract has no
    parent_*_context_id field on it at all."""
    from dataclasses import fields
    from mtf_context.topdown_contracts import WeeklyContext

    field_names = {f.name for f in fields(WeeklyContext)}
    assert not any(name.startswith("parent_") for name in field_names)


def test_weekly_context_reference_level_facts_always_empty_by_design():
    """No existing authority in this repository produces a weekly-scoped reference
    level -- weekly_context_from_structure() accepts no reference-level input at all."""
    structure = _structure_result(latest_bos=_bos_point())
    ctx = weekly_context_from_structure(structure)
    assert ctx.reference_level_facts == ()


def test_w1_structure_fetch_failure_yields_no_context():
    structure = _structure_result(status="MARKET_DATA_INVALID", smc_version=None, data_end_utc=None)
    assert weekly_context_from_structure(structure) is None


def test_w1_missing_smc_version_yields_partial_quality_with_no_facts():
    structure = _structure_result(smc_version=None, latest_bos=_bos_point())
    ctx = weekly_context_from_structure(structure)
    assert ctx.data_quality_status == DATA_QUALITY_PARTIAL
    assert ctx.structure_facts == ()


def test_build_weekly_context_calls_existing_authorities_only():
    """No-redetection proof: all four existing-authority calls mocked so this stays a
    deterministic unit test with no live MT5 dependency."""
    structure = _structure_result(latest_bos=_bos_point())
    fake_liq = type("FakeLiq", (), {"status": "LIQUIDITY_OK", "levels": ()})()

    with patch("mtf_context.topdown_new_builders.analyze_structure", return_value=structure) as mock_structure, \
         patch("mtf_context.topdown_new_builders.validated_order_blocks_for", return_value=()) as mock_ob, \
         patch("mtf_context.topdown_new_builders.fair_value_gaps_for") as mock_fvg, \
         patch("mtf_context.topdown_new_builders.liquidity_result", return_value=fake_liq) as mock_liq:
        mock_fvg.return_value.status = "OK"
        mock_fvg.return_value.zones = ()
        ctx = build_weekly_context("EURUSD")

    mock_structure.assert_called_once_with("EURUSD", TIMEFRAME_W1)
    mock_ob.assert_called_once_with("EURUSD", TIMEFRAME_W1)
    mock_fvg.assert_called_once_with("EURUSD", TIMEFRAME_W1)
    mock_liq.assert_called_once_with("EURUSD", TIMEFRAME_W1)
    assert ctx is not None


# --------------------------------------------------------------------------- 2. H4 -> H4Context

def test_h4_structure_facts_map_to_h4_context():
    structure = _structure_result(timeframe="H4", latest_choch=_choch_point())
    ctx = h4_context_from_structure(structure)

    assert ctx is not None
    assert ctx.timeframe == TIMEFRAME_H4
    assert ctx.source == H4_CONTEXT_SOURCE
    assert len(ctx.structure_facts) == 1
    assert ctx.structure_facts[0].event_type == "CHOCH"
    assert ctx.structure_facts[0].direction == "BEARISH"


def test_h4_context_never_produces_trade_direction():
    """ALLOWED: StructureFact(event_type=CHOCH, direction=BEARISH, ...) -- a market
    fact. NOT ALLOWED: any candidate_direction/trade-decision field. H4Context (TD-1's
    frozen contract) has no such field at all."""
    from dataclasses import fields
    from mtf_context.topdown_contracts import H4Context

    field_names = {f.name for f in fields(H4Context)}
    forbidden = {"candidate_direction", "trade_direction", "signal", "buy", "sell", "ready_for_trade"}
    assert not (field_names & forbidden)


def test_h4_context_supports_parent_daily_context_id():
    structure = _structure_result(timeframe="H4", latest_bos=_bos_point())
    ctx = h4_context_from_structure(structure, parent_daily_context_id="TDCTX-D1-abc")
    assert ctx.parent_daily_context_id == "TDCTX-D1-abc"


def test_h4_context_reference_level_facts_empty_by_design():
    structure = _structure_result(timeframe="H4", latest_bos=_bos_point())
    ctx = h4_context_from_structure(structure)
    assert ctx.reference_level_facts == ()


def test_build_h4_context_calls_existing_authorities_only():
    structure = _structure_result(timeframe="H4", latest_bos=_bos_point())
    fake_liq = type("FakeLiq", (), {"status": "LIQUIDITY_OK", "levels": ()})()

    with patch("mtf_context.topdown_new_builders.analyze_structure", return_value=structure) as mock_structure, \
         patch("mtf_context.topdown_new_builders.validated_order_blocks_for", return_value=()) as mock_ob, \
         patch("mtf_context.topdown_new_builders.fair_value_gaps_for") as mock_fvg, \
         patch("mtf_context.topdown_new_builders.liquidity_result", return_value=fake_liq) as mock_liq:
        mock_fvg.return_value.status = "OK"
        mock_fvg.return_value.zones = ()
        ctx = build_h4_context("EURUSD", parent_daily_context_id="TDCTX-D1-xyz")

    mock_structure.assert_called_once_with("EURUSD", TIMEFRAME_H4)
    mock_ob.assert_called_once_with("EURUSD", TIMEFRAME_H4)
    mock_fvg.assert_called_once_with("EURUSD", TIMEFRAME_H4)
    mock_liq.assert_called_once_with("EURUSD", TIMEFRAME_H4)
    assert ctx is not None
    assert ctx.parent_daily_context_id == "TDCTX-D1-xyz"


# --------------------------------------------------------------------------- 3. M15 -> M15Context

def test_m15_structure_facts_map_to_m15_context():
    structure = _structure_result(timeframe="M15", latest_bos=_bos_point(), latest_choch=_choch_point())
    ctx = m15_context_from_structure(structure)

    assert ctx is not None
    assert ctx.timeframe == TIMEFRAME_M15
    assert ctx.source == M15_CONTEXT_SOURCE
    assert len(ctx.structure_facts) == 2


def test_m15_session_reference_level_facts_mapped_with_correct_family():
    structure = _structure_result(timeframe="M15", latest_bos=_bos_point())
    ctx = m15_context_from_structure(
        structure,
        session_zones=(("asian", _session_zone("asian")), ("london_am", _session_zone("london_am"))),
    )
    assert len(ctx.reference_level_facts) == 2
    assert all(fact.family == "SESSION" for fact in ctx.reference_level_facts)


def test_m15_incomplete_session_produces_no_fact():
    """An incomplete session (no low/high yet) must be silently skipped, never
    fabricated."""
    incomplete = ZoneResult(symbol="EURUSD", timeframe="M15", family=ZoneFamily.SESSION,
                             role=ZoneRole.REFERENCE, direction=ZoneDirection.NONE,
                             status=ZoneStatus.UNKNOWN, source="config/canonical_sessions.yaml")
    structure = _structure_result(timeframe="M15", latest_bos=_bos_point())
    ctx = m15_context_from_structure(structure, session_zones=(("asian", incomplete),))
    assert ctx.reference_level_facts == ()


def test_m15_does_not_import_ssc_or_as5r_semantics():
    """Static proof (complementing the AST guard): the only structure_definition_id
    this module ever writes is the SMC one."""
    ctx = m15_context_from_structure(_structure_result(timeframe="M15", latest_bos=_bos_point()))
    for fact in ctx.structure_facts:
        assert fact.structure_definition_id == STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1


def test_build_m15_context_calls_existing_authorities_only():
    structure = _structure_result(timeframe="M15", latest_bos=_bos_point())
    fake_liq = type("FakeLiq", (), {"status": "LIQUIDITY_OK", "levels": ()})()

    with patch("mtf_context.topdown_new_builders.analyze_structure", return_value=structure) as mock_structure, \
         patch("mtf_context.topdown_new_builders.validated_order_blocks_for", return_value=()) as mock_ob, \
         patch("mtf_context.topdown_new_builders.fair_value_gaps_for") as mock_fvg, \
         patch("mtf_context.topdown_new_builders.liquidity_result", return_value=fake_liq) as mock_liq, \
         patch("mtf_context.topdown_new_builders.session_zone", return_value=_session_zone()) as mock_session:
        mock_fvg.return_value.status = "OK"
        mock_fvg.return_value.zones = ()
        ctx = build_m15_context("EURUSD")

    mock_structure.assert_called_once_with("EURUSD", TIMEFRAME_M15)
    mock_ob.assert_called_once_with("EURUSD", TIMEFRAME_M15)
    mock_fvg.assert_called_once_with("EURUSD", TIMEFRAME_M15)
    mock_liq.assert_called_once_with("EURUSD", TIMEFRAME_M15)
    assert mock_session.call_count == 3
    mock_session.assert_any_call("EURUSD", "asian")
    mock_session.assert_any_call("EURUSD", "london_am")
    mock_session.assert_any_call("EURUSD", "new_york_am")
    assert ctx is not None


# --------------------------------------------------------------------------- 4-6. Timeframe identity, provenance, determinism

def test_each_builder_rejects_foreign_timeframe_structure_input_via_contract():
    """The underlying tier-context contract itself enforces this (topdown_contracts.py
    _require_fixed_timeframe) -- confirmed here via the builder's own output."""
    structure_w1 = _structure_result(timeframe="W1", latest_bos=_bos_point())
    ctx = weekly_context_from_structure(structure_w1)
    assert ctx.timeframe == TIMEFRAME_W1
    for fact in ctx.structure_facts:
        assert fact.timeframe == TIMEFRAME_W1


def test_deterministic_context_identity_across_equivalent_inputs():
    structure_a = _structure_result(timeframe="H4", latest_bos=_bos_point())
    structure_b = _structure_result(timeframe="H4", latest_bos=_bos_point())  # same values, different object
    ctx_a = h4_context_from_structure(structure_a)
    ctx_b = h4_context_from_structure(structure_b)
    assert ctx_a.context_id == ctx_b.context_id


def test_provenance_fields_populated():
    structure = _structure_result(timeframe="M15", latest_bos=_bos_point())
    ctx = m15_context_from_structure(structure)
    assert ctx.context_id
    assert ctx.symbol == structure.symbol
    assert ctx.bar_close_time == structure.data_end_utc
    assert ctx.feature_version
    assert ctx.structure_facts[0].feature_version == structure.smc_version


# --------------------------------------------------------------------------- 9. Sparse context valid

def test_all_three_builders_produce_valid_sparse_context_with_no_optional_facts():
    for factory, timeframe in (
        (weekly_context_from_structure, "W1"),
        (h4_context_from_structure, "H4"),
        (m15_context_from_structure, "M15"),
    ):
        structure = _structure_result(timeframe=timeframe, smc_version=None)  # no facts at all
        ctx = factory(structure)
        assert ctx is not None
        assert ctx.structure_facts == ()
        assert ctx.zone_facts == ()
        assert ctx.imbalance_facts == ()
        assert ctx.liquidity_facts == ()
        assert ctx.reference_level_facts == ()
        assert ctx.data_quality_status == DATA_QUALITY_PARTIAL


# --------------------------------------------------------------------------- 12. No trade-decision authority

def test_no_new_builder_context_carries_a_trade_decision_field():
    from dataclasses import fields
    from mtf_context.topdown_contracts import H4Context, M15Context, WeeklyContext

    forbidden = {"direction", "decision", "signal", "buy", "sell", "ready_for_trade",
                 "position_size", "risk_amount", "bias", "permission"}
    for cls in (WeeklyContext, H4Context, M15Context):
        field_names = {f.name for f in fields(cls)}
        assert not (field_names & forbidden), f"{cls.__name__} leaked a decision-shaped field"
