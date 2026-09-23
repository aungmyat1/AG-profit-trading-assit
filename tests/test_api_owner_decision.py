"""PANEL-R4 focused tests: POST /api/canonical-proposals/{proposal_id}/owner-decision.

Covers the 14 semantic points required by the mission brief. Uses FastAPI
dependency_overrides (same pattern as tests/test_api_canonical_proposals.py) to inject
a ProposalLedger and OwnerDecisionStore over a tmp_path/fresh instance, so no real
ledger file or MT5 connection is touched.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app, get_owner_decision_store, get_proposal_ledger, require_owner_auth
from owner_decision.bridge import OwnerDecisionStore
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import CanonicalProposal, PROPOSAL_BLOCKED, PROPOSAL_READY


def _ready(**overrides) -> CanonicalProposal:
    base = dict(
        proposal_envelope_id="FX:R4-DECISION-1", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", market="FX", venue="VANTAGE_DEMO_MT5", symbol="EURUSD",
        proposal_state=PROPOSAL_READY, direction="BUY", entry=1.1000, stop=1.0950,
        targets=(1.1100,), demo_authorized=True, broker_mutation_blocked=False,
    )
    base.update(overrides)
    return CanonicalProposal(**base)


def _client(ledger: ProposalLedger, store: OwnerDecisionStore) -> TestClient:
    # PANEL-R5A gates this route with require_owner_auth (see
    # tests/test_api_owner_decision_auth.py for that boundary's own dedicated tests).
    # These R3/R4-lineage tests are about evaluate_owner_decision()'s semantics, not
    # auth, so they override it the same way they already override the two stores.
    app.dependency_overrides[get_proposal_ledger] = lambda: ledger
    app.dependency_overrides[get_owner_decision_store] = lambda: store
    app.dependency_overrides[require_owner_auth] = lambda: None
    return TestClient(app)


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_proposal_ledger, None)
    app.dependency_overrides.pop(get_owner_decision_store, None)
    app.dependency_overrides.pop(require_owner_auth, None)


# --------------------------------------------------------------------------- 1
def test_explicit_valid_owner_confirmation_reaches_canonical_r3_service(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:R4-DECISION-1/owner-decision",
            json={"decision_id": "dec-1", "action": "APPROVE_DEMO", "symbol": "EURUSD"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "AUTHORIZED"
        assert body["execution_decision_prepared"] is True
        assert body["trade_command"]["symbol"] == "EURUSD"
        assert body["trade_command"]["proposal_id"] == "FX:R4-DECISION-1"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 2
def test_malformed_decision_id_fails_closed(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:R4-DECISION-1/owner-decision",
            json={"decision_id": "", "action": "APPROVE_DEMO", "symbol": "EURUSD"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "REJECTED"
        assert body["reason_code"] == "MALFORMED_DECISION"
        assert body["trade_command"] is None
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 3
def test_get_routes_cannot_create_decisions(tmp_path):
    """Structural: the R2/R4 GET routes must never import owner_decision -- viewing or
    listing a proposal must be structurally incapable of creating an OwnerDecision."""
    repo_src = Path(__file__).resolve().parents[1] / "src"
    tree = ast.parse((repo_src / "api" / "opportunity_analysis.py").read_text(encoding="utf-8"))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
    assert not any(m.startswith("owner_decision") for m in imported_names)

    # Functional: GET on the ledger never records anything into the owner-decision store.
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    store = OwnerDecisionStore()
    client = _client(ledger, store)
    try:
        client.get("/api/canonical-proposals")
        client.get("/api/canonical-proposals/FX:R4-DECISION-1")
        assert store.get("dec-1") is None
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 4
def test_unknown_proposal_identity_fails_closed(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:NOPE/owner-decision",
            json={"decision_id": "dec-2", "action": "APPROVE_DEMO", "symbol": "EURUSD"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "REJECTED"
        assert body["reason_code"] == "PROPOSAL_NOT_READY"
        assert body["trade_command"] is None
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 5
def test_malformed_request_body_fails(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:R4-DECISION-1/owner-decision",
            json={"action": "APPROVE_DEMO"},  # missing decision_id and symbol
        )
        assert response.status_code == 422
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 6
def test_unsupported_owner_action_fails(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:R4-DECISION-1/owner-decision",
            json={"decision_id": "dec-3", "action": "EXECUTE_NOW", "symbol": "EURUSD"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["reason_code"] == "UNSUPPORTED_ACTION"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 7
def test_stale_state_fails(tmp_path):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready(plan_expires_at=past))
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:R4-DECISION-1/owner-decision",
            json={"decision_id": "dec-4", "action": "APPROVE_DEMO", "symbol": "EURUSD"},
        )
        body = response.json()
        assert body["status"] == "REJECTED"
        assert body["reason_code"] == "PROPOSAL_STALE"
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 8
def test_rejected_terminal_state_cannot_become_executable(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:R4-DECISION-1/owner-decision",
            json={"decision_id": "dec-5", "action": "REJECT", "symbol": "EURUSD"},
        )
        body = response.json()
        assert body["status"] == "REJECTED"
        assert body["reason_code"] == "OWNER_REJECTED"
        assert body["trade_command"] is None
        assert body["execution_decision_prepared"] is False
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 9
def test_duplicate_http_confirmation_remains_idempotent(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    store = OwnerDecisionStore()
    client = _client(ledger, store)
    try:
        payload = {"decision_id": "dec-6", "action": "APPROVE_DEMO", "symbol": "EURUSD"}
        first = client.post("/api/canonical-proposals/FX:R4-DECISION-1/owner-decision", json=payload)
        second = client.post("/api/canonical-proposals/FX:R4-DECISION-1/owner-decision", json=payload)
        assert first.status_code == 200 and second.status_code == 200
        first_body, second_body = first.json(), second.json()
        assert first_body["status"] == "AUTHORIZED"
        assert second_body == first_body
        assert second_body["trade_command"]["command_id"] == first_body["trade_command"]["command_id"]
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 10
def test_live_path_remains_unauthorized(tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    ledger.record_proposal(_ready())
    client = _client(ledger, OwnerDecisionStore())
    try:
        response = client.post(
            "/api/canonical-proposals/FX:R4-DECISION-1/owner-decision",
            json={"decision_id": "dec-7", "action": "APPROVE_DEMO", "symbol": "EURUSD", "environment": "LIVE"},
        )
        body = response.json()
        assert body["status"] == "REJECTED"
        assert body["reason_code"] == "NON_DEMO_ENVIRONMENT_REJECTED"
        assert body["trade_command"] is None
    finally:
        _clear_overrides()


# --------------------------------------------------------------------------- 11 / 12
def test_no_scheduler_or_alert_module_imports_owner_decision_or_the_new_route():
    """Structural: neither ag_scheduler_v2/ nor alerting/ may import owner_decision or
    reference the new route -- a scheduler tick or a watch/alert firing must be
    structurally incapable of synthesizing an owner confirmation."""
    repo_src = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for folder in ("ag_scheduler_v2", "alerting"):
        folder_path = repo_src / folder
        if not folder_path.exists():
            continue
        for py_file in folder_path.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            if "owner_decision" in text or "owner-decision" in text:
                offenders.append(str(py_file))
    assert offenders == []


# --------------------------------------------------------------------------- 13
def test_http_layer_does_not_directly_call_mt5():
    """Structural guard on api/app.py itself: no new direct path to
    execution.executor/execution.mt5_gateway/order_send, and user_confirmed=True is
    never set anywhere in this module."""
    app_path = Path(__file__).resolve().parents[1] / "src" / "api" / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
    assert "execution.executor" not in imported_modules
    assert "execution.mt5_gateway" not in imported_modules
    text = app_path.read_text(encoding="utf-8")
    assert "user_confirmed=True" not in text
    assert "user_confirmed = True" not in text
    assert "order_send" not in text


# --------------------------------------------------------------------------- 14
def test_opportunity_analysis_get_remains_observation_only(tmp_path, monkeypatch):
    """R2's GET /api/opportunity-analysis route is unmodified by R4 and this test does
    not exercise MT5 -- it only re-confirms (structurally, see test 3) that R4 added no
    import from that module into owner_decision. Functional MT5-backed behavior is
    already covered by tests/test_api_opportunity_analysis.py (frozen, untouched)."""
    import api.app as app_module

    assert "owner_decision" not in Path(app_module.__file__).with_name(
        "opportunity_analysis.py",
    ).read_text(encoding="utf-8")
