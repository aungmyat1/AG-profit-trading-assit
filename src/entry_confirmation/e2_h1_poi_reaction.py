"""E2 = PRICE_REACT_H1_POI -- one of three interchangeable entry conditions in
SMC_CONDITIONAL_ENTRY_V2 (entry_models_v1.py). H1 answers WHERE (location, via poi.py's
already-signed POI inventory) AND is also the CHECK timeframe (spec section 2: E2's
REFERENCE_TIMEFRAME = H1, CHECK_TIMEFRAME = H1 -- both on H1, but conceptually
separate: location vs. reaction). This module owns ONLY the H1-POI-specific gating: has
price reached the POI, and did it produce a qualifying M5 reaction? It never goes
further than that -- `eligible_for_confirmation` gates ANY of M1/M2/M3, not just M2, via
the generic `EConditionResult` envelope (`e2_to_econdition`).

SEMANTIC CHANGE from the prior revision of this file (E2_PRICE_REACT_H1_POI_V2): that
version delegated everything downstream of "a relevant M5 sweep occurred" to
`engine_v2_1.evaluate_reversal_sweep_shift` (SMC_SWEEP_SHIFT_ARRAY_V1: sweep -> CHoCH ->
displacement -> FVG/OB). That pipeline is now recognized as belonging to M3
(SWEEP_DROP_PUMP, m3_sweep_drop_pump.py) -- HTF-liquidity-sweep-driven, not
supply/demand-shift-driven. Reusing it here would have produced
`M1 == M2 == M3 == sweep + CHoCH + displacement + FVG`, exactly the failure mode this
architecture prohibits. `engine_v2_1.py`/`sweep_shift.py` themselves are untouched --
only this file's downstream composition changed; M3 reuses them directly. No
functionality was deleted, only re-homed to its correct model.

POIContext carries no timestamp, so "when did price interact with the H1 POI" is found
the same mechanical way `daytrading_runtime/snapshot.py::build_e1_result` already finds
a D1 gap's touch candle: scan candles chronologically for the first one intersecting the
zone's [low, high] bounds -- not a new rule, the same technique applied to an H1 zone.
"Reaction" (touch != reaction, spec section 8) reuses the same qualifying-candle
technique `gap.py::evaluate_gap_context` already uses for GAP_REACTED: the first
post-interaction M5 candle that passes AG_ENTRY_DISPLACEMENT_V1 in the candidate
direction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from strategy_engine.session import Candle
from supply_demand import ZoneResult

from .displacement import evaluate_displacement
from .entry_models_v1 import REFERENCE_TIMEFRAME_E2, CHECK_TIMEFRAME, EConditionResult, EntryModelState
from .models import CandidateDirection, ConfirmationState
from .poi import evaluate_poi_context

E2_H1_POI_REACTION_V1 = "E2_H1_POI_REACTION_V1"

_DORMANT_POI_STATUSES = ("UNRESOLVED", "WAITING_POI")


@dataclass(frozen=True)
class E2Result:
    version: str = E2_H1_POI_REACTION_V1
    symbol: str = ""
    poi: Optional[ZoneResult] = None
    poi_type: Optional[str] = None
    direction: Optional[str] = None  # "LONG" / "SHORT"
    touch_status: str = "WAITING_POI"  # WAITING_POI / POI_TOUCHED
    reaction_status: str = "WAITING_REACTION"  # WAITING_REACTION / POI_REACTED
    invalidation: Optional[str] = None  # None or "POI_INVALIDATED"
    eligible_for_confirmation: bool = False
    poi_interaction_time: Optional[datetime] = None
    reaction_time: Optional[datetime] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class E2PoiReactionRequest:
    symbol: str
    h1_poi_zone: Optional[ZoneResult]
    h1_candles: Sequence[Candle] = ()  # for the POI touch-time scan
    m5_candles: Sequence[Candle] = ()  # closed M5 bars, oldest first, spanning the POI-interaction window
    m5_displacement_history: Sequence[Candle] = ()  # >=20 prior bars, oldest first, for evaluate_displacement
    evaluation_time: Optional[datetime] = None


def _dormant_result(symbol: str, poi_zone: Optional[ZoneResult], poi_type: Optional[str],
                     touch_status: str, reason: str, invalidation: Optional[str] = None) -> E2Result:
    return E2Result(symbol=symbol, poi=poi_zone, poi_type=poi_type, touch_status=touch_status,
                     invalidation=invalidation, eligible_for_confirmation=False, reason=reason)


def _poi_interaction_time(zone: ZoneResult, candles: Sequence[Candle]) -> Optional[datetime]:
    if zone.low is None or zone.high is None:
        return None
    for candle in candles:
        if zone.origin_time is not None and candle.time <= zone.origin_time:
            continue
        if candle.low <= zone.high and candle.high >= zone.low:
            return candle.time
    return None


def _reaction_direction(poi_direction: Optional[str]) -> Optional[CandidateDirection]:
    # A bearish H1 POI implies a candidate SHORT reaction (price rallies INTO supply and
    # is expected to reverse down); a bullish POI implies LONG (spec section 9).
    if poi_direction == "BEARISH":
        return CandidateDirection.SHORT
    if poi_direction == "BULLISH":
        return CandidateDirection.LONG
    return None


def _first_reacting_candle(
    candles: Sequence[Candle], not_before: datetime, direction: CandidateDirection,
    history: Sequence[Candle], evaluation_time: Optional[datetime],
) -> Optional[Candle]:
    after = [c for c in candles if c.time > not_before and (evaluation_time is None or c.time <= evaluation_time)]
    for candle in after:
        prior = [c for c in candles if c.time < candle.time]
        evidence = evaluate_displacement(candle, direction, prior or history)
        if evidence.status == ConfirmationState.PASS:
            return candle
    return None


def evaluate_e2_h1_poi_reaction(request: E2PoiReactionRequest) -> E2Result:
    if request.h1_poi_zone is None:
        return _dormant_result(request.symbol, None, None, "WAITING_POI", "No H1 POI zone supplied.")

    poi_context = evaluate_poi_context(request.h1_poi_zone)

    if poi_context.status in _DORMANT_POI_STATUSES:
        return _dormant_result(request.symbol, request.h1_poi_zone, poi_context.poi_type, "WAITING_POI",
                                poi_context.reason or "Waiting for POI.")
    if poi_context.status == "INVALIDATED":
        return _dormant_result(request.symbol, request.h1_poi_zone, poi_context.poi_type, "WAITING_POI",
                                "H1 POI invalidated.", invalidation="POI_INVALIDATED")

    direction = _reaction_direction(poi_context.poi_direction)
    if direction is None:
        return _dormant_result(request.symbol, request.h1_poi_zone, poi_context.poi_type, "WAITING_POI",
                                "H1 POI direction unresolved -- cannot determine candidate reaction direction.")

    poi_interaction_time = _poi_interaction_time(request.h1_poi_zone, request.h1_candles)
    if poi_interaction_time is None:
        return E2Result(symbol=request.symbol, poi=request.h1_poi_zone, poi_type=poi_context.poi_type,
                         direction=direction.value, touch_status="WAITING_POI", eligible_for_confirmation=False,
                         reason="POI status reports interaction but no touching H1 candle found in supplied history.")

    reaction_candle = _first_reacting_candle(
        request.m5_candles, poi_interaction_time, direction,
        request.m5_displacement_history, request.evaluation_time,
    )
    if reaction_candle is None:
        return E2Result(symbol=request.symbol, poi=request.h1_poi_zone, poi_type=poi_context.poi_type,
                         direction=direction.value, touch_status="POI_TOUCHED", reaction_status="WAITING_REACTION",
                         eligible_for_confirmation=False, poi_interaction_time=poi_interaction_time,
                         reason="POI touched but no M5 candle has yet qualified under AG_ENTRY_DISPLACEMENT_V1.")

    return E2Result(
        symbol=request.symbol, poi=request.h1_poi_zone, poi_type=poi_context.poi_type, direction=direction.value,
        touch_status="POI_TOUCHED", reaction_status="POI_REACTED", eligible_for_confirmation=True,
        poi_interaction_time=poi_interaction_time, reaction_time=reaction_candle.time,
    )


def e2_to_econdition(result: E2Result) -> EConditionResult:
    """Converts the detailed E2Result to the generic envelope any M1/M2/M3 maneuver
    (or the composer) can consume without importing E2Result itself."""
    touch_status = EntryModelState.WAITING_H1_REACTION.value if result.touch_status == "POI_TOUCHED" \
        else EntryModelState.WAITING_HTF_TOUCH.value
    reaction_status = EntryModelState.HTF_QUALIFIED.value if result.reaction_status == "POI_REACTED" \
        else EntryModelState.WAITING_H1_REACTION.value
    return EConditionResult(
        entry_condition="E2", symbol=result.symbol, direction=result.direction,
        reference_timeframe=REFERENCE_TIMEFRAME_E2, check_timeframe=CHECK_TIMEFRAME,
        reference_type=result.poi_type,
        reference_low=result.poi.low if result.poi is not None else None,
        reference_high=result.poi.high if result.poi is not None else None,
        touch_status=touch_status, reaction_status=reaction_status,
        invalidation_status=result.invalidation, eligible_for_confirmation=result.eligible_for_confirmation,
        evidence={"poi": result.poi, "poi_interaction_time": result.poi_interaction_time,
                  "reaction_time": result.reaction_time},
        missing_conditions=() if result.eligible_for_confirmation else ("H1_REACTION",),
    )
