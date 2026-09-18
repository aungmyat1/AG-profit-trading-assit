"""Focused tests for WP9 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): the read-only
GET /api/canonical-proposals[/{id}] routes. Uses FastAPI dependency_overrides
(matching tests/test_api.py's existing pattern) to inject a ProposalLedger over a
tmp_path, so no real ledger file or MT5 connection is touched.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app, get_proposal_ledger
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import CanonicalProposal, PROPOSAL_READY


def _ready(**overrides) -> CanonicalProposal:
    base = dict(
        proposal_envelope_id="FX:DECISION-1", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", symbol="EURUSD", market="FX", proposal_state=PROPOSAL_READY,
        direction="LONG", entry=1.0850, stop=1.0830, targets=(1.0900,),
    )
    base.update(overrides)
    return CanonicalProposal(**base)


def test_list_canonical_proposals_empty(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    try:
        response = TestClient(app).get("/api/canonical-proposals")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)


def test_list_and_get_canonical_proposal(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    try:
        client = TestClient(app)
        listing = client.get("/api/canonical-proposals")
        assert listing.status_code == 200
        body = listing.json()
        assert len(body) == 1
        assert body[0]["proposal_id"] == "FX:DECISION-1"
        assert body[0]["execution_authority"] == "NONE"
        assert body[0]["execution_eligible"] is False

        detail = client.get("/api/canonical-proposals/FX:DECISION-1")
        assert detail.status_code == 200
        assert detail.json()["entry"] == 1.0850
        assert detail.json()["symbol"] == "EURUSD"
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)


def test_get_unknown_canonical_proposal_is_404(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    try:
        response = TestClient(app).get("/api/canonical-proposals/FX:NOPE")
        assert response.status_code == 404
        assert response.json()["detail"]["reason_code"] == "CANONICAL_PROPOSAL_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)


def test_canonical_proposal_governance_fields_survive_restart(tmp_path):
    """WP12-D (AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2): the V1.2 additive
    governance fields (proposal_only/execution_eligible/demo_authorized/live_authorized/
    broker_mutation_blocked/lifecycle_stage/economic_edge_established) round-trip through
    JsonKeyValueStore serialization and are still correct after a simulated application
    restart (a fresh ProposalLedger instance over the same store path)."""
    path = str(tmp_path / "ledger.json")
    ledger = ProposalLedger(path=path)
    ledger.record_proposal(_ready(
        lifecycle_stage="OFFLINE_RESEARCH", demo_eligible=False, demo_authorized=False,
        live_authorized=False, economic_edge_established=False,
    ))
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    try:
        before = TestClient(app).get("/api/canonical-proposals").json()[0]
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)

    # Simulated restart: a brand-new ProposalLedger instance over the same JSON path --
    # no in-process state carried over, matching a real process restart.
    restarted_ledger = ProposalLedger(path=path)
    app.dependency_overrides[get_proposal_ledger] = lambda: restarted_ledger
    try:
        after = TestClient(app).get("/api/canonical-proposals").json()[0]
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)

    for field in (
        "strategy_id", "strategy_version", "proposal_state", "proposal_only",
        "execution_eligible", "demo_authorized", "live_authorized",
        "broker_mutation_blocked", "economic_edge_established", "lifecycle_stage",
    ):
        assert field in before, f"{field} missing from pre-restart response"
        assert before[field] == after[field], f"{field} changed across restart"

    assert after["proposal_only"] is True
    assert after["execution_eligible"] is False
    assert after["demo_authorized"] is False
    assert after["live_authorized"] is False
    assert after["broker_mutation_blocked"] is True
    assert after["economic_edge_established"] is False
    assert after["lifecycle_stage"] == "OFFLINE_RESEARCH"


def test_route_is_read_only_no_post_method(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    try:
        response = TestClient(app).post("/api/canonical-proposals", json={})
        assert response.status_code == 405  # method not allowed -- no write route exists
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)
