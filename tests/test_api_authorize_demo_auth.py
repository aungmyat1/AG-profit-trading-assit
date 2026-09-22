"""PANEL-R5A-R1: the authenticated-owner boundary in front of
POST /api/tickets/{approval_id}/authorize-demo.

This route is the pre-existing, separate execution pathway flagged as a known gap in
docs/status/AG_PANEL_R5A_OWNER_AUTH_STATUS.md: it is closer to an actual broker call
than owner-decision (its execution_handler resolves to the real MT5 execution handler
in production) and, until this change, had no equivalent auth boundary.

These tests exercise api.app.require_owner_auth for real -- unlike
tests/test_api.py, which overrides it (those tests are about
authorize_demo_execution()'s own semantics, not this boundary). The execution
handler itself is always a mock/fake here; no test in this file can reach a
real MT5/broker call.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import (
    OWNER_API_KEY_ENV,
    OWNER_AUTH_HEADER,
    app,
    get_execution_handler,
    get_proposal_registry,
    get_store,
    require_owner_auth,
)
from api.execution_service import InMemoryProposalRegistry
from authorization.models import VENUE_MT5
from authorization.store import ExecutionApprovalStore
from authorization.telegram_gateway import ExecutionHandlerResult
from execution.adapter import TradeProposal


def _proposal(**overrides) -> TradeProposal:
    base = dict(
        setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-08",
        strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol="GBPUSD", profile_id="FOREX",
        direction="SHORT", entry=1.34942, stop_loss=1.35026, tp1=1.34798, tp2=1.34522,
        volume=0.05, risk_amount=4.2, risk_percent=0.5,
    )
    base.update(overrides)
    return TradeProposal(**base)


def _client(tmp_path, *, handler_calls=None):
    """Never overrides require_owner_auth -- the real dependency is exercised.
    handler_calls, if given, is appended to on every execution_handler invocation, so
    tests can assert zero calls on an auth failure."""
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    registry = InMemoryProposalRegistry()

    def fake_handler(proposal):
        if handler_calls is not None:
            handler_calls.append(proposal)
        return ExecutionHandlerResult(success=True, result_reference="999999", detail="EXECUTED ticket=999999")

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_proposal_registry] = lambda: registry
    app.dependency_overrides[get_execution_handler] = lambda: fake_handler
    return TestClient(app), store, registry


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_store, None)
    app.dependency_overrides.pop(get_proposal_registry, None)
    app.dependency_overrides.pop(get_execution_handler, None)
    # require_owner_auth deliberately never touched here -- real dependency under test.


def _seed_ready_approval(store, registry):
    proposal = _proposal()
    approval = store.create(proposal, venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    registry.register(proposal)
    return approval


def _authorize(client, approval_id, **headers):
    return client.post(
        f"/api/tickets/{approval_id}/authorize-demo",
        json={"action": "EXECUTE_DEMO"},
        headers=headers,
    )


# --------------------------------------------------------------------------- 1
def test_unset_owner_key_rejects_closed_not_open(tmp_path, monkeypatch):
    monkeypatch.delenv(OWNER_API_KEY_ENV, raising=False)
    calls: list = []
    client, store, registry = _client(tmp_path, handler_calls=calls)
    try:
        approval = _seed_ready_approval(store, registry)
        response = _authorize(client, approval.approval_id, **{OWNER_AUTH_HEADER: "anything"})
        assert response.status_code == 503
        assert response.json()["detail"]["reason_code"] == "OWNER_AUTH_NOT_CONFIGURED"
        assert calls == []  # execution handler never invoked
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 2
def test_missing_header_rejected_handler_not_called(tmp_path, monkeypatch):
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    calls: list = []
    client, store, registry = _client(tmp_path, handler_calls=calls)
    try:
        approval = _seed_ready_approval(store, registry)
        response = _authorize(client, approval.approval_id)
        assert response.status_code == 401
        assert response.json()["detail"]["reason_code"] == "OWNER_AUTH_REJECTED"
        assert calls == []
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 3
def test_wrong_header_rejected_handler_not_called(tmp_path, monkeypatch):
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    calls: list = []
    client, store, registry = _client(tmp_path, handler_calls=calls)
    try:
        approval = _seed_ready_approval(store, registry)
        response = _authorize(client, approval.approval_id, **{OWNER_AUTH_HEADER: "wrong-key"})
        assert response.status_code == 401
        assert calls == []
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 4
def test_valid_header_reaches_existing_authorize_demo_semantics(tmp_path, monkeypatch):
    """Authentication success must not itself execute anything -- it only permits the
    request to reach the pre-existing checks, which for this seeded, demo-authorized-
    mocked approval succeed exactly as they did before this change."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    monkeypatch.setattr(
        "api.execution_service.check_strategy_demo_authorized",
        lambda strategy_id, registry_path=None: __import__(
            "authorization.models", fromlist=["AuthorizationCheckResult"]
        ).AuthorizationCheckResult(True),
    )
    calls: list = []
    client, store, registry = _client(tmp_path, handler_calls=calls)
    try:
        approval = _seed_ready_approval(store, registry)
        response = _authorize(client, approval.approval_id, **{OWNER_AUTH_HEADER: "correct-owner-key"})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["state"] == "EXECUTED"
        assert len(calls) == 1  # handler invoked exactly once, only after auth passed
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 5 / 6
def test_failed_auth_produces_zero_handler_and_broker_calls(tmp_path, monkeypatch):
    """Combines the P6 #5/#6 assertions: zero execution_handler calls (the only path
    to a broker call this module has) on either a missing or a wrong header."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    calls: list = []
    client, store, registry = _client(tmp_path, handler_calls=calls)
    try:
        approval = _seed_ready_approval(store, registry)
        _authorize(client, approval.approval_id)
        _authorize(client, approval.approval_id, **{OWNER_AUTH_HEADER: "wrong-key"})
        assert calls == []
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 7
def test_valid_auth_alone_does_not_bypass_user_confirmation(tmp_path, monkeypatch):
    """The explicit action=="EXECUTE_DEMO" body field is this route's own existing
    confirmation mechanism (preserved, unmodified). A valid owner-auth header with a
    different/missing action must still be rejected before the execution handler runs
    -- auth success is not itself the confirmation."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    calls: list = []
    client, store, registry = _client(tmp_path, handler_calls=calls)
    try:
        approval = _seed_ready_approval(store, registry)
        response = client.post(
            f"/api/tickets/{approval.approval_id}/authorize-demo",
            json={"action": "NOT_A_REAL_CONFIRMATION"},
            headers={OWNER_AUTH_HEADER: "correct-owner-key"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["reason_code"] == "UNSUPPORTED_ACTION"
        assert calls == []
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 8
def test_valid_auth_alone_does_not_bypass_demo_authority_guard(tmp_path, monkeypatch):
    """No monkeypatch of check_strategy_demo_authorized here: ST_ASIAN_SWEEP_5R_V1 is
    demo_authorized: false in the real, current strategies/registry.yaml. A valid
    owner-auth header must not change that outcome -- auth and Demo authority are
    separate gates."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    calls: list = []
    client, store, registry = _client(tmp_path, handler_calls=calls)
    try:
        approval = _seed_ready_approval(store, registry)
        response = _authorize(client, approval.approval_id, **{OWNER_AUTH_HEADER: "correct-owner-key"})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["reason_code"] == "BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED"
        assert calls == []
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 9
def test_owner_decision_route_remains_authenticated(tmp_path, monkeypatch):
    """The R5A route this package reuses auth from must still be gated -- proves this
    change did not accidentally weaken or remove that dependency."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    from api.app import get_owner_decision_store, get_proposal_ledger
    from owner_decision.bridge import OwnerDecisionStore
    from proposal_envelope.ledger import ProposalLedger
    from proposal_envelope.models import CanonicalProposal, PROPOSAL_READY

    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(CanonicalProposal(
        proposal_envelope_id="FX:R5A-R1-CHECK-1", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", market="FX", venue="VANTAGE_DEMO_MT5", symbol="EURUSD",
        proposal_state=PROPOSAL_READY, direction="BUY", entry=1.1000, stop=1.0950,
        targets=(1.1100,), demo_authorized=True, broker_mutation_blocked=False,
    ))
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    app.dependency_overrides[get_owner_decision_store] = lambda: OwnerDecisionStore()
    try:
        response = app_client = TestClient(app)
        resp = app_client.post(
            "/api/canonical-proposals/FX:R5A-R1-CHECK-1/owner-decision",
            json={"decision_id": "dec-r5a-r1-1", "action": "APPROVE_DEMO", "symbol": "EURUSD"},
        )
        assert resp.status_code in (401, 503)
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)
        app.dependency_overrides.pop(get_owner_decision_store, None)


# --------------------------------------------------------------------------- 10
def test_get_routes_remain_unauthenticated(tmp_path, monkeypatch):
    """No GET route acquires an auth requirement from this change. /api/tickets is a
    GET list route on the same store this package's POST route also uses."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        response = client.get("/api/tickets")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_store, None)
