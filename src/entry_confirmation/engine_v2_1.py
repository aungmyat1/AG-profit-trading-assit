"""AG_ENTRY_CONFIRMATION_V2_1 -- public entry point for SMC_SWEEP_SHIFT_ARRAY_V1.
Purely additive to V1 (engine.py) and V2 (engine_v2.py); none of those files are
modified. See docs/specs/ENTRY_CONFIRMATION_V2_1_SPEC.md.

Composition mirrors spec section 68:

    HTF liquidity/POI -> sweep -> valid structural pivot -> body-close structure break
        -> displacement -> FVG/OB entry array -> structural invalidation

Two setup families are supported (spec rules 29-31):

- SMC_REVERSAL_SWEEP_SHIFT_V1 (`evaluate_reversal_sweep_shift`): sweep is REQUIRED,
  the structural event must occur strictly after the sweep, and a wick-only
  penetration is explicitly classified as FAKEOUT_WICK rather than a failure.
- SMC_CONTINUATION_PULLBACK_V1 (`evaluate_continuation_pullback`): no HTF reversal
  sweep required; driven by an existing directional context + BOS + displacement +
  pullback into the resulting array. Implemented at reduced depth relative to the
  reversal route (VERIFIED/PARTIAL per spec's own Definition of Done allowance) --
  see docs/specs/ENTRY_CONFIRMATION_V2_1_SPEC.md's Known Gaps.

`evaluate_sweep_shift_array()` dispatches to whichever family the caller's evidence
supports (sweep evidence -> REVERSAL; BOS/trend evidence with no sweep -> CONTINUATION;
neither -> UNRESOLVED, never guessed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from liquidity import LiquidityLevel
from market_structure.models import StructureTier
from strategy_engine.session import Candle
from supply_demand import ValidatedOrderBlock

from .entry_array import evaluate_entry_array, fvg_associated_with_leg, ob_associated_with_shift
from .models import CandidateDirection, ConfirmationState, DisplacementEvidence, StructureAlignment
from .models_v2 import GapContext, TypedEvent
from .models_v2_1 import (
    DisplacementLeg,
    PivotContext,
    SetupFamily,
    SMCSweepShiftArrayResult,
    StructureShiftQualityStatus,
)
from .sweep_shift import classify_wick_or_close, evaluate_pivot_context, evaluate_structure_shift_quality


@dataclass(frozen=True)
class SweepShiftArrayRequest:
    symbol: str
    timeframe: str
    candidate_direction: CandidateDirection = CandidateDirection.NONE
    evaluation_time: Optional[datetime] = None

    sweep_level: Optional[LiquidityLevel] = None
    sweep_candle: Optional[Candle] = None
    poi_reference: Optional[str] = None

    pivot_price: Optional[float] = None
    pivot_time: Optional[datetime] = None
    pivot_type: Optional[str] = None
    external_tier: Optional[StructureTier] = None
    internal_tier: Optional[StructureTier] = None
    pivot_tolerance_price: Optional[float] = None

    structure_shift: Optional[StructureAlignment] = None
    structure_break_candle_time: Optional[datetime] = None

    displacement: Optional[DisplacementEvidence] = None
    displacement_leg_start: Optional[datetime] = None
    displacement_leg_end: Optional[datetime] = None

    gap_context: Optional[GapContext] = None
    gap_origin_time: Optional[datetime] = None
    order_block: Optional[ValidatedOrderBlock] = None

    premium_discount_zone: Optional[str] = None
    current_price: Optional[float] = None
    target_liquidity_reference: Optional[float] = None

    # Continuation-only evidence
    bos_time: Optional[datetime] = None
    trend_context_valid: Optional[bool] = None


def _not_future(ts, evaluation_time) -> bool:
    if ts is None or evaluation_time is None:
        return True
    return ts <= evaluation_time


def determine_setup_family(request: SweepShiftArrayRequest) -> str:
    if request.sweep_level is not None and request.sweep_level.sweep_time is not None:
        return SetupFamily.REVERSAL.value
    if request.bos_time is not None:
        return SetupFamily.CONTINUATION.value
    return SetupFamily.UNRESOLVED.value


def evaluate_sweep_shift_array(request: SweepShiftArrayRequest) -> SMCSweepShiftArrayResult:
    family = determine_setup_family(request)
    if family == SetupFamily.REVERSAL.value:
        return evaluate_reversal_sweep_shift(request)
    if family == SetupFamily.CONTINUATION.value:
        return evaluate_continuation_pullback(request)
    return SMCSweepShiftArrayResult(
        symbol=request.symbol, timeframe=request.timeframe, evaluation_time=request.evaluation_time,
        setup_family=SetupFamily.UNRESOLVED.value, status="WAITING_SWEEP", aggregation_status="INDETERMINATE",
        reason="No sweep and no BOS/trend evidence supplied -- neither setup family qualifies.",
    )


def evaluate_reversal_sweep_shift(request: SweepShiftArrayRequest) -> SMCSweepShiftArrayResult:
    events = [TypedEvent(kind="HTF_LIQUIDITY_IDENTIFIED",
                          status="PASS" if request.sweep_level is not None else "FAIL")]

    sweep = request.sweep_level
    if sweep is None or sweep.sweep_time is None:
        events.append(TypedEvent(kind="SWEEP", status="UNRESOLVED"))
        return SMCSweepShiftArrayResult(
            symbol=request.symbol, timeframe=request.timeframe, evaluation_time=request.evaluation_time,
            setup_family=SetupFamily.REVERSAL.value, event_sequence=tuple(events),
            status="WAITING_SWEEP", aggregation_status="INDETERMINATE",
            reason="No causally-valid liquidity sweep supplied.",
        )

    sweep_present = _not_future(sweep.sweep_time, request.evaluation_time)
    events.append(TypedEvent(kind="SWEEP", status="PASS" if sweep_present else "PENDING",
                              timestamp=sweep.sweep_time))
    events.append(TypedEvent(
        kind="RECLAIM", status="PASS" if sweep.reclaim_time is not None else "PENDING",
        timestamp=sweep.reclaim_time,
    ))

    wick_evidence = None
    if request.sweep_candle is not None and request.pivot_price is not None:
        wick_evidence = classify_wick_or_close(request.sweep_candle, request.pivot_price, sweep.side)

    pivot_context = evaluate_pivot_context(
        request.pivot_price, request.pivot_time, request.pivot_type, request.timeframe,
        request.external_tier, request.internal_tier, request.pivot_tolerance_price,
    )
    events.append(TypedEvent(kind="VALID_PIVOT_SELECTED",
                              status="PASS" if pivot_context.pivot_price is not None else "UNRESOLVED"))

    structure_shift = request.structure_shift or StructureAlignment(status=ConfirmationState.UNAVAILABLE)
    structure_time = structure_shift.event_time
    post_sweep = None
    if structure_time is not None:
        post_sweep = sweep.sweep_time <= structure_time
    events.append(TypedEvent(
        kind="CHOCH_CLOSE", status="PASS" if structure_shift.status == ConfirmationState.PASS else "FAIL",
        timestamp=structure_time,
    ))

    displacement = request.displacement or DisplacementEvidence(status=ConfirmationState.UNAVAILABLE)
    events.append(TypedEvent(kind="DISPLACEMENT",
                              status="PASS" if displacement.status == ConfirmationState.PASS else "FAIL"))

    fvg_associated = fvg_associated_with_leg(
        request.gap_context, request.displacement_leg_start, request.displacement_leg_end,
        request.gap_origin_time,
    )
    events.append(TypedEvent(kind="FVG_CREATED", status="PASS" if fvg_associated else "FAIL"))

    quality = evaluate_structure_shift_quality(
        sweep_present=True, post_sweep_ordering=post_sweep, pivot_context=pivot_context,
        structure_shift=structure_shift, displacement=displacement, fvg_created=fvg_associated,
    )

    ob_associated = ob_associated_with_shift(request.order_block, structure_time)
    entry_array = evaluate_entry_array(
        request.gap_context, fvg_associated, request.order_block, ob_associated,
        request.candidate_direction, sweep_price=sweep.price, current_price=request.current_price,
        target_liquidity_reference=request.target_liquidity_reference,
    )
    events.append(TypedEvent(kind="ENTRY_ARRAY_AVAILABLE",
                              status="PASS" if entry_array.entry_reference is not None else "UNRESOLVED"))

    displacement_leg = DisplacementLeg(
        direction=displacement.direction, start_time=request.displacement_leg_start,
        end_time=request.displacement_leg_end, qualification=displacement.qualification,
        associated_structure_event_time=structure_time,
        associated_fvg_origin_time=request.gap_origin_time if fvg_associated else None,
        associated_ob_origin_time=request.order_block.origin_time if ob_associated and request.order_block else None,
    )

    invalidated = False
    if request.current_price is not None and entry_array.structural_invalidation_candidates:
        if request.candidate_direction == CandidateDirection.LONG:
            invalidated = request.current_price < min(entry_array.structural_invalidation_candidates)
        elif request.candidate_direction == CandidateDirection.SHORT:
            invalidated = request.current_price > max(entry_array.structural_invalidation_candidates)

    status, aggregation = _resolve_status(quality.status, entry_array.entry_status, invalidated, wick_evidence)

    return SMCSweepShiftArrayResult(
        symbol=request.symbol, timeframe=request.timeframe, evaluation_time=request.evaluation_time,
        setup_family=SetupFamily.REVERSAL.value,
        liquidity_reference=sweep.price, liquidity_side=sweep.side.value, liquidity_state=sweep.status.value,
        poi_reference=request.poi_reference,
        sweep_event=sweep.status.value, reclaim_event=sweep.status.value if sweep.reclaim_time else None,
        sweep_candle_time=request.sweep_candle.time if request.sweep_candle else None,
        structural_pivot=pivot_context, structure_event=structure_shift,
        structure_break_candle_time=request.structure_break_candle_time,
        structure_quality=quality,
        displacement=displacement, displacement_leg=displacement_leg,
        associated_fvg=request.gap_context if fvg_associated else None,
        associated_order_block=(f"OB@{request.order_block.origin_time}" if ob_associated and request.order_block else None),
        premium_discount_context=request.premium_discount_zone,
        entry_array=entry_array,
        event_sequence=tuple(events),
        status=status, aggregation_status=aggregation, quality_status=quality.status,
        reason=quality.reason,
    )


def evaluate_continuation_pullback(request: SweepShiftArrayRequest) -> SMCSweepShiftArrayResult:
    events = [TypedEvent(kind="TREND_CONTEXT",
                          status="PASS" if request.trend_context_valid else "UNRESOLVED")]

    if request.bos_time is None or not _not_future(request.bos_time, request.evaluation_time):
        events.append(TypedEvent(kind="BOS", status="UNRESOLVED"))
        return SMCSweepShiftArrayResult(
            symbol=request.symbol, timeframe=request.timeframe, evaluation_time=request.evaluation_time,
            setup_family=SetupFamily.CONTINUATION.value, event_sequence=tuple(events),
            status="WAITING_STRUCTURE_SHIFT", aggregation_status="INDETERMINATE",
            reason="No causally-valid BOS evidence supplied.",
        )
    events.append(TypedEvent(kind="BOS", status="PASS", timestamp=request.bos_time))

    displacement = request.displacement or DisplacementEvidence(status=ConfirmationState.UNAVAILABLE)
    events.append(TypedEvent(kind="DISPLACEMENT",
                              status="PASS" if displacement.status == ConfirmationState.PASS else "FAIL"))

    fvg_associated = fvg_associated_with_leg(
        request.gap_context, request.displacement_leg_start, request.displacement_leg_end,
        request.gap_origin_time,
    )
    ob_associated = ob_associated_with_shift(request.order_block, None)  # BOS has no CHoCH event to match against
    events.append(TypedEvent(kind="FVG_OR_OB_CREATED", status="PASS" if (fvg_associated or ob_associated) else "FAIL"))

    entry_array = evaluate_entry_array(
        request.gap_context, fvg_associated, request.order_block, ob_associated,
        request.candidate_direction, sweep_price=None, current_price=request.current_price,
        target_liquidity_reference=request.target_liquidity_reference,
    )
    events.append(TypedEvent(kind="CORRECTION",
                              status="PASS" if entry_array.entry_reference is not None else "UNRESOLVED"))
    events.append(TypedEvent(kind="ARRAY_REACTION",
                              status="PASS" if entry_array.entry_status == "ENTRY_REFERENCE_AVAILABLE" else "PENDING"))

    if not (fvg_associated or ob_associated):
        aggregation = "PARTIAL" if displacement.status == ConfirmationState.PASS else "INDETERMINATE"
        status = "WAITING_ENTRY_PRICE" if aggregation == "PARTIAL" else "WAITING_STRUCTURE_SHIFT"
        quality_status = StructureShiftQualityStatus.VALID_WEAK.value if aggregation == "PARTIAL" \
            else StructureShiftQualityStatus.INDETERMINATE.value
    elif displacement.status != ConfirmationState.PASS:
        aggregation, status, quality_status = "PARTIAL", entry_array.entry_status, StructureShiftQualityStatus.VALID_WEAK.value
    else:
        aggregation = "CONFIRMED"
        status = entry_array.entry_status
        quality_status = StructureShiftQualityStatus.VALID_STRONG.value

    return SMCSweepShiftArrayResult(
        symbol=request.symbol, timeframe=request.timeframe, evaluation_time=request.evaluation_time,
        setup_family=SetupFamily.CONTINUATION.value,
        structure_break_candle_time=request.bos_time,
        displacement=displacement,
        displacement_leg=DisplacementLeg(
            direction=displacement.direction, start_time=request.displacement_leg_start,
            end_time=request.displacement_leg_end, qualification=displacement.qualification,
            associated_fvg_origin_time=request.gap_origin_time if fvg_associated else None,
            associated_ob_origin_time=request.order_block.origin_time if ob_associated and request.order_block else None,
        ),
        associated_fvg=request.gap_context if fvg_associated else None,
        associated_order_block=(f"OB@{request.order_block.origin_time}" if ob_associated and request.order_block else None),
        premium_discount_context=request.premium_discount_zone,
        entry_array=entry_array,
        event_sequence=tuple(events),
        status=status, aggregation_status=aggregation, quality_status=quality_status,
        unresolved_policies=("CONTINUATION_ARRAY_REACTION_QUALIFICATION",),
        reason="SMC_CONTINUATION_PULLBACK_V1 implemented at reduced depth relative to the reversal route.",
    )


def _resolve_status(quality_status: str, entry_status: str, invalidated: bool, wick_evidence):
    if invalidated:
        return "INVALIDATED", "NOT_CONFIRMED"
    if quality_status == StructureShiftQualityStatus.FAKEOUT_WICK.value:
        return "FAKEOUT_WICK", "NOT_CONFIRMED"
    if quality_status in (StructureShiftQualityStatus.WRONG_SEQUENCE.value,
                          StructureShiftQualityStatus.INVALID_PIVOT.value):
        return "NOT_CONFIRMED", "NOT_CONFIRMED"
    if quality_status == StructureShiftQualityStatus.MID_RANGE_LOW_CONTEXT.value:
        return entry_status if entry_status != "UNRESOLVED" else "WAITING_ENTRY_PRICE", "PARTIAL"
    if quality_status == StructureShiftQualityStatus.INDETERMINATE.value:
        return "WAITING_STRUCTURE_SHIFT", "INDETERMINATE"
    if quality_status == StructureShiftQualityStatus.VALID_WEAK.value:
        return (entry_status if entry_status != "UNRESOLVED" else "WAITING_ENTRY_PRICE"), "PARTIAL"
    # VALID_STRONG
    return (entry_status if entry_status != "UNRESOLVED" else "WAITING_ENTRY_PRICE"), "CONFIRMED"
