"""E1/E2/E3 adapters (spec sections 14-19): translate already-computed evidence from
entry_confirmation.gap/poi and liquidity.status into the generic SMCConditionResult
shape. No gap/POI/sweep semantics are redefined here -- gap_context and poi_context are
built by entry_confirmation.gap.evaluate_gap_context / entry_confirmation.poi.
evaluate_poi_context exactly as engine_v2.py already does; sweep_level is a
liquidity.LiquidityLevel exactly as liquidity's own analyzer already produces.

Trigger rules (deliberately conservative, matching existing repo authority):
  E1 triggers on gap_context.status == "GAP_REACTED" -- gap.py's own AG_ENTRY_
     DISPLACEMENT_V1-gated reaction rule, already signed; the deeper CHoCH/inducement
     chain in route.evaluate_e1 is an ENTRY-confirmation concern, downstream of "does
     this deserve an alert."
  E2 triggers only when poi_context.status == "POI_REACHED" AND the caller explicitly
     asserts poi_reacted=True with a poi_reaction_time. entry_confirmation/route.py's own
     docstring says no signed generic POI-reaction detector exists in this repo (rule
     14/136-138) -- so this module fails closed (E2_REACTION_RULE_UNDEFINED) rather than
     inventing one, exactly like route.py's own poi_reacted parameter already does.
  E3 triggers whenever sweep_level.sweep_time is not None (SWEPT/RECLAIMED/CONSUMED) --
     the same criterion entry_confirmation.route.classify_route already uses to route
     LIQUIDITY_SWEEP, so this does not invent a second, divergent sweep-triggering rule.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from entry_confirmation.models_v2 import GapContext, POIContext
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus

from .models import (
    CONDITION_E1,
    CONDITION_E2,
    CONDITION_E3,
    CONDITION_TYPE_DAILY_GAP_REACTION,
    CONDITION_TYPE_H1_POI_REACTION,
    CONDITION_TYPE_LIQUIDITY_SWEEP,
    STATE_FILLED,
    STATE_INDETERMINATE,
    STATE_INVALIDATED,
    STATE_POI_TOUCHED,
    STATE_RECLAIMED,
    STATE_REACTED,
    STATE_SWEPT,
    STATE_TOUCHED,
    STATE_WATCHING,
    SMCConditionResult,
)

_GAP_STATUS_TO_STATE = {
    "UNAVAILABLE": STATE_INDETERMINATE,
    "UNTOUCHED": STATE_WATCHING,
    "GAP_TOUCHED": STATE_TOUCHED,
    "GAP_FILLED": STATE_FILLED,
    "GAP_REACTED": STATE_REACTED,
    "GAP_INVALIDATED": STATE_INVALIDATED,
}


def evaluate_e1_condition(
    gap_context: Optional[GapContext], evaluation_time: Optional[datetime] = None,
) -> SMCConditionResult:
    if gap_context is None:
        return SMCConditionResult(
            condition_id=CONDITION_E1, condition_type=CONDITION_TYPE_DAILY_GAP_REACTION,
            state=STATE_WATCHING, reason_codes=("NO_ACTIVE_D1_GAP",),
        )

    state = _GAP_STATUS_TO_STATE.get(gap_context.status, STATE_INDETERMINATE)
    triggered = state == STATE_REACTED
    # Directional implication requires the candidate_direction gap.py was built with
    # (evaluate_gap_context does not echo it back onto GapContext) -- not re-derived here.
    source_key = f"D1_GAP:{gap_context.gap_low}:{gap_context.gap_high}"

    return SMCConditionResult(
        condition_id=CONDITION_E1, condition_type=CONDITION_TYPE_DAILY_GAP_REACTION,
        state=state, triggered=triggered, directional_implication=None, source_key=source_key,
        evidence={
            "gap_low": gap_context.gap_low, "gap_high": gap_context.gap_high,
            "gap_midpoint": gap_context.gap_midpoint, "reaction_time": gap_context.reaction_time,
        },
        reason_codes=gap_context.evidence + ((gap_context.reason,) if gap_context.reason else ()),
    )


def evaluate_e2_condition(
    poi_context: Optional[POIContext],
    poi_reaction_time: Optional[datetime] = None,
    poi_reacted: Optional[bool] = None,
) -> SMCConditionResult:
    if poi_context is None:
        return SMCConditionResult(
            condition_id=CONDITION_E2, condition_type=CONDITION_TYPE_H1_POI_REACTION,
            state=STATE_WATCHING, reason_codes=("NO_ACTIVE_H1_POI",),
        )

    if poi_context.status == "INVALIDATED":
        state = STATE_INVALIDATED
    elif poi_context.status == "POI_REACHED":
        state = STATE_POI_TOUCHED
    elif poi_context.status in ("DORMANT", "UNRESOLVED", "WAITING_POI"):
        state = STATE_WATCHING
    else:
        state = STATE_INDETERMINATE

    reason_codes = list(poi_context.evidence)
    triggered = False
    if state == STATE_POI_TOUCHED:
        if poi_reacted and poi_reaction_time is not None:
            state = STATE_REACTED
            triggered = True
            reason_codes.append("CALLER_ASSERTED_POI_REACTION")
        else:
            reason_codes.append("E2_REACTION_RULE_UNDEFINED")

    source_key = f"H1_POI:{poi_context.poi_type}:{poi_context.poi_low}:{poi_context.poi_high}"

    return SMCConditionResult(
        condition_id=CONDITION_E2, condition_type=CONDITION_TYPE_H1_POI_REACTION,
        state=state, triggered=triggered, directional_implication=poi_context.poi_direction,
        source_key=source_key,
        evidence={
            "poi_type": poi_context.poi_type, "poi_low": poi_context.poi_low,
            "poi_high": poi_context.poi_high, "poi_reaction_time": poi_reaction_time,
        },
        reason_codes=tuple(reason_codes),
    )


_SWEEP_STATE_MAP = {
    LiquidityStatus.UNSWEPT: STATE_WATCHING,
    LiquidityStatus.SWEPT: STATE_SWEPT,
    LiquidityStatus.RECLAIMED: STATE_RECLAIMED,
    LiquidityStatus.CONSUMED: STATE_SWEPT,  # closed beyond, no reclaim -- still a swept event for alerting purposes
    LiquidityStatus.UNKNOWN: STATE_INDETERMINATE,
}


def evaluate_e3_condition(sweep_level: Optional[LiquidityLevel]) -> SMCConditionResult:
    if sweep_level is None:
        return SMCConditionResult(
            condition_id=CONDITION_E3, condition_type=CONDITION_TYPE_LIQUIDITY_SWEEP,
            state=STATE_WATCHING, reason_codes=("NO_ELIGIBLE_LIQUIDITY_LEVEL",),
        )

    state = _SWEEP_STATE_MAP.get(sweep_level.status, STATE_INDETERMINATE)
    # Same criterion entry_confirmation.route.classify_route already uses to route
    # LIQUIDITY_SWEEP -- sweep alone (no reclaim requirement) is sufficient here too.
    triggered = sweep_level.sweep_time is not None
    direction = "LONG" if sweep_level.side == LiquiditySide.SELL_SIDE else "SHORT"
    source_key = f"LIQUIDITY:{sweep_level.source}:{sweep_level.price}:{sweep_level.sweep_time}"

    return SMCConditionResult(
        condition_id=CONDITION_E3, condition_type=CONDITION_TYPE_LIQUIDITY_SWEEP,
        state=state, triggered=triggered, directional_implication=direction if triggered else None,
        source_key=source_key,
        evidence={
            "liquidity_type": sweep_level.source, "liquidity_side": sweep_level.side.value,
            "level": sweep_level.price, "sweep_time": sweep_level.sweep_time,
            "reclaim_time": sweep_level.reclaim_time, "reclaim_state": sweep_level.status.value,
        },
        reason_codes=sweep_level.reason_codes,
    )
