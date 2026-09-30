"""Liquidity-reclaim alignment primitive -- consumes liquidity.LiquidityResult verbatim.
Never re-detects sweeps/reclaims; only checks whether the relevant side's nearest level
is RECLAIMED and aligns with a caller-supplied candidate direction.

Deliberately generic: consumes `liquidity.LiquidityResult`, never
`strategy_engine.session.setups.entry_2_sweep` (ST_ASIAN_SWEEP_5R_V1's own qualified
sweep) or any other strategy-specific sweep contract. See
docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md's "Strategy-specific skill ownership" section.
"""
from __future__ import annotations

from typing import Optional

from liquidity import LiquidityResult, LiquiditySide, LiquidityStatus

from .models import CandidateDirection, ConfirmationState, LiquidityAlignment

# LONG needs sell-side liquidity (resting lows) taken-and-reclaimed; SHORT needs buy-side.
_RELEVANT_SIDE = {
    CandidateDirection.LONG: LiquiditySide.SELL_SIDE,
    CandidateDirection.SHORT: LiquiditySide.BUY_SIDE,
}


def evaluate_liquidity_alignment(
    liquidity_result: Optional[LiquidityResult],
    candidate_direction: CandidateDirection,
) -> LiquidityAlignment:
    if liquidity_result is None:
        return LiquidityAlignment(
            status=ConfirmationState.UNAVAILABLE,
            candidate_direction=candidate_direction.value,
            reason="No liquidity_result supplied in EntryConfirmationRequest.",
        )

    if liquidity_result.status != "LIQUIDITY_OK":
        return LiquidityAlignment(
            status=ConfirmationState.INSUFFICIENT_DATA,
            candidate_direction=candidate_direction.value,
            reason=f"liquidity result not LIQUIDITY_OK (status={liquidity_result.status!r}, "
                   f"reason_codes={liquidity_result.reason_codes!r}).",
        )

    if candidate_direction == CandidateDirection.NONE:
        return LiquidityAlignment(
            status=ConfirmationState.INSUFFICIENT_DATA,
            candidate_direction=candidate_direction.value,
            reason="candidate_direction is required to evaluate liquidity_reclaim alignment.",
        )

    relevant_side = _RELEVANT_SIDE[candidate_direction]
    level = (
        liquidity_result.nearest_sell_side
        if relevant_side == LiquiditySide.SELL_SIDE
        else liquidity_result.nearest_buy_side
    )

    if level is None:
        return LiquidityAlignment(
            status=ConfirmationState.FAIL,
            candidate_direction=candidate_direction.value,
            level_side=relevant_side.value,
            reason=f"No {relevant_side.value} liquidity level available.",
        )

    if level.status == LiquidityStatus.RECLAIMED:
        state = ConfirmationState.PASS
        reason = None
    elif level.status == LiquidityStatus.SWEPT:
        state = ConfirmationState.INSUFFICIENT_DATA
        reason = "Level is currently SWEPT (live tick only) -- not yet confirmed by a closed candle."
    elif level.status == LiquidityStatus.UNSWEPT:
        state = ConfirmationState.FAIL
        reason = "Level is UNSWEPT -- no sweep has occurred."
    elif level.status == LiquidityStatus.CONSUMED:
        state = ConfirmationState.FAIL
        reason = "Level is CONSUMED -- swept and closed beyond, with no reclaim since."
    else:  # UNKNOWN
        state = ConfirmationState.UNAVAILABLE
        reason = "Level status could not be determined."

    return LiquidityAlignment(
        status=state,
        candidate_direction=candidate_direction.value,
        level_side=level.side.value,
        level_status=level.status.value,
        level_price=level.price,
        reclaim_time=level.reclaim_time,
        reason=reason,
    )
