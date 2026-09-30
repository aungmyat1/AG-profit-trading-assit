"""Structure-shift alignment primitive -- consumes market_structure.StructureResult
verbatim. Never re-detects swings/BOS/CHoCH; only checks whether the latest CHoCH
already reported by market_structure aligns with a caller-supplied candidate direction.

"Structure shift" is scoped to CHoCH specifically (SMC's own term for a change of
character), not BOS (continuation) -- matching the vocabulary the mission's own worked
examples use (BULLISH_CHOCH / bearish CHoCH). market_structure's BOS facts remain
available to a caller directly from StructureResult.latest_bos if a future primitive
wants them; this primitive does not fold BOS into "structure shift" on its own
authority.
"""
from __future__ import annotations

from typing import Optional

from market_structure import StructurePointKind, StructureResult

from .models import CandidateDirection, ConfirmationState, StructureAlignment

_BULLISH_KINDS = {StructurePointKind.BULLISH_CHOCH.value}
_BEARISH_KINDS = {StructurePointKind.BEARISH_CHOCH.value}


def evaluate_structure_alignment(
    structure_result: Optional[StructureResult],
    candidate_direction: CandidateDirection,
    reference_time=None,
) -> StructureAlignment:
    if structure_result is None:
        return StructureAlignment(
            status=ConfirmationState.UNAVAILABLE,
            candidate_direction=candidate_direction.value,
            reason="No structure_result supplied in EntryConfirmationRequest.",
        )

    if structure_result.status != "VALID":
        return StructureAlignment(
            status=ConfirmationState.INSUFFICIENT_DATA,
            candidate_direction=candidate_direction.value,
            reason=f"market_structure result not VALID (status={structure_result.status!r}, "
                   f"reason_codes={structure_result.reason_codes!r}).",
        )

    event = structure_result.latest_choch
    if event is None:
        return StructureAlignment(
            status=ConfirmationState.UNAVAILABLE,
            candidate_direction=candidate_direction.value,
            reason="market_structure reported no CHoCH -- no structural-shift event to evaluate.",
        )

    if candidate_direction == CandidateDirection.NONE:
        return StructureAlignment(
            status=ConfirmationState.INSUFFICIENT_DATA,
            candidate_direction=candidate_direction.value,
            event_kind=event.kind.value,
            event_time=event.time_utc,
            event_price=event.price,
            reason="candidate_direction is required to evaluate structure_shift alignment.",
        )

    if reference_time is not None and event.time_utc < reference_time:
        return StructureAlignment(
            status=ConfirmationState.FAIL,
            candidate_direction=candidate_direction.value,
            event_kind=event.kind.value,
            event_time=event.time_utc,
            event_price=event.price,
            reason="Latest CHoCH predates reference_time -- not relevant evidence for this setup.",
        )

    event_kind_value = event.kind.value
    if candidate_direction == CandidateDirection.LONG:
        aligned = event_kind_value in _BULLISH_KINDS
    else:  # SHORT
        aligned = event_kind_value in _BEARISH_KINDS

    return StructureAlignment(
        status=ConfirmationState.PASS if aligned else ConfirmationState.FAIL,
        candidate_direction=candidate_direction.value,
        event_kind=event_kind_value,
        event_time=event.time_utc,
        event_price=event.price,
        reason=None if aligned else f"Latest CHoCH ({event_kind_value}) does not match "
                                     f"candidate direction ({candidate_direction.value}).",
    )
