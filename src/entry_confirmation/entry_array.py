"""Entry array (FVG/OB) association, confluence, and entry-array geometry
(SMC_SWEEP_SHIFT_ARRAY_V1 steps 7-9). Consumes a caller-supplied FVG `GapContext` (V2's
gap.py) and/or an Order Block `supply_demand.ZoneResult`/`ValidatedOrderBlock` verbatim
-- never redetects FVG/OB geometry.

Association is temporal/causal, not proximity-only (spec rule 17/46): an FVG/OB is only
accepted as "created by this shift" when its origin falls within the displacement leg's
own time window, or (for an OB) its own recorded `structure_event` matches the shift
being evaluated. A nearby-but-unrelated older zone is never silently promoted.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from entry_confirmation.models import CandidateDirection
from entry_confirmation.models_v2 import GapContext
from entry_confirmation.models_v2_1 import ConfluenceRelation, EntryArrayContext, EntryArrayType, EntryMethodV21
from supply_demand import ValidatedOrderBlock


def fvg_associated_with_leg(gap_context: Optional[GapContext], leg_start: Optional[datetime],
                             leg_end: Optional[datetime], gap_origin_time: Optional[datetime]) -> bool:
    if gap_context is None or gap_context.gap_low is None or gap_origin_time is None:
        return False
    if leg_start is None or leg_end is None:
        return False
    return leg_start <= gap_origin_time <= leg_end


def ob_associated_with_shift(ob: Optional[ValidatedOrderBlock], structure_event_time: Optional[datetime]) -> bool:
    if ob is None or ob.structure_event is None or structure_event_time is None:
        return False
    return ob.structure_event.time_utc == structure_event_time


def _confluence(fvg_low, fvg_high, ob_low, ob_high) -> str:
    if None in (fvg_low, fvg_high, ob_low, ob_high):
        return ConfluenceRelation.UNRESOLVED.value
    if fvg_low <= ob_high and ob_low <= fvg_high:
        overlap_low = max(fvg_low, ob_low)
        overlap_high = min(fvg_high, ob_high)
        full = overlap_low <= fvg_low + 1e-12 and overlap_high >= fvg_high - 1e-12 and \
            overlap_low <= ob_low + 1e-12 and overlap_high >= ob_high - 1e-12
        return ConfluenceRelation.OVERLAP.value if overlap_high > overlap_low else ConfluenceRelation.PARTIAL_OVERLAP.value
    return ConfluenceRelation.SAME_LEG_NO_OVERLAP.value


def evaluate_entry_array(
    gap_context: Optional[GapContext],
    fvg_associated: bool,
    ob: Optional[ValidatedOrderBlock],
    ob_associated: bool,
    candidate_direction: CandidateDirection,
    sweep_price: Optional[float] = None,
    current_price: Optional[float] = None,
    target_liquidity_reference: Optional[float] = None,
) -> EntryArrayContext:
    fvg_ok = fvg_associated and gap_context is not None and gap_context.gap_low is not None
    ob_ok = ob_associated and ob is not None and ob.low is not None and ob.high is not None

    fvg_low, fvg_high = (gap_context.gap_low, gap_context.gap_high) if fvg_ok else (None, None)
    ob_low, ob_high = (ob.low, ob.high) if ob_ok else (None, None)

    invalidation_candidates = []
    if sweep_price is not None:
        invalidation_candidates.append(sweep_price)
    if ob_ok:
        invalidation_candidates.append(ob_low if candidate_direction == CandidateDirection.LONG else ob_high)

    if fvg_ok and ob_ok:
        confluence = _confluence(fvg_low, fvg_high, ob_low, ob_high)
        entry_type = EntryArrayType.FVG_AND_ORDER_BLOCK.value
        candidates = (EntryArrayType.FVG.value, EntryArrayType.ORDER_BLOCK.value)
        if confluence in (ConfluenceRelation.OVERLAP.value, ConfluenceRelation.PARTIAL_OVERLAP.value):
            entry_method = EntryMethodV21.FVG_OB_CONFLUENCE.value
            overlap_low, overlap_high = max(fvg_low, ob_low), min(fvg_high, ob_high)
            entry_reference = (overlap_low + overlap_high) / 2.0
        else:
            entry_method = EntryMethodV21.UNRESOLVED.value
            entry_reference = None
    elif fvg_ok:
        confluence = ConfluenceRelation.UNRELATED.value
        entry_type = EntryArrayType.FVG.value
        candidates = (EntryArrayType.FVG.value,)
        entry_method = EntryMethodV21.FVG_MIDPOINT.value
        entry_reference = (fvg_low + fvg_high) / 2.0
    elif ob_ok:
        confluence = ConfluenceRelation.UNRELATED.value
        entry_type = EntryArrayType.ORDER_BLOCK.value
        candidates = (EntryArrayType.ORDER_BLOCK.value,)
        entry_method = EntryMethodV21.ORDER_BLOCK_ZONE.value
        entry_reference = (ob_low + ob_high) / 2.0
    else:
        confluence = ConfluenceRelation.UNRESOLVED.value
        entry_type = EntryArrayType.NONE.value
        candidates = ()
        entry_method = EntryMethodV21.UNRESOLVED.value
        entry_reference = None

    if entry_reference is None:
        entry_status = "UNRESOLVED"
    elif current_price is not None and (
        (candidate_direction == CandidateDirection.LONG and current_price <= entry_reference) or
        (candidate_direction == CandidateDirection.SHORT and current_price >= entry_reference)
    ):
        entry_status = "ENTRY_REFERENCE_AVAILABLE"
    else:
        entry_status = "WAITING_ENTRY_PRICE"

    return EntryArrayContext(
        entry_array_type=entry_type, entry_method=entry_method, entry_candidates=candidates,
        entry_reference=entry_reference, entry_status=entry_status, confluence=confluence,
        structural_invalidation_candidates=tuple(invalidation_candidates),
        target_liquidity_reference=target_liquidity_reference,
    )
