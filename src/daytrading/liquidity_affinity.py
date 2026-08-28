"""DayTrading skill 2: Liquidity Affinity (DAYTRADING_LIQUIDITY_AFFINITY_V1) -- "which
liquidity matters now, what liquidity is price likely interacting with, and what
liquidity relationship should the LTF Execution skill later monitor?"

NOT a second liquidity detector (spec section 2). Every fact this module reasons over is
consumed, never redetected:

    liquidity.LiquidityResult              -- SMC liquidity levels, including session
                                               sources (ASIAN_HIGH/LOW, LONDON_HIGH/LOW,
                                               NEW_YORK_HIGH/LOW -- see
                                               liquidity/contract.py's SOURCES table)
    liquidity.hierarchy.ScopedLiquidityLevel -- EXTERNAL/INTERNAL scoping (spec 6-7)
    liquidity.affinity.evaluate_liquidity_affinity() -- the SMC-technique external/
                                               internal/imbalance relationship engine
                                               (spec section 14: SMC_LIQUIDITY_AFFINITY
                                               != DAYTRADING_LIQUIDITY_AFFINITY; this
                                               module wraps its OUTPUT, never its logic)
    market_structure.TieredStructureResult / StructureResult -- H1 external/internal
                                               structure, BOS/CHoCH (spec 10-11, 19)
    supply_demand.ZoneResult (FVG)          -- internal imbalance (spec 7)
    supply_demand.DealingRangeZones          -- premium/discount context (spec 3.10)

Backward compatible: the original (symbol, narrative_bias, liquidity) call shape and its
RESOLVED/PARTIAL/UNRESOLVED primary_draw/entry_side_liquidity/target_side_liquidity
result still behave identically with no keyword arguments supplied -- every V1 field
below is additive and populated only when the richer optional evidence is passed in
(spec section 46: minimum implementation, no forced rewrite of working callers).

Zero look-ahead (spec section 31): this function touches no clock and fetches no data --
every input is caller-supplied, already-closed-candle evidence. Given identical inputs
it always returns an identical result (proven by tests/test_daytrading_liquidity_
affinity.py's determinism test) -- causality is therefore the caller's responsibility
(never fetch candles/levels newer than the evaluation instant), exactly as narrative_bias.py
and entry_confirmation already require of their own callers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

from liquidity.hierarchy import SCOPE_EXTERNAL, SCOPE_INTERNAL
from liquidity.models import LiquiditySide, LiquidityStatus
from market_structure.models import STATE_BEARISH, STATE_BULLISH

from .models import (
    AFFINITY_CONFLICTED,
    AFFINITY_INSUFFICIENT_DATA,
    AFFINITY_PARTIAL,
    AFFINITY_RESOLVED,
    AFFINITY_UNRESOLVED,
    BIAS_BEARISH,
    BIAS_BULLISH,
    DayTradingLiquidityAffinityResult,
    NarrativeBiasResult,
    PHASE_BALANCED,
    PHASE_CORRECTIVE,
    PHASE_IMPULSIVE,
    PHASE_UNRESOLVED,
    REL_BALANCED,
    REL_EXPANDING_EXTERNAL,
    REL_EXTERNAL_SWEPT,
    REL_INTERNAL_REBALANCE,
    REL_RETURNING_INTERNAL,
    REL_UNRESOLVED,
    SESSION_CONTEXT_DETECTED,
    SESSION_CONTEXT_NOT_AVAILABLE,
    SESSION_CONTEXT_RELEVANT,
    SessionLiquidityContext,
    TIMEFRAME_INTEREST,
)

if TYPE_CHECKING:
    from liquidity.affinity import LiquidityAffinityResult as SMCLiquidityAffinityResult
    from liquidity.hierarchy import ScopedLiquidityLevel
    from liquidity.models import LiquidityResult
    from market_structure.models import StructureResult, TieredStructureResult
    from supply_demand.models import ZoneResult
    from supply_demand.native_zones import DealingRangeZones

_TARGET_SIDE_FOR_BIAS = {BIAS_BULLISH: LiquiditySide.BUY_SIDE, BIAS_BEARISH: LiquiditySide.SELL_SIDE}
_OPPOSITE_SIDE = {LiquiditySide.BUY_SIDE: LiquiditySide.SELL_SIDE, LiquiditySide.SELL_SIDE: LiquiditySide.BUY_SIDE}
_STATE_FOR_BIAS = {BIAS_BULLISH: STATE_BULLISH, BIAS_BEARISH: STATE_BEARISH}

# SMC liquidity.affinity's own vocabulary -> this module's REL_* relationship-phase
# vocabulary (spec section 8) -- a relabeling for DayTrading's own contract, never a
# second definition of the underlying relationship.
_SMC_RELATIONSHIP_MAP = {
    "BULLISH_INTERNAL_TO_EXTERNAL": REL_RETURNING_INTERNAL,
    "BEARISH_INTERNAL_TO_EXTERNAL": REL_RETURNING_INTERNAL,
    "EXTERNAL_TO_INTERNAL": REL_RETURNING_INTERNAL,
    "INTERNAL_REBALANCING": REL_INTERNAL_REBALANCE,
    "EXTERNAL_LIQUIDITY_REACHED": REL_EXTERNAL_SWEPT,
    "AFFINITY_INVALIDATED": REL_UNRESOLVED,
    "INDETERMINATE": REL_UNRESOLVED,
}

_SESSION_SOURCES = {
    LiquiditySide.BUY_SIDE: ("ASIAN_HIGH", "LONDON_HIGH", "NEW_YORK_HIGH"),
    LiquiditySide.SELL_SIDE: ("ASIAN_LOW", "LONDON_LOW", "NEW_YORK_LOW"),
}
_ALL_SESSION_SOURCES = _SESSION_SOURCES[LiquiditySide.BUY_SIDE] + _SESSION_SOURCES[LiquiditySide.SELL_SIDE]


def _market_phase(smc_result: Optional["SMCLiquidityAffinityResult"], narrative_bias: NarrativeBiasResult) -> str:
    if smc_result is not None:
        if smc_result.market_phase == "IMPULSIVE":
            return PHASE_IMPULSIVE
        if smc_result.market_phase == "CORRECTIVE":
            return PHASE_CORRECTIVE
    if narrative_bias.bias == "BALANCED":
        return PHASE_BALANCED
    return PHASE_UNRESOLVED


def _relationship_phase(smc_result: Optional["SMCLiquidityAffinityResult"], structural_bias: Optional[str],
                         market_phase: str) -> Optional[str]:
    if smc_result is None:
        return None
    phase = _SMC_RELATIONSHIP_MAP.get(smc_result.affinity, REL_UNRESOLVED)
    if phase == REL_UNRESOLVED and market_phase == PHASE_IMPULSIVE and structural_bias in (STATE_BULLISH, STATE_BEARISH):
        return REL_EXPANDING_EXTERNAL  # SMC only emits *_INTERNAL_TO_EXTERNAL during CORRECTIVE; this is the IMPULSIVE mirror
    if phase == REL_UNRESOLVED and market_phase == PHASE_BALANCED:
        return REL_BALANCED
    return phase


def _session_liquidity_context(
    liquidity: Optional["LiquidityResult"], h1_structure_state: Optional[str],
    external_gap_context: Optional[bool], external_ob_context: Optional[bool],
    session_ob_reaction: Optional[bool],
) -> Optional[SessionLiquidityContext]:
    if liquidity is None or not getattr(liquidity, "levels", None):
        return None
    session_levels = [l for l in liquidity.levels if l.source in _ALL_SESSION_SOURCES]
    if not session_levels:
        return SessionLiquidityContext(
            status=SESSION_CONTEXT_NOT_AVAILABLE,
            evidence=("no session-sourced liquidity levels present in the supplied H1 LiquidityResult.",),
        )

    swept = [l for l in session_levels if l.status != LiquidityStatus.UNSWEPT]
    evidence = tuple(f"{l.source}={l.price} ({l.status.value})" for l in session_levels)

    session_name = session_high = session_low = swept_side = opposes = None
    if swept:
        anchor = swept[0]
        session_name = anchor.source.rsplit("_", 1)[0]  # "ASIAN_HIGH" -> "ASIAN"
        session_high = next((l.price for l in session_levels if l.source == f"{session_name}_HIGH"), None)
        session_low = next((l.price for l in session_levels if l.source == f"{session_name}_LOW"), None)
        swept_side = anchor.side.value
        if h1_structure_state in (STATE_BULLISH, STATE_BEARISH):
            h1_bias = BIAS_BULLISH if h1_structure_state == STATE_BULLISH else BIAS_BEARISH
            objective_side = _TARGET_SIDE_FOR_BIAS[h1_bias]
            # spec section 19: a sweep OPPOSES H1 structure when the swept side is not the
            # side H1 structure is itself drawing toward (e.g. BEARISH H1 + BUY_SIDE swept).
            opposes = anchor.side != objective_side

    status = SESSION_CONTEXT_RELEVANT if opposes else SESSION_CONTEXT_DETECTED
    return SessionLiquidityContext(
        session=session_name, session_high=session_high, session_low=session_low,
        swept_side=swept_side, h1_structure_direction=h1_structure_state, sweep_opposes_h1_structure=opposes,
        external_gap_context=external_gap_context, external_ob_context=external_ob_context,
        session_ob_reaction=session_ob_reaction, evidence=evidence, status=status,
    )


def _label_liquidity(scoped: Sequence["ScopedLiquidityLevel"], scope: str) -> tuple:
    return tuple(
        f"{scope}_{'BUY_SIDE' if s.level.side == LiquiditySide.BUY_SIDE else 'SELL_SIDE'}"
        f"@{s.level.price}:{s.level.status.value}"
        for s in scoped if s.scope == scope
    )


def _label_imbalances(imbalances: Sequence["ZoneResult"]) -> tuple:
    return tuple(f"INTERNAL_FVG@{z.low}-{z.high}:{z.status.value}" for z in imbalances if z.low is not None and z.high is not None)


def _consumed_vs_remaining(labels: Sequence[str]) -> tuple:
    consumed = tuple(l for l in labels if any(s in l for s in (":SWEPT", ":RECLAIMED", ":CONSUMED", ":MITIGATED", ":INVALIDATED")))
    remaining = tuple(l for l in labels if l not in consumed)
    return consumed, remaining


def evaluate_liquidity_affinity(
    symbol: str,
    narrative_bias: NarrativeBiasResult,
    liquidity: Optional["LiquidityResult"],
    *,
    tiers: Optional["TieredStructureResult"] = None,
    scoped_levels: Sequence["ScopedLiquidityLevel"] = (),
    imbalances: Sequence["ZoneResult"] = (),
    dealing_range: Optional["DealingRangeZones"] = None,
    h1_structure: Optional["StructureResult"] = None,
    current_price: Optional[float] = None,
    evaluation_time=None,
    external_gap_context: Optional[bool] = None,
    external_ob_context: Optional[bool] = None,
    session_ob_reaction: Optional[bool] = None,
) -> DayTradingLiquidityAffinityResult:
    external_liquidity = _label_liquidity(scoped_levels, SCOPE_EXTERNAL)
    internal_liquidity = _label_liquidity(scoped_levels, SCOPE_INTERNAL) + _label_imbalances(imbalances)
    consumed, remaining = _consumed_vs_remaining(external_liquidity + internal_liquidity)

    session_liquidity = _session_liquidity_context(
        liquidity, getattr(getattr(tiers, "external", None), "direction", None) or
        getattr(h1_structure, "state", None),
        external_gap_context, external_ob_context, session_ob_reaction,
    )

    smc_result = None
    if tiers is not None and current_price is not None:
        from liquidity.affinity import evaluate_liquidity_affinity as _smc_evaluate_liquidity_affinity
        smc_result = _smc_evaluate_liquidity_affinity(
            symbol, TIMEFRAME_INTEREST, tiers, scoped_levels, imbalances, dealing_range, current_price,
        )

    structural_bias = tiers.external.direction if (tiers is not None and tiers.external is not None) else None
    market_phase = _market_phase(smc_result, narrative_bias)
    relationship_phase = _relationship_phase(smc_result, structural_bias, market_phase)

    structure_context = None
    if h1_structure is not None and h1_structure.status == "VALID":
        latest_event = h1_structure.latest_bos or h1_structure.latest_choch
        structure_context = f"H1 {h1_structure.state}" + (f", latest event {latest_event.kind.value}" if latest_event else "")

    premium_discount_context = dealing_range.current_zone if dealing_range is not None else None

    internal_rebalance_target = None
    if smc_result is not None and smc_result.imbalance_candidate == "FVG":
        internal_rebalance_target = f"FVG {smc_result.imbalance_low}-{smc_result.imbalance_high}"
    elif smc_result is not None and smc_result.internal_liquidity_candidate is not None:
        internal_rebalance_target = f"{smc_result.internal_liquidity_type}@{smc_result.internal_liquidity_price}"

    common = dict(
        symbol=symbol, narrative_bias=narrative_bias.bias, evaluation_time=evaluation_time,
        external_liquidity=external_liquidity, internal_liquidity=internal_liquidity,
        session_liquidity=session_liquidity, consumed_liquidity=consumed, remaining_liquidity=remaining,
        internal_rebalance_target=internal_rebalance_target, external_internal_relationship=relationship_phase,
        market_phase=market_phase, structure_context=structure_context,
        premium_discount_context=premium_discount_context,
    )

    # --- narrative gate (spec section 5/30): Liquidity Affinity never assigns a
    # directional target independently of Narrative Bias, even with excellent H1 evidence. ---
    if narrative_bias.bias not in _TARGET_SIDE_FOR_BIAS:
        return DayTradingLiquidityAffinityResult(
            **common, status=AFFINITY_UNRESOLVED, affinity_direction=None,
            reason=f"narrative_bias={narrative_bias.bias} -- no directional draw to interpret liquidity against "
                   f"(narrative is context, not a command; spec section 30).",
        )
    if liquidity is None or liquidity.status not in ("LIQUIDITY_OK", "NO_LIQUIDITY_LEVELS"):
        return DayTradingLiquidityAffinityResult(
            **common, status=AFFINITY_INSUFFICIENT_DATA, affinity_direction=None,
            reason=f"liquidity data unavailable (status={getattr(liquidity, 'status', None)}).",
        )

    # --- conflict gate (spec section 28/29): higher-order H1 structure disagreeing with
    # Narrative Bias is grounds to refuse a directional target, even if nearby liquidity
    # levels would otherwise suggest one. Narrative Bias does not override this evidence. ---
    contradictions = []
    if structural_bias is not None and structural_bias != _STATE_FOR_BIAS[narrative_bias.bias]:
        contradictions.append(f"H1 external-tier structure={structural_bias} disagrees with "
                               f"narrative_bias={narrative_bias.bias}.")
        return DayTradingLiquidityAffinityResult(
            **common, status=AFFINITY_CONFLICTED, affinity_direction=None, contradictions=tuple(contradictions),
            reason="H1 structure and Narrative Bias disagree -- refusing to force a liquidity target "
                   "(spec section 28/29).",
        )

    target_side = _TARGET_SIDE_FOR_BIAS[narrative_bias.bias]
    entry_side = _OPPOSITE_SIDE[target_side]
    target_level = liquidity.nearest_buy_side if target_side == LiquiditySide.BUY_SIDE else liquidity.nearest_sell_side
    entry_level = liquidity.nearest_buy_side if entry_side == LiquiditySide.BUY_SIDE else liquidity.nearest_sell_side

    evidence = []
    relevant = tuple(l for l in (target_level, entry_level) if l is not None)
    if target_level is not None:
        evidence.append(f"target-side {target_side.value} liquidity at {target_level.price} "
                         f"({target_level.status.value}).")
    if entry_level is not None:
        evidence.append(f"entry-side {entry_side.value} liquidity at {entry_level.price} "
                         f"({entry_level.status.value}) -- may be swept first, not itself bearish/bullish "
                         f"(spec section 15: sweep is an event, not a direction).")

    if target_level is None:
        return DayTradingLiquidityAffinityResult(
            **common, entry_side_liquidity=entry_side.value if entry_level else None,
            relevant_levels=relevant, evidence=tuple(evidence), status=AFFINITY_UNRESOLVED,
            affinity_direction=None, reason="no target-side liquidity objective identified.",
        )

    if target_level.status != LiquidityStatus.UNSWEPT:
        return DayTradingLiquidityAffinityResult(
            **common, target_side_liquidity=target_side.value, relevant_levels=relevant,
            evidence=tuple(evidence), status=AFFINITY_UNRESOLVED, affinity_direction=None,
            reason=f"target-side {target_side.value} liquidity already {target_level.status.value} "
                   f"-- draw already resolved, no fresh objective (spec section 40: never keep using "
                   f"already-consumed liquidity as an active primary draw).",
        )

    status = AFFINITY_RESOLVED if entry_level is not None else AFFINITY_PARTIAL
    return DayTradingLiquidityAffinityResult(
        **common, primary_draw=target_side.value,
        entry_side_liquidity=entry_side.value if entry_level else None,
        target_side_liquidity=target_side.value, relevant_levels=relevant, evidence=tuple(evidence),
        status=status, affinity_direction=target_side.value,
        primary_target_price=target_level.price, primary_target_type=f"EXTERNAL_{target_side.value}",
        primary_target_timeframe=TIMEFRAME_INTEREST,
        primary_target_reason="nearest unswept target-side external liquidity, consistent with narrative_bias.",
        reason=None if status == AFFINITY_RESOLVED else "entry-side liquidity not identified; target-side draw still stands.",
    )
