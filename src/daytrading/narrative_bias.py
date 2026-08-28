"""DAYTRADING_NARRATIVE_BIAS_V1 -- "what kind of day is developing, and what is the
expected direction of price delivery?" (DayTrading skill 1). Interprets, and never
redetects, D1/H1 market_structure.StructureResult, liquidity.LiquidityResult, an optional
supply_demand dealing range (premium/discount) and an optional supply_demand FVG query
(inefficiency) -- all caller-supplied. Reuses market_structure's own CHoCH detection as
the only reversal evidence (see REVERSAL_CLASSIFICATION_POLICY_PARTIAL in models.py); no
new structure/liquidity detector, no invented numeric thresholds.

EXPECTED_PROFILE vs REALIZED_PROFILE (spec section 10) are two different entry points,
never the same call: `evaluate_narrative_bias()` only ever sees H1 candles at/before
`evaluation_time` (defensively re-filtered here even if the caller over-supplies) and
sets `expected_profile`; `evaluate_realized_narrative_bias()` is for completed-day
hindsight/labeling and sets `realized_profile` only. Structure/liquidity/dealing-range
inputs must be pre-computed accordingly by the caller for whichever entry point is used.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Sequence, Tuple

from liquidity.models import LiquiditySide, LiquidityStatus
from market_structure.models import STATE_BEARISH, STATE_BULLISH, STATE_UNDEFINED, StructurePointKind

from .models import (
    BIAS_UNRESOLVED,
    DELIVERY_BALANCED,
    DELIVERY_DOWN,
    DELIVERY_UNRESOLVED,
    DELIVERY_UP,
    DIRECTION_LONG,
    DIRECTION_NONE,
    DIRECTION_SHORT,
    DIRECTION_UNRESOLVED,
    EVIDENCE_CONFLICTS,
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_NEUTRAL,
    EVIDENCE_SUPPORTS,
    NARRATIVE_STATUS_CONFLICTED,
    NARRATIVE_STATUS_INSUFFICIENT_DATA,
    NARRATIVE_STATUS_SUPPORTED,
    NARRATIVE_STATUS_UNRESOLVED,
    NarrativeBiasResult,
    PROFILE_BEARISH_DAY,
    PROFILE_BEARISH_REVERSAL_DAY,
    PROFILE_BULLISH_DAY,
    PROFILE_BULLISH_REVERSAL_DAY,
    PROFILE_CONSOLIDATION_DAY,
    PROFILE_UNRESOLVED,
    REVERSAL_CLASSIFICATION_POLICY_PARTIAL,
    PROFILE_TO_BIAS,
)
from .true_day import TrueDayContext, causal_candles, true_day_open as _true_day_open, true_day_window

if TYPE_CHECKING:
    from liquidity.models import LiquidityResult
    from market_structure.models import StructureResult
    from supply_demand.models import ZoneQueryResult
    from supply_demand.native_zones import DealingRangeZones

_SIDE_FOR_STATE = {STATE_BULLISH: LiquiditySide.BUY_SIDE, STATE_BEARISH: LiquiditySide.SELL_SIDE}
_OPPOSITE_SIDE = {LiquiditySide.BUY_SIDE: LiquiditySide.SELL_SIDE, LiquiditySide.SELL_SIDE: LiquiditySide.BUY_SIDE}
_DELIVERY_FOR_STATE = {STATE_BULLISH: DELIVERY_UP, STATE_BEARISH: DELIVERY_DOWN}
_REVERSAL_CHOCH_FOR_STATE = {
    STATE_BULLISH: StructurePointKind.BULLISH_CHOCH,  # D1 bullish but day opened down -> needs an H1 bullish CHoCH
    STATE_BEARISH: StructurePointKind.BEARISH_CHOCH,
}
_REVERSAL_PROFILE_FOR_STATE = {STATE_BULLISH: PROFILE_BULLISH_REVERSAL_DAY, STATE_BEARISH: PROFILE_BEARISH_REVERSAL_DAY}
_CONTINUATION_PROFILE_FOR_STATE = {STATE_BULLISH: PROFILE_BULLISH_DAY, STATE_BEARISH: PROFILE_BEARISH_DAY}
_DIRECTION_FOR_STATE = {STATE_BULLISH: DIRECTION_LONG, STATE_BEARISH: DIRECTION_SHORT}


def _initial_delivery(true_open: Optional[float], last_close: Optional[float]) -> str:
    if true_open is None or last_close is None:
        return DELIVERY_UNRESOLVED
    if last_close > true_open:
        return DELIVERY_UP
    if last_close < true_open:
        return DELIVERY_DOWN
    return DELIVERY_BALANCED


def _price_location(dealing_range: Optional["DealingRangeZones"]) -> Optional[str]:
    return dealing_range.current_zone if dealing_range is not None else None


def _inefficiency_levels(
    inefficiency: Optional["ZoneQueryResult"], reference_price: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    if inefficiency is None or reference_price is None or not getattr(inefficiency, "zones", None):
        return None, None
    above = [z.low for z in inefficiency.zones if z.low is not None and z.low > reference_price]
    below = [z.high for z in inefficiency.zones if z.high is not None and z.high < reference_price]
    return (min(above) if above else None, max(below) if below else None)


def _build(
    *, symbol: str, reference_timeframe: str, day_context: Optional[TrueDayContext],
    evaluation_time: Optional[datetime], true_open: Optional[float],
    profile: str, expected_delivery: str, preferred_direction: str, initial_delivery: str,
    primary_draw: Optional[str], major_target: Optional[float], invalidation: Optional[float],
    supporting: Sequence[str], contradictory: Sequence[str], reason: Optional[str],
    structure_evidence: str, liquidity_evidence: str, premium_discount_evidence: str,
    inefficiency_evidence: str, narrative_status: str, price_location: Optional[str],
    inefficiency_above: Optional[float], inefficiency_below: Optional[float],
    as_realized: bool,
) -> NarrativeBiasResult:
    bias = PROFILE_TO_BIAS.get(profile, BIAS_UNRESOLVED)
    status = "OK" if narrative_status != NARRATIVE_STATUS_INSUFFICIENT_DATA else "INSUFFICIENT_DATA"
    return NarrativeBiasResult(
        symbol=symbol, reference_timeframe=reference_timeframe, bias=bias,
        primary_draw=primary_draw, major_target=major_target,
        supporting_evidence=tuple(supporting), contradictory_evidence=tuple(contradictory),
        invalidation=invalidation, status=status, reason=reason,
        evaluation_time=evaluation_time,
        reference_timezone=(day_context.reference_timezone if day_context else None),
        trading_date=(day_context.trading_date if day_context else None),
        true_day_open=true_open,
        initial_delivery=initial_delivery,
        expected_delivery=(expected_delivery if not as_realized else DELIVERY_UNRESOLVED),
        preferred_direction=(preferred_direction if not as_realized else DIRECTION_UNRESOLVED),
        expected_profile=(profile if not as_realized else PROFILE_UNRESOLVED),
        realized_profile=(profile if as_realized else None),
        price_location=price_location, inefficiency_above=inefficiency_above, inefficiency_below=inefficiency_below,
        structure_evidence=structure_evidence, liquidity_evidence=liquidity_evidence,
        premium_discount_evidence=premium_discount_evidence, inefficiency_evidence=inefficiency_evidence,
        narrative_status=narrative_status,
    )


def _classify(
    symbol: str, reference_timeframe: str, structure: Optional["StructureResult"],
    liquidity: Optional["LiquidityResult"], dealing_range: Optional["DealingRangeZones"],
    day_context: Optional[TrueDayContext], evaluation_time: Optional[datetime],
    true_open: Optional[float], last_close: Optional[float], h1_structure: Optional["StructureResult"],
    inefficiency: Optional["ZoneQueryResult"], as_realized: bool,
) -> NarrativeBiasResult:
    price_location = _price_location(dealing_range)
    ineff_above, ineff_below = _inefficiency_levels(inefficiency, last_close if last_close is not None else
                                                      (dealing_range.current_price if dealing_range else None))
    premium_discount_evidence = EVIDENCE_NEUTRAL if price_location else EVIDENCE_INSUFFICIENT
    inefficiency_evidence = EVIDENCE_NEUTRAL if (ineff_above or ineff_below) else EVIDENCE_INSUFFICIENT

    def build(**kw):
        return _build(symbol=symbol, reference_timeframe=reference_timeframe, day_context=day_context,
                       evaluation_time=evaluation_time, true_open=true_open, price_location=price_location,
                       inefficiency_above=ineff_above, inefficiency_below=ineff_below,
                       inefficiency_evidence=kw.pop("inefficiency_evidence", inefficiency_evidence),
                       premium_discount_evidence=kw.pop("premium_discount_evidence", premium_discount_evidence),
                       as_realized=as_realized, **kw)

    if structure is None or structure.status != "VALID":
        return build(profile=PROFILE_UNRESOLVED, expected_delivery=DELIVERY_UNRESOLVED,
                     preferred_direction=DIRECTION_UNRESOLVED, initial_delivery=DELIVERY_UNRESOLVED,
                     primary_draw=None, major_target=None, invalidation=None, supporting=(), contradictory=(),
                     structure_evidence=EVIDENCE_INSUFFICIENT, liquidity_evidence=EVIDENCE_INSUFFICIENT,
                     narrative_status=NARRATIVE_STATUS_INSUFFICIENT_DATA,
                     reason=f"structure unavailable on {reference_timeframe} "
                            f"(status={getattr(structure, 'status', None)}).")
    if liquidity is None or liquidity.status not in ("LIQUIDITY_OK", "NO_LIQUIDITY_LEVELS"):
        return build(profile=PROFILE_UNRESOLVED, expected_delivery=DELIVERY_UNRESOLVED,
                     preferred_direction=DIRECTION_UNRESOLVED, initial_delivery=DELIVERY_UNRESOLVED,
                     primary_draw=None, major_target=None, invalidation=None, supporting=(), contradictory=(),
                     structure_evidence=EVIDENCE_SUPPORTS, liquidity_evidence=EVIDENCE_INSUFFICIENT,
                     narrative_status=NARRATIVE_STATUS_INSUFFICIENT_DATA,
                     reason=f"liquidity unavailable on {reference_timeframe} "
                            f"(status={getattr(liquidity, 'status', None)}).")

    state = structure.state
    initial_delivery = _initial_delivery(true_open, last_close)

    if state == STATE_UNDEFINED:
        if price_location:
            return build(profile=PROFILE_CONSOLIDATION_DAY, expected_delivery=DELIVERY_BALANCED,
                         preferred_direction=DIRECTION_NONE, initial_delivery=initial_delivery,
                         primary_draw=None, major_target=None, invalidation=None,
                         supporting=(f"no clear {reference_timeframe} structure; price in "
                                     f"{price_location} of the reference dealing range.",),
                         contradictory=(), structure_evidence=EVIDENCE_NEUTRAL, liquidity_evidence=EVIDENCE_NEUTRAL,
                         narrative_status=NARRATIVE_STATUS_SUPPORTED,
                         reason="structure undefined -- treated as consolidation/range context, "
                                "direction not forced.")
        return build(profile=PROFILE_UNRESOLVED, expected_delivery=DELIVERY_UNRESOLVED,
                     preferred_direction=DIRECTION_UNRESOLVED, initial_delivery=initial_delivery,
                     primary_draw=None, major_target=None, invalidation=None, supporting=(), contradictory=(),
                     structure_evidence=EVIDENCE_NEUTRAL, liquidity_evidence=EVIDENCE_INSUFFICIENT,
                     narrative_status=NARRATIVE_STATUS_INSUFFICIENT_DATA,
                     reason="structure undefined and no dealing range available to assess consolidation.")

    side = _SIDE_FOR_STATE[state]
    opposite = _OPPOSITE_SIDE[side]
    target_level = liquidity.nearest_buy_side if side == LiquiditySide.BUY_SIDE else liquidity.nearest_sell_side
    opposite_level = liquidity.nearest_sell_side if side == LiquiditySide.BUY_SIDE else liquidity.nearest_buy_side

    supporting = [f"{reference_timeframe} structure state = {state}."]
    contradictory = []
    if opposite_level is not None and opposite_level.status == LiquidityStatus.UNSWEPT:
        contradictory.append(f"unswept {opposite.value} liquidity at {opposite_level.price} remains "
                              f"on the opposite side -- not enough alone to flip the structural bias.")

    if target_level is None:
        return build(profile=PROFILE_UNRESOLVED, expected_delivery=DELIVERY_UNRESOLVED,
                     preferred_direction=DIRECTION_UNRESOLVED, initial_delivery=initial_delivery,
                     primary_draw=None, major_target=None, invalidation=None,
                     supporting=tuple(supporting), contradictory=tuple(contradictory),
                     structure_evidence=EVIDENCE_SUPPORTS, liquidity_evidence=EVIDENCE_INSUFFICIENT,
                     narrative_status=NARRATIVE_STATUS_INSUFFICIENT_DATA,
                     reason=f"{reference_timeframe} structural bias present; no remaining {side.value} "
                            f"liquidity objective identified -- structure alone is not narrative "
                            f"(spec section 17).")

    if target_level.status != LiquidityStatus.UNSWEPT:
        contradictory.append(f"{side.value} liquidity at {target_level.price} already "
                              f"{target_level.status.value} -- prior draw already reached.")
        return build(profile=PROFILE_UNRESOLVED, expected_delivery=DELIVERY_UNRESOLVED,
                     preferred_direction=DIRECTION_UNRESOLVED, initial_delivery=initial_delivery,
                     primary_draw=None, major_target=None, invalidation=None,
                     supporting=tuple(supporting), contradictory=tuple(contradictory),
                     structure_evidence=EVIDENCE_SUPPORTS, liquidity_evidence=EVIDENCE_CONFLICTS,
                     narrative_status=NARRATIVE_STATUS_CONFLICTED,
                     reason="prior liquidity objective already reached -- narrative in transition, "
                            "continuation not assumed.")

    supporting.append(f"remaining {side.value} liquidity at {target_level.price} unswept.")
    liquidity_evidence = EVIDENCE_SUPPORTS
    delivery = _DELIVERY_FOR_STATE[state]
    direction = _DIRECTION_FOR_STATE[state]
    invalidation = opposite_level.price if opposite_level is not None else None

    if initial_delivery == delivery:
        return build(profile=_CONTINUATION_PROFILE_FOR_STATE[state], expected_delivery=delivery,
                     preferred_direction=direction, initial_delivery=initial_delivery,
                     primary_draw=side.value, major_target=target_level.price, invalidation=invalidation,
                     supporting=tuple(supporting), contradictory=tuple(contradictory),
                     structure_evidence=EVIDENCE_SUPPORTS, liquidity_evidence=liquidity_evidence,
                     narrative_status=(NARRATIVE_STATUS_CONFLICTED if contradictory else NARRATIVE_STATUS_SUPPORTED),
                     reason=None)

    if initial_delivery in (DELIVERY_UNRESOLVED, DELIVERY_BALANCED):
        return build(profile=PROFILE_UNRESOLVED, expected_delivery=DELIVERY_UNRESOLVED,
                     preferred_direction=DIRECTION_UNRESOLVED, initial_delivery=initial_delivery,
                     primary_draw=side.value, major_target=target_level.price, invalidation=invalidation,
                     supporting=tuple(supporting), contradictory=tuple(contradictory),
                     structure_evidence=EVIDENCE_SUPPORTS, liquidity_evidence=liquidity_evidence,
                     narrative_status=NARRATIVE_STATUS_INSUFFICIENT_DATA,
                     reason=f"{reference_timeframe} structural bias present but intraday delivery not yet "
                            f"established (initial_delivery={initial_delivery}).")

    # initial_delivery opposes the D1 structural direction -- only a confirmed H1 CHoCH
    # back toward that direction is treated as reversal evidence (no invented thresholds).
    choch_kind = getattr(getattr(h1_structure, "latest_choch", None), "kind", None)
    if h1_structure is not None and choch_kind == _REVERSAL_CHOCH_FOR_STATE[state]:
        contradictory.append(f"initial_delivery={initial_delivery} opposed {reference_timeframe} "
                              f"structure before the H1 CHoCH reversed it.")
        supporting.append(f"H1 {choch_kind.value} confirms reversal back toward {reference_timeframe} structure.")
        return build(profile=_REVERSAL_PROFILE_FOR_STATE[state], expected_delivery=delivery,
                     preferred_direction=direction, initial_delivery=initial_delivery,
                     primary_draw=side.value, major_target=target_level.price, invalidation=invalidation,
                     supporting=tuple(supporting), contradictory=tuple(contradictory),
                     structure_evidence=EVIDENCE_SUPPORTS, liquidity_evidence=liquidity_evidence,
                     narrative_status=NARRATIVE_STATUS_SUPPORTED,
                     reason=REVERSAL_CLASSIFICATION_POLICY_PARTIAL)

    contradictory.append(f"initial_delivery={initial_delivery} opposes {reference_timeframe} structure "
                          f"({state}); no H1 CHoCH reversal evidence yet.")
    return build(profile=PROFILE_UNRESOLVED, expected_delivery=DELIVERY_UNRESOLVED,
                 preferred_direction=DIRECTION_UNRESOLVED, initial_delivery=initial_delivery,
                 primary_draw=side.value, major_target=target_level.price, invalidation=invalidation,
                 supporting=tuple(supporting), contradictory=tuple(contradictory),
                 structure_evidence=EVIDENCE_SUPPORTS, liquidity_evidence=liquidity_evidence,
                 narrative_status=NARRATIVE_STATUS_CONFLICTED,
                 reason="initial delivery opposes structure and no confirming reversal evidence exists yet. "
                        + REVERSAL_CLASSIFICATION_POLICY_PARTIAL)


def evaluate_narrative_bias(
    symbol: str,
    reference_timeframe: str,
    structure: Optional["StructureResult"],
    liquidity: Optional["LiquidityResult"],
    dealing_range: Optional["DealingRangeZones"] = None,
    evaluation_time: Optional[datetime] = None,
    h1_structure: Optional["StructureResult"] = None,
    h1_candles: Sequence = (),
    inefficiency: Optional["ZoneQueryResult"] = None,
) -> NarrativeBiasResult:
    """EXPECTED_PROFILE (live/causal). `evaluation_time` defaults to now (UTC) if omitted.
    `h1_candles` may be any set of H1 candles; only those inside the true day and
    at/before `evaluation_time` are ever used (zero look-ahead, spec section 11)."""
    evaluation_time = evaluation_time or datetime.now(timezone.utc)
    day_context = true_day_window(evaluation_time)
    causal = causal_candles(h1_candles, evaluation_time, day_context)
    true_open = _true_day_open(causal, day_context)
    last_close = causal[-1].close if causal else None
    return _classify(symbol, reference_timeframe, structure, liquidity, dealing_range, day_context,
                      evaluation_time, true_open, last_close, h1_structure, inefficiency, as_realized=False)


def evaluate_realized_narrative_bias(
    symbol: str,
    reference_timeframe: str,
    structure: Optional["StructureResult"],
    liquidity: Optional["LiquidityResult"],
    dealing_range: Optional["DealingRangeZones"] = None,
    h1_structure: Optional["StructureResult"] = None,
    h1_candles: Sequence = (),
    inefficiency: Optional["ZoneQueryResult"] = None,
    day_context: Optional[TrueDayContext] = None,
) -> NarrativeBiasResult:
    """REALIZED_PROFILE (post-hoc/hindsight labeling, spec section 10). May use the full
    completed day's candles; never called from the live path. `structure`/`liquidity`/
    `dealing_range` must themselves already reflect the completed day if that's the
    intent -- this function does not refetch or re-derive them."""
    if day_context is None and h1_candles:
        day_context = true_day_window(max(c.time for c in h1_candles))
    ordered = tuple(sorted(h1_candles, key=lambda c: c.time)) if h1_candles else ()
    in_day = tuple(c for c in ordered
                    if day_context is None or (day_context.day_start_utc <= c.time < day_context.day_end_utc))
    true_open = _true_day_open(in_day, day_context) if day_context else None
    last_close = in_day[-1].close if in_day else None
    return _classify(symbol, reference_timeframe, structure, liquidity, dealing_range, day_context,
                      None, true_open, last_close, h1_structure, inefficiency, as_realized=True)
