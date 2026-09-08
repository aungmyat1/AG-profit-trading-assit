"""Tests for the FastAPI HTTP layer (api.app). No test here reaches a real
MT5/broker call -- api.app.get_execution_handler is always overridden with a
fake/mocked callable, and get_store/get_proposal_registry are overridden with
tmp_path-backed instances so tests never touch the real journal/ directory.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app, get_execution_handler, get_proposal_registry, get_store
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


def _client(tmp_path, *, execution_handler=None, registry_path_patch=None):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    registry = InMemoryProposalRegistry()

    def fake_handler(proposal):
        return ExecutionHandlerResult(success=True, result_reference="999999", detail="EXECUTED ticket=999999")

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_proposal_registry] = lambda: registry
    app.dependency_overrides[get_execution_handler] = lambda: (execution_handler or fake_handler)

    client = TestClient(app)
    return client, store, registry


def test_health():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "OK"}


def test_cors_never_allows_wildcard_origin():
    """AI Studio/VS Code integration section 10/26: default allow-list is the known
    local Vite dev origins only, and AG_ALLOWED_ORIGINS (if set) is never treated as
    a wildcard even if misconfigured with one -- FastAPI's CORSMiddleware simply
    wouldn't match a literal '*' string against a real Origin header the way an
    actual wildcard config would, so this asserts the app's own default never emits one."""
    from api.app import _allowed_origins

    origins = _allowed_origins()
    assert "*" not in origins
    assert all(o.startswith("http://") or o.startswith("https://") for o in origins)


def test_authorize_demo_actor_id_recorded_from_request(tmp_path, monkeypatch):
    """The requester's client host is threaded through as audit-only actor_id --
    proves the wiring exists without asserting on the exact loopback string TestClient
    uses (which is an httpx/starlette implementation detail, not part of this
    module's contract)."""
    captured = {}
    monkeypatch.setattr(
        "api.execution_service.check_strategy_demo_authorized",
        lambda strategy_id, registry_path=None: __import__(
            "authorization.models", fromlist=["AuthorizationCheckResult"]
        ).AuthorizationCheckResult(True),
    )
    original_journal = __import__("api.execution_service", fromlist=["_journal"])._journal

    def spy_journal(approval, proposal, source, actor_id, **kwargs):
        captured["actor_id"] = actor_id
        return original_journal(approval, proposal, source, actor_id, **kwargs)

    monkeypatch.setattr("api.execution_service._journal", spy_journal)

    client, store, registry = _client(tmp_path)
    proposal = _proposal()
    approval = store.create(proposal, venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    registry.register(proposal)

    client.post(f"/api/tickets/{approval.approval_id}/authorize-demo", json={"action": "EXECUTE_DEMO"})
    assert "actor_id" in captured  # captured, even if TestClient's value is None/loopback
    app.dependency_overrides.clear()


def test_ticket_not_found(tmp_path):
    client, _store, _registry = _client(tmp_path)
    resp = client.get("/api/tickets/does-not-exist")
    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_list_and_get_ticket(tmp_path):
    client, store, registry = _client(tmp_path)
    proposal = _proposal()
    approval = store.create(proposal, venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    registry.register(proposal)

    resp = client.get("/api/tickets")
    assert resp.status_code == 200
    ids = [t["approval_id"] for t in resp.json()]
    assert approval.approval_id in ids

    resp = client.get(f"/api/tickets/{approval.approval_id}")
    assert resp.status_code == 200
    assert resp.json()["setup_id"] == proposal.setup_id
    app.dependency_overrides.clear()


def test_authorize_demo_end_to_end_mocked_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.execution_service.check_strategy_demo_authorized",
        lambda strategy_id, registry_path=None: __import__(
            "authorization.models", fromlist=["AuthorizationCheckResult"]
        ).AuthorizationCheckResult(True),
    )
    client, store, registry = _client(tmp_path)
    proposal = _proposal()
    approval = store.create(proposal, venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    registry.register(proposal)

    resp = client.post(f"/api/tickets/{approval.approval_id}/authorize-demo", json={"action": "EXECUTE_DEMO"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["state"] == "EXECUTED"
    assert body["result_reference"] == "999999"
    app.dependency_overrides.clear()


def test_authorize_demo_blocked_by_real_strategy_registry_by_default(tmp_path):
    """No monkeypatch here: proves the API genuinely consults the real, current
    strategies/registry.yaml -- ST_ASIAN_SWEEP_5R_V1 is demo_authorized: false there
    today, so this must be blocked, never silently allowed."""
    client, store, registry = _client(tmp_path)
    proposal = _proposal()
    approval = store.create(proposal, venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    registry.register(proposal)

    resp = client.post(f"/api/tickets/{approval.approval_id}/authorize-demo", json={"action": "EXECUTE_DEMO"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["reason_code"] == "BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED"
    app.dependency_overrides.clear()


def test_duplicate_authorize_demo_request_calls_gateway_exactly_once(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.execution_service.check_strategy_demo_authorized",
        lambda strategy_id, registry_path=None: __import__(
            "authorization.models", fromlist=["AuthorizationCheckResult"]
        ).AuthorizationCheckResult(True),
    )
    calls = []

    def counting_handler(proposal):
        calls.append(proposal)
        return ExecutionHandlerResult(success=True, result_reference="1", detail="EXECUTED")

    client, store, registry = _client(tmp_path, execution_handler=counting_handler)
    proposal = _proposal()
    approval = store.create(proposal, venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    registry.register(proposal)

    first = client.post(f"/api/tickets/{approval.approval_id}/authorize-demo", json={"action": "EXECUTE_DEMO"})
    second = client.post(f"/api/tickets/{approval.approval_id}/authorize-demo", json={"action": "EXECUTE_DEMO"})

    assert first.json()["success"] is True
    assert second.json()["success"] is False
    assert second.json()["reason_code"] == "APPROVAL_ALREADY_PROCESSED"
    assert len(calls) == 1  # the execution gateway was invoked exactly once, not twice
    app.dependency_overrides.clear()


def test_no_response_model_field_named_like_a_secret():
    import inspect

    from api import schemas

    for name, obj in vars(schemas).items():
        if inspect.isclass(obj) and issubclass(obj, schemas.BaseModel):
            for field_name in obj.model_fields:
                lowered = field_name.lower()
                assert "password" not in lowered and "secret" not in lowered and "token" not in lowered, (
                    f"{name}.{field_name} looks credential-shaped"
                )
