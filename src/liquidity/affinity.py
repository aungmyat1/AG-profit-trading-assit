"""AG_LIQUIDITY_AFFINITY_V1 -- external/internal liquidity relationship.

Contextual SMC reasoning only: never an entry trigger, never trade-execution authority
(see LiquidityAffinityResult.trade_signal, which is hardcoded "NONE" on every result --
enforced in code, not just documented). Belongs to the LIQUIDITY skill; does not move
Entry Confirmation logic here and does not redefine BOS/CHoCH/FVG/dealing-range -- every
input below is consumed from market_structure/liquidity/supply_demand output unchanged.

Two layers:
  - evaluate_liquidity_affinity(): pure function over already-computed inputs
    (TieredStructureResult, scoped liquidity levels, FVG zones, a dealing range).
    Deterministic and MT5-free -- this is what the synthetic tests exercise.
  - liquidity_affinity_result(): live-data convenience wrapper that fetches those same
    inputs from market_structure.tiers / liquidity.hierarchy / supply_demand and calls
    the pure function. Imports are deferred to call time, same reasoning as
    supply_demand/native_zones.py's session_zone() docstring: this module sits inside
    the liquidity package, which entry_confirmation/assistant import at module load
    time, so importing supply_demand eagerly here would re-enter that chain.

External vs internal status depends on market_structure's own EXTERNAL/INTERNAL tier
split (market_structure/tiers.py) via liquidity.hierarchy.scope_liquidity_levels --
no price level is ever hardcoded as globally external or internal (spec section 11).

All states are probabilistic/contextual: CANDIDATE, POSSIBLE, PLAUSIBLE, UNRESOLVED,
INDETERMINATE. Nothing here asserts price WILL retrace, WILL sweep, or MUST return to a
zone -- see AffinityState docstring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Sequence, Tuple

from market_structure.models import STATE_BEARISH, STATE_BULLISH, STATE_UNDEFINED, StructureTier

from .hierarchy import SCOPE_EXTERNAL, SCOPE_INTERNAL, ScopedLiquidityLevel
from .models import LiquiditySide, LiquidityStatus

if TYPE_CHECKING:
    from market_structure.models import TieredStructureResult
    from supply_demand.models import ZoneResult
    from supply_demand.native_zones import DealingRangeZones

AFFINITY_RULE_VERSION = "AG_LIQUIDITY_AFFINITY_V1"

# --- Affinity states (spec section 5) --------------------------------------------------
BULLISH_INTERNAL_TO_EXTERNAL = "BULLISH_INTERNAL_TO_EXTERNAL"
BEARISH_INTERNAL_TO_EXTERNAL = "BEARISH_INTERNAL_TO_EXTERNAL"
EXTERNAL_TO_INTERNAL = "EXTERNAL_TO_INTERNAL"
INTERNAL_REBALANCING = "INTERNAL_REBALANCING"
EXTERNAL_LIQUIDITY_REACHED = "EXTERNAL_LIQUIDITY_REACHED"
AFFINITY_INVALIDATED = "AFFINITY_INVALIDATED"
INDETERMINATE = "INDETERMINATE"

# --- Market phase (spec section 3) ------------------------------------------------------
PHASE_IMPULSIVE = "IMPULSIVE"
PHASE_CORRECTIVE = "CORRECTIVE"
PHASE_INDETERMINATE = "INDETERMINATE"

# --- Confidence (spec section 16) -------------------------------------------------------
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_INDETERMINATE = "INDETERMINATE"

_SWEPT_STATUSES = (LiquidityStatus.SWEPT, LiquidityStatus.RECLAIMED, LiquidityStatus.CONSUMED)

# The side an EXTERNAL sweep must happen on to precede a reversal into this bias --
# opposite of the objective side for that same bias (sweep the lows to go up, and
# vice versa). Never inferred from price alone -- always this fixed structural mapping.
_OBJECTIVE_SIDE = {STATE_BULLISH: LiquiditySide.BUY_SIDE, STATE_BEARISH: LiquiditySide.SELL_SIDE}
_OPPOSITE_SIDE = {LiquiditySide.BUY_SIDE: LiquiditySide.SELL_SIDE, LiquiditySide.SELL_SIDE: LiquiditySide.BUY_SIDE}


@dataclass(frozen=True)
class LiquidityAffinityResult:
    """See spec section 15. Additive-only: no field here ever feeds execution --
    `trade_signal` is fixed to "NONE" and is not meant to be branched on for anything
    other than proving that invariant in tests."""

    symbol: str
    timeframe: str
    affinity: str = INDETERMINATE

    structural_bias: str = STATE_UNDEFINED
    market_phase: str = PHASE_INDETERMINATE

    external_liquidity_objective: Optional[str] = None  # level_id (liquidity.hierarchy.level_id)
    external_liquidity_type: Optional[str] = None        # e.g. "EXTERNAL_BSL" / "EXTERNAL_SSL"
    external_liquidity_price: Optional[float] = None

    internal_liquidity_candidate: Optional[str] = None
    internal_liquidity_type: Optional[str] = None         # "INTERNAL_BSL" / "INTERNAL_SSL"
    internal_liquidity_price: Optional[float] = None

    imbalance_candidate: Optional[str] = None
    imbalance_type: str = "NONE"                           # "FVG" / "NONE"
    imbalance_low: Optional[float] = None
    imbalance_high: Optional[float] = None

    dealing_range_high: Optional[float] = None
    dealing_range_low: Optional[float] = None
    equilibrium: Optional[float] = None
    premium_discount_location: Optional[str] = None        # "PREMIUM" / "DISCOUNT" / "EQUILIBRIUM"

    latest_structure_event: Optional[str] = None
    latest_liquidity_event: Optional[str] = None

    external_target_swept: bool = False
    affinity_invalidated: bool = False

    evidence: Tuple[str, ...] = field(default_factory=tuple)
    missing_evidence: Tuple[str, ...] = field(default_factory=tuple)
    confidence: str = CONFIDENCE_INDETERMINATE

    rule_version: str = AFFINITY_RULE_VERSION
    trade_signal: str = "NONE"  # ALWAYS "NONE" -- affinity never authorizes a trade (spec 13/18/27)


def _external_objective(scoped: Sequence[ScopedLiquidityLevel], bias: str, current_price: float) -> Optional[ScopedLiquidityLevel]:
    side = _OBJECTIVE_SIDE.get(bias)
    if side is None:
        return None
    candidates = [
        s for s in scoped
        if s.scope == SCOPE_EXTERNAL and s.level.side == side and s.level.status == LiquidityStatus.UNSWEPT
        and ((side == LiquiditySide.BUY_SIDE and s.level.price > current_price)
             or (side == LiquiditySide.SELL_SIDE and s.level.price < current_price))
    ]
    return min(candidates, key=lambda s: abs(s.level.price - current_price)) if candidates else None


def _external_reached(scoped: Sequence[ScopedLiquidityLevel], bias: str) -> Optional[ScopedLiquidityLevel]:
    side = _OBJECTIVE_SIDE.get(bias)
    if side is None:
        return None
    swept = [s for s in scoped if s.scope == SCOPE_EXTERNAL and s.level.side == side and s.level.status in _SWEPT_STATUSES]
    if not swept:
        return None
    return max(swept, key=lambda s: s.level.sweep_time or s.level.origin_time or 0)


def _opposite_side_sweep(scoped: Sequence[ScopedLiquidityLevel], bias: str) -> Optional[ScopedLiquidityLevel]:
    objective_side = _OBJECTIVE_SIDE.get(bias)
    if objective_side is None:
        return None
    opposite = _OPPOSITE_SIDE[objective_side]
    swept = [
        s for s in scoped
        if s.scope == SCOPE_EXTERNAL and s.level.side == opposite and s.level.status in _SWEPT_STATUSES
        and s.level.sweep_time is not None
    ]
    return max(swept, key=lambda s: s.level.sweep_time) if swept else None


def _internal_liquidity_candidate(scoped: Sequence[ScopedLiquidityLevel], bias: str, current_price: float) -> Optional[ScopedLiquidityLevel]:
    # Bullish retracement target = internal SELL_SIDE liquidity below price; bearish
    # mirror = internal BUY_SIDE liquidity above price. Never the objective side.
    side = {STATE_BULLISH: LiquiditySide.SELL_SIDE, STATE_BEARISH: LiquiditySide.BUY_SIDE}.get(bias)
    if side is None:
        return None
    candidates = [
        s for s in scoped
        if s.scope == SCOPE_INTERNAL and s.level.side == side and s.level.status == LiquidityStatus.UNSWEPT
        and ((side == LiquiditySide.SELL_SIDE and s.level.price < current_price)
             or (side == LiquiditySide.BUY_SIDE and s.level.price > current_price))
    ]
    return min(candidates, key=lambda s: abs(s.level.price - current_price)) if candidates else None


def _imbalance_candidate(imbalances: Sequence["ZoneResult"], bias: str, current_price: float,
                          after_time=None) -> Optional["ZoneResult"]:
    """FVG only (spec section 2C) -- an imbalance, never blindly relabeled as liquidity.
    Bullish bias wants a BULLISH FVG at/below current price (a pullback target below a
    rising move); bearish mirrors with a BEARISH FVG at/above current price."""
    from supply_demand.models import ZoneDirection, ZoneStatus  # deferred, see module docstring

    direction = {STATE_BULLISH: ZoneDirection.BULLISH, STATE_BEARISH: ZoneDirection.BEARISH}.get(bias)
    if direction is None:
        return None
    candidates = []
    for z in imbalances:
        if z.direction != direction or z.status not in (ZoneStatus.FRESH, ZoneStatus.TOUCHED):
            continue
        if z.low is None or z.high is None:
            continue
        if direction == ZoneDirection.BULLISH and not (z.low < current_price):
            continue
        if direction == ZoneDirection.BEARISH and not (z.high > current_price):
            continue
        if after_time is not None and z.origin_time is not None and z.origin_time < after_time:
            continue
        candidates.append(z)
    if not candidates:
        return None
    mid = lambda z: (z.low + z.high) / 2.0
    return min(candidates, key=lambda z: abs(mid(z) - current_price))


def _premium_discount(dealing_range: Optional["DealingRangeZones"], price: Optional[float]) -> Optional[str]:
    if dealing_range is None or price is None:
        return None
    if price > dealing_range.equilibrium:
        return "PREMIUM"
    if price < dealing_range.equilibrium:
        return "DISCOUNT"
    return "EQUILIBRIUM"


def _structural_bias(tiers: "TieredStructureResult") -> str:
    if tiers.external is None:
        return STATE_UNDEFINED
    return tiers.external.direction


def _market_phase(tiers: "TieredStructureResult") -> str:
    if tiers.external is None or tiers.internal is None:
        return PHASE_INDETERMINATE
    bias = tiers.external.direction
    internal_dir = tiers.internal.direction
    if bias == STATE_UNDEFINED or internal_dir == STATE_UNDEFINED:
        return PHASE_INDETERMINATE
    return PHASE_IMPULSIVE if internal_dir == bias else PHASE_CORRECTIVE


def _bias_flip_invalidates(previous_affinity: Optional[str], bias: str) -> bool:
    """Spec section 9/22: a prior continuation hypothesis is invalidated by an opposing
    structural break -- here, the higher-order (EXTERNAL tier) bias no longer supports
    the direction the prior affinity assumed. Does NOT fire on FVG non-mitigation alone
    (that condition is never checked here at all)."""
    if previous_affinity == BULLISH_INTERNAL_TO_EXTERNAL and bias != STATE_BULLISH:
        return True
    if previous_affinity == BEARISH_INTERNAL_TO_EXTERNAL and bias != STATE_BEARISH:
        return True
    return False


def evaluate_liquidity_affinity(
    symbol: str,
    timeframe: str,
    tiers: "TieredStructureResult",
    scoped_levels: Sequence[ScopedLiquidityLevel],
    imbalances: Sequence["ZoneResult"] = (),
    dealing_range: Optional["DealingRangeZones"] = None,
    current_price: Optional[float] = None,
    previous_affinity: Optional[str] = None,
) -> LiquidityAffinityResult:
    base = dict(symbol=symbol, timeframe=timeframe)

    if tiers is None or tiers.status != "VALID" or tiers.external is None or tiers.internal is None:
        return LiquidityAffinityResult(
            **base, affinity=INDETERMINATE, confidence=CONFIDENCE_INDETERMINATE,
            missing_evidence=(f"structure_tiers_unavailable:{getattr(tiers, 'status', 'NONE')}",),
        )
    if current_price is None:
        return LiquidityAffinityResult(
            **base, affinity=INDETERMINATE, confidence=CONFIDENCE_INDETERMINATE,
            structural_bias=tiers.external.direction,
            missing_evidence=("current_price_unavailable",),
        )

    bias = _structural_bias(tiers)
    phase = _market_phase(tiers)
    dr_high = dealing_range.high if dealing_range else None
    dr_low = dealing_range.low if dealing_range else None
    equilibrium = dealing_range.equilibrium if dealing_range else None
    pd_location = _premium_discount(dealing_range, current_price)

    latest_structure_event = None
    latest_event_point = max(
        [p for p in (tiers.external.latest_bos, tiers.external.latest_choch,
                     tiers.internal.latest_bos, tiers.internal.latest_choch) if p is not None],
        key=lambda p: p.time_utc, default=None,
    )
    if latest_event_point is not None:
        latest_structure_event = latest_event_point.kind.value

    evidence = []
    missing = []

    # --- invalidation: checked before any continuation hypothesis is (re)built ---
    if previous_affinity is not None and _bias_flip_invalidates(previous_affinity, bias):
        evidence.append(f"prior_affinity={previous_affinity} no longer supported: structural_bias is now {bias}.")
        return LiquidityAffinityResult(
            **base, affinity=AFFINITY_INVALIDATED, structural_bias=bias, market_phase=phase,
            dealing_range_high=dr_high, dealing_range_low=dr_low, equilibrium=equilibrium,
            premium_discount_location=pd_location, latest_structure_event=latest_structure_event,
            affinity_invalidated=True, evidence=tuple(evidence), confidence=CONFIDENCE_LOW,
        )

    # --- external -> internal: an opposite-side external sweep followed by a same-bias imbalance ---
    opposite_sweep = _opposite_side_sweep(scoped_levels, bias)
    if opposite_sweep is not None:
        fresh_imbalance = _imbalance_candidate(imbalances, bias, current_price, after_time=opposite_sweep.level.sweep_time)
        if fresh_imbalance is not None:
            evidence.append(f"{opposite_sweep.level.side.value} external liquidity swept at {opposite_sweep.level.price}; "
                             f"a same-direction imbalance formed afterward.")
            return LiquidityAffinityResult(
                **base, affinity=EXTERNAL_TO_INTERNAL, structural_bias=bias, market_phase=phase,
                imbalance_candidate="FVG", imbalance_type="FVG",
                imbalance_low=fresh_imbalance.low, imbalance_high=fresh_imbalance.high,
                dealing_range_high=dr_high, dealing_range_low=dr_low, equilibrium=equilibrium,
                premium_discount_location=pd_location,
                latest_structure_event=latest_structure_event,
                latest_liquidity_event=f"{opposite_sweep.level.side.value}_SWEEP",
                evidence=tuple(evidence), confidence=CONFIDENCE_MEDIUM,
            )

    external_objective = _external_objective(scoped_levels, bias, current_price)
    internal_candidate = _internal_liquidity_candidate(scoped_levels, bias, current_price)
    fvg_candidate = _imbalance_candidate(imbalances, bias, current_price)

    if internal_candidate is not None:
        evidence.append(f"internal {internal_candidate.level.side.value} liquidity candidate at {internal_candidate.level.price}.")
    else:
        missing.append("no_unswept_internal_liquidity_candidate")
    if fvg_candidate is not None:
        evidence.append(f"imbalance (FVG) candidate {fvg_candidate.low}-{fvg_candidate.high}.")
    else:
        missing.append("no_matching_fvg_imbalance")
    if external_objective is not None:
        evidence.append(f"unswept external {external_objective.level.side.value} objective at {external_objective.level.price}.")
    else:
        missing.append("no_unswept_external_objective")

    if bias in (STATE_BULLISH, STATE_BEARISH) and phase == PHASE_CORRECTIVE and external_objective is not None \
            and (internal_candidate is not None or fvg_candidate is not None):
        affinity = BULLISH_INTERNAL_TO_EXTERNAL if bias == STATE_BULLISH else BEARISH_INTERNAL_TO_EXTERNAL
        confidence = CONFIDENCE_HIGH if (internal_candidate is not None and fvg_candidate is not None) else CONFIDENCE_MEDIUM
        return LiquidityAffinityResult(
            **base, affinity=affinity, structural_bias=bias, market_phase=phase,
            external_liquidity_objective=external_objective.level_id,
            external_liquidity_type=_side_label("EXTERNAL", external_objective.level.side),
            external_liquidity_price=external_objective.level.price,
            internal_liquidity_candidate=internal_candidate.level_id if internal_candidate else None,
            internal_liquidity_type=_side_label("INTERNAL", internal_candidate.level.side) if internal_candidate else None,
            internal_liquidity_price=internal_candidate.level.price if internal_candidate else None,
            imbalance_candidate="FVG" if fvg_candidate is not None else None,
            imbalance_type="FVG" if fvg_candidate is not None else "NONE",
            imbalance_low=fvg_candidate.low if fvg_candidate is not None else None,
            imbalance_high=fvg_candidate.high if fvg_candidate is not None else None,
            dealing_range_high=dr_high, dealing_range_low=dr_low, equilibrium=equilibrium,
            premium_discount_location=pd_location, latest_structure_event=latest_structure_event,
            evidence=tuple(evidence), missing_evidence=tuple(missing), confidence=confidence,
        )

    reached = _external_reached(scoped_levels, bias)
    if reached is not None:
        evidence.append(f"external {reached.level.side.value} objective at {reached.level.price} already {reached.level.status.value}.")
        return LiquidityAffinityResult(
            **base, affinity=EXTERNAL_LIQUIDITY_REACHED, structural_bias=bias, market_phase=phase,
            external_liquidity_objective=reached.level_id,
            external_liquidity_type=_side_label("EXTERNAL", reached.level.side),
            external_liquidity_price=reached.level.price,
            dealing_range_high=dr_high, dealing_range_low=dr_low, equilibrium=equilibrium,
            premium_discount_location=pd_location, latest_structure_event=latest_structure_event,
            latest_liquidity_event=f"{reached.level.side.value}_{reached.level.status.value}",
            external_target_swept=True, evidence=tuple(evidence), missing_evidence=tuple(missing),
            confidence=CONFIDENCE_LOW,
        )

    if phase == PHASE_CORRECTIVE and (internal_candidate is not None or fvg_candidate is not None):
        return LiquidityAffinityResult(
            **base, affinity=INTERNAL_REBALANCING, structural_bias=bias, market_phase=phase,
            internal_liquidity_candidate=internal_candidate.level_id if internal_candidate else None,
            internal_liquidity_type=_side_label("INTERNAL", internal_candidate.level.side) if internal_candidate else None,
            internal_liquidity_price=internal_candidate.level.price if internal_candidate else None,
            imbalance_candidate="FVG" if fvg_candidate is not None else None,
            imbalance_type="FVG" if fvg_candidate is not None else "NONE",
            imbalance_low=fvg_candidate.low if fvg_candidate is not None else None,
            imbalance_high=fvg_candidate.high if fvg_candidate is not None else None,
            dealing_range_high=dr_high, dealing_range_low=dr_low, equilibrium=equilibrium,
            premium_discount_location=pd_location, latest_structure_event=latest_structure_event,
            evidence=tuple(evidence), missing_evidence=tuple(missing), confidence=CONFIDENCE_LOW,
        )

    missing.append("no_qualifying_affinity_relationship")
    return LiquidityAffinityResult(
        **base, affinity=INDETERMINATE, structural_bias=bias, market_phase=phase,
        dealing_range_high=dr_high, dealing_range_low=dr_low, equilibrium=equilibrium,
        premium_discount_location=pd_location, latest_structure_event=latest_structure_event,
        evidence=tuple(evidence), missing_evidence=tuple(missing), confidence=CONFIDENCE_INDETERMINATE,
    )


def _side_label(scope: str, side: LiquiditySide) -> str:
    suffix = "BSL" if side == LiquiditySide.BUY_SIDE else "SSL"
    return f"{scope}_{suffix}"


def liquidity_affinity_result(
    symbol: str, timeframe: str, count: Optional[int] = None, previous_affinity: Optional[str] = None,
) -> LiquidityAffinityResult:
    """Live-data wrapper. Fetches TieredStructureResult, scoped liquidity levels, FVGs,
    and a dealing range built from the EXTERNAL tier's own latest swing range, then calls
    evaluate_liquidity_affinity() -- no detection logic lives here, only composition of
    already-existing analyzers (market_structure.tiers, liquidity.analyzer/hierarchy,
    supply_demand). Deferred imports: see module docstring."""
    from market_structure.tiers import analyze_structure_tiers
    from mt5.market_data import MarketDataError, get_latest_candles, get_tick
    from supply_demand import dealing_range_zones, fair_value_gaps_for

    from .analyzer import liquidity_result as _liquidity_result
    from .hierarchy import external_swing_liquidity, scope_liquidity_levels

    tiers = analyze_structure_tiers(symbol, timeframe, count)
    if tiers.status != "VALID":
        return evaluate_liquidity_affinity(symbol, timeframe, tiers, (), (), None, None, previous_affinity)

    current_price: Optional[float] = None
    try:
        current_price = get_tick(symbol).bid
    except MarketDataError:
        pass

    liq = _liquidity_result(symbol, timeframe)
    internal_levels = liq.levels if liq.status == "LIQUIDITY_OK" else ()

    try:
        candles = get_latest_candles(symbol, timeframe, count or 300)
    except MarketDataError:
        candles = []
    external_levels = external_swing_liquidity(symbol, timeframe, tiers.external, candles) if candles else ()
    scoped = scope_liquidity_levels(external_levels, internal_levels)

    fvg_result = fair_value_gaps_for(symbol, timeframe)
    imbalances = fvg_result.zones if fvg_result.status == "OK" else ()

    dealing_range = None
    sh, sl = tiers.external.latest_swing_high, tiers.external.latest_swing_low
    if sh is not None and sl is not None and sl.price < sh.price:
        dealing_range = dealing_range_zones(symbol, sl.price, sh.price, source="external_tier_swing_range",
                                             current_price=current_price)

    return evaluate_liquidity_affinity(
        symbol, timeframe, tiers, scoped, imbalances, dealing_range, current_price, previous_affinity,
    )
