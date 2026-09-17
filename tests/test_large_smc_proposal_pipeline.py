"""AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2, WP9: narrow tests for the new
large_smc_research_adapter (ST_LARGE_SMC_V1 -> CanonicalProposal). Exercises the
adapter directly against hand-built LargeSMCResearchDecision fixtures -- the engine
(LargeSMCResearchEngine) itself is unmodified and out of scope for this test file."""
from __future__ import annotations

from datetime import datetime, timezone

from large_smc_research.decision import LargeSMCResearchDecision
from proposal_envelope.adapters.large_smc_research_adapter import to_canonical_proposal
from proposal_envelope.formation_gate import apply_formation_gate
from proposal_envelope.models import (
    PLATFORM_STATE_WATCH_DETECTED,
    PROPOSAL_BLOCKED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_READY,
)
from proposal_envelope.strategy_authority import resolve_strategy_authority
from strategy_contract.market_snapshot import from_synthetic_candle
from strategy_engine.session.candles import Candle

STRATEGY_ID = "ST_LARGE_SMC_V1"
STRATEGY_VERSION = "1.0.7"


def _authority():
    return resolve_strategy_authority(STRATEGY_ID, STRATEGY_VERSION)


def _qualified_decision():
    return LargeSMCResearchDecision(
        strategy_version=STRATEGY_VERSION, symbol="EURUSD",
        evaluation_timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
        entry_condition="E1", maneuver="M1", combination="E1M1", direction="LONG",
        candidate_occurrence_id="OCC-1", entry_price=1.1000,
        structural_invalidation_price=1.0980, simulated_broker_stop=1.0985,
        target_price=1.1050, target_tier="PRIMARY_EXTERNAL_LIQUIDITY", target_type="LIQUIDITY_POOL",
        state="RESEARCH_QUALIFIED",
    )


def _watch_decision():
    return LargeSMCResearchDecision(
        strategy_version=STRATEGY_VERSION, symbol="EURUSD",
        evaluation_timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
        combination="E1M1", candidate_occurrence_id="OCC-2",
        state="WATCH", missing_conditions=("M1_ZONE_UNCONFIRMED",),
    )


# 12: incomplete geometry (WATCH) -> existing PROPOSAL_INCOMPLETE state, tagged
# WATCH_DETECTED at the evidence level -- never a fabricated CanonicalProposal, and
# never a new entry in the frozen PROPOSAL_STATES vocabulary.
def test_watch_state_produces_watch_detected_not_a_fabricated_proposal():
    envelope = to_canonical_proposal(_watch_decision(), _authority())
    assert envelope.proposal_state == PROPOSAL_INCOMPLETE
    assert envelope.setup_evidence["platform_state"] == PLATFORM_STATE_WATCH_DETECTED
    assert envelope.entry is None
    assert envelope.stop is None
    assert envelope.targets == ()


# 13: complete deterministic geometry (RESEARCH_QUALIFIED) -> PROPOSAL_READY, verbatim fields.
def test_research_qualified_maps_to_proposal_ready_verbatim():
    decision = _qualified_decision()
    envelope = to_canonical_proposal(decision, _authority())
    assert envelope.proposal_state == PROPOSAL_READY
    assert envelope.direction == decision.direction
    assert envelope.entry == decision.entry_price
    assert envelope.stop == decision.simulated_broker_stop
    assert envelope.targets == (decision.target_price,)
    assert envelope.demo_authorized is False
    assert envelope.live_authorized is False
    assert envelope.execution_eligible is False
    assert envelope.proposal_only is True
    # friction contract unsigned -- cost never fabricated as itemized
    assert envelope.cost_assumptions.status == "NOT_INCLUDED"


def test_qualified_still_blocked_by_formation_gate_without_real_snapshot():
    envelope = to_canonical_proposal(_qualified_decision(), _authority())
    gated = apply_formation_gate(envelope, market_snapshot=None)
    assert gated.proposal_state == PROPOSAL_BLOCKED


def test_qualified_blocked_by_synthetic_market_snapshot():
    envelope = to_canonical_proposal(_qualified_decision(), _authority())
    synthetic = from_synthetic_candle(
        "EURUSD", "M15", Candle(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), 1.1, 1.1, 1.1, 1.1),
    )
    gated = apply_formation_gate(envelope, market_snapshot=synthetic)
    assert gated.proposal_state == PROPOSAL_BLOCKED
