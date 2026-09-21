from datetime import datetime, timezone
from pathlib import Path

import pytest

from opportunity.contracts import OpportunityCandidate
from opportunity.candidate_store import CandidateConflictError, CandidateStore
from opportunity.stages import OUTCOME_ACTIVE, STAGE_SETUP_DETECTED, STAGE_TRIGGER_ARMED
from opportunity.transitions import FunnelTransition

T = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


def candidate(revision=1, stage=STAGE_SETUP_DETECTED, transition_id="t1"):
    return OpportunityCandidate(
        candidate_id="c1", occurrence_id="occ1", strategy_id="S", strategy_version="1.0.0",
        strategy_engine_version="1", symbol="EURUSD", market="FX", venue="demo", direction="LONG",
        detected_at=T, last_evaluated_at=T, expires_at=None, stage=stage, outcome=OUTCOME_ACTIVE,
        revision=revision, market_data_mode="REAL", latest_transition_id=transition_id,
    )


def transition(tid="t1", from_stage=None, to_stage=STAGE_SETUP_DETECTED):
    return FunnelTransition(
        transition_id=tid, candidate_id="c1", from_stage=from_stage, from_outcome=None if from_stage is None else OUTCOME_ACTIVE,
        to_stage=to_stage, to_outcome=OUTCOME_ACTIVE, evaluated_at=T, evidence_event_id=f"e-{tid}",
    )


def test_persist_and_restart_reconstructs_candidate_and_history(tmp_path: Path):
    path = str(tmp_path / "candidates.json")
    CandidateStore(path).persist(candidate(), transition())
    restarted = CandidateStore(path)
    assert restarted.get("c1") == candidate()
    assert restarted.transitions("c1") == (transition(),)


def test_exact_replay_is_idempotent(tmp_path: Path):
    store = CandidateStore(str(tmp_path / "candidates.json"))
    c, t = candidate(), transition()
    store.persist(c, t)
    store.persist(c, t)
    assert len(store.transitions("c1")) == 1


def test_revision_and_transition_append_atomically(tmp_path: Path):
    store = CandidateStore(str(tmp_path / "candidates.json"))
    store.persist(candidate(), transition())
    c2 = candidate(2, STAGE_TRIGGER_ARMED, "t2")
    t2 = transition("t2", STAGE_SETUP_DETECTED, STAGE_TRIGGER_ARMED)
    store.persist(c2, t2)
    assert store.get("c1") == c2
    assert [t.transition_id for t in store.transitions("c1")] == ["t1", "t2"]


def test_revision_gap_fails_closed(tmp_path: Path):
    store = CandidateStore(str(tmp_path / "candidates.json"))
    store.persist(candidate(), transition())
    with pytest.raises(CandidateConflictError):
        store.persist(candidate(3, STAGE_TRIGGER_ARMED, "t3"), transition("t3", STAGE_SETUP_DETECTED, STAGE_TRIGGER_ARMED))


def test_authority_change_fails_closed(tmp_path: Path):
    from dataclasses import replace
    store = CandidateStore(str(tmp_path / "candidates.json"))
    store.persist(candidate(), transition())
    changed = replace(candidate(2, STAGE_TRIGGER_ARMED, "t2"), strategy_id="OTHER")
    with pytest.raises(CandidateConflictError):
        store.persist(changed, transition("t2", STAGE_SETUP_DETECTED, STAGE_TRIGGER_ARMED))


def test_candidate_and_transition_identity_must_match(tmp_path: Path):
    from dataclasses import replace
    store = CandidateStore(str(tmp_path / "candidates.json"))
    with pytest.raises(CandidateConflictError):
        store.persist(candidate(), replace(transition(), candidate_id="other"))
