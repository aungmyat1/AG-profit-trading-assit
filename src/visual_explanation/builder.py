"""build_visual_explanation() -- turns one already-composed SMCEntryCombinationResult
(plus its underlying EConditionResult/M-result) into a portable annotation list. Never
recomputes structure/zones/liquidity itself (spec section 55) and never requires the
original detector to rerun (spec section 60) -- every annotation is read off fields the
frozen SMC_CONDITIONAL_ENTRY_V2 contracts already carry (EConditionResult.reference_*,
M-result entry_array_low/high / entry_fvg / entry_ob / entry_level).
"""
from __future__ import annotations

from typing import Optional

from entry_confirmation.entry_models_v1 import EntryModelState, SMCConditionalEntryAnalysis
from entry_confirmation.m1_character_change_inducement import M1Result
from entry_confirmation.m2_supply_demand_shift import M2Result
from entry_confirmation.m3_sweep_drop_pump import M3Result

from .models import ANNOTATION_BOX, ANNOTATION_LABEL, ANNOTATION_LINE, Annotation, SMCVisualExplanation


def _find_combination(analysis: SMCConditionalEntryAnalysis, combination: str):
    return next((c for c in analysis.combinations if c.combination == combination), None)


def _matching_m_result(analysis, combo):
    for r in analysis.m_maneuvers.get(combo.maneuver, ()):
        if r.direction == combo.direction and r.state == combo.state:
            return r
    return None


def _reference_annotation(e, snapshot_time: Optional[str]) -> Optional[Annotation]:
    if e.reference_low is None and e.reference_high is None and e.reference_level is None:
        return None
    low = e.reference_low if e.reference_low is not None else e.reference_level
    high = e.reference_high if e.reference_high is not None else e.reference_level
    return Annotation(
        type=ANNOTATION_BOX, timeframe=e.reference_timeframe, time_start=snapshot_time,
        low=low, high=high, label=e.reference_type or f"{e.entry_condition} reference",
        semantic_role="POI" if e.entry_condition == "E2" else "REFERENCE",
        developing=not e.eligible_for_confirmation,
    )


def _entry_array_annotation(m_result, timeframe: Optional[str], snapshot_time: Optional[str]) -> Optional[Annotation]:
    low = high = price = None
    label = "entry array"
    if isinstance(m_result, M1Result):
        low, high = m_result.entry_array_low, m_result.entry_array_high
        label = m_result.entry_array_type or label
    elif isinstance(m_result, M2Result):
        zone = m_result.entry_fvg or m_result.entry_ob
        if zone is not None:
            if zone.__class__.__name__ == "ValidatedOrderBlock" and zone.candidate is not None:
                low, high = zone.candidate.low, zone.candidate.high
                label = "ORDER_BLOCK"
            else:
                low, high = getattr(zone, "low", None), getattr(zone, "high", None)
                label = "FVG"
    elif isinstance(m_result, M3Result):
        price = m_result.entry_level
        label = m_result.gap or label

    if low is not None and high is not None:
        return Annotation(type=ANNOTATION_BOX, timeframe=timeframe, time_start=snapshot_time,
                           low=low, high=high, label=label, semantic_role="ENTRY_ARRAY",
                           developing=m_result.state != EntryModelState.READY.value)
    if price is not None:
        return Annotation(type=ANNOTATION_LINE, timeframe=timeframe, timestamp=snapshot_time,
                           price=price, label=label, semantic_role="ENTRY_ARRAY",
                           developing=m_result.state != EntryModelState.READY.value)
    return None


def _invalidation_annotation(combo, timeframe: Optional[str], snapshot_time: Optional[str]) -> Optional[Annotation]:
    """Reads combo.invalidation_price/source_type/trigger verbatim (copied from the
    underlying M-result's own entry_confirmation.invalidation fields, composer.py) --
    never recomputed here. Present whenever the M-model has an invalidation reference at
    all, not only once actually breached, so a READY setup's chart can show where it
    would invalidate in advance."""
    if combo.invalidation_price is None:
        return None
    return Annotation(
        type=ANNOTATION_LINE, timeframe=timeframe, timestamp=snapshot_time, price=combo.invalidation_price,
        label=combo.invalidation_source_type or "invalidation", semantic_role="INVALIDATION",
        developing=combo.state != EntryModelState.INVALIDATED.value,
    )


def build_visual_explanation(analysis: SMCConditionalEntryAnalysis, combination: str) -> SMCVisualExplanation:
    snapshot_time = analysis.snapshot_time.isoformat() if analysis.snapshot_time is not None else None
    combo = _find_combination(analysis, combination)
    if combo is None:
        return SMCVisualExplanation(symbol=analysis.symbol, combination=combination, snapshot_time=snapshot_time,
                                     reason_codes=("COMBINATION_NOT_PRESENT_IN_ANALYSIS",))

    e = analysis.e_conditions.get(combo.entry_condition)
    m_result = _matching_m_result(analysis, combo)

    annotations = []
    if e is not None:
        ref = _reference_annotation(e, snapshot_time)
        if ref is not None:
            annotations.append(ref)
    if m_result is not None:
        entry = _entry_array_annotation(m_result, combo.confirmation_timeframe, snapshot_time)
        if entry is not None:
            annotations.append(entry)

    invalidation = _invalidation_annotation(combo, combo.confirmation_timeframe, snapshot_time)
    if invalidation is not None:
        annotations.append(invalidation)

    annotations.append(Annotation(
        type=ANNOTATION_LABEL, timeframe=combo.confirmation_timeframe, timestamp=snapshot_time,
        label=f"{combo.combination} {combo.direction or '?'}", semantic_role="DIRECTION",
        developing=combo.state != EntryModelState.READY.value,
    ))

    reason_codes = () if (e is not None and m_result is not None) else ("PARTIAL_EVIDENCE",)
    return SMCVisualExplanation(symbol=analysis.symbol, combination=combination, direction=combo.direction,
                                 snapshot_time=snapshot_time, annotations=tuple(annotations),
                                 reason_codes=reason_codes)
