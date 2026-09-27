from datetime import datetime, timezone
from pathlib import Path

import pytest

from opportunity.contracts import CandidateGeometry, OpportunityCandidate
from opportunity.candidate_store import CandidateConflictError, CandidateStore
from opportunity.stages import OUTCOME_ACTIVE, STAGE_SETUP_DETECTED, STAGE_TRIGGER_ARMED
from opportunity.transitions import FunnelTransition
from runtime_state.store import StateStoreCorrupted

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


def _candidate_with_evidence() -> OpportunityCandidate:
    return OpportunityCandidate(
        candidate_id="c1", occurrence_id="occ1", strategy_id="S", strategy_version="1.0.0",
        strategy_engine_version="1", symbol="EURUSD", market="FX", venue="demo", direction="LONG",
        detected_at=T, last_evaluated_at=T, expires_at=T, stage=STAGE_SETUP_DETECTED,
        outcome=OUTCOME_ACTIVE, revision=1,
        raw_strategy_state={"phase": "SETUP", "sweep": {"level": 1.2345, "swept": True}},
        context_evidence={"session": "LONDON", "bias": "BULLISH"},
        setup_evidence={"order_block": [1.201, 1.203]},
        trigger_evidence={"displacement": True, "confirmations": ["FVG", "BOS"]},
        geometry=CandidateGeometry(
            direction="LONG", entry=1.2050, invalidation=1.1990,
            targets=(1.2100, 1.2150, 1.2200), estimated_rr=2.5,
        ),
        market_data_mode="REAL", data_lineage="snapshot-fingerprint-abc123",
        latest_transition_id="t1",
    )


def test_geometry_and_evidence_round_trip_through_restart(tmp_path: Path):
    path = str(tmp_path / "candidates.json")
    original = _candidate_with_evidence()
    CandidateStore(path).persist(original, transition())

    restarted = CandidateStore(path)
    reconstructed = restarted.get("c1")

    assert reconstructed == original
    # Explicit checks on the fields most at risk of silent tuple/list drift or
    # nested-mapping loss across a JSON round-trip.
    assert reconstructed.geometry.targets == (1.2100, 1.2150, 1.2200)
    assert isinstance(reconstructed.geometry.targets, tuple)
    assert reconstructed.raw_strategy_state == original.raw_strategy_state
    assert reconstructed.context_evidence == original.context_evidence
    assert reconstructed.setup_evidence == original.setup_evidence
    assert reconstructed.trigger_evidence == original.trigger_evidence
    assert reconstructed.data_lineage == "snapshot-fingerprint-abc123"
    assert reconstructed.expires_at == T
    assert reconstructed.expires_at.tzinfo is not None


def test_corrupted_store_fails_closed_not_empty(tmp_path: Path):
    path = tmp_path / "candidates.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = CandidateStore(str(path))

    with pytest.raises(StateStoreCorrupted):
        store.get("c1")

    with pytest.raises(StateStoreCorrupted):
        store.persist(candidate(), transition())


def test_corrupted_store_non_dict_json_fails_closed(tmp_path: Path):
    path = tmp_path / "candidates.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    store = CandidateStore(str(path))

    with pytest.raises(StateStoreCorrupted):
        store.all_candidates()
