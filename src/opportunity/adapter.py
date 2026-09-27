"""StrategyFunnelAdapter boundary (P19/P20).

Defines the protocol only -- no production strategy behavior is wired to it in
this mission. Proposal construction is deliberately NOT part of this interface:
that stays platform infrastructure (proposal_envelope.formation_gate), reached
only after ProposalEligibilityDecision says ELIGIBLE.

Import-boundary rule (statically checkable, see tests/test_opportunity_import_boundaries.py):
a StrategyFunnelAdapter implementation must not import execution.*, mt5.*, or any
order_send-capable module, must not mutate strategy_manager registry
authorization, must not call AI to make an authority decision, and must not
invent trade geometry or data lineage the strategy itself did not produce.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol

from .contracts import CandidateGeometry, MarketEvent
from .registry_binding import StrategyBinding
from .transitions import FunnelState


@dataclass(frozen=True)
class StrategyObservation:
    """What a strategy engine reports for one MarketEvent -- opaque
    `raw_strategy_state` plus the market_data_mode inherited from the event."""

    strategy_id: str
    event_id: str
    market_data_mode: str
    raw_strategy_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FunnelProjection:
    """The adapter's projection of a StrategyObservation onto the shared funnel
    vocabulary (stages.py) -- stage/outcome plus the reason codes and evidence
    that justify them. Never includes a proposal or execution decision."""

    stage: str
    outcome: str
    reason_codes: tuple = ()
    context_evidence: Mapping[str, Any] = field(default_factory=dict)
    setup_evidence: Mapping[str, Any] = field(default_factory=dict)
    trigger_evidence: Mapping[str, Any] = field(default_factory=dict)


class StrategyFunnelAdapter(Protocol):
    strategy_id: str
    strategy_version: str

    def supports(self, event: MarketEvent, binding: StrategyBinding) -> bool:
        ...

    def observe(self, event: MarketEvent, previous_state: FunnelState) -> StrategyObservation:
        ...

    def project(self, observation: StrategyObservation) -> FunnelProjection:
        ...

    def candidate_geometry(self, observation: StrategyObservation) -> Optional[CandidateGeometry]:
        ...
