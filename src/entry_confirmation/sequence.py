"""Event-sequencing check -- does the confirming evidence belong to the same causal
setup sequence, or are structure_shift/liquidity_reclaim/displacement independently
true but temporally unrelated?

Boundary (owner-signed, see docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md):

    liquidity_time < structure_time <= displacement_time

structure_time == displacement_time is explicitly allowed: the structural break and
the displacement that causes it may be the same completed candle. structure_time
strictly before liquidity_time is never valid -- a structure shift cannot confirm a
liquidity event it predates.

Derived only -- never independently requestable. Only meaningful once structure_shift,
liquidity_reclaim, and displacement have all been requested; see engine.py.
"""
from __future__ import annotations

from .models import ConfirmationState, DisplacementEvidence, EventSequenceEvidence, LiquidityAlignment, StructureAlignment


def evaluate_event_sequence(
    liquidity_reclaim: LiquidityAlignment,
    structure_shift: StructureAlignment,
    displacement: DisplacementEvidence,
) -> EventSequenceEvidence:
    liquidity_time = liquidity_reclaim.reclaim_time
    structure_time = structure_shift.event_time
    displacement_time = displacement.candle_timestamp

    missing = [
        name for name, value in (
            ("liquidity_reclaim.reclaim_time", liquidity_time),
            ("structure_shift.event_time", structure_time),
            ("displacement.candle_timestamp", displacement_time),
        ) if value is None
    ]
    if missing:
        return EventSequenceEvidence(
            status=ConfirmationState.INSUFFICIENT_DATA,
            liquidity_time=liquidity_time, structure_time=structure_time, displacement_time=displacement_time,
            reason=f"Missing timestamp(s) for sequencing: {', '.join(missing)}.",
        )

    ordered = liquidity_time < structure_time <= displacement_time
    return EventSequenceEvidence(
        status=ConfirmationState.PASS if ordered else ConfirmationState.FAIL,
        liquidity_time=liquidity_time, structure_time=structure_time, displacement_time=displacement_time,
        reason=None if ordered else "Evidence out of causal order -- expected "
                                     "liquidity_time < structure_time <= displacement_time.",
    )
