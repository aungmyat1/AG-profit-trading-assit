"""M1 = CHARACTER_CHANGE_WITH_INDUCEMENT -- one of three interchangeable M5 confirmation
maneuvers in SMC_CONDITIONAL_ENTRY_V2 (entry_models_v1.py). NOT generic CHoCH detection:
a CHoCH without a causally-prior, deterministically identified inducement sweep is
insufficient (fail closed -- "CHOCH=YES, INDUCEMENT=UNKNOWN => M1 != READY", spec
section 12). Never fabricates inducement by selecting the nearest swing.

DECOUPLED FROM E1 (spec section 10): this maneuver used to require an `E1Result`
specifically. It now accepts ANY qualified `EConditionResult` (from E1, E2, or E3) --
the composer decides which E's to feed it, this module only checks
`eligible_for_confirmation` and `direction`. If the caller-supplied inducement evidence
implies a direction that contradicts the E-condition's own direction, this reports
`NO_VALID_COMBINATION` rather than silently trusting one side.

Required sequence: E active -> inducement candidate identified -> inducement taken ->
CHoCH (strictly after) -> displacement -> entry array -> retracement -> READY.

Reuses, never redetects:
- `liquidity.hierarchy.InducementCandidate` (AG's own deterministic inducement
  RELATIONSHIP: an UNSWEPT INTERNAL-tier level positioned between current price and an
  UNSWEPT EXTERNAL-tier target on the same side) for WHICH level is the inducement --
  this module only asks whether that caller-identified candidate was subsequently taken.
- `market_structure.structural_breaks_for_candles` for CHoCH (closed-candle only, per
  config/market_structure.yaml's close_break=true).
- `entry_confirmation.displacement.evaluate_displacement` (AG_ENTRY_DISPLACEMENT_V1).
- `entry_confirmation.entry_array.evaluate_entry_array` for the resulting FVG/OB/
  confluence entry geometry (spec section 7 -- FVG/OB/last-pullback, not a new detector).

Direction -> expected inducement side (mirrors the same mapping
`e2_h1_poi_reaction.py::_relevant_liquidity_side` already uses for M5 liquidity, applied
here to the inducement candidate's own side): a bearish character change (SHORT) is
induced by a BUY_SIDE level taken (liquidity above trapped before the real drop); a
bullish character change (LONG) is induced by a SELL_SIDE level taken.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence, Tuple

from liquidity.hierarchy import InducementCandidate
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure import MarketStructureConfig, StructurePointKind, structural_breaks_for_candles
from strategy_engine.session import Candle
from supply_demand import ValidatedOrderBlock, ZoneResult

from .displacement import evaluate_displacement
from .entry_array import evaluate_entry_array
from .entry_models_v1 import EConditionResult, EntryModelState
from .gap import evaluate_gap_context
from .invalidation import SOURCE_INDUCEMENT_LEVEL, entry_array_invalidation
from .models import CandidateDirection

M1_CHARACTER_CHANGE_WITH_INDUCEMENT_V1 = "M1_CHARACTER_CHANGE_WITH_INDUCEMENT_V1"
MANEUVER = "M1"

_TAKEN_STATUSES = (LiquidityStatus.SWEPT, LiquidityStatus.RECLAIMED, LiquidityStatus.CONSUMED)

_CHOCH_KIND_FOR_DIRECTION = {
    CandidateDirection.SHORT: StructurePointKind.BEARISH_CHOCH,
    CandidateDirection.LONG: StructurePointKind.BULLISH_CHOCH,
}

_EXPECTED_INDUCEMENT_SIDE = {
    CandidateDirection.SHORT: LiquiditySide.BUY_SIDE,
    CandidateDirection.LONG: LiquiditySide.SELL_SIDE,
}

_INDUCEMENT_DIRECTION_FOR_SIDE = {
    LiquiditySide.BUY_SIDE: CandidateDirection.SHORT,
    LiquiditySide.SELL_SIDE: CandidateDirection.LONG,
}


@dataclass(frozen=True)
class M1Result:
    version: str = M1_CHARACTER_CHANGE_WITH_INDUCEMENT_V1
    maneuver: str = MANEUVER
    symbol: str = ""
    entry_condition: Optional[str] = None  # which E fed this evaluation ("E1"/"E2"/"E3"), if any
    direction: Optional[str] = None
    state: str = EntryModelState.NOT_APPLICABLE.value

    inducement_level: Optional[float] = None
    inducement_type: Optional[str] = None  # LiquidityLevel.source, e.g. "SWING_LOW"
    inducement_taken: bool = False

    choch_level: Optional[float] = None
    choch_confirmed: bool = False

    displacement_confirmed: bool = False

    entry_array_type: str = "NONE"
    entry_array_low: Optional[float] = None
    entry_array_high: Optional[float] = None
    entry_retrace_confirmed: bool = False

    invalidation_price: Optional[float] = None
    invalidation_source_type: Optional[str] = None
    invalidation_reason: Optional[str] = None
    invalidation_trigger: Optional[str] = None

    evidence: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


def _candle_at(candles: Sequence[Candle], time: datetime) -> Optional[Candle]:
    return next((c for c in candles if c.time == time), None)


def _zone_in_window(zones: Sequence[ZoneResult], start: datetime, end: datetime) -> Optional[ZoneResult]:
    matching = sorted(
        (z for z in zones if z.origin_time is not None and start <= z.origin_time <= end),
        key=lambda z: z.origin_time,
    )
    return matching[0] if matching else None


def _ob_for_event(order_blocks: Sequence[ValidatedOrderBlock], event_time: datetime) -> Optional[ValidatedOrderBlock]:
    return next(
        (ob for ob in order_blocks if ob.structure_event is not None and ob.structure_event.time_utc == event_time),
        None,
    )


def evaluate_m1_character_change_with_inducement(
    symbol: str,
    e_condition: Optional[EConditionResult],
    inducement_candidate: Optional[InducementCandidate],
    inducement_taken_level: Optional[LiquidityLevel] = None,
    m5_candles: Sequence[Candle] = (),
    m5_displacement_history: Sequence[Candle] = (),
    m5_fvg_zones: Sequence[ZoneResult] = (),
    m5_order_blocks: Sequence[ValidatedOrderBlock] = (),
    current_price: Optional[float] = None,
    evaluation_time: Optional[datetime] = None,
    structure_config: Optional[MarketStructureConfig] = None,
) -> M1Result:
    entry_condition = e_condition.entry_condition if e_condition is not None else None
    if e_condition is None or not e_condition.eligible_for_confirmation:
        return M1Result(symbol=symbol, entry_condition=entry_condition, state=EntryModelState.NOT_APPLICABLE.value,
                         reason="No qualified E-condition supplied -- M1 not applicable.")

    e_direction = CandidateDirection(e_condition.direction) if e_condition.direction in (
        CandidateDirection.LONG.value, CandidateDirection.SHORT.value,
    ) else CandidateDirection.NONE
    if e_direction == CandidateDirection.NONE:
        return M1Result(symbol=symbol, entry_condition=entry_condition, state=EntryModelState.NOT_APPLICABLE.value,
                         reason="E-condition direction unresolved -- cannot determine M1 candidate direction.")

    if inducement_candidate is None:
        # Fail closed (spec section 12): never fabricate inducement by picking the
        # nearest swing. A CHoCH found later without this is still not READY.
        return M1Result(symbol=symbol, entry_condition=entry_condition, direction=e_direction.value,
                         state=EntryModelState.WAITING_HTF_TOUCH.value, inducement_taken=False,
                         reason="INDUCEMENT=UNKNOWN -- no deterministic inducement candidate identified; "
                                "M1 cannot proceed (CHoCH alone is never sufficient).")

    m1_direction = _INDUCEMENT_DIRECTION_FOR_SIDE.get(inducement_candidate.side)
    if m1_direction != e_direction:
        # Direction alignment (spec section 10): the inducement evidence itself implies
        # a different direction than the E-condition qualified -- not a valid combination.
        return M1Result(symbol=symbol, entry_condition=entry_condition, direction=m1_direction.value if m1_direction else None,
                         state=EntryModelState.NO_VALID_COMBINATION.value,
                         inducement_level=inducement_candidate.candidate.price,
                         inducement_type=inducement_candidate.candidate.source, inducement_taken=False,
                         reason=f"Inducement candidate side {inducement_candidate.side.value} implies "
                                f"{m1_direction.value if m1_direction else 'an unresolved direction'}, which does "
                                f"not match the E-condition's {e_direction.value} direction.")

    direction = e_direction
    inducement_level = inducement_candidate.candidate.price
    inducement_type = inducement_candidate.candidate.source

    taken = (
        inducement_taken_level is not None
        and inducement_taken_level.price == inducement_level
        and inducement_taken_level.status in _TAKEN_STATUSES
        and inducement_taken_level.sweep_time is not None
    )
    if not taken:
        return M1Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_H1_REACTION.value,
                         inducement_level=inducement_level, inducement_type=inducement_type, inducement_taken=False,
                         reason="Inducement candidate identified but not yet taken.")

    inducement_taken_time = inducement_taken_level.sweep_time

    wanted_kind = _CHOCH_KIND_FOR_DIRECTION[direction]
    breaks = structural_breaks_for_candles(m5_candles, structure_config)
    qualifying = [
        b for b in breaks if b.kind == wanted_kind and b.time_utc > inducement_taken_time
        and (evaluation_time is None or b.time_utc <= evaluation_time)
    ]
    if not qualifying:
        return M1Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_M5_CONFIRMATION.value,
                         inducement_level=inducement_level, inducement_type=inducement_type, inducement_taken=True,
                         choch_confirmed=False,
                         reason="Inducement taken but no causally-ordered closed-candle CHoCH found yet.")
    choch_point = qualifying[0]

    displacement_candle = _candle_at(m5_candles, choch_point.time_utc)
    displacement = evaluate_displacement(displacement_candle, direction, m5_displacement_history)
    if displacement.status.value != "PASS":
        return M1Result(symbol=symbol, entry_condition=entry_condition, direction=direction.value,
                         state=EntryModelState.WAITING_M5_CONFIRMATION.value,
                         inducement_level=inducement_level, inducement_type=inducement_type, inducement_taken=True,
                         choch_level=choch_point.price, choch_confirmed=True, displacement_confirmed=False,
                         reason="CHoCH confirmed but displacement does not qualify under AG_ENTRY_DISPLACEMENT_V1.")

    leg_start, leg_end = inducement_taken_time, choch_point.time_utc
    fvg_zone = _zone_in_window(m5_fvg_zones, leg_start, leg_end)
    order_block = _ob_for_event(m5_order_blocks, choch_point.time_utc)
    gap_context = evaluate_gap_context(fvg_zone) if fvg_zone is not None else None
    fvg_associated = fvg_zone is not None and leg_start <= fvg_zone.origin_time <= leg_end if fvg_zone is not None else False
    ob_associated = order_block is not None

    entry_array = evaluate_entry_array(
        gap_context=gap_context, fvg_associated=fvg_associated, ob=order_block, ob_associated=ob_associated,
        candidate_direction=direction, sweep_price=inducement_level, current_price=current_price,
    )

    if entry_array.entry_array_type == "NONE":
        state = EntryModelState.WAITING_M5_CONFIRMATION.value
    elif entry_array.entry_status == "ENTRY_REFERENCE_AVAILABLE":
        state = EntryModelState.READY.value
    else:
        state = EntryModelState.WAITING_M5_ENTRY.value

    invalidation = entry_array_invalidation(entry_array, direction, current_price,
                                             inducement_level, SOURCE_INDUCEMENT_LEVEL)
    if invalidation is not None and invalidation.triggered:
        state = EntryModelState.INVALIDATED.value

    return M1Result(
        symbol=symbol, entry_condition=entry_condition, direction=direction.value, state=state,
        inducement_level=inducement_level, inducement_type=inducement_type, inducement_taken=True,
        choch_level=choch_point.price, choch_confirmed=True, displacement_confirmed=True,
        entry_array_type=entry_array.entry_array_type,
        entry_array_low=min(order_block.low, order_block.high) if order_block is not None else (fvg_zone.low if fvg_zone else None),
        entry_array_high=max(order_block.low, order_block.high) if order_block is not None else (fvg_zone.high if fvg_zone else None),
        entry_retrace_confirmed=entry_array.entry_status == "ENTRY_REFERENCE_AVAILABLE",
        invalidation_price=invalidation.price if invalidation is not None else None,
        invalidation_source_type=invalidation.source_type if invalidation is not None else None,
        invalidation_reason=invalidation.reason if invalidation is not None else None,
        invalidation_trigger=invalidation.trigger if invalidation is not None else None,
        evidence=(
            f"inducement={inducement_type}@{inducement_level}", f"choch@{choch_point.time_utc}",
            f"entry_array={entry_array.entry_array_type}",
        ),
        reason=invalidation.reason if (invalidation is not None and invalidation.triggered) else entry_array.reason,
    )
