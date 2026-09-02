"""Post-READY pending-entry lifecycle for ST_LARGE_SMC_V1 (OUTCOME_LIFECYCLE_V1 phase).

Resolves the "pending-entry expiry" question (previously
`docs/status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`, `BLOCKED`) by
EXACT REUSE of `historical_replay.fill_simulator.simulate_fill` -- an already-existing,
already-tested module built for exactly this question, for exactly the same E/M
pipeline, that this project simply had not wired to ST_LARGE_SMC_V1 before. Its own
module docstring already states the finding this phase adopts: "ENTRY_EXPIRY =
UNDEFINED... no signed time-based expiry rule exists anywhere in entry_confirmation
today. This module does NOT invent one." A pending candidate is therefore terminal only
via FILLED or structural INVALIDATED_BEFORE_FILL; if the loaded data runs out first,
that is UNFILLED_AS_OF_DATA_END -- a data-boundary fact, never fabricated into a
strategy-level EXPIRED state. INTRABAR_AMBIGUOUS and NO_ENTRY_CONTRACT are the same
fail-closed states `fill_simulator` already defines; none are renamed here (project
convention: reuse existing state vocabulary, no unnecessary synonyms).

This module is deliberately NOT called from `engine.py`'s own `_evaluate_combination` --
keeping it a separate, additive post-processing step guarantees the existing,
already-verified funnel counts (`docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`)
cannot regress; `LargeSMCResearchDecision.state` remains `BLOCKED` (C10 is still
unsigned) regardless of what this module finds.

Scope boundary, deliberately preserved from `fill_simulator.py` itself: this resolves
PENDING_ENTRY -> FILLED / INVALIDATED_BEFORE_FILL / UNFILLED_AS_OF_DATA_END /
INTRABAR_AMBIGUOUS only. It does NOT resolve FILLED -> TARGET_HIT / STOP_HIT -- that
still requires C10 (broker stop distance), which remains genuinely unsigned (see
`docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`). Computing a
target-reached signal without a stop would silently assume no adverse excursion ever
mattered -- exactly the kind of optimistic bias this project's own statistical-caution
discipline prohibits -- so this module does not attempt it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from historical_replay.fill_simulator import (
    STATUS_FILLED,
    STATUS_INTRABAR_AMBIGUOUS,
    STATUS_INVALIDATED_BEFORE_FILL,
    STATUS_NO_ENTRY_CONTRACT,
    STATUS_UNFILLED_AS_OF_DATA_END,
    simulate_fill,
)
from strategy_engine.session import Candle

from .decision import LargeSMCResearchDecision

__all__ = [
    "STATUS_FILLED", "STATUS_INTRABAR_AMBIGUOUS", "STATUS_INVALIDATED_BEFORE_FILL",
    "STATUS_NO_ENTRY_CONTRACT", "STATUS_UNFILLED_AS_OF_DATA_END",
    "PendingEntryOutcome", "simulate_pending_entry",
]


@dataclass(frozen=True)
class PendingEntryOutcome:
    """Full occurrence-identity chain preserved end to end (candidate_occurrence_id is
    the authoritative key -- setup_family_id/eligibility_interval_id retained alongside
    it for traceability, never used alone to key this record)."""

    candidate_occurrence_id: Optional[str]
    setup_family_id: Optional[str]
    eligibility_interval_id: Optional[str]
    combination: Optional[str]
    direction: Optional[str]
    ready_time: Optional[datetime]

    status: str
    fill_time: Optional[datetime] = None
    fill_price: Optional[float] = None
    invalidation_time: Optional[datetime] = None
    note: str = ""


def simulate_pending_entry(
    decision: LargeSMCResearchDecision, forward_m5_candles: Sequence[Candle],
) -> PendingEntryOutcome:
    """`forward_m5_candles` must already be filtered to `time >= decision.
    evaluation_timestamp`, ascending -- the same precondition `simulate_fill` itself
    documents. Only meaningful for a `BLOCKED` decision that reached the
    entry-available (READY-equivalent) stage; callers should skip WATCH/NO_TRADE/
    INVALIDATED/EXPIRED/DATA_ERROR decisions (no entry array exists for those)."""
    result = simulate_fill(
        setup_id=decision.candidate_occurrence_id or "", combination=decision.combination,
        direction=decision.direction, ready_time=decision.evaluation_timestamp,
        entry_low=decision.entry_low, entry_high=decision.entry_high, entry_reference=decision.entry_price,
        invalidation_price=decision.structural_invalidation_price,
        forward_candles=forward_m5_candles,
    )
    return PendingEntryOutcome(
        candidate_occurrence_id=decision.candidate_occurrence_id, setup_family_id=decision.setup_family_id,
        eligibility_interval_id=decision.eligibility_interval_id, combination=decision.combination,
        direction=decision.direction, ready_time=decision.evaluation_timestamp,
        status=result.status, fill_time=result.fill_time, fill_price=result.fill_price,
        invalidation_time=result.invalidation_time, note=result.note,
    )
