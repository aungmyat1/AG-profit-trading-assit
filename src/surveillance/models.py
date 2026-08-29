"""SMC_SURVEILLANCE_V1 -- state tracking + transition events over an already-produced
SMC_CONDITIONAL_ENTRY_V2 analysis (spec sections 26-29, 57-58). Consumes
`entry_confirmation.SMCConditionalEntryAnalysis` (from
daytrading_runtime.conditional_entry_snapshot) verbatim -- never re-derives E1/E2/E3/
M1/M2/M3/composer state itself. This module only adds: (a) persistence of the last-seen
state per symbol, (b) a diff against that prior state to emit transition events, and (c)
compact/detailed formatting for reporting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

SMC_SURVEILLANCE_V1 = "SMC_SURVEILLANCE_V1"


@dataclass(frozen=True)
class SurveillanceEvent:
    event_type: str  # see EVENT_TYPES below
    symbol: str
    snapshot_time: Optional[str]  # ISO string -- matches persisted record's own timestamp shape
    detail: Dict[str, object] = field(default_factory=dict)


# Event taxonomy (spec section 28). Not every listed event is emitted by this pass --
# only the ones this module can derive HONESTLY from fields SMC_CONDITIONAL_ENTRY_V2
# already exposes (EConditionResult.touch_status/reaction_status, M*Result.state,
# SMCEntryCombinationResult.state). No new detector backs any of these; they are pure
# state-diff labels over already-signed EntryModelState values.
EVENT_CONTEXT_QUALIFIED = "CONTEXT_QUALIFIED"           # E: WAITING_HTF_TOUCH -> touched
EVENT_REFERENCE_TOUCHED = "REFERENCE_TOUCHED"           # E.touch_status left WAITING_HTF_TOUCH
EVENT_H1_REACTION_CONFIRMED = "H1_REACTION_CONFIRMED"   # E.reaction_status reached HTF_QUALIFIED
EVENT_M_CONFIRMATION_DEVELOPING = "M_CONFIRMATION_DEVELOPING"  # M.state reached WAITING_M5_ENTRY
EVENT_ENTRY_READY = "ENTRY_READY"                       # combination.state reached READY
EVENT_SETUP_INVALIDATED = "SETUP_INVALIDATED"           # M.state or combination.state reached INVALIDATED
EVENT_SETUP_EXPIRED = "SETUP_EXPIRED"                   # M.state or combination.state reached EXPIRED

EVENT_TYPES: Tuple[str, ...] = (
    EVENT_CONTEXT_QUALIFIED, EVENT_REFERENCE_TOUCHED, EVENT_H1_REACTION_CONFIRMED,
    EVENT_M_CONFIRMATION_DEVELOPING, EVENT_ENTRY_READY, EVENT_SETUP_INVALIDATED, EVENT_SETUP_EXPIRED,
)

MAX_HISTORY_ENTRIES = 50  # bounded, per spec section 46 ("avoid storing enormous duplicated snapshots")


@dataclass(frozen=True)
class SurveillanceUpdate:
    """One poll's result: the freshly persisted record plus whatever transition events
    fired THIS poll (empty on an unchanged/duplicate poll -- spec section 58)."""

    symbol: str
    record: Dict[str, object]
    events: Tuple[SurveillanceEvent, ...] = field(default_factory=tuple)
