"""Wick-vs-close classification, pivot quality, and structural-shift quality
(SMC_SWEEP_SHIFT_ARRAY_V1 steps 3-6) -- consumes existing signed capabilities verbatim:

- `market_structure`'s own `close_break: true` config (config/market_structure.yaml)
  already guarantees `StructureResult.latest_choch`/`latest_bos` are body-close events,
  never wick-only -- this module does not redetect CHoCH, it classifies the RAW sweep
  candle against a level (pure geometry) and composes that with the already-signed
  `entry_confirmation.structure_alignment.StructureAlignment` primitive.
- `liquidity.LiquidityStatus` (SWEPT/RECLAIMED/CONSUMED) already distinguishes a
  wick-only sweep from a closed-beyond level -- reused via `liquidity_alignment`/the
  caller-supplied `LiquidityLevel`, not reimplemented.
- `market_structure.tiers` (EXTERNAL/INTERNAL swing tiers) is the source of pivot
  significance; a broken pivot found in the EXTERNAL tier is treated as a meaningful
  structural pivot, one found only in INTERNAL as a lesser (but not automatically
  disqualified) pivot, and one found in neither as MICRO_PIVOT/UNRESOLVED.

No new numeric threshold is invented anywhere in this module.
"""
from __future__ import annotations

from typing import Optional

from liquidity import LiquiditySide
from market_structure.models import StructureTier
from strategy_engine.session import Candle

from .models import ConfirmationState, DisplacementEvidence, StructureAlignment
from .models_v2_1 import PivotContext, PivotRole, StructureShiftQuality, StructureShiftQualityStatus

_PRICE_TOLERANCE = 1e-9


def classify_wick_or_close(candle: Candle, level_price: float, side: LiquiditySide) -> dict:
    """Pure geometry: did this single candle merely wick through `level_price`, or did
    it close beyond it? `side` is the side the level sits on relative to price (BUY_SIDE
    = resting liquidity above, e.g. a swing high; SELL_SIDE = resting liquidity below,
    e.g. a swing low) -- matches liquidity.LiquiditySide's own convention."""
    if side == LiquiditySide.BUY_SIDE:
        wick_through = candle.high > level_price
        close_through = candle.close > level_price
    else:
        wick_through = candle.low < level_price
        close_through = candle.close < level_price
    return {
        "wick_through": wick_through,
        "close_through": close_through,
        "fakeout": wick_through and not close_through,
    }


def evaluate_pivot_context(
    pivot_price: Optional[float],
    pivot_time=None,
    pivot_type: Optional[str] = None,
    timeframe: Optional[str] = None,
    external_tier: Optional[StructureTier] = None,
    internal_tier: Optional[StructureTier] = None,
    tolerance_price: Optional[float] = None,
) -> PivotContext:
    """`tolerance_price`: caller-supplied price distance for matching `pivot_price`
    against a tier's confirmed swings. Two independently-computed `StructureResult`/
    `TieredStructureResult` calls (different swing_length, possibly a different fetch
    window) can report microscopically different floats for what is conceptually the
    same swing -- exact equality alone under-matches real pivots (observed in live
    validation, AG_ENTRY_CONFIRMATION_V2_1_LIVE, 2026-08-28: a genuine swing was
    misclassified MICRO_PIVOT). Reuse the SAME signed tolerance
    `market_structure/tiers.py` already uses for its own HH/HL/LH/LL labeling
    (`config/liquidity.yaml`'s `equal_level_tolerance_points` x the symbol's tick_size)
    -- this module never fetches symbol metadata itself (architecture boundary: never
    calls MT5), so the caller must compute and pass it, the same way it already supplies
    `external_tier`/`internal_tier`. Omitting it falls back to near-exact float equality
    (a tiny fixed epsilon, not a new business threshold) rather than silently widening
    matching on its own authority."""
    if pivot_price is None:
        return PivotContext(reason="No structural pivot price supplied.")

    tolerance = tolerance_price if tolerance_price is not None else _PRICE_TOLERANCE

    def _matches(tier: Optional[StructureTier]) -> bool:
        if tier is None:
            return False
        return any(abs(s.price - pivot_price) <= tolerance for s in tier.swings)

    if _matches(external_tier):
        role = PivotRole.EXTERNAL_SWING.value
        reason = "Pivot matches a confirmed EXTERNAL-tier swing (market_structure.tiers)."
    elif _matches(internal_tier):
        role = PivotRole.INTERNAL_SWING.value
        reason = "Pivot matches a confirmed INTERNAL-tier swing only -- not externally significant."
    elif external_tier is None and internal_tier is None:
        role = PivotRole.UNRESOLVED.value
        reason = "No tiered structure supplied -- pivot significance cannot be classified."
    else:
        role = PivotRole.MICRO_PIVOT.value
        reason = "Pivot does not match any confirmed EXTERNAL or INTERNAL tier swing."

    return PivotContext(
        pivot_price=pivot_price, pivot_time=pivot_time, pivot_timeframe=timeframe,
        pivot_type=pivot_type, pivot_role=role, reason=reason,
    )


def evaluate_structure_shift_quality(
    sweep_present: Optional[bool],
    post_sweep_ordering: Optional[bool],
    pivot_context: PivotContext,
    structure_shift: StructureAlignment,
    displacement: DisplacementEvidence,
    fvg_created: Optional[bool],
) -> StructureShiftQuality:
    # market_structure's close_break=true config makes any PASS/FAIL StructureAlignment
    # already a body-close event by construction -- see module docstring. Only an
    # UNAVAILABLE/INSUFFICIENT_DATA event_kind means "no confirmed close-break yet".
    structure_event_exists = structure_shift.event_kind is not None
    body_close = True if structure_event_exists else None
    wick_only = (not structure_event_exists) if sweep_present else None

    pivot_valid = None
    if pivot_context.pivot_role in (PivotRole.EXTERNAL_SWING.value, PivotRole.PROTECTED_HIGH.value,
                                     PivotRole.PROTECTED_LOW.value, PivotRole.INTERNAL_SWING.value):
        pivot_valid = True
    elif pivot_context.pivot_role == PivotRole.MICRO_PIVOT.value:
        pivot_valid = False

    displacement_qualified = displacement.status == ConfirmationState.PASS

    context_valid = sweep_present if sweep_present is not None else None

    base = dict(
        body_close_beyond_pivot=body_close, wick_only_break=wick_only, pivot_valid=pivot_valid,
        post_sweep=post_sweep_ordering, displacement_qualified=displacement_qualified,
        fvg_created=fvg_created, context_valid=context_valid,
    )

    if not structure_event_exists:
        if sweep_present:
            return StructureShiftQuality(
                **base, status=StructureShiftQualityStatus.FAKEOUT_WICK.value,
                reason="Liquidity was swept but no body-close structural event has occurred yet.",
            )
        return StructureShiftQuality(**base, status=StructureShiftQualityStatus.INDETERMINATE.value,
                                      reason="No structural event and no sweep evidence supplied.")

    if pivot_valid is False:
        return StructureShiftQuality(**base, status=StructureShiftQualityStatus.INVALID_PIVOT.value,
                                      reason="Broken pivot is only a MICRO_PIVOT -- not a valid structural pivot.")

    if post_sweep_ordering is False:
        return StructureShiftQuality(**base, status=StructureShiftQualityStatus.WRONG_SEQUENCE.value,
                                      reason="Structural break predates the liquidity sweep -- cannot reuse an older break.")

    if context_valid is False:
        return StructureShiftQuality(**base, status=StructureShiftQualityStatus.MID_RANGE_LOW_CONTEXT.value,
                                      reason="No relevant HTF liquidity/POI context -- mid-range structural event.")

    if pivot_valid and (post_sweep_ordering in (True, None)) and displacement_qualified:
        return StructureShiftQuality(**base, status=StructureShiftQualityStatus.VALID_STRONG.value)

    if pivot_valid in (True, None) and (post_sweep_ordering in (True, None)):
        return StructureShiftQuality(
            **base, status=StructureShiftQualityStatus.VALID_WEAK.value,
            reason="Structural close confirmed but displacement not qualified -- formal break, not high-quality execution.",
        )

    return StructureShiftQuality(**base, status=StructureShiftQualityStatus.INDETERMINATE.value,
                                  reason="Insufficient evidence to classify shift quality.")
