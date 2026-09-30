"""3x3 composer (spec section 18) -- the lightweight layer that turns independently
evaluated E-conditions and M-maneuvers into `SMCEntryCombinationResult`s. Does NOT
duplicate M1/M2/M3 logic nine times: it is pure cross-join + gating over results the
caller already computed by calling `evaluate_e1_daily_gap_reaction`/
`evaluate_e2_h1_poi_reaction`/`evaluate_e3_htf_liquidity_sweep` (each converted via
`e1_to_econdition`/`e2_to_econdition`/`e3_to_econdition`) and
`evaluate_m1_character_change_with_inducement`/`evaluate_m2_supply_demand_shift`/
`evaluate_m3_sweep_drop_pump`.

A combination is produced only when (spec section 18):

    E.eligible_for_confirmation == True
    AND M.state not in (NOT_APPLICABLE, NO_VALID_COMBINATION)
    AND E.direction == M.direction (both non-None)

No priority or routing is invented here (spec section 22): every valid combination is
returned; multiple E's and multiple M's may all be simultaneously active (spec section
21), producing anywhere from 0 to 9 combinations.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple, Union

from .entry_models_v1 import (
    CONFIRMATION_TIMEFRAME,
    EXECUTION_TIMEFRAME,
    EConditionResult,
    EntryModelState,
    SMCEntryCombinationResult,
)
from .m1_character_change_inducement import M1Result
from .m2_supply_demand_shift import M2Result
from .m3_sweep_drop_pump import M3Result

ManeuverResult = Union[M1Result, M2Result, M3Result]

_EXCLUDED_M_STATES = (EntryModelState.NOT_APPLICABLE.value, EntryModelState.NO_VALID_COMBINATION.value)


def _entry_summary(m: ManeuverResult) -> Tuple[Optional[str], Optional[float]]:
    """Best-effort (array_type, entry_price) across the three differently-shaped
    M-results -- a display convenience, never used for gating."""
    if isinstance(m, M1Result):
        low, high = m.entry_array_low, m.entry_array_high
        price = (low + high) / 2.0 if low is not None and high is not None else None
        return (m.entry_array_type if m.entry_array_type != "NONE" else None), price
    if isinstance(m, M2Result):
        if m.entry_fvg is not None:
            return "FVG", (m.entry_fvg.low + m.entry_fvg.high) / 2.0 if m.entry_fvg.low is not None and m.entry_fvg.high is not None else None
        if m.entry_ob is not None:
            return "ORDER_BLOCK", (m.entry_ob.low + m.entry_ob.high) / 2.0 if m.entry_ob.low is not None and m.entry_ob.high is not None else None
        return None, None
    if isinstance(m, M3Result):
        return m.gap, m.entry_level
    return None, None


def compose(e: EConditionResult, m: ManeuverResult) -> Optional[SMCEntryCombinationResult]:
    """Composes exactly one (E, M) pair; returns None if the pair does not qualify."""
    if not e.eligible_for_confirmation:
        return None
    if m.state in _EXCLUDED_M_STATES:
        return None
    if e.direction is None or m.direction is None or e.direction != m.direction:
        return None

    maneuver = getattr(m, "maneuver", "")
    entry_array, entry_price = _entry_summary(m)

    return SMCEntryCombinationResult(
        combination=f"{e.entry_condition}{maneuver}",
        entry_condition=e.entry_condition, maneuver=maneuver,
        symbol=e.symbol or m.symbol, direction=e.direction,
        reference_timeframe=e.reference_timeframe, check_timeframe=e.check_timeframe,
        confirmation_timeframe=CONFIRMATION_TIMEFRAME, execution_timeframe=EXECUTION_TIMEFRAME,
        e_condition_state=EntryModelState.HTF_QUALIFIED.value, m_confirmation_state=m.state,
        entry_array=entry_array, entry_price=entry_price,
        invalidation=m.state if m.state in (EntryModelState.INVALIDATED.value, EntryModelState.EXPIRED.value) else None,
        invalidation_price=getattr(m, "invalidation_price", None),
        invalidation_source_type=getattr(m, "invalidation_source_type", None),
        invalidation_reason=getattr(m, "invalidation_reason", None),
        invalidation_trigger=getattr(m, "invalidation_trigger", None),
        state=m.state,
        evidence={"e_evidence": e.evidence, "m_evidence": getattr(m, "evidence", ())},
        missing_conditions=e.missing_conditions,
    )


def evaluate_entry_combinations(
    e_conditions: Sequence[EConditionResult], m_results: Sequence[ManeuverResult],
) -> Tuple[SMCEntryCombinationResult, ...]:
    """Cross-joins every supplied E-condition with every supplied M-result, keeping
    only pairs that pass `compose`'s gating. Deterministic: same inputs always produce
    the same output tuple, in (E, M) supplied order."""
    combinations = []
    for e in e_conditions:
        for m in m_results:
            result = compose(e, m)
            if result is not None:
                combinations.append(result)
    return tuple(combinations)
