"""Market bias adapter (DAYTRADING_BASIC_SKILLS_ROUTER_V1 spec section 4): turns
market_structure.tiers.TieredStructureResult's EXTERNAL tier -- already-computed
direction, latest BOS/CHoCH, protected swing high/low -- into BULLISH/BEARISH/NEUTRAL/
INDETERMINATE.

AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1 M2/M3 (2026-09-10): the direction label
itself (BULLISH/BEARISH/NEUTRAL) is no longer decided here -- it is delegated to
market_intelligence.bias_resolver.resolve_from_structure_tiers, the ONE canonical
resolver (AG_STRATEGY_DIRECTION_CONTRACT_V1 invariant 1/9). This module remains only to
(a) preserve its existing MarketBias/MarketBiasDirection output shape for its real,
already-wired callers (daytrading_runtime, daytrading_workflow -- see
docs/status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M2_M3_STATUS.md's
LEGACY_BIAS_CALLERS_REMAINING list) and (b) enrich that legacy shape with
protected-level/latest-break fields the canonical MarketBiasResult does not carry (those
are supplementary evidence, not a second bias decision). No field here is computed from
anything other than the SAME tiers.external evidence the canonical resolver itself reads,
and the two are never allowed to disagree on direction -- see
tests/test_daytrading_market_bias.py::test_legacy_direction_matches_canonical_resolver.

INDETERMINATE is preserved as this module's own legacy 4th state (existing callers'
tests depend on distinguishing "structure invalid" from "structure resolved but
NEUTRAL") -- the canonical resolver folds both into NEUTRAL on its own side, per
AG_STRATEGY_DIRECTION_CONTRACT_V1 invariant 2; this adapter recovers which of the two
actually happened by checking tiers.status itself, not by asking the canonical result
to distinguish them (it deliberately cannot -- fail-closed collapsing is the point).

H1 is the primary bias timeframe, matching daytrading/pipeline.py's own frozen
compass/interest/trade hierarchy (H1 = TIMEFRAME_INTEREST, already the canonical
protected-level/BOS source there) -- not a new H1/H4 convention invented for this
router.
"""
from __future__ import annotations

from datetime import datetime, timezone

from market_structure.models import STATE_BEARISH, STATE_BULLISH, TieredStructureResult

from market_intelligence.bias_resolver import resolve_from_structure_tiers

from .models import MarketBias, MarketBiasDirection

_CANONICAL_TO_LEGACY_DIRECTION = {
    "BULLISH": MarketBiasDirection.BULLISH.value,
    "BEARISH": MarketBiasDirection.BEARISH.value,
    # NEUTRAL is ambiguous on the canonical side (covers both a genuinely-undefined
    # structure and invalid/missing tiers) -- resolved below from tiers.status directly,
    # never guessed from the canonical result alone.
}


def derive_market_bias_from_tiers(tiers: TieredStructureResult, timeframe: str = "H1") -> MarketBias:
    # Single canonical direction authority (invariant 1/9) -- decision_time/symbol/
    # session_pair are irrelevant to the LABEL itself (only to fingerprint/decision_cycle_id,
    # which this legacy shape does not carry), so fixed placeholders are used here purely
    # to satisfy the canonical resolver's required arguments.
    canonical = resolve_from_structure_tiers(
        tiers, symbol="UNSPECIFIED", decision_time=datetime.now(timezone.utc),
        session_pair="UNSPECIFIED", timeframe=timeframe,
    )

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

    if canonical.bias == "BULLISH":
        assert external.direction == STATE_BULLISH  # canonical/legacy evidence must never disagree
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

    if canonical.bias == "BEARISH":
        assert external.direction == STATE_BEARISH
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
