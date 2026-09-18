"""TD-1: narrow tests for the top-down market-context data contracts
(src/mtf_context/topdown_contracts.py). Contract-only -- no market data, no
calculation, no cache. See docs/status/TD1_TOPDOWN_CONTEXT_CONTRACT_STATUS.md.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from mtf_context.models import AUTHORITY
from mtf_context.topdown_contracts import (
    ALLOWED_STRUCTURE_DEFINITION_IDS,
    DATA_QUALITY_MISSING,
    DATA_QUALITY_VALID,
    STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_H4,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
    DailyContext,
    H1Context,
    H4Context,
    InvalidDataQualityStatusError,
    InvalidStructureDefinitionError,
    InvalidTimeframeError,
    M5Context,
    M15Context,
    StructureFact,
    TimeframeRequirement,
    TopDownContext,
    WeeklyContext,
    compute_context_id,
)

_BAR_CLOSE = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)  # a Monday W1 close


def _weekly(context_id="TDCTX-W1-abc") -> WeeklyContext:
    return WeeklyContext(
        context_id=context_id, symbol="EURUSD", timeframe=TIMEFRAME_W1,
        source="VANTAGE_DEMO_MT5", bar_close_time=_BAR_CLOSE,
        feature_version="TOPDOWN_CONTEXT_V1", data_quality_status=DATA_QUALITY_VALID,
    )


def _daily(parent_weekly_context_id=None) -> DailyContext:
    return DailyContext(
        context_id="TDCTX-D1-def", symbol="EURUSD", timeframe=TIMEFRAME_D1,
        source="VANTAGE_DEMO_MT5", bar_close_time=_BAR_CLOSE,
        feature_version="TOPDOWN_CONTEXT_V1", data_quality_status=DATA_QUALITY_VALID,
        parent_weekly_context_id=parent_weekly_context_id,
    )


# --------------------------------------------------------------------------
# 1. Contract immutability
# --------------------------------------------------------------------------

def test_structure_fact_is_frozen():
    fact = StructureFact(
        structure_definition_id=STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
        timeframe=TIMEFRAME_H1, event_type="BOS", direction="BULLISH", level=1.0950,
        confirmation_bar_time=_BAR_CLOSE, source="market_structure.tiers",
        feature_version="TOPDOWN_CONTEXT_V1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.level = 1.1000  # type: ignore[misc]


def test_weekly_context_is_frozen():
    ctx = _weekly()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.symbol = "GBPUSD"  # type: ignore[misc]


def test_topdown_context_is_frozen():
    ctx = TopDownContext(
        context_id="TDCTX-TOP-1", symbol="EURUSD", evaluation_time=_BAR_CLOSE,
        data_quality_status=DATA_QUALITY_MISSING,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.symbol = "GBPUSD"  # type: ignore[misc]


# --------------------------------------------------------------------------
# 2. Required identity/provenance fields
# --------------------------------------------------------------------------

def test_weekly_context_rejects_empty_context_id():
    with pytest.raises(ValueError):
        WeeklyContext(
            context_id="", symbol="EURUSD", timeframe=TIMEFRAME_W1, source="VANTAGE_DEMO_MT5",
            bar_close_time=_BAR_CLOSE, feature_version="TOPDOWN_CONTEXT_V1",
            data_quality_status=DATA_QUALITY_VALID,
        )


def test_weekly_context_rejects_empty_source():
    with pytest.raises(ValueError):
        WeeklyContext(
            context_id="TDCTX-W1-x", symbol="EURUSD", timeframe=TIMEFRAME_W1, source="",
            bar_close_time=_BAR_CLOSE, feature_version="TOPDOWN_CONTEXT_V1",
            data_quality_status=DATA_QUALITY_VALID,
        )


def test_weekly_context_rejects_invalid_data_quality_status():
    with pytest.raises(InvalidDataQualityStatusError):
        WeeklyContext(
            context_id="TDCTX-W1-x", symbol="EURUSD", timeframe=TIMEFRAME_W1,
            source="VANTAGE_DEMO_MT5", bar_close_time=_BAR_CLOSE,
            feature_version="TOPDOWN_CONTEXT_V1", data_quality_status="NOT_A_STATUS",
        )


def test_weekly_context_is_serializable_via_to_dict():
    rendered = _weekly().to_dict()
    assert rendered["symbol"] == "EURUSD"
    assert rendered["bar_close_time"] == _BAR_CLOSE.isoformat()


# --------------------------------------------------------------------------
# 3. Timeframe validation
# --------------------------------------------------------------------------

def test_weekly_context_rejects_wrong_timeframe():
    with pytest.raises(InvalidTimeframeError):
        WeeklyContext(
            context_id="TDCTX-W1-x", symbol="EURUSD", timeframe=TIMEFRAME_D1,  # wrong tier
            source="VANTAGE_DEMO_MT5", bar_close_time=_BAR_CLOSE,
            feature_version="TOPDOWN_CONTEXT_V1", data_quality_status=DATA_QUALITY_VALID,
        )


def test_timeframe_requirement_rejects_noncanonical_timeframe():
    with pytest.raises(InvalidTimeframeError):
        TimeframeRequirement(timeframe="W2")


def test_timeframe_requirement_accepts_m1_for_execution_consumers():
    req = TimeframeRequirement(timeframe="M1", required=False)
    assert req.timeframe == "M1"


@pytest.mark.parametrize("cls,timeframe,kwarg", [
    (H4Context, TIMEFRAME_H4, "parent_daily_context_id"),
    (H1Context, TIMEFRAME_H1, "parent_h4_context_id"),
    (M15Context, TIMEFRAME_M15, "parent_h1_context_id"),
    (M5Context, TIMEFRAME_M5, "parent_m15_context_id"),
])
def test_each_tier_rejects_foreign_timeframe(cls, timeframe, kwarg):
    with pytest.raises(InvalidTimeframeError):
        cls(
            context_id="TDCTX-x", symbol="EURUSD", timeframe=TIMEFRAME_W1,  # always wrong
            source="VANTAGE_DEMO_MT5", bar_close_time=_BAR_CLOSE,
            feature_version="TOPDOWN_CONTEXT_V1", data_quality_status=DATA_QUALITY_VALID,
        )


# --------------------------------------------------------------------------
# 4. Deterministic context identity
# --------------------------------------------------------------------------

def test_compute_context_id_is_deterministic():
    kwargs = dict(
        symbol="EURUSD", timeframe=TIMEFRAME_H1, source="VANTAGE_DEMO_MT5",
        bar_close_time=_BAR_CLOSE, feature_version="TOPDOWN_CONTEXT_V1",
    )
    assert compute_context_id(**kwargs) == compute_context_id(**kwargs)


def test_compute_context_id_differs_on_different_bar_close_time():
    kwargs = dict(symbol="EURUSD", timeframe=TIMEFRAME_H1, source="VANTAGE_DEMO_MT5",
                  feature_version="TOPDOWN_CONTEXT_V1")
    id_a = compute_context_id(bar_close_time=_BAR_CLOSE, **kwargs)
    later = _BAR_CLOSE.replace(hour=1)
    id_b = compute_context_id(bar_close_time=later, **kwargs)
    assert id_a != id_b


def test_compute_context_id_rejects_noncanonical_timeframe():
    with pytest.raises(InvalidTimeframeError):
        compute_context_id(
            symbol="EURUSD", timeframe="W2", source="VANTAGE_DEMO_MT5",
            bar_close_time=_BAR_CLOSE, feature_version="TOPDOWN_CONTEXT_V1",
        )


# --------------------------------------------------------------------------
# 5. Parent-context lineage
# --------------------------------------------------------------------------

def test_topdown_context_accepts_consistent_lineage():
    weekly = _weekly(context_id="TDCTX-W1-same")
    daily = _daily(parent_weekly_context_id="TDCTX-W1-same")
    ctx = TopDownContext(
        context_id="TDCTX-TOP-2", symbol="EURUSD", evaluation_time=_BAR_CLOSE,
        data_quality_status=DATA_QUALITY_VALID, weekly=weekly, daily=daily,
    )
    assert ctx.daily.parent_weekly_context_id == ctx.weekly.context_id


def test_topdown_context_rejects_inconsistent_lineage():
    weekly = _weekly(context_id="TDCTX-W1-actual")
    daily = _daily(parent_weekly_context_id="TDCTX-W1-DIFFERENT")
    with pytest.raises(ValueError):
        TopDownContext(
            context_id="TDCTX-TOP-3", symbol="EURUSD", evaluation_time=_BAR_CLOSE,
            data_quality_status=DATA_QUALITY_VALID, weekly=weekly, daily=daily,
        )


def test_topdown_context_allows_partial_lineage_when_parent_not_yet_computed():
    """TD-1 defines no builder -- a DailyContext with a declared parent id but no
    WeeklyContext object supplied yet must not be rejected (parent tier simply hasn't
    been computed by this caller)."""
    daily = _daily(parent_weekly_context_id="TDCTX-W1-not-yet-supplied")
    ctx = TopDownContext(
        context_id="TDCTX-TOP-4", symbol="EURUSD", evaluation_time=_BAR_CLOSE,
        data_quality_status=DATA_QUALITY_VALID,
        daily=daily,
    )
    assert ctx.weekly is None
    assert ctx.daily.parent_weekly_context_id == "TDCTX-W1-not-yet-supplied"


# --------------------------------------------------------------------------
# 6. structure_definition_id is mandatory for structural facts
# --------------------------------------------------------------------------

def test_structure_fact_rejects_empty_definition_id():
    with pytest.raises(InvalidStructureDefinitionError):
        StructureFact(
            structure_definition_id="", timeframe=TIMEFRAME_H1, event_type="BOS",
            direction="BULLISH", level=1.0950, confirmation_bar_time=_BAR_CLOSE,
            source="market_structure.tiers", feature_version="TOPDOWN_CONTEXT_V1",
        )


def test_structure_fact_rejects_unqualified_definition_id():
    """Guards against exactly the confusion TD-0 flagged: a bare 'BOS'/'CHOCH'/'MSS'
    label that could be mistaken for SSC's or Sweep-Retest's own same-named concepts."""
    with pytest.raises(InvalidStructureDefinitionError):
        StructureFact(
            structure_definition_id="BOS", timeframe=TIMEFRAME_H1, event_type="BOS",
            direction="BULLISH", level=1.0950, confirmation_bar_time=_BAR_CLOSE,
            source="market_structure.tiers", feature_version="TOPDOWN_CONTEXT_V1",
        )


def test_structure_fact_accepts_the_one_seeded_definition_id():
    fact = StructureFact(
        structure_definition_id=STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1,
        timeframe=TIMEFRAME_H1, event_type="CHOCH", direction="BEARISH", level=1.0900,
        confirmation_bar_time=_BAR_CLOSE, source="market_structure.smc_adapter",
        feature_version="TOPDOWN_CONTEXT_V1",
    )
    assert fact.structure_definition_id in ALLOWED_STRUCTURE_DEFINITION_IDS


# --------------------------------------------------------------------------
# 7. TopDownContext cannot represent a trade decision
# --------------------------------------------------------------------------

def test_topdown_context_authority_is_fixed_advisory_only():
    ctx = TopDownContext(
        context_id="TDCTX-TOP-5", symbol="EURUSD", evaluation_time=_BAR_CLOSE,
        data_quality_status=DATA_QUALITY_MISSING,
    )
    assert ctx.authority == AUTHORITY == "ADVISORY_ONLY"


def test_topdown_context_rejects_overridden_authority():
    with pytest.raises(ValueError):
        TopDownContext(
            context_id="TDCTX-TOP-6", symbol="EURUSD", evaluation_time=_BAR_CLOSE,
            data_quality_status=DATA_QUALITY_MISSING, authority="LIVE_AUTHORITATIVE",
        )


def test_topdown_context_rejects_overridden_authorization():
    with pytest.raises(ValueError):
        TopDownContext(
            context_id="TDCTX-TOP-7", symbol="EURUSD", evaluation_time=_BAR_CLOSE,
            data_quality_status=DATA_QUALITY_MISSING,
            authorization={"may_create_trade": True, "may_reject_trade": False,
                            "may_change_strategy_decision": False, "may_modify_risk": False,
                            "may_execute": False},
        )


def test_topdown_context_has_no_direction_or_decision_field():
    field_names = {f.name for f in dataclasses.fields(TopDownContext)}
    forbidden = {"direction", "decision", "signal", "buy", "sell", "ready_for_trade",
                 "position_size", "risk_amount"}
    assert not (field_names & forbidden)


# --------------------------------------------------------------------------
# 8. mtf_context remains isolated from execution imports
# --------------------------------------------------------------------------

def test_topdown_contracts_module_is_inside_the_guarded_package():
    """tests/test_mtf_context_execution_guard.py AST-scans every *.py under
    src/mtf_context for forbidden imports/calls/terminal-state literals. This asserts
    the new module actually lives there, so that guard's coverage is not accidental."""
    import mtf_context.topdown_contracts as module

    assert "mtf_context" in module.__name__
