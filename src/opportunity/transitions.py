"""FunnelTransition and FunnelState (P12).

A FunnelTransition is a deterministic transition record. History is expected to
eventually live in a transition ledger (a later V2-2B deliverable, out of scope
here) -- OpportunityCandidate itself deliberately carries no growing history,
only `latest_transition_id`.

FunnelState is the small piece of prior state a strategy adapter's `observe()`
receives back each cycle (see adapter.py) -- current stage/outcome/revision plus
the raw strategy-owned state blob, never a full transition history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple

from .stages import validate_outcome, validate_stage


def _require_tz_aware(name: str, value: Optional[datetime]) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware, got naive datetime")


@dataclass(frozen=True)
class FunnelState:
    """Minimal previous-cycle state handed back into a strategy adapter."""

    stage: Optional[str] = None
    outcome: Optional[str] = None
    revision: int = 0
    raw_strategy_state: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stage is not None:
            validate_stage(self.stage)
        if self.outcome is not None:
            validate_outcome(self.outcome)
        if self.revision < 0:
            raise ValueError("revision must be >= 0")


@dataclass(frozen=True)
class FunnelTransition:
    transition_id: str
    candidate_id: str

    from_stage: Optional[str]
    from_outcome: Optional[str]

    to_stage: str
    to_outcome: str

    evaluated_at: datetime

    evidence_event_id: str

    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    raw_strategy_state: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.from_stage is not None:
            validate_stage(self.from_stage)
        if self.from_outcome is not None:
            validate_outcome(self.from_outcome)
        validate_stage(self.to_stage)
        validate_outcome(self.to_outcome)
        _require_tz_aware("evaluated_at", self.evaluated_at)
