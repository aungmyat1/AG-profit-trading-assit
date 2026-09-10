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


def test_system_status_shape():
    client = TestClient(app)
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "AG Profit Trading Assistant"
    assert body["execution_mode"] == "OWNER_AUTH_REQUIRED"
    assert "broker" in body and "mt5" in body and "telegram" in body
    assert isinstance(body["telegram"]["configured"], bool)


def test_broker_account_never_500s_and_matches_broker_status_connection_state():
    """Whatever this machine's real MT5 connection state is, the endpoint must report
    it consistently with /api/broker/status (same underlying connect()/account()
    call), never raise a raw 500, and never claim a balance without connected=True."""
    client = TestClient(app)
    status_resp = client.get("/api/broker/status")
    account_resp = client.get("/api/broker/account")
    assert account_resp.status_code == 200
    body = account_resp.json()
    assert body["connected"] == status_resp.json()["connected"]
    if not body["connected"]:
        assert body["reason_code"] is not None
        assert body["balance"] is None


def test_broker_history_returns_sanitized_mt5_deals(monkeypatch):
    from api import app as app_module

    monkeypatch.setattr(app_module.broker_service, "closed_deal_history", lambda **kwargs: {
        "account_redacted": "****2746", "server": "VantageMarkets-Demo", "environment": "DEMO",
        "lookback_days": kwargs["days"], "total_closing_deals": 1, "returned_deals": 1,
        "realized_net": -1.25, "deals": [{
            "ticket": 123, "position_id": 456, "time": "2026-09-09T10:00:00+00:00",
            "symbol": "EURUSD", "side": "SELL", "volume": 0.01, "price": 1.16,
            "profit": -1.25, "commission": 0.0, "swap": 0.0, "fee": 0.0, "comment": "[sl]",
        }],
    })
    response = TestClient(app).get("/api/broker/history?days=30&limit=10")
    assert response.status_code == 200
    assert response.json()["account_redacted"] == "****2746"
    assert response.json()["deals"][0]["ticket"] == 123
    assert "login" not in response.text.lower()


def test_broker_history_rejects_invalid_range(monkeypatch):
    from api import app as app_module

    def invalid(**_kwargs):
        raise ValueError("days must be between 1 and 3650")

    monkeypatch.setattr(app_module.broker_service, "closed_deal_history", invalid)
    response = TestClient(app).get("/api/broker/history?days=0")
    assert response.status_code == 400
    assert response.json()["detail"]["reason_code"] == "days must be between 1 and 3650"


def test_market_data_candles_returns_real_mt5_provenance(monkeypatch):
    """Roadmap R2 (AG_REAL_MARKET_WATCH_READY_V1): the response must carry real MT5
    provenance -- source, broker/environment, and per-candle OHLC/time -- never a
    fixture shape indistinguishable from the frontend's SYNTHETIC scanner proposals."""
    from api import app as app_module

    monkeypatch.setattr(app_module.broker_service, "real_market_data", lambda **kwargs: {
        "source": "MT5", "broker": "VantageMarkets-Demo", "environment": "DEMO",
        "symbol": kwargs["symbol"], "timeframe": kwargs["timeframe"], "bar_count": 2,
        "last_closed_candle_at": "2026-09-10T11:45:00+00:00", "freshness": "OK",
        "candles": [
            {"time": "2026-09-10T11:30:00+00:00", "open": 1.1, "high": 1.11, "low": 1.09, "close": 1.105, "volume": 120.0},
            {"time": "2026-09-10T11:45:00+00:00", "open": 1.105, "high": 1.108, "low": 1.1, "close": 1.107, "volume": 98.0},
        ],
    })
    response = TestClient(app).get("/api/market-data/candles?symbol=EURUSD&timeframe=M15&count=2")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "MT5"
    assert body["environment"] == "DEMO"
    assert body["symbol"] == "EURUSD"
    assert body["bar_count"] == 2
    assert len(body["candles"]) == 2


def test_market_data_candles_rejects_invalid_count(monkeypatch):
    from api import app as app_module

    def invalid(**_kwargs):
        raise ValueError("count must be between 1 and 500")

    monkeypatch.setattr(app_module.broker_service, "real_market_data", invalid)
    response = TestClient(app).get("/api/market-data/candles?symbol=EURUSD&count=0")
    assert response.status_code == 400
    assert response.json()["detail"]["reason_code"] == "count must be between 1 and 500"


def test_market_data_candles_fails_closed_never_synthesizes_on_mt5_failure(monkeypatch):
    """Invariant D: if real MT5 data is unavailable, this route must fail closed with a
    reason_code -- never fabricate/substitute candles so the caller could mistake a
    synthetic result for real MT5 data."""
    from api import app as app_module
    from mt5.market_data import MarketDataError

    def failing(**_kwargs):
        raise MarketDataError("DATA_MISSING", "EURUSD M15: no data")

    monkeypatch.setattr(app_module.broker_service, "real_market_data", failing)
    response = TestClient(app).get("/api/market-data/candles?symbol=EURUSD&timeframe=M15&count=100")
    assert response.status_code == 502
    assert response.json()["detail"]["reason_code"] == "DATA_MISSING"
    assert "candles" not in response.json()


def test_list_strategies_reads_real_registry():
    """No monkeypatch: proves this reads the real strategies/registry.yaml, same file
    the authorization path already consults."""
    client = TestClient(app)
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    ids = [s["strategy_id"] for s in resp.json()]
    assert "ST_ASIAN_SWEEP_5R_V1" in ids
    entry = next(s for s in resp.json() if s["strategy_id"] == "ST_ASIAN_SWEEP_5R_V1")
    assert entry["demo_authorized"] is False


def test_get_strategy_unknown_returns_404():
    client = TestClient(app)
    resp = client.get("/api/strategies/DOES_NOT_EXIST")
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "STRATEGY_NOT_REGISTERED"


def test_get_validation_unknown_adapter_returns_404():
    client = TestClient(app)
    resp = client.get("/api/validation/DOES_NOT_EXIST")
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "NO_VALIDATION_ADAPTER"


def test_list_and_get_proposal(tmp_path):
    client, _store, registry = _client(tmp_path)
    proposal = _proposal()
    proposal_hash = registry.register(proposal)

    resp = client.get("/api/proposals")
    assert resp.status_code == 200
    hashes = [p["proposal_hash"] for p in resp.json()]
    assert proposal_hash in hashes

    resp = client.get(f"/api/proposals/{proposal_hash}")
    assert resp.status_code == 200
    assert resp.json()["setup_id"] == proposal.setup_id
    app.dependency_overrides.clear()


def test_get_proposal_not_found(tmp_path):
    client, _store, _registry = _client(tmp_path)
    resp = client.get("/api/proposals/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "PROPOSAL_NOT_FOUND"
    app.dependency_overrides.clear()


def test_telegram_status_route_reflects_service(monkeypatch):
    from api import app as app_module
    from api.telegram_service import TelegramStatus

    monkeypatch.setattr(
        app_module.telegram_service, "get_status",
        lambda: TelegramStatus(configured=True, bot_configured=True, chat_configured=True, reachable=True),
    )
    client = TestClient(app)
    resp = client.get("/api/telegram/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "configured": True, "bot_configured": True, "chat_configured": True,
        "reachable": True, "reason_code": None,
    }


def test_telegram_status_route_never_configured_from_env_vars_alone(monkeypatch):
    """No monkeypatch of the service itself: proves the route calls the real
    telegram_service.get_status(), which never reports reachable=True without an
    actual (mocked-at-the-transport-level, here just absent) Telegram round trip."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    client = TestClient(app)
    resp = client.get("/api/telegram/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["reachable"] is False
    assert body["reason_code"] == "NOT_CONFIGURED"


def test_telegram_test_route(monkeypatch):
    from api import app as app_module
    from api.telegram_service import TelegramActionResult

    monkeypatch.setattr(
        app_module.telegram_service, "send_test_notification",
        lambda: TelegramActionResult(success=True, message_id="123"),
    )
    client = TestClient(app)
    resp = client.post("/api/telegram/test")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "reason_code": None, "message_id": "123"}


def test_telegram_test_route_not_configured(monkeypatch):
    from api import app as app_module
    from api.telegram_service import TelegramActionResult

    monkeypatch.setattr(
        app_module.telegram_service, "send_test_notification",
        lambda: TelegramActionResult(success=False, reason_code="NOT_CONFIGURED"),
    )
    client = TestClient(app)
    resp = client.post("/api/telegram/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["reason_code"] == "NOT_CONFIGURED"


def test_telegram_notify_trade_unknown_id_returns_404(tmp_path):
    client, _store, _registry = _client(tmp_path)
    resp = client.post("/api/telegram/trades/does-not-exist/notify")
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "TRADE_NOT_FOUND"
    app.dependency_overrides.clear()


def test_telegram_notify_trade_success_ignores_client_body(tmp_path, monkeypatch):
    """The endpoint accepts no request body at all -- proves a client cannot inject an
    arbitrary symbol/price/etc. even by trying to POST one."""
    from api import app as app_module
    from api.telegram_service import TelegramActionResult

    captured = {}

    def fake_notify_trade(approval):
        captured["approval_id"] = approval.approval_id
        return TelegramActionResult(success=True, message_id="55")

    monkeypatch.setattr(app_module.telegram_service, "notify_trade", fake_notify_trade)

    client, store, registry = _client(tmp_path)
    proposal = _proposal()
    approval = store.create(proposal, venue=VENUE_MT5)

    resp = client.post(
        f"/api/telegram/trades/{approval.approval_id}/notify",
        json={"symbol": "HACKED", "volume": 999.0},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert captured["approval_id"] == approval.approval_id  # canonical id used, body ignored
    app.dependency_overrides.clear()


def test_telegram_notify_position_unknown_ticket_returns_404(monkeypatch):
    from api import app as app_module

    monkeypatch.setattr("mt5.connection.connect", lambda: None)
    monkeypatch.setattr("mt5.account.positions", lambda ticket=None, symbol=None: [])

    client = TestClient(app)
    resp = client.post("/api/telegram/positions/999999/notify")
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "POSITION_NOT_FOUND"


def test_telegram_notify_position_success_reads_real_position_not_client_body(monkeypatch):
    from types import SimpleNamespace

    from api import app as app_module
    from api.telegram_service import TelegramActionResult
    from mt5.account import Account
    from trade_management.models import NormalizedPosition

    fake_account = Account(
        login=1, server="Test-Demo", is_demo=True, balance=1000.0, equity=1000.0,
        trade_allowed=True, is_hedging_account=False,
    )
    raw_position = SimpleNamespace(
        ticket=42, symbol="EURUSD", type=0, volume=0.1, price_open=1.1000, sl=None, tp=None,
        profit=5.0, swap=0.0, comment="", magic=0, time=1893456000,
    )

    monkeypatch.setattr("mt5.connection.connect", lambda: None)
    monkeypatch.setattr("mt5.account.positions", lambda ticket=None, symbol=None: [raw_position])
    monkeypatch.setattr("mt5.account.account", lambda: fake_account)
    monkeypatch.setattr("mt5.market_data.get_tick", lambda symbol: SimpleNamespace(bid=1.1005, ask=1.1007))

    captured = {}

    def fake_notify_position(position):
        captured["ticket"] = position.ticket
        captured["symbol"] = position.symbol
        return TelegramActionResult(success=True, message_id="77")

    monkeypatch.setattr(app_module.telegram_service, "notify_position", fake_notify_position)

    client = TestClient(app)
    resp = client.post("/api/telegram/positions/42/notify", json={"symbol": "HACKED"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert captured["ticket"] == 42
    assert captured["symbol"] == "EURUSD"  # from the real position, never the request body


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
