"""Tests for proposals: READY -> proposal, WAITING/direction-mismatch/invalidated/missing
-> no proposal (fail-closed), evidence traces back to the combination it came from.
"""
from __future__ import annotations

import datetime as dt

import pytest

from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from entry_confirmation.m1_character_change_inducement import M1Result
from proposals import STATUS_ENTRY_CANDIDATE_READY, explain, generate_proposals

UTC = dt.timezone.utc


def _analysis(combinations, m1_results=()):
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        e_conditions={"E2": EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT")},
        m_maneuvers={"M1": m1_results, "M2": (), "M3": ()},
        combinations=combinations,
    )


def _ready_combo(direction="SHORT"):
    return SMCEntryCombinationResult(
        combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD", direction=direction,
        reference_timeframe="H1", check_timeframe="H1", confirmation_timeframe="M5", execution_timeframe="M5",
        entry_array="ORDER_BLOCK", entry_price=1.1000, state="READY",
        evidence={"e_evidence": {"poi": "H1_OB"}, "m_evidence": ()},
    )


def _ready_m1(direction="SHORT"):
    return M1Result(symbol="EURUSD", entry_condition="E2", direction=direction, state="READY",
                     entry_array_low=1.0990, entry_array_high=1.1010)


# --------------------------------------------------------------------------- READY -> proposal

def test_ready_combination_produces_proposal():
    analysis = _analysis((_ready_combo(),), (_ready_m1(),))
    proposals = generate_proposals(analysis)
    assert len(proposals) == 1
    p = proposals[0]
    assert p.combination == "E2M1"
    assert p.direction == "SHORT"
    assert p.status == STATUS_ENTRY_CANDIDATE_READY
    assert p.entry_low == pytest.approx(1.0990)
    assert p.entry_high == pytest.approx(1.1010)
    assert p.evidence["e_evidence"] == {"poi": "H1_OB"}


def test_multiple_ready_combinations_all_returned_unranked():
    combo1 = _ready_combo()
    combo2 = SMCEntryCombinationResult(combination="E2M2", entry_condition="E2", maneuver="M2", symbol="EURUSD",
                                        direction="SHORT", state="READY", entry_price=1.1005)
    analysis = _analysis((combo1, combo2), (_ready_m1(),))
    proposals = generate_proposals(analysis)
    assert {p.combination for p in proposals} == {"E2M1", "E2M2"}


# --------------------------------------------------------------------------- fail-closed cases

@pytest.mark.parametrize("state", ["WAITING_M5_CONFIRMATION", "WAITING_M5_ENTRY", "NOT_APPLICABLE",
                                    "NO_VALID_COMBINATION", "SCANNING_CONTEXT"])
def test_non_ready_state_produces_no_proposal(state):
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD",
                                       direction="SHORT", state=state)
    analysis = _analysis((combo,))
    assert generate_proposals(analysis) == ()


def test_invalidated_combination_produces_no_proposal():
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD",
                                       direction="SHORT", state="INVALIDATED", invalidation="INVALIDATED")
    analysis = _analysis((combo,))
    assert generate_proposals(analysis) == ()


def test_no_combinations_produces_no_proposal():
    analysis = _analysis(())
    assert generate_proposals(analysis) == ()


def test_missing_matching_m_result_still_produces_proposal_without_range():
    """The composer already decided READY -- a proposal is emitted even if this module
    can't find the underlying M-result object (defensive only; should not happen in
    practice since the composer only marks READY off an M-result it was given), it just
    can't report an entry_low/entry_high range."""
    analysis = _analysis((_ready_combo(),), m1_results=())
    proposals = generate_proposals(analysis)
    assert len(proposals) == 1
    assert proposals[0].entry_low is None and proposals[0].entry_high is None
    assert proposals[0].entry_reference == pytest.approx(1.1000)


# --------------------------------------------------------------------------- determinism

def test_proposal_id_deterministic_for_same_snapshot():
    analysis = _analysis((_ready_combo(),), (_ready_m1(),))
    p1 = generate_proposals(analysis)[0]
    p2 = generate_proposals(analysis)[0]
    assert p1.proposal_id == p2.proposal_id


# --------------------------------------------------------------------------- explanation

def test_explain_never_invents_narrative_only_states_fields():
    analysis = _analysis((_ready_combo(),), (_ready_m1(),))
    proposal = generate_proposals(analysis)[0]
    text = explain(proposal)
    assert "EURUSD SHORT PROPOSAL" in text
    assert "E2M1" in text
    assert "1.09900" in text and "1.10100" in text
    assert "STATUS" in text and STATUS_ENTRY_CANDIDATE_READY in text
