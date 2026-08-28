"""Tests for AG_ENTRY_CONFIRMATION_V2_1 (SMC_SWEEP_SHIFT_ARRAY_V1) -- sweep_shift.py,
entry_array.py, engine_v2_1.py. Deterministic-fact tests only. Purely additive: V1/V2
test files are untouched and still pass.
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.engine_v2_1 import SweepShiftArrayRequest, evaluate_reversal_sweep_shift, evaluate_sweep_shift_array
from entry_confirmation.entry_array import evaluate_entry_array, fvg_associated_with_leg
from entry_confirmation.gap import evaluate_gap_context
from entry_confirmation.models import CandidateDirection, ConfirmationState, DisplacementEvidence, StructureAlignment
from entry_confirmation.sweep_shift import classify_wick_or_close, evaluate_pivot_context, evaluate_structure_shift_quality
from liquidity import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure import StructurePoint, StructurePointKind
from market_structure.models import StructureTier
from strategy_engine.session import Candle
from supply_demand import ValidatedOrderBlock
from supply_demand.ob_contract import OBFamily, OBValidationStatus
from supply_demand import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc


def _candle(o, h, l, c, when):
    return Candle(time=when, open=o, high=h, low=l, close=c, volume=1.0)


def _sweep_level(side, price=1.0950, sweep_time=None, reclaim_time=None, status=LiquidityStatus.RECLAIMED):
    return LiquidityLevel(
        symbol="EURUSD", timeframe="H1", side=side,
        source="SWING_LOW" if side == LiquiditySide.SELL_SIDE else "SWING_HIGH",
        price=price, origin_time=dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC), status=status,
        sweep_time=sweep_time, reclaim_time=reclaim_time,
    )


def _tier(tier_name, swing_length, prices_and_kinds):
    swings = tuple(
        StructurePoint(time_utc=dt.datetime(2026, 1, 5, h, 0, tzinfo=UTC), price=p, kind=k)
        for h, p, k in prices_and_kinds
    )
    return StructureTier(tier=tier_name, swing_length=swing_length, direction="BULLISH", swings=swings, events=())


def _zone(family=ZoneFamily.FVG, low=1.0960, high=1.0970, status=ZoneStatus.FRESH, origin_time=None):
    return ZoneResult(
        symbol="EURUSD", timeframe="M5", family=family, role=ZoneRole.REFERENCE, direction=ZoneDirection.BULLISH,
        status=status, source="test", low=low, high=high, origin_time=origin_time,
    )


def _ob(low=1.0955, high=1.0965, origin_time=None, structure_event=None):
    return ValidatedOrderBlock(
        symbol="EURUSD", timeframe="M5", family=OBFamily.PIVOT_OB, status=OBValidationStatus.VALID,
        direction=ZoneDirection.BULLISH, low=low, high=high, origin_time=origin_time,
        candidate=_zone(family=ZoneFamily.ORDER_BLOCK, low=low, high=high, origin_time=origin_time),
        structure_event=structure_event,
    )


# ---------------------------------------------------------------------------
# Wick != CHoCH (spec rules 7, 39)
# ---------------------------------------------------------------------------

def test_wick_through_swing_low_with_close_back_above_is_fakeout_not_close_break():
    candle = _candle(1.0955, 1.0958, 1.0940, 1.0954, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    result = classify_wick_or_close(candle, level_price=1.0950, side=LiquiditySide.SELL_SIDE)
    assert result["wick_through"] is True
    assert result["close_through"] is False
    assert result["fakeout"] is True


def test_wick_through_swing_high_with_close_back_below_is_fakeout_bullish_mirror():
    candle = _candle(1.1045, 1.1060, 1.1042, 1.1046, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    result = classify_wick_or_close(candle, level_price=1.1050, side=LiquiditySide.BUY_SIDE)
    assert result["wick_through"] is True
    assert result["close_through"] is False
    assert result["fakeout"] is True


def test_close_beyond_level_is_not_a_fakeout():
    candle = _candle(1.0955, 1.0958, 1.0940, 1.0938, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    result = classify_wick_or_close(candle, level_price=1.0950, side=LiquiditySide.SELL_SIDE)
    assert result["close_through"] is True
    assert result["fakeout"] is False


# ---------------------------------------------------------------------------
# Pivot quality (spec rules 10-11, 43)
# ---------------------------------------------------------------------------

def test_pivot_matching_external_tier_is_external_swing():
    ext = _tier("EXTERNAL", 50, [(8, 1.0950, StructurePointKind.SWING_LOW)])
    ctx = evaluate_pivot_context(1.0950, external_tier=ext, internal_tier=None)
    assert ctx.pivot_role == "EXTERNAL_SWING"


def test_pivot_not_matching_any_tier_is_micro_pivot():
    ext = _tier("EXTERNAL", 50, [(8, 1.2000, StructurePointKind.SWING_LOW)])
    intl = _tier("INTERNAL", 5, [(9, 1.1500, StructurePointKind.SWING_LOW)])
    ctx = evaluate_pivot_context(1.0950, external_tier=ext, internal_tier=intl)
    assert ctx.pivot_role == "MICRO_PIVOT"


def test_pivot_tolerance_matches_a_near_miss_float_from_independent_computation():
    # Same underlying swing, but two independently-computed StructureResult/
    # TieredStructureResult calls disagree in the last few decimal places (live
    # validation finding, AG_ENTRY_CONFIRMATION_V2_1_LIVE 2026-08-28). Exact equality
    # would misclassify this as MICRO_PIVOT; a caller-supplied tolerance fixes it.
    ext = _tier("EXTERNAL", 50, [(8, 1.09503, StructurePointKind.SWING_LOW)])
    ctx = evaluate_pivot_context(1.09500, external_tier=ext, tolerance_price=0.0001)
    assert ctx.pivot_role == "EXTERNAL_SWING"


def test_pivot_tolerance_does_not_rubber_stamp_a_genuinely_different_price():
    ext = _tier("EXTERNAL", 50, [(8, 1.2000, StructurePointKind.SWING_LOW)])
    intl = _tier("INTERNAL", 5, [(9, 1.1500, StructurePointKind.SWING_LOW)])
    ctx = evaluate_pivot_context(1.0950, external_tier=ext, internal_tier=intl, tolerance_price=0.0001)
    assert ctx.pivot_role == "MICRO_PIVOT"


def test_pivot_tolerance_defaults_to_near_exact_equality_when_omitted():
    ext = _tier("EXTERNAL", 50, [(8, 1.09503, StructurePointKind.SWING_LOW)])
    ctx = evaluate_pivot_context(1.09500, external_tier=ext)
    assert ctx.pivot_role == "MICRO_PIVOT"


# ---------------------------------------------------------------------------
# Structure shift quality composition (spec rules 26, 42-43)
# ---------------------------------------------------------------------------

def test_close_break_without_displacement_is_valid_weak_not_strong():
    pivot = evaluate_pivot_context(1.0950, external_tier=_tier("EXTERNAL", 50, [(8, 1.0950, StructurePointKind.SWING_LOW)]))
    structure_shift = StructureAlignment(status=ConfirmationState.PASS, event_kind="BULLISH_CHOCH",
                                          event_time=dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC), event_price=1.0950)
    displacement = DisplacementEvidence(status=ConfirmationState.FAIL, direction="BULLISH")
    quality = evaluate_structure_shift_quality(
        sweep_present=True, post_sweep_ordering=True, pivot_context=pivot,
        structure_shift=structure_shift, displacement=displacement, fvg_created=False,
    )
    assert quality.status == "VALID_WEAK"


def test_displacement_without_valid_pivot_is_invalid_pivot():
    pivot = evaluate_pivot_context(1.0950, external_tier=_tier("EXTERNAL", 50, [(8, 1.2000, StructurePointKind.SWING_LOW)]),
                                    internal_tier=_tier("INTERNAL", 5, [(9, 1.1500, StructurePointKind.SWING_LOW)]))
    structure_shift = StructureAlignment(status=ConfirmationState.PASS, event_kind="BULLISH_CHOCH",
                                          event_time=dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC), event_price=1.0950)
    displacement = DisplacementEvidence(status=ConfirmationState.PASS, direction="BULLISH")
    quality = evaluate_structure_shift_quality(
        sweep_present=True, post_sweep_ordering=True, pivot_context=pivot,
        structure_shift=structure_shift, displacement=displacement, fvg_created=True,
    )
    assert quality.status == "INVALID_PIVOT"


def test_sweep_without_structure_close_is_fakeout_wick_quality():
    pivot = evaluate_pivot_context(1.0950)
    structure_shift = StructureAlignment(status=ConfirmationState.UNAVAILABLE)
    displacement = DisplacementEvidence(status=ConfirmationState.UNAVAILABLE)
    quality = evaluate_structure_shift_quality(
        sweep_present=True, post_sweep_ordering=None, pivot_context=pivot,
        structure_shift=structure_shift, displacement=displacement, fvg_created=False,
    )
    assert quality.status == "FAKEOUT_WICK"


def test_no_fvg_does_not_invalidate_structure_confirmation():
    # spec rule 16/52: NO FVG != NO CHoCH -- structure quality may still be VALID_STRONG.
    pivot = evaluate_pivot_context(1.0950, external_tier=_tier("EXTERNAL", 50, [(8, 1.0950, StructurePointKind.SWING_LOW)]))
    structure_shift = StructureAlignment(status=ConfirmationState.PASS, event_kind="BULLISH_CHOCH",
                                          event_time=dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC), event_price=1.0950)
    displacement = DisplacementEvidence(status=ConfirmationState.PASS, direction="BULLISH")
    quality = evaluate_structure_shift_quality(
        sweep_present=True, post_sweep_ordering=True, pivot_context=pivot,
        structure_shift=structure_shift, displacement=displacement, fvg_created=False,
    )
    assert quality.status == "VALID_STRONG"
    assert quality.fvg_created is False


# ---------------------------------------------------------------------------
# FVG association: only the leg's own gap counts (spec rules 17, 44-45)
# ---------------------------------------------------------------------------

def test_old_unrelated_fvg_not_accepted_as_shift_footprint():
    gap_ctx = evaluate_gap_context(_zone(status=ZoneStatus.FRESH, low=1.0960, high=1.0970))
    leg_start = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    leg_end = dt.datetime(2026, 1, 5, 11, 30, tzinfo=UTC)
    old_origin = dt.datetime(2026, 1, 3, 9, 0, tzinfo=UTC)
    assert fvg_associated_with_leg(gap_ctx, leg_start, leg_end, old_origin) is False


def test_fvg_within_leg_window_is_accepted():
    gap_ctx = evaluate_gap_context(_zone(status=ZoneStatus.FRESH, low=1.0960, high=1.0970))
    leg_start = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    leg_end = dt.datetime(2026, 1, 5, 11, 30, tzinfo=UTC)
    origin = dt.datetime(2026, 1, 5, 11, 10, tzinfo=UTC)
    assert fvg_associated_with_leg(gap_ctx, leg_start, leg_end, origin) is True


# ---------------------------------------------------------------------------
# Entry array selection / confluence (spec rules 19-22)
# ---------------------------------------------------------------------------

def test_entry_array_fvg_only_uses_midpoint_and_waits_for_price():
    gap_ctx = evaluate_gap_context(_zone(status=ZoneStatus.FRESH, low=1.0960, high=1.0970))
    array = evaluate_entry_array(gap_ctx, True, None, False, CandidateDirection.LONG)
    assert array.entry_array_type == "FVG"
    assert array.entry_reference == 1.0965
    assert array.entry_status == "WAITING_ENTRY_PRICE"


def test_entry_array_reference_available_once_price_reaches_it():
    gap_ctx = evaluate_gap_context(_zone(status=ZoneStatus.FRESH, low=1.0960, high=1.0970))
    array = evaluate_entry_array(gap_ctx, True, None, False, CandidateDirection.LONG, current_price=1.0963)
    assert array.entry_status == "ENTRY_REFERENCE_AVAILABLE"


def test_entry_array_confluence_overlap_when_fvg_and_ob_share_range():
    gap_ctx = evaluate_gap_context(_zone(status=ZoneStatus.FRESH, low=1.0960, high=1.0970))
    ob = _ob(low=1.0958, high=1.0968)
    array = evaluate_entry_array(gap_ctx, True, ob, True, CandidateDirection.LONG)
    assert array.entry_array_type == "FVG_AND_ORDER_BLOCK"
    assert array.confluence in ("OVERLAP", "PARTIAL_OVERLAP")
    assert array.entry_method == "FVG_OB_CONFLUENCE"


# ---------------------------------------------------------------------------
# Full reversal route (spec rules 40-41, 48)
# ---------------------------------------------------------------------------

def _valid_reversal_request(**overrides):
    sweep = _sweep_level(LiquiditySide.SELL_SIDE, price=1.0950,
                          sweep_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
                          reclaim_time=dt.datetime(2026, 1, 5, 10, 5, tzinfo=UTC))
    structure_shift = StructureAlignment(status=ConfirmationState.PASS, event_kind="BULLISH_CHOCH",
                                          event_time=dt.datetime(2026, 1, 5, 10, 30, tzinfo=UTC), event_price=1.0980)
    displacement = DisplacementEvidence(status=ConfirmationState.PASS, direction="BULLISH",
                                         candle_timestamp=dt.datetime(2026, 1, 5, 10, 30, tzinfo=UTC))
    gap_ctx = evaluate_gap_context(_zone(status=ZoneStatus.FRESH, low=1.0985, high=1.0995))
    ext_tier = _tier("EXTERNAL", 50, [(8, 1.0980, StructurePointKind.SWING_HIGH)])
    kwargs = dict(
        symbol="EURUSD", timeframe="M5", candidate_direction=CandidateDirection.LONG,
        evaluation_time=dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC),
        sweep_level=sweep, pivot_price=1.0980, pivot_type="SWING_HIGH", external_tier=ext_tier,
        structure_shift=structure_shift, displacement=displacement,
        displacement_leg_start=dt.datetime(2026, 1, 5, 10, 25, tzinfo=UTC),
        displacement_leg_end=dt.datetime(2026, 1, 5, 10, 35, tzinfo=UTC),
        gap_context=gap_ctx, gap_origin_time=dt.datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
    )
    kwargs.update(overrides)
    return SweepShiftArrayRequest(**kwargs)


def test_valid_bullish_reversal_shift_is_confirmed_strong():
    result = evaluate_reversal_sweep_shift(_valid_reversal_request())
    assert result.setup_family == "REVERSAL"
    assert result.quality_status == "VALID_STRONG"
    assert result.aggregation_status == "CONFIRMED"
    assert result.status in ("WAITING_ENTRY_PRICE", "ENTRY_REFERENCE_AVAILABLE")


def test_reversal_wrong_order_choch_before_sweep_is_not_confirmed():
    sweep = _sweep_level(LiquiditySide.SELL_SIDE, price=1.0950,
                          sweep_time=dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC))
    structure_shift = StructureAlignment(status=ConfirmationState.PASS, event_kind="BULLISH_CHOCH",
                                          event_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC), event_price=1.0980)
    request = _valid_reversal_request(sweep_level=sweep, structure_shift=structure_shift,
                                       evaluation_time=dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC))
    result = evaluate_reversal_sweep_shift(request)
    assert result.quality_status == "WRONG_SEQUENCE"
    assert result.aggregation_status == "NOT_CONFIRMED"


def test_sweep_only_no_structure_close_waits():
    sweep = _sweep_level(LiquiditySide.SELL_SIDE, price=1.0950,
                          sweep_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    request = SweepShiftArrayRequest(
        symbol="EURUSD", timeframe="M5", candidate_direction=CandidateDirection.LONG,
        sweep_level=sweep,
    )
    result = evaluate_reversal_sweep_shift(request)
    assert result.status == "FAKEOUT_WICK" or result.status == "WAITING_STRUCTURE_SHIFT"
    assert result.aggregation_status in ("NOT_CONFIRMED", "INDETERMINATE")


def test_no_sweep_at_all_waits_for_sweep():
    request = SweepShiftArrayRequest(symbol="EURUSD", timeframe="M5")
    result = evaluate_reversal_sweep_shift(request)
    assert result.status == "WAITING_SWEEP"
    assert result.aggregation_status == "INDETERMINATE"


def test_mid_range_choch_without_htf_context_is_low_context_not_confirmed_route():
    # CHoCH-only evidence with no sweep is dispatched to UNRESOLVED family entirely --
    # SMC_REVERSAL_SWEEP_SHIFT requires a sweep by construction (spec rule 51).
    result = evaluate_sweep_shift_array(SweepShiftArrayRequest(symbol="EURUSD", timeframe="M5"))
    assert result.setup_family == "UNRESOLVED"
    assert result.aggregation_status == "INDETERMINATE"


def test_structural_invalidation_marks_setup_invalidated():
    request = _valid_reversal_request(current_price=1.0940)  # below sweep_price=1.0950, LONG invalidation
    result = evaluate_reversal_sweep_shift(request)
    assert result.status == "INVALIDATED"
    assert result.aggregation_status == "NOT_CONFIRMED"


# ---------------------------------------------------------------------------
# Setup family dispatch (spec rules 29-31, 49)
# ---------------------------------------------------------------------------

def test_continuation_dispatched_when_bos_present_without_sweep():
    displacement = DisplacementEvidence(status=ConfirmationState.PASS, direction="BULLISH")
    gap_ctx = evaluate_gap_context(_zone(status=ZoneStatus.FRESH, low=1.0960, high=1.0970))
    request = SweepShiftArrayRequest(
        symbol="EURUSD", timeframe="M5", candidate_direction=CandidateDirection.LONG,
        bos_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC), trend_context_valid=True,
        displacement=displacement, gap_context=gap_ctx,
        displacement_leg_start=dt.datetime(2026, 1, 5, 9, 55, tzinfo=UTC),
        displacement_leg_end=dt.datetime(2026, 1, 5, 10, 5, tzinfo=UTC),
        gap_origin_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )
    result = evaluate_sweep_shift_array(request)
    assert result.setup_family == "CONTINUATION"
    assert result.aggregation_status == "CONFIRMED"


# ---------------------------------------------------------------------------
# Aggregation states preserved (spec rule 57)
# ---------------------------------------------------------------------------

def test_aggregation_vocabulary_is_still_the_frozen_four_states():
    result = evaluate_reversal_sweep_shift(_valid_reversal_request())
    assert result.aggregation_status in ("CONFIRMED", "PARTIAL", "NOT_CONFIRMED", "INDETERMINATE")


# ---------------------------------------------------------------------------
# No DayTrading dependency preserved (spec rule 75-carryover)
# ---------------------------------------------------------------------------

def test_entry_confirmation_v2_1_package_has_no_daytrading_or_execution_imports():
    import ast
    import pathlib

    pkg_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "entry_confirmation"
    for path in pkg_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for n in names:
                assert n is None or not n.startswith("daytrading"), f"{path.name} imports {n}"
                assert n is None or not (n.startswith("execution") or n.startswith("mt5")), f"{path.name} imports {n}"
