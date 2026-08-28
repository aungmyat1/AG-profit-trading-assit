"""Market bias adapter (DAYTRADING_BASIC_SKILLS_ROUTER_V1 spec section 4): turns
market_structure.tiers.TieredStructureResult's EXTERNAL tier -- already-computed
direction, latest BOS/CHoCH, protected swing high/low -- into BULLISH/BEARISH/NEUTRAL/
INDETERMINATE. No new structure algorithm: every field on MarketBias traces back to a
field already on StructureTier.

H1 is the primary bias timeframe, matching daytrading/pipeline.py's own frozen
compass/interest/trade hierarchy (H1 = TIMEFRAME_INTEREST, already the canonical
protected-level/BOS source there) -- not a new H1/H4 convention invented for this
router.
"""
from __future__ import annotations

from market_structure.models import STATE_BEARISH, STATE_BULLISH, TieredStructureResult

from .models import MarketBias, MarketBiasDirection


def derive_market_bias_from_tiers(tiers: TieredStructureResult, timeframe: str = "H1") -> MarketBias:
    if tiers.status != "VALID" or tiers.external is None:
        return MarketBias(
            direction=MarketBiasDirection.INDETERMINATE.value, timeframe=timeframe,
            reasons=(f"TIERED_STRUCTURE_STATUS={tiers.status}",),
        )

    external = tiers.external
    latest_break = None
    if external.latest_bos is not None and external.latest_choch is not None:
        latest_break = external.latest_bos if external.latest_bos.time_utc >= external.latest_choch.time_utc \
            else external.latest_choch
    else:
        latest_break = external.latest_bos or external.latest_choch

    if external.direction == STATE_BULLISH:
        protected = external.latest_swing_low
        reasons = ["EXTERNAL_STRUCTURE_BULLISH"]
        reasons.append("PROTECTED_LOW_INTACT" if protected is not None else "PROTECTED_LOW_UNAVAILABLE")
        return MarketBias(
            direction=MarketBiasDirection.BULLISH.value, timeframe=timeframe,
            external_structure_direction=external.direction,
            protected_level_type="PROTECTED_LOW" if protected is not None else None,
            protected_level=protected.price if protected is not None else None,
            latest_break=latest_break.kind.value if latest_break is not None else None,
            reasons=tuple(reasons),
        )

    if external.direction == STATE_BEARISH:
        protected = external.latest_swing_high
        reasons = ["EXTERNAL_STRUCTURE_BEARISH"]
        reasons.append("PROTECTED_HIGH_INTACT" if protected is not None else "PROTECTED_HIGH_UNAVAILABLE")
        return MarketBias(
            direction=MarketBiasDirection.BEARISH.value, timeframe=timeframe,
            external_structure_direction=external.direction,
            protected_level_type="PROTECTED_HIGH" if protected is not None else None,
            protected_level=protected.price if protected is not None else None,
            latest_break=latest_break.kind.value if latest_break is not None else None,
            reasons=tuple(reasons),
        )

    return MarketBias(
        direction=MarketBiasDirection.NEUTRAL.value, timeframe=timeframe,
        external_structure_direction=external.direction,
        latest_break=latest_break.kind.value if latest_break is not None else None,
        reasons=("EXTERNAL_STRUCTURE_UNDEFINED",),
    )


def derive_market_bias(symbol: str, timeframe: str = "H1") -> MarketBias:
    """Convenience wrapper: fetches TieredStructureResult itself. Mirrors the exact H1
    tiers fetch daytrading/pipeline.py already performs for protected-level/BOS
    evidence -- no second fetch convention invented."""
    from market_structure.tiers import analyze_structure_tiers

    tiers = analyze_structure_tiers(symbol, timeframe)
    return derive_market_bias_from_tiers(tiers, timeframe)
