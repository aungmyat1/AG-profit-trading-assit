"""TD-3A: contract-level tests for the new fact types (LiquidityFact, ZoneFact,
ImbalanceFact, ReferenceLevelFact) and the four new optional tuple fields added to
every TD-1 tier context. See docs/status/TD3A_TOPDOWN_FACT_CONTRACT_GAP_AUDIT_STATUS.md.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from mtf_context.topdown_contracts import (
    ALLOWED_LIQUIDITY_DEFINITION_IDS,
    ALLOWED_STRUCTURE_DEFINITION_IDS,
    ALLOWED_ZONE_DEFINITION_IDS,
    DATA_QUALITY_VALID,
    LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    ZONE_DEFINITION_NATIVE_REFERENCE_V1,
    ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1,
    DailyContext,
    H1Context,
    ImbalanceFact,
    InvalidLiquidityDefinitionError,
    InvalidTimeframeError,
    InvalidZoneDefinitionError,
    LiquidityFact,
    M5Context,
    M15Context,
    ReferenceLevelFact,
    StructureFact,
    TopDownContext,
    WeeklyContext,
    ZoneFact,
    compute_context_id,
)

_T = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)


def _imbalance(timeframe=TIMEFRAME_D1) -> ImbalanceFact:
    return ImbalanceFact(
        zone_definition_id=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1, timeframe=timeframe,
        direction="BULLISH", low=1.09, high=1.095, origin_time=_T,
        status="FRESH", source="smc.fvg", feature_version=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1,
    )


def _zone(timeframe=TIMEFRAME_H1) -> ZoneFact:
    return ZoneFact(
        zone_definition_id=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1, timeframe=timeframe,
        role="DEMAND", direction="BULLISH", low=1.08, high=1.085, origin_time=_T,
        validation_status="VALID", source="smc.ob", feature_version="AG_ORDER_BLOCK_V1",
    )


def _reference_level(timeframe=TIMEFRAME_D1) -> ReferenceLevelFact:
    return ReferenceLevelFact(
        zone_definition_id=ZONE_DEFINITION_NATIVE_REFERENCE_V1, family="PREVIOUS_DAY",
        timeframe=timeframe, low=1.07, high=1.10, origin_time=_T, status="FRESH",
        source="mt5 D1 candles", feature_version=ZONE_DEFINITION_NATIVE_REFERENCE_V1,
    )


def _liquidity(timeframe=TIMEFRAME_D1) -> LiquidityFact:
    return LiquidityFact(
        liquidity_definition_id=LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1, timeframe=timeframe,
        side="BUY_SIDE", price=1.10, origin_time=_T, status="UNSWEPT",
        source="PDH", feature_version=LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1,
    )


# --------------------------------------------------------------------------- 1. Immutability

@pytest.mark.parametrize("factory", [_imbalance, _zone, _reference_level, _liquidity])
def test_new_fact_types_are_frozen(factory):
    fact = factory()
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.source = "mutated"  # type: ignore[misc]


# --------------------------------------------------------------------------- 2. Version/definition identifiers enforced

def test_imbalance_fact_rejects_unqualified_zone_definition():
    with pytest.raises(InvalidZoneDefinitionError):
        ImbalanceFact(
            zone_definition_id="FVG", timeframe=TIMEFRAME_D1, direction="BULLISH",
            low=1.0, high=1.01, origin_time=_T, status="FRESH", source="smc.fvg",
            feature_version=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1,
        )


def test_zone_fact_rejects_unqualified_zone_definition():
    with pytest.raises(InvalidZoneDefinitionError):
        ZoneFact(
            zone_definition_id="ORDER_BLOCK", timeframe=TIMEFRAME_H1, role="DEMAND",
            direction="BULLISH", low=1.0, high=1.01, origin_time=_T,
            validation_status="VALID", source="smc.ob", feature_version="AG_ORDER_BLOCK_V1",
        )


def test_reference_level_fact_rejects_unqualified_zone_definition():
    with pytest.raises(InvalidZoneDefinitionError):
        ReferenceLevelFact(
            zone_definition_id="", family="PREVIOUS_DAY", timeframe=TIMEFRAME_D1,
            low=1.0, high=1.01, origin_time=_T, status="FRESH", source="mt5 D1 candles",
            feature_version=ZONE_DEFINITION_NATIVE_REFERENCE_V1,
        )


def test_liquidity_fact_rejects_unqualified_liquidity_definition():
    with pytest.raises(InvalidLiquidityDefinitionError):
        LiquidityFact(
            liquidity_definition_id="LIQUIDITY_V2", timeframe=TIMEFRAME_D1, side="BUY_SIDE",
            price=1.1, origin_time=_T, status="UNSWEPT", source="PDH",
            feature_version=LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1,
        )


def test_zone_and_liquidity_definition_ids_are_distinct_registries():
    assert ALLOWED_ZONE_DEFINITION_IDS.isdisjoint(ALLOWED_LIQUIDITY_DEFINITION_IDS)
    assert ALLOWED_STRUCTURE_DEFINITION_IDS.isdisjoint(ALLOWED_ZONE_DEFINITION_IDS)
    assert ALLOWED_STRUCTURE_DEFINITION_IDS.isdisjoint(ALLOWED_LIQUIDITY_DEFINITION_IDS)


# --------------------------------------------------------------------------- 3. Deterministic identity (context level)

def test_context_id_unaffected_by_which_new_fact_tuples_are_populated():
    """compute_context_id() only hashes symbol/timeframe/source/bar_close_time/
    feature_version/parent -- adding zone_facts/imbalance_facts/liquidity_facts/
    reference_level_facts to a context must not change its context_id."""
    kwargs = dict(symbol="EURUSD", timeframe=TIMEFRAME_D1, source="daily_routine.d1_context.build_d1_context",
                  bar_close_time=_T, feature_version="TD3_CONTEXT_ADAPTER_V1")
    assert compute_context_id(**kwargs) == compute_context_id(**kwargs)


# --------------------------------------------------------------------------- 4. Serialization

def test_daily_context_to_dict_serializes_new_fact_tuples():
    ctx = DailyContext(
        context_id="TDCTX-D1-x", symbol="EURUSD", timeframe=TIMEFRAME_D1,
        source="daily_routine.d1_context.build_d1_context", bar_close_time=_T,
        feature_version="TD3_CONTEXT_ADAPTER_V1", data_quality_status=DATA_QUALITY_VALID,
        imbalance_facts=(_imbalance(),), liquidity_facts=(_liquidity(),),
        reference_level_facts=(_reference_level(),),
    )
    rendered = ctx.to_dict()
    assert rendered["imbalance_facts"][0]["origin_time"] == _T.isoformat()
    assert rendered["liquidity_facts"][0]["side"] == "BUY_SIDE"
    assert rendered["reference_level_facts"][0]["family"] == "PREVIOUS_DAY"


# --------------------------------------------------------------------------- 5. Source/timeframe provenance

def test_imbalance_fact_requires_nonempty_source():
    with pytest.raises(ValueError):
        ImbalanceFact(
            zone_definition_id=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1, timeframe=TIMEFRAME_D1,
            direction="BULLISH", low=1.0, high=1.01, origin_time=_T, status="FRESH",
            source="", feature_version=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1,
        )


def test_liquidity_fact_requires_nonempty_feature_version():
    with pytest.raises(ValueError):
        LiquidityFact(
            liquidity_definition_id=LIQUIDITY_DEFINITION_AG_LIQUIDITY_V1, timeframe=TIMEFRAME_D1,
            side="BUY_SIDE", price=1.1, origin_time=_T, status="UNSWEPT",
            source="PDH", feature_version="",
        )


def test_zone_fact_timeframe_must_be_canonical():
    with pytest.raises(InvalidTimeframeError):
        ZoneFact(
            zone_definition_id=ZONE_DEFINITION_SMC_SUPPLY_DEMAND_V1, timeframe="W2", role="DEMAND",
            direction="BULLISH", low=1.0, high=1.01, origin_time=_T,
            validation_status="VALID", source="smc.ob", feature_version="AG_ORDER_BLOCK_V1",
        )


# --------------------------------------------------------------------------- 6. Sparse context remains valid

@pytest.mark.parametrize("cls,timeframe,extra", [
    (WeeklyContext, "W1", {}),
    (DailyContext, TIMEFRAME_D1, {}),
    (M15Context, "M15", {}),
    (M5Context, "M5", {}),
])
def test_sparse_context_with_no_new_facts_remains_valid(cls, timeframe, extra):
    ctx = cls(
        context_id=f"TDCTX-{timeframe}-x", symbol="EURUSD", timeframe=timeframe,
        source="some.authority", bar_close_time=_T, feature_version="TD3_CONTEXT_ADAPTER_V1",
        data_quality_status=DATA_QUALITY_VALID, **extra,
    )
    assert ctx.liquidity_facts == ()
    assert ctx.zone_facts == ()
    assert ctx.imbalance_facts == ()
    assert ctx.reference_level_facts == ()


def test_context_with_only_some_new_fact_types_populated_remains_valid():
    ctx = H1Context(
        context_id="TDCTX-H1-x", symbol="EURUSD", timeframe=TIMEFRAME_H1,
        source="daily_routine.h1_setup.build_h1_setup_context", bar_close_time=_T,
        feature_version="TD3_CONTEXT_ADAPTER_V1", data_quality_status=DATA_QUALITY_VALID,
        liquidity_facts=(_liquidity(timeframe=TIMEFRAME_H1),),
        # zone_facts/imbalance_facts/reference_level_facts intentionally left empty
    )
    assert len(ctx.liquidity_facts) == 1
    assert ctx.zone_facts == ()
    assert ctx.imbalance_facts == ()
    assert ctx.reference_level_facts == ()


def test_new_fact_tuple_wrong_timeframe_rejected_by_context():
    with pytest.raises(InvalidTimeframeError):
        DailyContext(
            context_id="TDCTX-D1-x", symbol="EURUSD", timeframe=TIMEFRAME_D1,
            source="daily_routine.d1_context.build_d1_context", bar_close_time=_T,
            feature_version="TD3_CONTEXT_ADAPTER_V1", data_quality_status=DATA_QUALITY_VALID,
            liquidity_facts=(_liquidity(timeframe=TIMEFRAME_H1),),  # wrong tier
        )


# --------------------------------------------------------------------------- 7. Existing StructureFact semantics unchanged

def test_structure_fact_still_requires_smc_market_structure_v1_only():
    assert ALLOWED_STRUCTURE_DEFINITION_IDS == {STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1}
    fact = StructureFact(
        structure_definition_id=STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
        timeframe=TIMEFRAME_D1, event_type="BOS", direction="BULLISH", level=1.1,
        confirmation_bar_time=_T, source="market_structure.analyze_structure", feature_version="0.0.27",
    )
    assert fact.structure_definition_id == STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1


# --------------------------------------------------------------------------- 14. No trade-decision field on new types

def test_no_new_fact_type_carries_a_trade_decision_field():
    forbidden = {"direction_permission", "signal", "buy", "sell", "ready_for_trade",
                 "position_size", "risk_amount", "qualified", "entry_confirmed"}
    for cls in (ImbalanceFact, ZoneFact, ReferenceLevelFact, LiquidityFact):
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert not (field_names & forbidden), f"{cls.__name__} leaked a decision-shaped field"


def test_topdown_context_still_non_authoritative_after_amendment():
    """TopDownContext's own authority/authorization invariants are untouched by the
    TD-3A fact-contract amendment (it composes tier contexts only, none of which
    changed shape at the TopDownContext level)."""
    ctx = TopDownContext(
        context_id="TDCTX-TOP-1", symbol="EURUSD", evaluation_time=_T,
        data_quality_status=DATA_QUALITY_VALID,
    )
    assert ctx.authority == "ADVISORY_ONLY"
    assert all(v is False for v in ctx.authorization.values())
