"""AG_ENTRY_CONFIRMATION_V2 -- public entry point for the upgraded Entry & Confirmation
capability. Purely additive: does not modify entry_confirmation.engine.evaluate_entry_
confirmation (V1) or any V1 dataclass. See docs/specs/ENTRY_CONFIRMATION_V2_SPEC.md.

Composition order mirrors spec section 87:

    HTF context (pass-through)
        -> liquidity map (pass-through)
        -> POI context (poi.py)
        -> gap context (gap.py)
        -> route classification (route.py::classify_route)
        -> LTF confirmation for the single matching route (route.py::evaluate_e1/e2/e3)
        -> entry geometry + structural invalidation
        -> spread-aware alert/invalidation (spread.py)

Everything upstream of route classification is caller-supplied evidence; this module
never fetches market data and never redetects structure/liquidity/zones. If no route
matches, LTF confirmation is deliberately never evaluated (spec rule 73/38 -- "do not
continuously promote every 5M pattern"): status resolves to DORMANT/WAITING_CONTEXT and
`route.matching_routes` is empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from liquidity import LiquidityLevel
from strategy_engine.session import Candle
from supply_demand import ZoneResult

from .models import CandidateDirection, ConfirmationState, EntryConfirmationResult, StructureAlignment
from .models_v2 import (
    ConfirmationModel,
    ConfirmationRoute,
    DirectionalContext,
    EntryConfirmationV2Result,
    EntryGeometry,
    GapContext,
    POIContext,
    RouteResult,
    SpreadContext,
)
from .gap import evaluate_gap_context
from .poi import evaluate_poi_context
from .route import classify_route, evaluate_e1, evaluate_e2, evaluate_e3
from .spread import evaluate_spread_context


@dataclass(frozen=True)
class EntryConfirmationV2Request:
    symbol: str
    timeframe: str
    candidate_direction: CandidateDirection = CandidateDirection.NONE
    evaluation_time: Optional[datetime] = None

    v1_result: Optional[EntryConfirmationResult] = None  # caller-computed V1 result, embedded verbatim

    directional_context: DirectionalContext = field(default_factory=DirectionalContext)

    # E1 -- daily gap reaction
    daily_gap_zone: Optional[ZoneResult] = None
    daily_gap_touch_candle: Optional[Candle] = None
    daily_gap_reaction_candle: Optional[Candle] = None
    daily_gap_reaction_history: tuple = ()
    inducement_level: Optional[LiquidityLevel] = None
    structure_shift: Optional[StructureAlignment] = None

    # E2 -- H1 POI reaction
    h1_poi_zone: Optional[ZoneResult] = None
    h1_poi_liquidity_level: Optional[LiquidityLevel] = None
    h1_poi_liquidity_side: Optional[str] = None
    poi_reaction_time: Optional[datetime] = None
    poi_reacted: bool = False
    m5_ob_zone: Optional[ZoneResult] = None
    current_gap_zone: Optional[ZoneResult] = None
    current_gap_touch_candle: Optional[Candle] = None

    # E3 -- liquidity sweep
    sweep_level: Optional[LiquidityLevel] = None
    drop_pump_candle: Optional[Candle] = None
    drop_pump_history: tuple = ()
    inverted_gap_zone: Optional[ZoneResult] = None
    current_price: Optional[float] = None

    # Spread alert (A5)
    price: Optional[float] = None
    spread: Optional[float] = None


def evaluate_entry_confirmation_v2(request: EntryConfirmationV2Request) -> EntryConfirmationV2Result:
    from .displacement import evaluate_displacement

    gap_context = evaluate_gap_context(
        request.daily_gap_zone, request.daily_gap_touch_candle, request.daily_gap_reaction_candle,
        request.daily_gap_reaction_history, request.candidate_direction,
    )
    current_gap_context = evaluate_gap_context(
        request.current_gap_zone, request.current_gap_touch_candle,
        candidate_direction=request.candidate_direction,
    ) if request.current_gap_zone is not None else None

    poi_context = evaluate_poi_context(
        request.h1_poi_zone, request.h1_poi_liquidity_level, request.h1_poi_liquidity_side,
    )

    route_result = classify_route(
        gap_context=gap_context, poi_context=poi_context, poi_reacted=request.poi_reacted,
        sweep_level=request.sweep_level,
    )

    unresolved_policies = []
    events = ()
    geometry = EntryGeometry()
    confirmation_model = ConfirmationModel.NONE.value
    status = "DORMANT"

    if route_result.route == ConfirmationRoute.DAILY_GAP_REACTION.value:
        structure_shift = request.structure_shift or StructureAlignment(status=ConfirmationState.UNAVAILABLE)
        events, geometry, confirmation_model, status = evaluate_e1(
            gap_context, request.inducement_level, structure_shift, request.evaluation_time,
        )
        unresolved_policies.append("ENTRY_REFERENCE_SELECTION_POLICY")

    elif route_result.route == ConfirmationRoute.H1_POI_REACTION.value:
        events, geometry, confirmation_model, status = evaluate_e2(
            poi_context, request.poi_reaction_time,
            request.m5_ob_zone.low if request.m5_ob_zone else None,
            request.m5_ob_zone.high if request.m5_ob_zone else None,
            request.candidate_direction, current_gap_context, request.evaluation_time,
        )
        unresolved_policies.extend(["SUPPLY_DEMAND_SHIFT_POLICY", "LAST_ORDERFLOW_POLICY"])

    elif route_result.route == ConfirmationRoute.LIQUIDITY_SWEEP.value:
        drop_pump_status = ConfirmationState.INSUFFICIENT_DATA
        drop_pump_time = None
        if request.drop_pump_candle is not None:
            d = evaluate_displacement(request.drop_pump_candle, request.candidate_direction, request.drop_pump_history)
            drop_pump_status = d.status
            drop_pump_time = request.drop_pump_candle.time
        events, geometry, confirmation_model, status = evaluate_e3(
            request.sweep_level, drop_pump_status, drop_pump_time,
            request.inverted_gap_zone.low if request.inverted_gap_zone else None,
            request.inverted_gap_zone.high if request.inverted_gap_zone else None,
            request.inverted_gap_zone.origin_time if request.inverted_gap_zone else None,
            request.current_price, request.evaluation_time,
        )
        unresolved_policies.append("INVERTED_GAP_POLICY")

    elif route_result.route == ConfirmationRoute.MULTIPLE.value:
        status = "INDETERMINATE"
    elif route_result.route == ConfirmationRoute.NONE.value:
        status = "DORMANT"
    else:
        status = "WAITING_CONTEXT"

    inverted_gap_context = None
    if request.inverted_gap_zone is not None:
        from .gap import evaluate_inverted_gap_context
        inverted_gap_context = evaluate_inverted_gap_context(request.inverted_gap_zone)

    spread_context = evaluate_spread_context(
        request.price, request.spread, request.candidate_direction,
        geometry.structural_invalidation_reference,
    )

    return EntryConfirmationV2Result(
        symbol=request.symbol,
        timeframe=request.timeframe,
        evaluation_time=request.evaluation_time,
        v1=request.v1_result,
        directional_context=request.directional_context,
        gap_context=gap_context,
        inverted_gap_context=inverted_gap_context or _default_inverted_gap_context(),
        poi_context=poi_context,
        route=route_result,
        confirmation_model=confirmation_model,
        event_sequence=events,
        entry_geometry=geometry,
        spread_context=spread_context,
        status=status,
        unresolved_policies=tuple(unresolved_policies),
    )


def _default_inverted_gap_context():
    from .models_v2 import InvertedGapContext
    return InvertedGapContext(status="UNAVAILABLE")
