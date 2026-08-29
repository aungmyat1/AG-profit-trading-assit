"""E3 = PRICE_SWEEP_HTF_LIQUIDITY -- one of three interchangeable entry conditions in
SMC_CONDITIONAL_ENTRY_V2 (entry_models_v1.py). E3 answers WHERE/WHETHER: has a
meaningful HTF liquidity level been swept and shown failure/reclaim? It never
constructs an entry -- `eligible_for_confirmation` gates ANY of M1/M2/M3, not just M3,
via the generic `EConditionResult` envelope (`e3_to_econdition`).

REFERENCE_TIMEFRAME is NOT fixed (spec section 2/9): a caller-supplied
`liquidity.LiquidityLevel` may originate on H1, H4, or D1 (its own `.timeframe` field is
copied verbatim as `reference_timeframe`) -- E3 never forces every liquidity level to
originate on H1. CHECK_TIMEFRAME is always H1 (the reclaim/failure evidence this module
reports is the H1-scale sweep+reclaim state machine below).

Consumes the `LiquidityLevel` verbatim (from `liquidity.analyzer.liquidity_result`,
`liquidity.hierarchy.external_swing_liquidity`, or any other already-signed liquidity
source -- session high/low, PDH/PDL, equal highs/lows, protected high/low, external
swing) -- never redetects the level or its sweep state. `liquidity.status.compute_status`'s
own state machine already distinguishes the exact TOUCH/PENETRATION/SWEEP/RECLAIM
vocabulary spec section 11 asks for; this module only relabels it, it does not add a new
one:

    UNSWEPT   -> TOUCH only (no penetration confirmed yet)
    SWEPT     -> PENETRATION (current live tick trading through, not yet closed-confirmed)
    CONSUMED  -> SWEEP with no reclaim (closed beyond, still beyond -- a genuine break,
                 not a trap; NOT eligible for any maneuver's reversal thesis)
    RECLAIMED -> SWEEP + RECLAIM/FAILURE (closed beyond, then closed back -- the
                 liquidity-grab-then-reversal pattern M3 in particular requires)

A simple touch is never treated as a sweep (spec section 11): `eligible_for_confirmation`
requires RECLAIMED specifically, never SWEPT/CONSUMED/UNSWEPT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from .entry_models_v1 import CHECK_TIMEFRAME, EConditionResult, EntryModelState
from .models import CandidateDirection

E3_HTF_LIQUIDITY_SWEEP_V1 = "E3_HTF_LIQUIDITY_SWEEP_V1"

# BUY_SIDE liquidity swept above price implies a candidate bearish reversal (SHORT);
# SELL_SIDE liquidity swept below implies a candidate bullish reversal (LONG) -- the
# same convention e2_h1_poi_reaction.py / m1_character_change_inducement.py already use.
_DIRECTION_FOR_SIDE = {
    LiquiditySide.BUY_SIDE: CandidateDirection.SHORT,
    LiquiditySide.SELL_SIDE: CandidateDirection.LONG,
}


@dataclass(frozen=True)
class E3Result:
    version: str = E3_HTF_LIQUIDITY_SWEEP_V1
    symbol: str = ""
    liquidity_level: Optional[LiquidityLevel] = None
    liquidity_price: Optional[float] = None
    liquidity_type: Optional[str] = None  # LiquidityLevel.source
    reference_timeframe: Optional[str] = None  # LiquidityLevel.timeframe -- H1/H4/D1, caller-determined
    direction: Optional[str] = None  # "LONG" / "SHORT"
    penetration: bool = False
    sweep: bool = False
    reclaim: bool = False
    invalidation: Optional[str] = None  # None or "SWEEP_CONSUMED_NO_RECLAIM"
    eligible_for_confirmation: bool = False
    reason: Optional[str] = None


def evaluate_e3_htf_liquidity_sweep(symbol: str, level: LiquidityLevel) -> E3Result:
    if level is None:
        return E3Result(symbol=symbol, eligible_for_confirmation=False, reason="No candidate HTF liquidity level supplied.")

    direction = _DIRECTION_FOR_SIDE[level.side]
    penetration = level.status in (LiquidityStatus.SWEPT, LiquidityStatus.RECLAIMED, LiquidityStatus.CONSUMED)
    swept = level.status in (LiquidityStatus.RECLAIMED, LiquidityStatus.CONSUMED)
    reclaimed = level.status == LiquidityStatus.RECLAIMED

    if level.status == LiquidityStatus.CONSUMED:
        return E3Result(
            symbol=symbol, liquidity_level=level, liquidity_price=level.price, liquidity_type=level.source,
            reference_timeframe=level.timeframe, direction=direction.value, penetration=True, sweep=True,
            reclaim=False, invalidation="SWEEP_CONSUMED_NO_RECLAIM", eligible_for_confirmation=False,
            reason="Level swept and closed beyond with no reclaim -- a genuine break, not a liquidity trap; "
                   "the reversal thesis requires a reclaim.",
        )

    return E3Result(
        symbol=symbol, liquidity_level=level, liquidity_price=level.price, liquidity_type=level.source,
        reference_timeframe=level.timeframe, direction=direction.value, penetration=penetration, sweep=swept,
        reclaim=reclaimed, eligible_for_confirmation=reclaimed,
        reason=None if reclaimed else "Level not yet swept-and-reclaimed -- touch/penetration alone is not a sweep.",
    )


def e3_to_econdition(result: E3Result) -> EConditionResult:
    """Converts the detailed E3Result to the generic envelope any M1/M2/M3 maneuver
    (or the composer) can consume without importing E3Result itself."""
    touch_status = EntryModelState.WAITING_H1_REACTION.value if result.penetration \
        else EntryModelState.WAITING_HTF_TOUCH.value
    reaction_status = EntryModelState.HTF_QUALIFIED.value if result.reclaim \
        else EntryModelState.WAITING_H1_REACTION.value
    return EConditionResult(
        entry_condition="E3", symbol=result.symbol, direction=result.direction,
        reference_timeframe=result.reference_timeframe, check_timeframe=CHECK_TIMEFRAME,
        reference_type=result.liquidity_type, reference_level=result.liquidity_price,
        touch_status=touch_status, reaction_status=reaction_status,
        invalidation_status=result.invalidation, eligible_for_confirmation=result.eligible_for_confirmation,
        evidence={"liquidity_level": result.liquidity_level, "penetration": result.penetration,
                  "sweep": result.sweep, "reclaim": result.reclaim},
        missing_conditions=() if result.eligible_for_confirmation else ("H1_RECLAIM",),
    )
