"""M3 = SWEEP_DROP_PUMP -- one of three interchangeable M5 confirmation maneuvers in
SMC_CONDITIONAL_ENTRY_V2 (entry_models_v1.py). This is the model the prior revision of
`e2_h1_poi_reaction.py` was structurally implementing (sweep -> CHoCH -> displacement ->
FVG/OB) before that pass re-homed it: HTF-liquidity-sweep-driven reversal composition
belongs here. Delegates the sweep -> pivot -> body-close structure-shift -> displacement
-> FVG/OB entry-array chain verbatim to `engine_v2_1.evaluate_reversal_sweep_shift`
(SMC_SWEEP_SHIFT_ARRAY_V1, already owner-signed) -- no structure/liquidity/FVG/OB/
displacement detector duplicated.

DECOUPLED FROM E3 (spec section 10): this maneuver used to require an `E3Result`
specifically. It now accepts ANY qualified `EConditionResult` (from E1, E2, or E3) plus
the concrete `LiquidityLevel` evidence separately (a POI reaction or a Daily gap
reaction can also motivate checking whether a *local* M5 liquidity level got swept and
reclaimed, not only an HTF one). The composer decides which E's to feed it; this module
only checks `eligible_for_confirmation` and `direction`. M3 derives its OWN direction
independently from the liquidity level's side -- if that contradicts the E-condition's
direction, this reports `NO_VALID_COMBINATION`.

Bearish: BSL swept+reclaimed -> M5 bearish CHoCH strictly after the reclaim -> bearish
displacement -> FVG/OB entry array -> 50% pullback -> SHORT READY. Bullish mirrors (SSL
swept+reclaimed -> bullish CHoCH -> ...).

M3_INVERTED_GAP_POLICY = OPTIONAL (frozen this pass, not changed from prior behavior --
made explicit). Audited against the two possible contracts:

    Contract A -- inverted gap is OPTIONAL: M3 = sweep -> rejection -> drop/pump ->
        QUALIFYING immediate entry structure (gap, FVG, wick/body retracement, or any
        other already-implemented immediate entry array) -> 50% pullback. Inverted gap
        is one *possible* specialization of "entry structure", never the only one, and
        never gates READY.
    Contract B -- inverted gap is MANDATORY: 50% of an inverted gap specifically is
        required; without a signed inverted-gap definition, M3 could never legitimately
        reach READY, and would need to report M3_FULL_REFERENCE_CONFORMANCE = PARTIAL.

This module already implements Contract A: `entry_array.py`'s regular FVG/OB midpoint
(never an inverted-gap-specific midpoint) is the actual gating entry structure, and
`pullback_percent` is computed from THAT structure, not from an inverted gap. INVERTED_GAP
has no signed definition anywhere in this repo (`gap.py::evaluate_inverted_gap_context`
already reports this honestly as `policy="PARTIAL"`); this module surfaces that same
PARTIAL policy as auxiliary evidence (`M3Result.inverted_gap_policy`) and never gates
READY on it (fail closed on the undefined primitive) -- consistent with Contract A, which
this module is now explicitly frozen to. `M3_FULL_REFERENCE_CONFORMANCE` is therefore not
applicable under Contract A (there is no "full reference" gap to be partially conformant
to); had Contract B applied, this module's classification would instead need to be
PARTIAL. The "50% pullback" IS well-defined regardless of which contract applies: it is
exactly `entry_array.py`'s existing FVG-midpoint / OB-midpoint / confluence-overlap-
midpoint arithmetic (`PULLBACK_PERCENT` is always 50.0 by construction of a midpoint --
not a separately invented threshold).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence, Tuple

from liquidity import level_id
from liquidity.models import LiquidityLevel, LiquiditySide
from market_structure import MarketStructureConfig, StructurePointKind, StructureResult, structural_breaks_for_candles
from strategy_engine.session import Candle
from supply_demand import ValidatedOrderBlock, ZoneResult

from .displacement import evaluate_displacement
from .engine_v2_1 import SweepShiftArrayRequest, evaluate_reversal_sweep_shift
from .entry_models_v1 import EConditionResult, EntryModelState
from .gap import evaluate_gap_context, evaluate_inverted_gap_context
from .invalidation import SOURCE_LIQUIDITY_SWEEP_LEVEL, entry_array_invalidation
from .models import CandidateDirection
from .structure_alignment import evaluate_structure_alignment

M3_SWEEP_DROP_PUMP_V1 = "M3_SWEEP_DROP_PUMP_V1"
MANEUVER = "M3"
M3_INVERTED_GAP_POLICY = "OPTIONAL"  # frozen this pass -- see module docstring, Contract A

_CHOCH_KIND_FOR_DIRECTION = {
    CandidateDirection.SHORT: StructurePointKind.BEARISH_CHOCH,
    CandidateDirection.LONG: StructurePointKind.BULLISH_CHOCH,
}

# BUY_SIDE swept implies a bearish reversal candidate; SELL_SIDE swept implies bullish
# -- same convention e3_liquidity_sweep.py's own _DIRECTION_FOR_SIDE uses.
_DIRECTION_FOR_SIDE = {
    LiquiditySide.BUY_SIDE: CandidateDirection.SHORT,
    LiquiditySide.SELL_SIDE: CandidateDirection.LONG,
}

_STATUS_TO_STATE = {
    "WAITING_SWEEP": EntryModelState.WAITING_HTF_TOUCH.value,
    "WAITING_STRUCTURE_SHIFT": EntryModelState.WAITING_M5_CONFIRMATION.value,
    "FAKEOUT_WICK": EntryModelState.INVALIDATED.value,
    "INVALIDATED": EntryModelState.INVALIDATED.value,
    "NOT_CONFIRMED": EntryModelState.INVALIDATED.value,
    "WAITING_ENTRY_PRICE": EntryModelState.WAITING_M5_ENTRY.value,
    "ENTRY_REFERENCE_AVAILABLE": EntryModelState.READY.value,
    "INDETERMINATE": EntryModelState.WAITING_M5_CONFIRMATION.value,
}


@dataclass(frozen=True)
class M3Result:
    version: str = M3_SWEEP_DROP_PUMP_V1
    maneuver: str = MANEUVER
    symbol: str = ""
    entry_condition: Optional[str] = None  # which E fed this evaluation ("E1"/"E2"/"E3"), if any
    direction: Optional[str] = None
    state: str = EntryModelState.NOT_APPLICABLE.value

    sweep_level: Optional[float] = None
    sweep_type: Optional[str] = None
    reclaim: bool = False

    choch: Optional[float] = None
    choch_time: Optional[datetime] = None
    displacement: bool = False

    gap: Optional[str] = None  # entry_array_type from the underlying SMCSweepShiftArrayResult
    inverted_gap_policy: str = "PARTIAL"  # spec section 16/31 -- no signed inversion definition exists
    pullback_percent: Optional[float] = None
    entry_level: Optional[float] = None

    invalidation_price: Optional[float] = None
    invalidation_source_type: Optional[str] = None
    invalidation_reason: Optional[str] = None
    invalidation_trigger: Optional[str] = None

    # Canonical structural identity of THIS specific M3 candidate (ST_LARGE_SMC_V1
    # C14B) -- None until the M5 structural failure (choch_point) is found, since no
    # concrete candidate exists before then. Composed from the swept liquidity level's
    # own existing level_id (liquidity.level_id) and the confirming CHoCH timestamp --
    # both already computed above, nothing new detected. Additive/optional: existing
    # callers unaffected.
    source_id: Optional[str] = None

    evidence: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


def _m3_source_id(swept_level: LiquidityLevel, choch_time: datetime) -> str:
    """Same construction as _m1_source_id/_m2_source_id (ST_LARGE_SMC_V1 C14B): the
    swept liquidity level's own existing level_id plus the confirming CHoCH timestamp.
    No new hashing infrastructure."""
    import hashlib
    digest = hashlib.blake2b(
        f"{level_id(swept_level)}|{choch_time.isoformat()}".encode("utf-8"), digest_size=8,
    ).hexdigest()
    return f"M3-{digest}"


def evaluate_m3_sweep_drop_pump(
    symbol: str,
    e_condition: Optional[EConditionResult],
    liquidity_level: Optional[LiquidityLevel],
    m5_candles: Sequence[Candle] = (),
    m5_displacement_history: Sequence[Candle] = (),
    m5_fvg_zones: Sequence[ZoneResult] = (),
    m5_order_blocks: Sequence[ValidatedOrderBlock] = (),
    current_price: Optional[float] = None,
    evaluation_time: Optional[datetime] = None,
    structure_config: Optional[MarketStructureConfig] = None,
) -> M3Result:
    entry_condition = e_condition.entry_condition if e_condition is not None else None
    if e_condition is None or not e_condition.eligible_for_confirmation:
        return M3Result(symbol=symbol, entry_condition=entry_condition, state=EntryModelState.NOT_APPLICABLE.value,
                         reason="No qualified E-condition supplied -- M3 not applicable.")

    e_direction = CandidateDirection(e_condition.direction) if e_condition.direction in (
        CandidateDirection.LONG.value, CandidateDirection.SHORT.value,
    ) else CandidateDirection.NONE
    if e_direction == CandidateDirection.NONE:
        return M3Result(symbol=symbol, entry_condition=entry_condition, state=EntryModelState.NOT_APPLICABLE.value,
                         reason="E-condition direction unresolved -- cannot determine M3 candidate direction.")

    if liquidity_level is None:
        return M3Result(symbol=symbol, entry_condition=entry_condition, direction=e_direction.value,
                         state=EntryModelState.WAITING_HTF_TOUCH.value,
                         reason="No candidate liquidity level supplied -- M3 cannot proceed.")

    m3_direction = _DIRECTION_FOR_SIDE.get(liquidity_level.side)
    if m3_direction != e_direction:
        # Direction alignment (spec section 10): the liquidity level's own side implies
        # a different reversal direction than the E-condition qualified -- not a valid combination.
        return M3Result(symbol=symbol, entry_condition=entry_condition,
                         direction=m3_direction.value if m3_direction else None,
                         state=EntryModelState.NO_VALID_COMBINATION.value,
                         sweep_level=liquidity_level.price, sweep_type=liquidity_level.source,
                         reason=f"Liquidity level side {liquidity_level.side.value} implies "
                                f"{m3_direction.value if m3_direction else 'an unresolved direction'}, which does "
                                f"not match the E-condition's {e_direction.value} direction.")

    direction = e_direction
    reclaim_time = liquidity_level.reclaim_time
    if reclaim_time is None:
        return M3Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_H1_REACTION.value,
                         sweep_level=liquidity_level.price, sweep_type=liquidity_level.source, reclaim=False,
                         reason="Liquidity level not (yet) reclaimed -- cannot order the M5 structural failure causally.")

    wanted_kind = _CHOCH_KIND_FOR_DIRECTION[direction]
    breaks = structural_breaks_for_candles(m5_candles, structure_config)
    qualifying = [
        b for b in breaks if b.kind == wanted_kind and b.time_utc > reclaim_time
        and (evaluation_time is None or b.time_utc <= evaluation_time)
    ]
    if not qualifying:
        return M3Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_M5_CONFIRMATION.value,
                         sweep_level=liquidity_level.price, sweep_type=liquidity_level.source, reclaim=True,
                         reason="Sweep reclaimed but no causally-ordered closed-candle M5 structural failure found yet.")
    choch_point = qualifying[0]

    structure_result = StructureResult(symbol=symbol, timeframe="M5", status="VALID", reason_codes=(),
                                        latest_choch=choch_point)
    structure_shift = evaluate_structure_alignment(structure_result, direction, reference_time=reclaim_time)

    displacement_candle = next((c for c in m5_candles if c.time == choch_point.time_utc), None)
    displacement = evaluate_displacement(displacement_candle, direction, m5_displacement_history)

    leg_start, leg_end = reclaim_time, choch_point.time_utc
    fvg_zone = next(
        (z for z in m5_fvg_zones if z.origin_time is not None and leg_start <= z.origin_time <= leg_end), None,
    )
    order_block = next(
        (ob for ob in m5_order_blocks
         if ob.structure_event is not None and ob.structure_event.time_utc == choch_point.time_utc), None,
    )
    gap_context = evaluate_gap_context(fvg_zone) if fvg_zone is not None else None
    inverted_gap = evaluate_inverted_gap_context(fvg_zone) if fvg_zone is not None else None

    swreq = SweepShiftArrayRequest(
        symbol=symbol, timeframe="M5", candidate_direction=direction, evaluation_time=evaluation_time,
        sweep_level=liquidity_level, sweep_candle=None, pivot_price=choch_point.price, pivot_time=choch_point.time_utc,
        structure_shift=structure_shift, structure_break_candle_time=choch_point.time_utc,
        displacement=displacement, displacement_leg_start=leg_start, displacement_leg_end=leg_end,
        gap_context=gap_context, gap_origin_time=fvg_zone.origin_time if fvg_zone is not None else None,
        order_block=order_block, current_price=current_price,
    )
    result = evaluate_reversal_sweep_shift(swreq)

    state = _STATUS_TO_STATE.get(result.status, EntryModelState.WAITING_M5_CONFIRMATION.value)
    entry_reference = result.entry_array.entry_reference
    pullback_percent = 50.0 if entry_reference is not None else None

    # Recomputes via the SAME shared helper `engine_v2_1.evaluate_reversal_sweep_shift`
    # already used internally to decide `result.status == "INVALIDATED"` (never a
    # second/different rule) -- this just exposes price/source/reason alongside the
    # state that delegate already produced.
    invalidation = entry_array_invalidation(result.entry_array, direction, current_price,
                                             liquidity_level.price, SOURCE_LIQUIDITY_SWEEP_LEVEL)

    return M3Result(
        symbol=symbol, entry_condition=entry_condition, direction=direction.value, state=state,
        sweep_level=liquidity_level.price, sweep_type=liquidity_level.source, reclaim=True,
        choch=choch_point.price, choch_time=choch_point.time_utc,
        source_id=_m3_source_id(liquidity_level, choch_point.time_utc),
        displacement=displacement.status.value == "PASS",
        gap=result.entry_array.entry_array_type,
        inverted_gap_policy=inverted_gap.status if inverted_gap is not None else "UNAVAILABLE",
        pullback_percent=pullback_percent, entry_level=entry_reference,
        invalidation_price=invalidation.price if invalidation is not None else None,
        invalidation_source_type=invalidation.source_type if invalidation is not None else None,
        invalidation_reason=invalidation.reason if invalidation is not None else None,
        invalidation_trigger=invalidation.trigger if invalidation is not None else None,
        evidence=(f"sweep_reclaim@{reclaim_time}", f"choch@{choch_point.time_utc}",
                  f"aggregation_status={result.aggregation_status}"),
        reason=result.reason,
    )
