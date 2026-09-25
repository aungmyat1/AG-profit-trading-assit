"""PANEL-R5A: the authenticated-owner boundary in front of
POST /api/canonical-proposals/{proposal_id}/owner-decision.

The R4 independent audit (docs/status/AG_PANEL_R4_INDEPENDENT_AUDIT_STATUS.md) found
this route had no authentication boundary and named it as a prerequisite before any
broker-side-effect (R5B+) work. These tests exercise api.app.require_owner_auth for
real -- unlike tests/test_api_owner_decision.py, which overrides it (those tests are
about evaluate_owner_decision()'s own semantics, not this boundary).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import (
    OWNER_API_KEY_ENV,
    OWNER_AUTH_HEADER,
    app,
    get_owner_decision_store,
    get_proposal_ledger,
    require_owner_auth,
)
from owner_decision.bridge import OwnerDecisionStore
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import CanonicalProposal, PROPOSAL_READY


def _ready(**overrides) -> CanonicalProposal:
    base = dict(
        proposal_envelope_id="FX:R5A-AUTH-1", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", market="FX", venue="VANTAGE_DEMO_MT5", symbol="EURUSD",
        proposal_state=PROPOSAL_READY, direction="BUY", entry=1.1000, stop=1.0950,
        targets=(1.1100,), demo_authorized=True, broker_mutation_blocked=False,
    )
    base.update(overrides)
    return CanonicalProposal(**base)


def _client(tmp_path, ledger: ProposalLedger | None = None) -> TestClient:
    ledger = ledger or ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    app.dependency_overrides[get_owner_decision_store] = lambda: OwnerDecisionStore()
    return TestClient(app)


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_proposal_ledger, None)
    app.dependency_overrides.pop(get_owner_decision_store, None)
    # require_owner_auth is deliberately never put in dependency_overrides here --
    # these tests exercise the real dependency, gated only via monkeypatch.setenv.


def _post(client: TestClient, **headers):
    return client.post(
        "/api/canonical-proposals/FX:R5A-AUTH-1/owner-decision",
        json={"decision_id": "dec-r5a-1", "action": "APPROVE_DEMO", "symbol": "EURUSD"},
        headers=headers,
    )


# --------------------------------------------------------------------------- 1
def test_unset_owner_key_rejects_closed_not_open(tmp_path, monkeypatch):
    """No AG_OWNER_API_KEY configured must mean the route is disabled, never that
    auth is skipped."""
    monkeypatch.delenv(OWNER_API_KEY_ENV, raising=False)
    client = _client(tmp_path)
    try:
        response = _post(client, **{OWNER_AUTH_HEADER: "anything"})
        assert response.status_code == 503
        assert response.json()["detail"]["reason_code"] == "OWNER_AUTH_NOT_CONFIGURED"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 2
def test_missing_header_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    client = _client(tmp_path)
    try:
        response = _post(client)
        assert response.status_code == 401
        assert response.json()["detail"]["reason_code"] == "OWNER_AUTH_REJECTED"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 3
def test_wrong_header_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    client = _client(tmp_path)
    try:
        response = _post(client, **{OWNER_AUTH_HEADER: "wrong-key"})
        assert response.status_code == 401
        assert response.json()["detail"]["reason_code"] == "OWNER_AUTH_REJECTED"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 4
def test_correct_header_reaches_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    client = _client(tmp_path)
    try:
        response = _post(client, **{OWNER_AUTH_HEADER: "correct-owner-key"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "AUTHORIZED"
        assert body["trade_command"]["proposal_id"] == "FX:R5A-AUTH-1"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 5
def test_empty_header_treated_as_missing(tmp_path, monkeypatch):
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    client = _client(tmp_path)
    try:
        response = _post(client, **{OWNER_AUTH_HEADER: ""})
        assert response.status_code == 401
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 6
def test_get_routes_never_require_owner_auth(tmp_path, monkeypatch):
    """This boundary is scoped to exactly the owner-decision POST -- every GET route
    audited in R4 stays reachable with no header, auth configured or not."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    try:
        client = TestClient(app)
        response = client.get("/api/canonical-proposals/FX:R5A-AUTH-1")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_proposal_ledger, None)


# --------------------------------------------------------------------------- 7
def test_auth_rejection_leaves_no_owner_decision_recorded(tmp_path, monkeypatch):
    """A rejected-auth request must never reach evaluate_owner_decision() -- confirmed
    by posting the same decision_id again with a correct key and observing a fresh
    AUTHORIZED result rather than a conflicting-reuse rejection."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    client = _client(tmp_path)
    try:
        rejected = _post(client, **{OWNER_AUTH_HEADER: "wrong-key"})
        assert rejected.status_code == 401

        authorized = _post(client, **{OWNER_AUTH_HEADER: "correct-owner-key"})
        assert authorized.status_code == 200
        assert authorized.json()["status"] == "AUTHORIZED"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 8
def test_cors_preflight_allows_owner_auth_header(tmp_path, monkeypatch):
    """A cross-origin browser preflight (OPTIONS + Access-Control-Request-Headers)
    for the owner-decision route must allow X-AG-Owner-Key, or the real POST never
    leaves the browser -- see AG_PANEL frontend/CORS review finding."""
    monkeypatch.setenv(OWNER_API_KEY_ENV, "correct-owner-key")
    client = _client(tmp_path)
    try:
        response = client.options(
            "/api/canonical-proposals/FX:R5A-AUTH-1/owner-decision",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": f"Content-Type, {OWNER_AUTH_HEADER}",
            },
        )
        assert response.status_code == 200
        allowed = response.headers.get("access-control-allow-headers", "")
        assert OWNER_AUTH_HEADER.lower() in allowed.lower()
    finally:
        _clear_overrides()
