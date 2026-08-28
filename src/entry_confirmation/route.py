"""Conditional-execution routes (E1/E2/E3) and their LTF confirmation models --
AG_ENTRY_CONFIRMATION_V2's reusable classification of "which conditional route is
active" and "has the required LTF confirmation occurred," per docs/specs/
ENTRY_CONFIRMATION_V2_SPEC.md.

Every route consumes evidence the caller already has (structure_shift from
market_structure via entry_confirmation.structure_alignment, liquidity from
liquidity.LiquidityLevel, gap reaction from entry_confirmation.gap) -- nothing here
redetects CHoCH, sweeps, or gaps. Where the presenter material names a concept this
repo has no signed definition for (inducement priority, "last orderflow", supply/demand
shift, drop/pump threshold, last-pullback-vs-gap priority), the corresponding field is
left UNRESOLVED/PARTIAL with preserved evidence rather than invented.

No route ever produces a route priority when more than one condition matches
(spec rule 72): `classify_route` returns MULTIPLE with `matching_routes` populated,
never guesses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence, Tuple

from liquidity import LiquidityLevel, LiquiditySide

from .models import CandidateDirection, ConfirmationState, StructureAlignment
from .models_v2 import (
    ConfirmationModel,
    ConfirmationRoute,
    EntryGeometry,
    EntryMethod,
    GapContext,
    POIContext,
    RouteResult,
    StructuralInvalidationType,
    TypedEvent,
)


def classify_route(
    gap_context: Optional[GapContext] = None,
    poi_context: Optional[POIContext] = None,
    poi_reacted: bool = False,
    sweep_level: Optional[LiquidityLevel] = None,
) -> RouteResult:
    matches = []
    if gap_context is not None and gap_context.status == "GAP_REACTED":
        matches.append(ConfirmationRoute.DAILY_GAP_REACTION.value)
    if poi_context is not None and poi_context.status == "POI_REACHED" and poi_reacted:
        matches.append(ConfirmationRoute.H1_POI_REACTION.value)
    if sweep_level is not None and sweep_level.sweep_time is not None:
        matches.append(ConfirmationRoute.LIQUIDITY_SWEEP.value)

    if not matches:
        return RouteResult(route=ConfirmationRoute.NONE.value, matching_routes=())
    if len(matches) > 1:
        return RouteResult(
            route=ConfirmationRoute.MULTIPLE.value, matching_routes=tuple(matches),
            reason="Multiple routes qualify -- no route-priority rule exists in this repo; "
                   "caller must disambiguate.",
        )
    return RouteResult(route=matches[0], matching_routes=tuple(matches))


def _not_future(ts: Optional[datetime], evaluation_time: Optional[datetime]) -> bool:
    """Zero-lookahead guard (spec rule 48): a timestamp after evaluation_time is not
    usable evidence at evaluation_time, regardless of what a caller supplies."""
    if ts is None or evaluation_time is None:
        return True
    return ts <= evaluation_time


def evaluate_e1(
    gap_context: GapContext,
    inducement_level: Optional[LiquidityLevel],
    structure_shift: StructureAlignment,
    evaluation_time: Optional[datetime] = None,
) -> Tuple[Tuple[TypedEvent, ...], EntryGeometry, str, str]:
    """DAILY_GAP_REACTION: D1 gap reaction -> inducement -> character change (CHoCH) ->
    entry from last pullback or gap (rules 18-24)."""
    gap_time = gap_context.reaction_time
    inducement_time = inducement_level.sweep_time if inducement_level is not None else None
    character_time = structure_shift.event_time

    events = [TypedEvent(kind="D1_GAP_REACTION", status="PASS" if gap_time else "FAIL", timestamp=gap_time)]

    if inducement_level is None or inducement_time is None:
        events.append(TypedEvent(kind="INDUCEMENT", status="UNRESOLVED", reason="No inducement evidence supplied."))
        return tuple(events), EntryGeometry(), ConfirmationModel.CHARACTER_CHANGE_WITH_INDUCEMENT.value, "INDETERMINATE"

    if not _not_future(inducement_time, evaluation_time) or not _not_future(character_time, evaluation_time):
        events.append(TypedEvent(kind="INDUCEMENT", status="PENDING", timestamp=inducement_time))
        return tuple(events), EntryGeometry(), ConfirmationModel.CHARACTER_CHANGE_WITH_INDUCEMENT.value, "WAITING_CONFIRMATION"

    events.append(TypedEvent(kind="INDUCEMENT", status="PASS", timestamp=inducement_time))

    if structure_shift.status != ConfirmationState.PASS or character_time is None:
        events.append(TypedEvent(kind="CHARACTER_CHANGE", status="FAIL", timestamp=character_time,
                                  reason=structure_shift.reason))
        return tuple(events), EntryGeometry(), ConfirmationModel.CHARACTER_CHANGE_WITH_INDUCEMENT.value, "PARTIAL"

    if gap_time is None or not (gap_time <= inducement_time <= character_time):
        events.append(TypedEvent(kind="CHARACTER_CHANGE", status="FAIL", timestamp=character_time,
                                  reason="Events out of causal order: expected "
                                         "gap_reaction <= inducement <= character_change."))
        return tuple(events), EntryGeometry(), ConfirmationModel.CHARACTER_CHANGE_WITH_INDUCEMENT.value, "NOT_CONFIRMED"

    events.append(TypedEvent(kind="CHARACTER_CHANGE", status="PASS", timestamp=character_time))
    events.append(TypedEvent(kind="ENTRY_REFERENCE", status="UNRESOLVED",
                              reason="ENTRY_REFERENCE_SELECTION_POLICY = UNRESOLVED (last pullback vs gap)."))

    geometry = EntryGeometry(
        entry_method=EntryMethod.UNRESOLVED.value,
        entry_candidates=(EntryMethod.LAST_PULLBACK.value, EntryMethod.GAP.value),
        status="WAITING_ENTRY_PRICE",
        structural_invalidation_type=StructuralInvalidationType.CHOCH_EXTREME_SWING.value,
        structural_invalidation_reference=structure_shift.event_price,
        reason="Entry reference selector unresolved -- both candidates preserved, no priority invented.",
    )
    return tuple(events), geometry, ConfirmationModel.CHARACTER_CHANGE_WITH_INDUCEMENT.value, "CONFIRMED"


def evaluate_e2(
    poi_context: POIContext,
    poi_reaction_time: Optional[datetime],
    m5_ob_zone_low: Optional[float],
    m5_ob_zone_high: Optional[float],
    candidate_direction: CandidateDirection,
    current_gap_context: Optional[GapContext] = None,
    evaluation_time: Optional[datetime] = None,
) -> Tuple[Tuple[TypedEvent, ...], EntryGeometry, str, str]:
    """H1_POI_REACTION: H1 POI reaction -> supply/demand shift -> last orderflow ->
    entry from current gap/OB (rules 25-30). SUPPLY_DEMAND_SHIFT and LAST_ORDERFLOW have
    no signed definition anywhere in this repo (audited market_structure/, supply_demand/,
    liquidity/) -- both are represented as PARTIAL/UNRESOLVED, never fabricated."""
    events = [TypedEvent(kind="H1_POI_REACTION",
                          status="PASS" if poi_context.status == "POI_REACHED" else "FAIL",
                          timestamp=poi_reaction_time)]

    if poi_reaction_time is None or not _not_future(poi_reaction_time, evaluation_time):
        return tuple(events), EntryGeometry(), ConfirmationModel.UNRESOLVED.value, "WAITING_REACTION"

    events.append(TypedEvent(kind="SUPPLY_DEMAND_SHIFT", status="PARTIAL",
                              reason="SUPPLY_DEMAND_SHIFT_POLICY = PARTIAL -- no formally signed "
                                     "definition found in this repo."))
    events.append(TypedEvent(kind="LAST_ORDERFLOW", status="UNRESOLVED",
                              reason="LAST_ORDERFLOW_POLICY = UNRESOLVED -- no deterministic "
                                     "origin-candle selector found in this repo."))

    candidates = []
    if current_gap_context is not None and current_gap_context.status in ("GAP_TOUCHED", "GAP_FILLED", "GAP_REACTED"):
        candidates.append(EntryMethod.CURRENT_GAP.value)
    if m5_ob_zone_low is not None and m5_ob_zone_high is not None:
        candidates.append(EntryMethod.ORDER_BLOCK.value)
    entry_method = EntryMethod.GAP_AND_ORDER_BLOCK.value if len(candidates) == 2 else (
        candidates[0] if candidates else EntryMethod.UNRESOLVED.value
    )

    invalidation_ref = None
    if m5_ob_zone_low is not None and m5_ob_zone_high is not None:
        invalidation_ref = m5_ob_zone_low if candidate_direction == CandidateDirection.LONG else m5_ob_zone_high

    geometry = EntryGeometry(
        entry_method=entry_method,
        entry_candidates=tuple(candidates),
        status="WAITING_ENTRY_PRICE" if candidates else "UNRESOLVED",
        structural_invalidation_type=(
            StructuralInvalidationType.M5_ORDER_BLOCK_EXTREME.value if invalidation_ref is not None
            else StructuralInvalidationType.UNRESOLVED.value
        ),
        structural_invalidation_reference=invalidation_ref,
    )
    # SUPPLY_DEMAND_SHIFT policy is PARTIAL by design -- this route never reports CONFIRMED
    # in this implementation, an honest reflection of the undefined presenter term.
    return tuple(events), geometry, ConfirmationModel.SUPPLY_DEMAND_SHIFT.value, "PARTIAL"


def evaluate_e3(
    sweep_level: LiquidityLevel,
    drop_pump_status: ConfirmationState,
    drop_pump_time: Optional[datetime],
    inverted_gap_low: Optional[float],
    inverted_gap_high: Optional[float],
    inverted_gap_origin_time: Optional[datetime],
    current_price: Optional[float] = None,
    evaluation_time: Optional[datetime] = None,
) -> Tuple[Tuple[TypedEvent, ...], EntryGeometry, str, str]:
    """LIQUIDITY_SWEEP: sweep -> drop/pump displacement -> inverted gap -> 50% pullback
    entry (rules 31-37). Sweep != entry (rule 32) -- this route requires the full chain,
    never promotes the sweep alone."""
    sweep_time = sweep_level.sweep_time
    events = [TypedEvent(kind="LIQUIDITY_SWEEP", status="PASS" if sweep_time else "FAIL", timestamp=sweep_time)]

    if sweep_time is None or not _not_future(sweep_time, evaluation_time):
        return tuple(events), EntryGeometry(), ConfirmationModel.UNRESOLVED.value, "WAITING_CONFIRMATION"

    if drop_pump_time is None or not _not_future(drop_pump_time, evaluation_time) or drop_pump_time < sweep_time:
        events.append(TypedEvent(kind="DROP_OR_PUMP", status="INDETERMINATE", timestamp=drop_pump_time))
        return tuple(events), EntryGeometry(), ConfirmationModel.SWEEP_DROP_PUMP.value, "PARTIAL"

    drop_pump_confirmed = drop_pump_status == ConfirmationState.PASS
    events.append(TypedEvent(
        kind="DROP_OR_PUMP", status="PASS" if drop_pump_confirmed else "FAIL", timestamp=drop_pump_time,
        reason=None if drop_pump_confirmed else "AG_ENTRY_DISPLACEMENT_V1 not satisfied on the "
                                                 "post-sweep candle.",
    ))
    if not drop_pump_confirmed:
        return tuple(events), EntryGeometry(), ConfirmationModel.SWEEP_DROP_PUMP.value, "PARTIAL"

    if inverted_gap_origin_time is None or not _not_future(inverted_gap_origin_time, evaluation_time) \
            or inverted_gap_origin_time < drop_pump_time:
        events.append(TypedEvent(kind="INVERTED_GAP", status="INDETERMINATE", timestamp=inverted_gap_origin_time,
                                  reason="No causally-valid inverted gap yet -- future/missing gap must not "
                                         "leak backwards."))
        return tuple(events), EntryGeometry(), ConfirmationModel.SWEEP_DROP_PUMP.value, "WAITING_CONFIRMATION"

    events.append(TypedEvent(kind="INVERTED_GAP", status="PASS", timestamp=inverted_gap_origin_time))

    if inverted_gap_low is None or inverted_gap_high is None:
        events.append(TypedEvent(kind="FIFTY_PERCENT_PULLBACK", status="UNRESOLVED",
                                  reason="Inverted gap has no bounds -- cannot compute midpoint."))
        return tuple(events), EntryGeometry(), ConfirmationModel.SWEEP_DROP_PUMP.value, "PARTIAL"

    midpoint = (inverted_gap_low + inverted_gap_high) / 2.0
    bearish = sweep_level.side == LiquiditySide.BUY_SIDE  # BSL swept -> aggressive bearish delivery
    invalidation_ref = sweep_level.price  # sweep wick, side-specific by construction of the level

    price_reached = current_price is not None and (
        (bearish and current_price <= midpoint) or (not bearish and current_price >= midpoint)
    )
    entry_status = "ENTRY_REFERENCE_AVAILABLE" if price_reached else "WAITING_ENTRY_PRICE"

    events.append(TypedEvent(kind="FIFTY_PERCENT_PULLBACK", status="PASS" if price_reached else "PENDING"))

    geometry = EntryGeometry(
        entry_method=EntryMethod.FIFTY_PERCENT_INVERTED_GAP.value,
        entry_candidates=(EntryMethod.FIFTY_PERCENT_INVERTED_GAP.value,),
        entry_reference=midpoint,
        status=entry_status,
        structural_invalidation_type=StructuralInvalidationType.LIQUIDITY_SWEEP_WICK.value,
        structural_invalidation_reference=invalidation_ref,
    )
    overall = "CONFIRMED" if price_reached else "WAITING_ENTRY_PRICE"
    return tuple(events), geometry, ConfirmationModel.SWEEP_DROP_PUMP.value, overall
