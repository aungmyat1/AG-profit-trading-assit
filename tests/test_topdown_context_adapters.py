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
from liquidity.models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from market_structure.models import StructurePoint, StructurePointKind, StructureResult
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
from supply_demand.ob_contract import OBFamily, OBValidationStatus, ValidatedOrderBlock
from mtf_context.topdown_contracts import (
    DATA_QUALITY_DATA_ERROR,
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    ZONE_DEFINITION_NATIVE_REFERENCE_V1,
    ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_M5,
)
from mtf_context.topdown_context_adapters import (
    D1_CONTEXT_SOURCE,
    H1_CONTEXT_SOURCE,
    M5_CONTEXT_SOURCE,
    ORDER_BLOCK_FEATURE_VERSION,
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
    build_d1_context, previous_day_high_low, and previous_week_high_low exactly once
    each and use their results verbatim -- it must never call
    market_structure/liquidity/supply_demand OB/FVG functions directly itself.
    All three existing-authority calls are mocked so this test never touches a live
    MT5 terminal."""
    structure = _structure_result(latest_bos=_bos_point())
    fake_d1 = _d1_context(structure)

    with patch("mtf_context.topdown_context_adapters.build_d1_context", return_value=fake_d1) as mock_build, \
         patch("mtf_context.topdown_context_adapters.previous_day_high_low", return_value=None) as mock_pdh, \
         patch("mtf_context.topdown_context_adapters.previous_week_high_low", return_value=None) as mock_pwh:
        ctx = build_daily_context("EURUSD")

    mock_build.assert_called_once_with("EURUSD")
    mock_pdh.assert_called_once_with("EURUSD")
    mock_pwh.assert_called_once_with("EURUSD")
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
    """No-redetection proof, all six existing-authority calls mocked so this stays a
    deterministic unit test with no live MT5 dependency."""
    structure = _structure_result(timeframe="H1", latest_bos=_bos_point())
    fake_d1 = _d1_context(_structure_result(timeframe="D1"))
    fake_h1_setup = _h1_setup_context()

    with patch("mtf_context.topdown_context_adapters.build_d1_context", return_value=fake_d1) as mock_d1, \
         patch("mtf_context.topdown_context_adapters.build_h1_setup_context", return_value=fake_h1_setup) as mock_h1, \
         patch("mtf_context.topdown_context_adapters.analyze_structure", return_value=structure) as mock_structure, \
         patch("mtf_context.topdown_context_adapters.validated_order_blocks_for", return_value=()) as mock_ob, \
         patch("mtf_context.topdown_context_adapters.fair_value_gaps_for") as mock_fvg, \
         patch("mtf_context.topdown_context_adapters.session_zone", return_value=None) as mock_session:
        mock_fvg.return_value.status = "OK"
        mock_fvg.return_value.zones = ()
        ctx = build_h1_context("EURUSD")

    mock_d1.assert_called_once_with("EURUSD")
    mock_h1.assert_called_once_with("EURUSD", fake_d1)
    mock_structure.assert_called_once_with("EURUSD", TIMEFRAME_H1)
    mock_ob.assert_called_once_with("EURUSD", TIMEFRAME_H1)
    mock_fvg.assert_called_once_with("EURUSD", TIMEFRAME_H1)
    mock_session.assert_called_once_with("EURUSD", "asian")
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
    """All four existing-authority calls mocked so this stays a deterministic unit
    test with no live MT5 dependency."""
    structure = _structure_result(timeframe="M5", latest_bos=_bos_point())
    fake_liq = type("FakeLiq", (), {"status": "LIQUIDITY_OK", "levels": ()})()
    with patch("mtf_context.topdown_context_adapters.analyze_structure", return_value=structure) as mock_structure, \
         patch("mtf_context.topdown_context_adapters.validated_order_blocks_for", return_value=()) as mock_ob, \
         patch("mtf_context.topdown_context_adapters.fair_value_gaps_for") as mock_fvg, \
         patch("mtf_context.topdown_context_adapters.liquidity_result", return_value=fake_liq) as mock_liq:
        mock_fvg.return_value.status = "OK"
        mock_fvg.return_value.zones = ()
        ctx = build_m5_context("EURUSD")

    mock_structure.assert_called_once_with("EURUSD", TIMEFRAME_M5)
    mock_ob.assert_called_once_with("EURUSD", TIMEFRAME_M5)
    mock_fvg.assert_called_once_with("EURUSD", TIMEFRAME_M5)
    mock_liq.assert_called_once_with("EURUSD", TIMEFRAME_M5)
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


# --------------------------------------------------------------------------- TD-3A: fact-type mapping (D1/H1/M5)

def _fvg_zone(timeframe="D1", low=1.090, high=1.095, direction=ZoneDirection.BULLISH, origin_time=_BAR_CLOSE) -> ZoneResult:
    return ZoneResult(symbol="EURUSD", timeframe=timeframe, family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=direction, status=ZoneStatus.FRESH, source="smc.fvg",
                       low=low, high=high, origin_time=origin_time)


def _reference_zone(family=ZoneFamily.PREVIOUS_DAY, timeframe="D1", low=1.07, high=1.10, origin_time=_BAR_CLOSE) -> ZoneResult:
    return ZoneResult(symbol="EURUSD", timeframe=timeframe, family=family, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.NONE, status=ZoneStatus.FRESH,
                       source="mt5 D1 candles", low=low, high=high, origin_time=origin_time)


def _validated_ob(timeframe="H1", role=ZoneRole.DEMAND, low=1.080, high=1.085, origin_time=_BAR_CLOSE,
                   structure_event=None) -> ValidatedOrderBlock:
    candidate = ZoneResult(symbol="EURUSD", timeframe=timeframe, family=ZoneFamily.ORDER_BLOCK, role=role,
                            direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="smc.ob",
                            low=low, high=high, origin_time=origin_time)
    return ValidatedOrderBlock(symbol="EURUSD", timeframe=timeframe, family=OBFamily.PIVOT_OB,
                                status=OBValidationStatus.VALID, direction=ZoneDirection.BULLISH,
                                low=low, high=high, origin_time=origin_time, candidate=candidate,
                                structure_event=structure_event)


def _liquidity_level(timeframe="D1", side=LiquiditySide.BUY_SIDE, source="PDH", price=1.10,
                      origin_time=_BAR_CLOSE, status=LiquidityStatus.UNSWEPT) -> LiquidityLevel:
    return LiquidityLevel(symbol="EURUSD", timeframe=timeframe, side=side, source=source,
                           price=price, origin_time=origin_time, status=status)


def test_d1_imbalance_facts_mapped_from_gap_liquidity():
    structure = _structure_result(latest_bos=_bos_point())
    d1 = D1Context(symbol="EURUSD", as_of=None, status="READY", evidence={"structure": structure},
                    gap_liquidity=(_fvg_zone(),))

    ctx = daily_context_from_d1(d1)

    assert len(ctx.imbalance_facts) == 1
    assert ctx.imbalance_facts[0].zone_definition_id == ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1
    assert ctx.imbalance_facts[0].direction == "BULLISH"


def test_d1_liquidity_facts_mapped_from_evidence_liquidity():
    structure = _structure_result(latest_bos=_bos_point())
    liq_result = LiquidityResult(symbol="EURUSD", timeframe="D1", status="LIQUIDITY_OK",
                                  levels=(_liquidity_level(),))
    d1 = D1Context(symbol="EURUSD", as_of=None, status="READY",
                    evidence={"structure": structure, "liquidity": liq_result})

    ctx = daily_context_from_d1(d1)

    assert len(ctx.liquidity_facts) == 1
    assert ctx.liquidity_facts[0].side == "BUY_SIDE"
    assert ctx.liquidity_facts[0].source == "PDH"


def test_d1_reference_level_facts_mapped_from_injected_zones():
    structure = _structure_result(latest_bos=_bos_point())
    d1 = D1Context(symbol="EURUSD", as_of=None, status="READY", evidence={"structure": structure})

    ctx = daily_context_from_d1(
        d1,
        previous_day_zone=_reference_zone(family=ZoneFamily.PREVIOUS_DAY),
        previous_week_zone=_reference_zone(family=ZoneFamily.PREVIOUS_WEEK),
    )

    assert len(ctx.reference_level_facts) == 2
    families = {fact.family for fact in ctx.reference_level_facts}
    assert families == {"PREVIOUS_DAY", "PREVIOUS_WEEK"}
    assert all(fact.zone_definition_id == ZONE_DEFINITION_NATIVE_REFERENCE_V1 for fact in ctx.reference_level_facts)


def test_d1_reference_level_facts_absent_when_not_injected():
    structure = _structure_result(latest_bos=_bos_point())
    d1 = D1Context(symbol="EURUSD", as_of=None, status="READY", evidence={"structure": structure})
    ctx = daily_context_from_d1(d1)
    assert ctx.reference_level_facts == ()


def test_h1_liquidity_facts_mapped_from_evidence_liquidity():
    structure = _structure_result(timeframe="H1", latest_bos=_bos_point())
    liq_result = LiquidityResult(symbol="EURUSD", timeframe="H1", status="LIQUIDITY_OK",
                                  levels=(_liquidity_level(timeframe="H1"),))
    h1_setup = H1SetupContext(symbol="EURUSD", as_of=None, status=H1_POI_IDENTIFIED,
                               evidence={"liquidity": liq_result})

    ctx = h1_context_from_sources(h1_setup, structure)

    assert len(ctx.liquidity_facts) == 1


def test_h1_zone_facts_mapped_from_unfiltered_order_blocks_not_poi_candidates():
    """H1SetupContext.poi_candidates is role-filtered by D1 permission -- the ZoneFact
    mapping must come from a fresh, UNFILTERED validated_order_blocks_for() call
    instead (passed in here as `order_blocks`), never from h1_setup.poi_candidates."""
    structure = _structure_result(timeframe="H1", latest_bos=_bos_point())
    h1_setup = _h1_setup_context()
    obs = (_validated_ob(role=ZoneRole.DEMAND), _validated_ob(role=ZoneRole.SUPPLY, low=1.2, high=1.21))

    ctx = h1_context_from_sources(h1_setup, structure, order_blocks=obs)

    assert len(ctx.zone_facts) == 2
    roles = {fact.role for fact in ctx.zone_facts}
    assert roles == {"DEMAND", "SUPPLY"}  # both roles present -- not filtered by D1 permission
    assert all(fact.feature_version == ORDER_BLOCK_FEATURE_VERSION for fact in ctx.zone_facts)


def test_h1_imbalance_and_reference_level_facts_mapped_from_injected_sources():
    structure = _structure_result(timeframe="H1", latest_bos=_bos_point())
    h1_setup = _h1_setup_context()

    ctx = h1_context_from_sources(
        h1_setup, structure,
        fvg_zones=(_fvg_zone(timeframe="H1"),),
        asian_session_zone=_reference_zone(family=ZoneFamily.SESSION, timeframe="H1"),
    )

    assert len(ctx.imbalance_facts) == 1
    assert len(ctx.reference_level_facts) == 1
    assert ctx.reference_level_facts[0].family == "SESSION"


def test_m5_zone_imbalance_liquidity_facts_mapped():
    structure = _structure_result(timeframe="M5", latest_bos=_bos_point())
    obs = (_validated_ob(timeframe="M5"),)
    fvgs = (_fvg_zone(timeframe="M5"),)
    levels = (_liquidity_level(timeframe="M5"),)

    ctx = m5_context_from_structure(structure, order_blocks=obs, fvg_zones=fvgs, liquidity_levels=levels)

    assert len(ctx.zone_facts) == 1
    assert len(ctx.imbalance_facts) == 1
    assert len(ctx.liquidity_facts) == 1


def test_zone_fact_carries_structure_confirmation_time_when_available():
    confirming_point = StructurePoint(time_utc=_BAR_CLOSE, price=1.083, kind=StructurePointKind.BULLISH_BOS)
    ob = _validated_ob(structure_event=confirming_point)

    from mtf_context.topdown_context_adapters import _zone_facts_from_validated_obs
    facts = _zone_facts_from_validated_obs((ob,), TIMEFRAME_H1)

    assert facts[0].structure_confirmation_time == _BAR_CLOSE


def test_facts_with_missing_bounds_are_skipped_not_fabricated():
    """A ZoneResult/ValidatedOrderBlock/LiquidityLevel missing low/high/origin_time
    must be silently skipped, never given a fabricated placeholder value."""
    from mtf_context.topdown_context_adapters import (
        _imbalance_facts_from_zones,
        _liquidity_facts_from_levels,
        _zone_facts_from_validated_obs,
    )

    incomplete_zone = ZoneResult(symbol="EURUSD", timeframe="D1", family=ZoneFamily.FVG,
                                  role=ZoneRole.REFERENCE, direction=ZoneDirection.BULLISH,
                                  status=ZoneStatus.UNKNOWN, source="smc.fvg")  # no low/high/origin_time
    assert _imbalance_facts_from_zones((incomplete_zone,), "D1") == ()

    incomplete_ob = ValidatedOrderBlock(symbol="EURUSD", timeframe="H1", family=OBFamily.PIVOT_OB,
                                         status=OBValidationStatus.VALID, direction=ZoneDirection.BULLISH,
                                         low=None, high=None, origin_time=None,
                                         candidate=_fvg_zone())
    assert _zone_facts_from_validated_obs((incomplete_ob,), "H1") == ()

    incomplete_level = LiquidityLevel(symbol="EURUSD", timeframe="D1", side=LiquiditySide.BUY_SIDE,
                                       source="PDH", price=1.1, origin_time=None, status=LiquidityStatus.UNSWEPT)
    assert _liquidity_facts_from_levels((incomplete_level,), "D1") == ()


# --------------------------------------------------------------------------- 12/13. Semantic firewall

def test_ssc_and_sweep_retest_semantics_cannot_be_mislabeled_smc():
    """Static proof (complementing the AST guard in
    test_topdown_context_adapters_no_redetection.py): the only structure_definition_id
    this module ever writes is the SMC one -- there is no code path in
    topdown_context_adapters.py capable of writing an SSC or Sweep-Retest label into a
    StructureFact/ZoneFact/ImbalanceFact, because it never imports either module."""
    import ast
    from pathlib import Path

    source = Path("src/mtf_context/topdown_context_adapters.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literal_strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "S1" not in literal_strings and "S2" not in literal_strings and "S3" not in literal_strings
    assert "MSS" not in literal_strings
    assert "SSC" not in literal_strings
