"""Tests for svos.candidate -- candidate freeze + fingerprint immutability (P7)."""
from __future__ import annotations

from svos.candidate import CandidateFreeze, compute_candidate_fingerprint, freeze_candidate


def _freeze(**overrides) -> CandidateFreeze:
    base = dict(
        strategy_id="ST_TEST_V1", version="1.0.0", code_config_hash="cc1",
        dataset_role="DEVELOPMENT", parameters={"stop_buffer": 1.5},
        friction_contract="FR1", session_contract="SC1",
        decision_tf="M15", execution_tf="M5", risk_contract="RC1",
    )
    base.update(overrides)
    return CandidateFreeze(**base)


def test_fingerprint_is_deterministic():
    assert compute_candidate_fingerprint(_freeze()) == compute_candidate_fingerprint(_freeze())


def test_any_semantic_change_changes_fingerprint():
    a = _freeze()
    for kwargs in (
        {"version": "1.0.1"},
        {"parameters": {"stop_buffer": 2.0}},
        {"code_config_hash": "cc2"},
        {"dataset_role": "HOLDOUT"},
        {"friction_contract": "FR2"},
        {"execution_tf": "M15"},
    ):
        assert compute_candidate_fingerprint(_freeze(**kwargs)) != compute_candidate_fingerprint(a)


def test_freeze_binds_fingerprint_and_verifies():
    frozen = freeze_candidate(_freeze())
    assert frozen.fingerprint
    assert frozen.verify()
    assert frozen.candidate_id.startswith("ST_TEST_V1@1.0.0:")
