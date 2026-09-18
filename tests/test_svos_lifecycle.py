"""Tests for svos.lifecycle -- reconciliation + transition guard (P2)."""
from __future__ import annotations

import pytest

from svos import authority, lifecycle
from svos.lifecycle import evaluate_transition, gate_for_state


def test_every_mission_state_reconciles_without_new_label():
    # No mission state may require inventing a new authoritative lifecycle label.
    for state in lifecycle.MISSION_STATE_TO_GATE:
        assert authority.reconcile_requires_new_lifecycle_label(state) is False


def test_unknown_state_requires_adjudication():
    with pytest.raises(authority.ArchitecturalAdjudicationRequired):
        authority.assert_reconcilable("SOME_NEW_INVENTED_STAGE")


def test_state_to_gate_mapping():
    assert gate_for_state("BASELINE_BACKTESTED") == ("G2", "PASS")
    assert gate_for_state("ECONOMIC_GATE_FAIL") == ("G3", "FAIL")
    assert gate_for_state("DEMO_ELIGIBLE") == ("G9", "PASS")
    assert gate_for_state("CANDIDATE_FROZEN") is None


def test_transition_requires_contiguous_prefix():
    # G2 requested but G0/G1 not PASS -> blocked.
    decision = evaluate_transition(
        requested_gate="G2",
        gate_results={"G0": "PASS"},
        evidence_refs={"G0": ("ref",)},
    )
    assert not decision.allowed
    assert any("G1" in b for b in decision.blockers)


def test_transition_requires_evidence():
    decision = evaluate_transition(
        requested_gate="G2",
        gate_results={"G0": "PASS", "G1": "PASS"},
        evidence_refs={"G0": ("ref",)},  # G1 has no evidence refs
    )
    assert not decision.allowed
    assert any("G1" in b for b in decision.blockers)


def test_transition_allowed_with_evidence_and_frozen_candidate():
    decision = evaluate_transition(
        requested_gate="G5",
        gate_results={"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS"},
        evidence_refs={"G0": ("r",), "G1": ("r",), "G2": ("r",), "G3": ("r",), "G4": ("r",)},
        candidate_frozen=True,
    )
    assert decision.allowed


def test_robustness_requires_frozen_candidate():
    decision = evaluate_transition(
        requested_gate="G5",
        gate_results={"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS"},
        evidence_refs={"G0": ("r",), "G1": ("r",), "G2": ("r",), "G3": ("r",), "G4": ("r",)},
        candidate_frozen=False,
    )
    assert not decision.allowed
    assert "CANDIDATE_NOT_FROZEN" in decision.blockers


def test_holdout_one_shot():
    base = {"G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS"}
    refs = {g: ("r",) for g in base}
    first = evaluate_transition(requested_gate="G6", gate_results=base, evidence_refs=refs,
                                candidate_frozen=True, holdout_used=False)
    assert first.allowed
    second = evaluate_transition(requested_gate="G6", gate_results=base, evidence_refs=refs,
                                 candidate_frozen=True, holdout_used=True)
    assert not second.allowed
    assert "HOLDOUT_ONE_SHOT_ALREADY_USED" in second.blockers


def test_unknown_gate_rejected():
    with pytest.raises(ValueError):
        evaluate_transition(requested_gate="G99", gate_results={}, evidence_refs={})
