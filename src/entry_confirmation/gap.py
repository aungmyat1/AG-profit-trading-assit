"""Gap context (A3/A4/E1/E3 reference material) -- consumes a caller-supplied
supply_demand.ZoneResult (family=FVG) verbatim; never redetects gaps/FVGs.

Distinguishes TOUCH from REACTION (spec rules 20, 50): a candle intersecting the gap
range is only ever GAP_TOUCHED/GAP_FILLED. GAP_REACTED additionally requires a
caller-supplied reaction candle that qualifies under the already-signed
AG_ENTRY_DISPLACEMENT_V1 primitive (entry_confirmation.displacement) -- reused, not
reinvented, per the "no new threshold" rule.

Inverted-gap identification has no signed definition anywhere in this repo (rule 35);
`evaluate_inverted_gap_context` therefore always reports `policy="PARTIAL"` and never
fabricates an inversion threshold. The 50% midpoint is pure arithmetic and always
computed.
"""
from __future__ import annotations

from typing import Optional, Sequence

from strategy_engine.session import Candle
from supply_demand import ZoneResult, ZoneStatus

from .displacement import evaluate_displacement
from .models import CandidateDirection, ConfirmationState
from .models_v2 import GapContext, InvertedGapContext


def gap_midpoint(low: Optional[float], high: Optional[float]) -> Optional[float]:
    if low is None or high is None:
        return None
    return (low + high) / 2.0


def _intersects(candle: Candle, low: float, high: float) -> bool:
    return candle.low <= high and candle.high >= low


def evaluate_gap_context(
    gap_zone: Optional[ZoneResult],
    touch_candle: Optional[Candle] = None,
    reaction_candle: Optional[Candle] = None,
    reaction_history: Sequence[Candle] = (),
    candidate_direction: CandidateDirection = CandidateDirection.NONE,
) -> GapContext:
    if gap_zone is None:
        return GapContext(status="UNAVAILABLE", reason="No gap/FVG zone supplied.")

    low, high = gap_zone.low, gap_zone.high
    midpoint = gap_midpoint(low, high)

    if gap_zone.status == ZoneStatus.INVALIDATED:
        return GapContext(
            status="GAP_INVALIDATED", gap_low=low, gap_high=high, gap_midpoint=midpoint,
            reason="Upstream supply_demand zone reports INVALIDATED.",
        )

    if touch_candle is None:
        return GapContext(status="UNTOUCHED", gap_low=low, gap_high=high, gap_midpoint=midpoint)

    if low is None or high is None or not _intersects(touch_candle, low, high):
        return GapContext(status="UNTOUCHED", gap_low=low, gap_high=high, gap_midpoint=midpoint)

    filled = touch_candle.close is not None and low <= touch_candle.close <= high
    base_status = "GAP_FILLED" if filled else "GAP_TOUCHED"

    if reaction_candle is None or candidate_direction == CandidateDirection.NONE:
        return GapContext(
            status=base_status, gap_low=low, gap_high=high, gap_midpoint=midpoint,
            reason="No reaction evidence supplied -- touch/fill only, reaction not evaluated.",
        )

    reaction = evaluate_displacement(reaction_candle, candidate_direction, reaction_history)
    if reaction.status == ConfirmationState.PASS:
        return GapContext(
            status="GAP_REACTED", gap_low=low, gap_high=high, gap_midpoint=midpoint,
            reaction_time=reaction_candle.time,
            evidence=(f"AG_ENTRY_DISPLACEMENT_V1 PASS on reaction candle @ {reaction_candle.time}",),
        )

    return GapContext(
        status=base_status, gap_low=low, gap_high=high, gap_midpoint=midpoint,
        reason=f"Reaction candle did not qualify under AG_ENTRY_DISPLACEMENT_V1 "
               f"(status={reaction.status.value}) -- GAP_REACTION_POLICY = PARTIAL.",
    )


def evaluate_inverted_gap_context(gap_zone: Optional[ZoneResult]) -> InvertedGapContext:
    if gap_zone is None:
        return InvertedGapContext(status="UNAVAILABLE", reason="No inverted-gap candidate zone supplied.")

    low, high = gap_zone.low, gap_zone.high
    midpoint = gap_midpoint(low, high)

    if gap_zone.status == ZoneStatus.INVALIDATED:
        return InvertedGapContext(
            status="INVALIDATED_GAP", gap_low=low, gap_high=high, gap_midpoint=midpoint,
            origin_time=gap_zone.origin_time,
            reason="Upstream supply_demand zone reports INVALIDATED.",
        )

    return InvertedGapContext(
        status="NORMAL_GAP", gap_low=low, gap_high=high, gap_midpoint=midpoint,
        origin_time=gap_zone.origin_time,
        reason="INVERTED_GAP_POLICY = PARTIAL -- no signed inversion definition found in this repo; "
               "midpoint math is exact regardless.",
    )
