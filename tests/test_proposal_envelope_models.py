"""Contract tests for proposal_envelope.models: the three independent dimensions, the
enum vocabularies (frozen verbatim from BEST_MONEY_MAKING_PATHS_AND_TICKET_DELIVERY_
ACTION_PLAN_V1.md's "Watcher state, proposal state, and authorization are orthogonal"
section), and the single BLOCKED escape hatch for a missing required field.
"""
from __future__ import annotations

from proposal_envelope.models import (
    AUTHORITY_DEMO_AUTHORIZED,
    AUTHORITY_DEMO_ELIGIBLE,
    AUTHORITY_LIVE_AUTHORIZED,
    AUTHORITY_NONE,
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    EXECUTION_AUTHORITIES,
    PROPOSAL_BLOCKED,
    PROPOSAL_EXPIRED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_INVALIDATED,
    PROPOSAL_NOT_EVALUATED,
    PROPOSAL_NO_TRADE,
    PROPOSAL_READY,
    PROPOSAL_STATES,
    PROPOSAL_STRATEGY_UNMATCHED,
    SCHEMA_VERSION,
    WATCHER_CONTEXT_IDENTIFIED,
    WATCHER_DATA_BLOCKED,
    WATCHER_EXPIRED,
    WATCHER_INVALIDATED,
    WATCHER_LIQUIDITY_APPROACH,
    WATCHER_LIQUIDITY_SWEPT,
    WATCHER_POI_APPROACH,
    WATCHER_SCANNING,
    WATCHER_STATES,
    WATCHER_STRUCTURE_CONFIRMING,
    WATCHER_SETUP_QUALIFIED,
    WatcherOccurrenceTimestamps,
    blocked_envelope,
)


def test_schema_version_is_frozen():
    assert SCHEMA_VERSION == "AG_CANONICAL_PROPOSAL_V1"
    assert CanonicalProposal().schema_version == SCHEMA_VERSION


def test_watcher_states_match_source_plan_vocabulary_exactly():
    assert WATCHER_STATES == {
        WATCHER_SCANNING, WATCHER_CONTEXT_IDENTIFIED, WATCHER_LIQUIDITY_APPROACH,
        WATCHER_POI_APPROACH, WATCHER_LIQUIDITY_SWEPT, WATCHER_STRUCTURE_CONFIRMING,
        WATCHER_SETUP_QUALIFIED, WATCHER_INVALIDATED, WATCHER_EXPIRED, WATCHER_DATA_BLOCKED,
    }


def test_proposal_states_match_source_plan_vocabulary_exactly():
    assert PROPOSAL_STATES == {
        PROPOSAL_NOT_EVALUATED, PROPOSAL_NO_TRADE, PROPOSAL_INCOMPLETE, PROPOSAL_STRATEGY_UNMATCHED,
        PROPOSAL_READY, PROPOSAL_INVALIDATED, PROPOSAL_EXPIRED, PROPOSAL_BLOCKED,
    }


def test_execution_authorities_match_source_plan_vocabulary_exactly():
    assert EXECUTION_AUTHORITIES == {
        AUTHORITY_NONE, AUTHORITY_DEMO_ELIGIBLE, AUTHORITY_DEMO_AUTHORIZED, AUTHORITY_LIVE_AUTHORIZED,
    }


def test_three_dimensions_are_independent_fields_not_one_enum():
    # The exact scenario the source plan calls out by name: SETUP_QUALIFIED research
    # evidence with no compatible strategy, and NONE execution authority, coexisting.
    envelope = CanonicalProposal(
        watcher_state=WATCHER_SETUP_QUALIFIED,
        proposal_state=PROPOSAL_STRATEGY_UNMATCHED,
        execution_authority=AUTHORITY_NONE,
    )
    assert envelope.watcher_state == WATCHER_SETUP_QUALIFIED
    assert envelope.proposal_state == PROPOSAL_STRATEGY_UNMATCHED
    assert envelope.execution_authority == AUTHORITY_NONE

    # And the other named scenario: PROPOSAL_READY together with execution_authority NONE.
    ready_but_unauthorized = CanonicalProposal(
        proposal_state=PROPOSAL_READY, execution_authority=AUTHORITY_NONE,
    )
    assert ready_but_unauthorized.proposal_state == PROPOSAL_READY
    assert ready_but_unauthorized.execution_authority == AUTHORITY_NONE


def test_blocked_envelope_is_the_only_missing_field_escape_hatch():
    envelope = blocked_envelope(
        source_module="test.fixture", source_record_id="X1", symbol="EURUSD",
        strategy_id="ST_TEST", strategy_version="1.0.0", reasons=("MISSING_STOP_LOSS",),
    )
    assert envelope.proposal_state == PROPOSAL_BLOCKED
    assert envelope.reasons == ("MISSING_STOP_LOSS",)
    assert envelope.source_module == "test.fixture"
    assert envelope.source_record_id == "X1"


def test_cost_assumptions_default_is_not_included_never_silently_zero():
    costs = CostAssumptions()
    assert costs.status == "NOT_INCLUDED"
    assert costs.spread is None
    assert costs.commission is None
    assert costs.slippage is None
    assert costs.swap_or_funding is None


def test_watcher_occurrence_timestamp_fields_present_and_optional_by_default():
    ts = WatcherOccurrenceTimestamps()
    for f in ("detected_at", "state_entered_at", "last_evaluated_at",
              "evidence_candle_close", "expires_at"):
        assert getattr(ts, f) is None
    assert ts.evidence_complete == ()
    assert ts.next_required_evidence == ()


def test_data_provenance_defaults_never_claim_complete_candle_evidence():
    provenance = DataProvenance()
    assert provenance.complete_candle_evidence is False


def test_envelope_is_frozen_immutable():
    envelope = CanonicalProposal()
    try:
        envelope.proposal_state = PROPOSAL_READY  # type: ignore[misc]
        assert False, "CanonicalProposal must be frozen/immutable"
    except AttributeError:
        pass
