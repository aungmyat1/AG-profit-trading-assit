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
from typing import Optional

from market_structure.models import STATE_BEARISH, STATE_BULLISH, TieredStructureResult

from .models import MarketBias, MarketBiasDirection

_CANONICAL_TO_LEGACY_DIRECTION = {
    "BULLISH": MarketBiasDirection.BULLISH.value,
    "BEARISH": MarketBiasDirection.BEARISH.value,
    # NEUTRAL is ambiguous on the canonical side (covers both a genuinely-undefined
    # structure and invalid/missing tiers) -- resolved below from tiers.status directly,
    # never guessed from the canonical result alone.
}


def derive_market_bias_from_tiers(
    tiers: TieredStructureResult,
    timeframe: str = "H1",
    decision_time: Optional[datetime] = None,
    session_pair: str = "UNSPECIFIED",
) -> MarketBias:
    """AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1 M4: `decision_time`/`session_pair`
    are optional and additive -- every existing caller that omits them keeps working
    unchanged. Supplying them (as daytrading_workflow.evaluate_session_completion now
    does, via its own `evaluation_time`/`reference_session`) makes the resulting
    MarketBias.canonical_provenance a REAL, reproducible MarketBiasResult (same
    decision_time -> same input_fingerprint, P22 determinism); omitting decision_time
    falls back to `now()`, which is honest (this call truly has no caller-supplied
    decision instant) but not reproducible across two separate calls -- existing
    callers were already not asserting on provenance, so this is not a behavior
    regression for them.

    `tiers.symbol` (always real, never a placeholder) is used as the canonical
    resolver's `symbol` -- no separate symbol parameter is needed here."""
    # Deferred/lazy import: market_intelligence.bias_resolver (module level) imports
    # daytrading.decision.models, and this module is part of daytrading.decision's own
    # package __init__ chain (derive_market_bias_from_tiers is re-exported there) -- a
    # module-level import here forms a circular import between the two packages.
    # Deferring it to call time (Python caches the import in sys.modules either way, so
    # this is a zero-behavior-change fix, not a new import path) breaks the cycle
    # without altering which canonical resolver function is called or when.
    from market_intelligence.bias_resolver import resolve_from_structure_tiers

    resolved_decision_time = decision_time or datetime.now(timezone.utc)
    # Single canonical direction authority (invariant 1/9).
    canonical = resolve_from_structure_tiers(
        tiers, symbol=tiers.symbol, decision_time=resolved_decision_time,
        session_pair=session_pair, timeframe=timeframe,
    )

    if tiers.status != "VALID" or tiers.external is None:
        return MarketBias(
            direction=MarketBiasDirection.INDETERMINATE.value, timeframe=timeframe,
            reasons=(f"TIERED_STRUCTURE_STATUS={tiers.status}",),
            canonical_provenance=canonical,
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
            canonical_provenance=canonical,
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
            canonical_provenance=canonical,
        )

    return MarketBias(
        direction=MarketBiasDirection.NEUTRAL.value, timeframe=timeframe,
        external_structure_direction=external.direction,
        latest_break=latest_break.kind.value if latest_break is not None else None,
        reasons=("EXTERNAL_STRUCTURE_UNDEFINED",),
        canonical_provenance=canonical,
    )


def derive_market_bias(
    symbol: str, timeframe: str = "H1",
    decision_time: Optional[datetime] = None, session_pair: str = "UNSPECIFIED",
) -> MarketBias:
    """Convenience wrapper: fetches TieredStructureResult itself. Mirrors the exact H1
    tiers fetch daytrading/pipeline.py already performs for protected-level/BOS
    evidence -- no second fetch convention invented."""
    from market_structure.tiers import analyze_structure_tiers

    tiers = analyze_structure_tiers(symbol, timeframe)
    return derive_market_bias_from_tiers(tiers, timeframe, decision_time=decision_time, session_pair=session_pair)
