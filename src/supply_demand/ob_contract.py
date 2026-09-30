"""AG Order Block Validator -- AG_ORDER_BLOCK_V1 (frozen by owner 2026-08-26).

smc.ob() = candidate detector only. smc.fvg() = FVG detector only. This module is the
FINAL Order Block authority: it turns an smc.ob() CANDIDATE into a project-owned
ValidatedOrderBlock by checking structure, FVG, geometry, mitigation, and invalidation
against the frozen contract below.

AG_ORDER_BLOCK_V1 (verbatim, as frozen by the owner):

    PIVOT_OB:  identification = last opposing closed candle before qualifying displacement
               zone = FULL_CANDLE
    SHADOW_OB: identification = qualifying wick-rejection/sweep candle before displacement
               zone = WICK_TIP_TO_BODY
    FLIP_OB:   identification = failed prior S/D reaction/base displaced in opposite direction
               zone = FULL_CANDLE

    STRUCTURE: required = true; confirmation = CLOSED_CANDLE; event = matching BOS or CHOCH;
               source = INTERNAL_OR_EXTERNAL
    FVG:       required = true; direction must match OB; MAX_CANDLES_TO_FVG = 3;
               minimum_size = strictly > 0; proximity = SAME_DISPLACEMENT_LEG;
               no literal OB/FVG overlap required
    MITIGATION:   WICK_TOUCH_BOUNDARY
    INVALIDATION: Bullish = closed candle closes below zone low
                  Bearish = closed candle closes above zone high

IMPLEMENTATION CHOICES NOT VERBATIM IN THE FROZEN SPEC (flagged, not hidden):

  - PIVOT_OB vs. SHADOW_OB classification: the owner defines WHAT each family means but
    not the exact numeric test that decides which one a given smc.ob() candidate is.
    This module classifies by body-to-range ratio of the candidate's own origin candle:
    body_ratio = |close-open| / (high-low). body_ratio >= threshold -> PIVOT_OB (a
    "normal" opposing candle, body-dominant); below it -> SHADOW_OB (wick-dominant, i.e.
    rejection/sweep character). The threshold is NOT a frozen owner number -- it is an
    explicit, named, configurable AG_ORDER_BLOCK_V1 parameter,
    `pivot_shadow_body_ratio_threshold` in config/ag_order_block_v1.yaml (default 0.5,
    the natural body-vs-wick midpoint), loaded via ob_config.py. No magic number lives
    in this module -- see AGOrderBlockConfig below.

  - FLIP_OB classification is NOT implemented. "Failed prior S/D reaction/base
    displaced in opposite direction" requires tracking prior zones, a lookback window,
    and a proximity rule -- none of which the frozen contract specifies (unlike FVG's
    MAX_CANDLES_TO_FVG=3). Per instruction not to guess, no candidate is ever classified
    FLIP_OB; every candidate resolves to PIVOT_OB or SHADOW_OB via the rule above. The
    FLIP_OB enum value and its FULL_CANDLE zone rule are frozen and ready for when
    identification logic is defined.

  - STRUCTURE "source = INTERNAL_OR_EXTERNAL": market_structure/ currently has exactly
    ONE swing-length-based classifier, with no internal/external tiering. `structure_source`
    is preserved as a field on ValidatedOrderBlock for later research but is always
    "UNCLASSIFIED_SINGLE_SWING_LENGTH" today -- not a real internal/external distinction yet.

  - STRUCTURE matching window: the frozen contract gives no candle-count bound for the
    structure event (only FVG has one, MAX_CANDLES_TO_FVG=3). This module requires a
    matching-direction BOS/CHOCH confirmed at or after the OB's origin_time, anywhere in
    the analyzed window -- no additional window invented beyond what's frozen.

Explicitly UNSIGNED (owner instruction: do not infer from the reference image):
  L1_L2_CLASSIFICATION = UNSIGNED
  INSIDE_BAR_FLIP_RULE = UNSIGNED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from market_structure import StructurePoint, StructurePointKind, structural_breaks_for_candles
from strategy_engine.session import Candle

from .models import ZoneDirection, ZoneResult
from .ob_config import AGOrderBlockConfig, load_ag_order_block_config

MAX_CANDLES_TO_FVG = 3

L1_L2_CLASSIFICATION = "UNSIGNED"
INSIDE_BAR_FLIP_RULE = "UNSIGNED"


class OBFamily(str, Enum):
    PIVOT_OB = "PIVOT_OB"
    SHADOW_OB = "SHADOW_OB"
    FLIP_OB = "FLIP_OB"       # frozen (zone=FULL_CANDLE) but never assigned -- see module docstring
    UNKNOWN_OB = "UNKNOWN_OB"


class OBValidationStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    VALID = "VALID"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ValidatedOrderBlock:
    symbol: str
    timeframe: str
    family: OBFamily
    status: OBValidationStatus
    direction: ZoneDirection
    low: Optional[float]
    high: Optional[float]
    origin_time: Optional[datetime]
    candidate: ZoneResult  # the underlying smc.ob() ZoneResult, unmodified -- see smc_adapter.py
    matching_fvg: Optional[ZoneResult] = None
    structure_event: Optional[StructurePoint] = None
    structure_source: str = "UNCLASSIFIED_SINGLE_SWING_LENGTH"  # see module docstring
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


def validate_order_blocks(
    ob_candidates: Sequence[ZoneResult],
    fvg_candidates: Sequence[ZoneResult],
    candles: Sequence[Candle],
    config: Optional[AGOrderBlockConfig] = None,
) -> List[ValidatedOrderBlock]:
    """Batch entry point: candles is the SAME candle list ob_candidates/fvg_candidates
    were computed from (positions must line up for the MAX_CANDLES_TO_FVG window and
    the structure-event lookup)."""
    config = config or load_ag_order_block_config()
    time_to_pos = {c.time: i for i, c in enumerate(candles)}
    breaks = structural_breaks_for_candles(candles)
    return [
        validate_order_block(cand, candles, time_to_pos, fvg_candidates, breaks, config)
        for cand in ob_candidates
    ]


def validate_order_block(
    candidate: ZoneResult,
    candles: Sequence[Candle],
    time_to_pos: Optional[dict] = None,
    fvg_candidates: Sequence[ZoneResult] = (),
    breaks: Optional[Sequence[StructurePoint]] = None,
    config: Optional[AGOrderBlockConfig] = None,
) -> ValidatedOrderBlock:
    """candidate must be a ZoneResult with family=ORDER_BLOCK (see smc_adapter.order_blocks()).
    candles must include the candidate's own origin candle and enough history after it
    to evaluate structure/FVG/mitigation/invalidation."""
    config = config or load_ag_order_block_config()
    time_to_pos = time_to_pos if time_to_pos is not None else {c.time: i for i, c in enumerate(candles)}
    breaks = breaks if breaks is not None else structural_breaks_for_candles(candles)

    if candidate.low is None or candidate.high is None or candidate.high < candidate.low:
        return _result(candidate, OBFamily.UNKNOWN_OB, OBValidationStatus.REJECTED,
                        low=candidate.low, high=candidate.high, reason_codes=("INVALID_OB_GEOMETRY",))

    origin_pos = time_to_pos.get(candidate.origin_time)
    if origin_pos is None:
        return _result(candidate, OBFamily.UNKNOWN_OB, OBValidationStatus.REJECTED,
                        low=candidate.low, high=candidate.high, reason_codes=("INVALID_OB_GEOMETRY",))

    origin_candle = candles[origin_pos]
    is_bullish = candidate.direction == ZoneDirection.BULLISH

    family, low, high = _classify_family_and_zone(origin_candle, is_bullish, config.pivot_shadow_body_ratio_threshold)

    reason_codes: List[str] = []

    matching_break = _find_matching_break(breaks, candidate.origin_time, is_bullish)
    if matching_break is None:
        reason_codes.append("REQUIRED_STRUCTURE_MISSING")

    matching_fvg, fvg_reason = _find_matching_fvg(fvg_candidates, candidate.origin_time, is_bullish, time_to_pos)
    if fvg_reason:
        reason_codes.append(fvg_reason)

    if reason_codes:
        return _result(candidate, family, OBValidationStatus.REJECTED, low=low, high=high,
                        structure_event=matching_break, matching_fvg=matching_fvg, reason_codes=tuple(reason_codes))

    # All required checks passed -- scan forward for mitigation (wick touch) / invalidation (close beyond).
    after = [c for c in candles if c.time > candidate.origin_time]
    lifecycle_status, lifecycle_reason = _lifecycle(after, is_bullish, low, high)

    return _result(candidate, family, lifecycle_status, low=low, high=high,
                    structure_event=matching_break, matching_fvg=matching_fvg, reason_codes=(lifecycle_reason,))


def _classify_family_and_zone(origin_candle: Candle, is_bullish: bool, threshold: float) -> "tuple[OBFamily, float, float]":
    candle_range = origin_candle.high - origin_candle.low
    body = abs(origin_candle.close - origin_candle.open)
    body_ratio = (body / candle_range) if candle_range > 0 else 1.0

    if body_ratio >= threshold:
        # PIVOT_OB, zone = FULL_CANDLE
        return OBFamily.PIVOT_OB, origin_candle.low, origin_candle.high

    # SHADOW_OB, zone = WICK_TIP_TO_BODY
    body_edge_low = min(origin_candle.open, origin_candle.close)
    body_edge_high = max(origin_candle.open, origin_candle.close)
    if is_bullish:
        # demand: wick tip is the candle's low, body edge is the bottom of the body
        return OBFamily.SHADOW_OB, origin_candle.low, body_edge_low
    else:
        # supply: wick tip is the candle's high, body edge is the top of the body
        return OBFamily.SHADOW_OB, body_edge_high, origin_candle.high


def _find_matching_break(breaks: Sequence[StructurePoint], origin_time: datetime, is_bullish: bool) -> Optional[StructurePoint]:
    wanted = {StructurePointKind.BULLISH_BOS, StructurePointKind.BULLISH_CHOCH} if is_bullish \
        else {StructurePointKind.BEARISH_BOS, StructurePointKind.BEARISH_CHOCH}
    candidates = [b for b in breaks if b.time_utc >= origin_time and b.kind in wanted]
    return candidates[0] if candidates else None


def _find_matching_fvg(fvg_candidates: Sequence[ZoneResult], origin_time: datetime, is_bullish: bool,
                        time_to_pos: dict) -> "tuple[Optional[ZoneResult], Optional[str]]":
    origin_pos = time_to_pos.get(origin_time)
    wanted_direction = ZoneDirection.BULLISH if is_bullish else ZoneDirection.BEARISH

    in_window = []
    right_direction_anywhere = []
    for fvg in fvg_candidates:
        fvg_pos = time_to_pos.get(fvg.origin_time)
        if fvg_pos is None or fvg_pos <= origin_pos:
            continue
        if fvg.low is None or fvg.high is None or (fvg.high - fvg.low) <= 0:
            continue  # minimum_size = strictly > 0
        distance = fvg_pos - origin_pos
        if fvg.direction == wanted_direction:
            right_direction_anywhere.append((distance, fvg))
        if distance <= MAX_CANDLES_TO_FVG:
            in_window.append(fvg)

    if right_direction_anywhere:
        right_direction_anywhere.sort(key=lambda t: t[0])
        distance, fvg = right_direction_anywhere[0]
        if distance <= MAX_CANDLES_TO_FVG:
            return fvg, None
        return None, "FVG_TOO_LATE"

    if any(f.direction != wanted_direction for f in in_window):
        return None, "FVG_DIRECTION_MISMATCH"

    return None, "REQUIRED_FVG_MISSING"


def _lifecycle(after: Sequence[Candle], is_bullish: bool, low: float, high: float) -> "tuple[OBValidationStatus, str]":
    mitigated = False
    for c in after:
        invalidated = (c.close < low) if is_bullish else (c.close > high)
        if invalidated:
            return OBValidationStatus.INVALIDATED, "OB_INVALIDATED"
        touched = c.low <= high and c.high >= low  # WICK_TOUCH_BOUNDARY: any wick overlap with the zone
        if touched:
            mitigated = True
    if mitigated:
        return OBValidationStatus.MITIGATED, "OB_MITIGATED"
    return OBValidationStatus.VALID, "VALID_OB"


def _result(candidate, family, status, low, high, reason_codes,
            structure_event=None, matching_fvg=None) -> ValidatedOrderBlock:
    return ValidatedOrderBlock(
        symbol=candidate.symbol, timeframe=candidate.timeframe, family=family, status=status,
        direction=candidate.direction, low=low, high=high, origin_time=candidate.origin_time,
        candidate=candidate, matching_fvg=matching_fvg, structure_event=structure_event,
        reason_codes=reason_codes,
    )


# --------------------------------------------------------------------------- ORDER_BLOCK_CONTRACT_GAPS

@dataclass(frozen=True)
class OrderBlockContractGap:
    family: str
    item: str
    question: str


ORDER_BLOCK_CONTRACT_GAPS: Tuple[OrderBlockContractGap, ...] = (
    OrderBlockContractGap("PIVOT_OB", "classification", "PIVOT_OB vs SHADOW_OB is split by "
                          "body_ratio >= config/ag_order_block_v1.yaml's pivot_shadow_body_ratio_threshold "
                          "(default 0.5) -- a named, configurable AG_ORDER_BLOCK_V1 parameter, not a frozen "
                          "owner number. Confirm the value or supply a different one."),
    OrderBlockContractGap("FLIP_OB", "identification", "FLIP_OB identification ('failed prior S/D reaction/base "
                          "displaced in opposite direction') needs a lookback window and proximity rule to prior "
                          "zones -- not specified in AG_ORDER_BLOCK_V1. No candidate is currently ever classified FLIP_OB."),
    OrderBlockContractGap("FLIP_OB", "L1_L2", "L1/L2 classification for FLIP_OB -- explicitly UNSIGNED per owner instruction."),
    OrderBlockContractGap("FLIP_OB", "inside_bar", "Inside-Bar D2S/S2D flip rule -- explicitly UNSIGNED per owner instruction."),
    OrderBlockContractGap("STRUCTURE", "internal_external", "STRUCTURE source=INTERNAL_OR_EXTERNAL: market_structure/ "
                          "has one swing-length-based classifier with no internal/external tiering yet -- "
                          "structure_source is a placeholder field, not a real classification."),
)
