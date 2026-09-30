"""E1 = PRICE_FILL_AND_REACT_D1_GAP -- one of three interchangeable entry conditions in
SMC_CONDITIONAL_ENTRY_V2 (entry_models_v1.py). E1 answers WHERE/WHY only (layers 1-2:
REFERENCE + CHECK): does a valid Daily gap exist, has price filled/touched it, and has
it produced a qualifying reaction? E1 never constructs an entry and is no longer
hard-wired to a specific maneuver -- `eligible_for_confirmation` gates ANY of
M1/M2/M3 (m1_character_change_inducement.py / m2_supply_demand_shift.py /
m3_sweep_drop_pump.py) via the generic `EConditionResult` envelope
(`e1_to_econdition`), not just M1.

REFERENCE_TIMEFRAME = D1, CHECK_TIMEFRAME = H1 (spec section 2) -- the "H1 check" here
IS the reaction test: `gap.py::evaluate_gap_context`'s GAP_REACTED already requires a
caller-supplied reaction candle passing AG_ENTRY_DISPLACEMENT_V1, which is how this
package's H1-reaction evidence is expressed (a candle on whichever timeframe the caller
determined price is reacting at the gap -- typically H1 for a D1 reference, per the same
convention `daytrading_runtime/snapshot.py::build_e1_result` already uses). No new
gap-detection or reaction-detection logic exists here; direction is caller-supplied
(gap.py's own convention).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from strategy_engine.session import Candle
from supply_demand import ZoneResult

from .entry_models_v1 import REFERENCE_TIMEFRAME_E1, CHECK_TIMEFRAME, EConditionResult, EntryModelState
from .gap import evaluate_gap_context
from .models import CandidateDirection

E1_DAILY_GAP_REACTION_V1 = "E1_DAILY_GAP_REACTION_V1"

_FILL_STATUSES = ("UNTOUCHED", "GAP_TOUCHED", "GAP_FILLED")


@dataclass(frozen=True)
class E1Result:
    version: str = E1_DAILY_GAP_REACTION_V1
    symbol: str = ""
    gap: Optional[ZoneResult] = None
    direction: Optional[str] = None  # "LONG" / "SHORT" -- caller-asserted, per gap.py convention
    fill_status: str = "UNTOUCHED"  # UNTOUCHED / GAP_TOUCHED / GAP_FILLED
    reaction_status: str = "WAITING_REACTION"  # WAITING_REACTION / GAP_REACTED
    invalidation: Optional[str] = None  # None or "GAP_INVALIDATED"
    eligible_for_confirmation: bool = False
    reason: Optional[str] = None


def evaluate_e1_daily_gap_reaction(
    symbol: str,
    gap_zone: Optional[ZoneResult],
    candidate_direction: CandidateDirection = CandidateDirection.NONE,
    touch_candle: Optional[Candle] = None,
    reaction_candle: Optional[Candle] = None,
    reaction_history: Sequence[Candle] = (),
) -> E1Result:
    if gap_zone is None:
        return E1Result(symbol=symbol, eligible_for_confirmation=False, reason="No candidate Daily gap supplied.")

    gap_context = evaluate_gap_context(
        gap_zone, touch_candle=touch_candle, reaction_candle=reaction_candle,
        reaction_history=reaction_history, candidate_direction=candidate_direction,
    )

    if gap_context.status == "GAP_INVALIDATED":
        return E1Result(
            symbol=symbol, gap=gap_zone, direction=candidate_direction.value,
            fill_status="UNTOUCHED", reaction_status="WAITING_REACTION",
            invalidation="GAP_INVALIDATED", eligible_for_confirmation=False,
            reason="Daily gap invalidated -- no maneuver can confirm against it.",
        )

    fill_status = gap_context.status if gap_context.status in _FILL_STATUSES else "UNTOUCHED"
    reacted = gap_context.status == "GAP_REACTED"

    return E1Result(
        symbol=symbol, gap=gap_zone, direction=candidate_direction.value if candidate_direction != CandidateDirection.NONE else None,
        fill_status=fill_status if not reacted else "GAP_FILLED",
        reaction_status="GAP_REACTED" if reacted else "WAITING_REACTION",
        invalidation=None, eligible_for_confirmation=reacted,
        reason=gap_context.reason,
    )


def e1_to_econdition(result: E1Result) -> EConditionResult:
    """Converts the detailed E1Result to the generic envelope any M1/M2/M3 maneuver
    (or the composer) can consume without importing E1Result itself."""
    touch_status = EntryModelState.WAITING_H1_REACTION.value if result.fill_status != "UNTOUCHED" \
        else EntryModelState.WAITING_HTF_TOUCH.value
    reaction_status = EntryModelState.HTF_QUALIFIED.value if result.reaction_status == "GAP_REACTED" \
        else EntryModelState.WAITING_H1_REACTION.value
    return EConditionResult(
        entry_condition="E1", symbol=result.symbol, direction=result.direction,
        reference_timeframe=REFERENCE_TIMEFRAME_E1, check_timeframe=CHECK_TIMEFRAME,
        reference_type="D1_GAP",
        reference_low=result.gap.low if result.gap is not None else None,
        reference_high=result.gap.high if result.gap is not None else None,
        touch_status=touch_status, reaction_status=reaction_status,
        invalidation_status=result.invalidation, eligible_for_confirmation=result.eligible_for_confirmation,
        evidence={"gap": result.gap, "fill_status": result.fill_status},
        missing_conditions=() if result.eligible_for_confirmation else ("H1_REACTION",),
    )
