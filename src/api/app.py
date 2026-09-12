"""Minimum HTTP API (AG_DEMO_EXECUTION_GATEWAY_PHASE_D2_API_AND_EXECUTION_WIRING_V1
section 9). Thin HTTP adapter only -- every domain decision is delegated to
authorization.store / api.execution_service; this module owns no trading semantics.

Binding: 127.0.0.1 only by default -- see scripts/run_api.py
(AG_AI_STUDIO_PREVIEW_VSCODE_RUNTIME_INTEGRATION_V1), the deterministic local dev-server
launcher this module's own prior docstring anticipated. This module never binds a
socket itself (FastAPI apps don't); the run script is what chooses 127.0.0.1 over
0.0.0.0.

CORS: narrow by construction. AG_ALLOWED_ORIGINS (comma-separated) overrides the
default allow-list of the known local Vite dev origins (see web/vite.config.ts's
port 3000). No wildcard "*" origin is ever used for this router -- see
test_api.py::test_cors_never_allows_wildcard_origin.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from authorization.models import ENVIRONMENT_DEMO
from authorization.store import ExecutionApprovalStore
from authorization.telegram_gateway import ExecutionHandlerResult

from proposal_envelope.ledger import ProposalLedger

from . import broker_service, strategy_service, telegram_service
from .execution_service import InMemoryProposalRegistry, SOURCE_WEB, authorize_demo_execution
from .schemas import (
    AuthorizeDemoRequest,
    AuthorizeDemoResponse,
    BrokerAccountResponse,
    BrokerHistoryResponse,
    BrokerStatusResponse,
    CanonicalProposalResponse,
    GateResultResponse,
    HealthResponse,
    MarketDataCandlesResponse,
    MT5StatusResponse,
    ProposalResponse,
    StrategyResponse,
    SystemStatusResponse,
    TelegramActionResponse,
    TelegramStatusDetailResponse,
    TelegramStatusResponse,
    TicketResponse,
    ValidationResponse,
)

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

# This gateway has exactly one execution path (authorize_demo_execution) and it always
# requires a resolved, claimed approval plus a passing strategy Demo-authority check --
# there is no unauthenticated/automatic execution route anywhere in this API. Fixed
# fact about this deployment, not a per-request computed value.
EXECUTION_MODE = "OWNER_AUTH_REQUIRED"

# strategies/STRATEGY_LEDGER.md / large_smc_research.live_ledger's own default -- reused
# here rather than a second literal; AG_APPLICATION_RELEASE overrides for a future
# release bump without touching source.
DEFAULT_APPLICATION_RELEASE = "AG_TRADE_ASSISTANT_V1_0_3"


def _allowed_origins() -> list[str]:
    """AG_ALLOWED_ORIGINS, comma-separated, overrides the default local-dev list --
    e.g. to add a stable, known AI Studio preview origin (section 10: only if that
    origin is verified stable; never "*"). Empty/whitespace entries are dropped."""
    raw = os.environ.get("AG_ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_ALLOWED_ORIGINS)


app = FastAPI(title="AG Profit Trading -- Demo Execution Gateway API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Process-wide singletons for this minimal app. A real deployment may want these
# constructed per-request from a persistent path instead -- kept simple/overridable
# here (see tests/test_api.py's dependency_overrides) rather than adding a DI
# framework this phase doesn't need.
_default_store = ExecutionApprovalStore()
_default_registry = InMemoryProposalRegistry()
_default_proposal_ledger = ProposalLedger()


def get_store() -> ExecutionApprovalStore:
    return _default_store


def get_proposal_registry() -> InMemoryProposalRegistry:
    return _default_registry


def get_proposal_ledger() -> ProposalLedger:
    return _default_proposal_ledger


def get_execution_handler():
    """Production default: the real MT5 execution handler. Tests MUST override this
    dependency with a fake/mocked callable -- see tests/test_api.py."""
    from authorization.mt5_execution_handler import mt5_execution_handler

    return mt5_execution_handler


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="OK")


@app.get("/api/broker/status", response_model=BrokerStatusResponse)
def broker_status() -> BrokerStatusResponse:
    """Read-only. Never exposes password/token/full login -- see mt5.account_guard for
    the actual identity-match decision this only reports the outcome of."""
    try:
        from mt5.account import account
        from mt5.connection import MT5ConnectionError, connect

        connect()
        acct = account()
    except MT5ConnectionError as exc:
        return BrokerStatusResponse(connected=False, reason_code=f"MT5_NOT_CONNECTED:{exc}")
    except Exception as exc:  # noqa: BLE001 -- never leak a raw traceback to the client
        return BrokerStatusResponse(connected=False, reason_code=f"MT5_STATUS_ERROR:{type(exc).__name__}")

    login_str = str(acct.login)
    redacted = "*" * max(0, len(login_str) - 4) + login_str[-4:]
    return BrokerStatusResponse(
        connected=True,
        environment=ENVIRONMENT_DEMO if acct.is_demo else "LIVE",
        server=acct.server,
        account_redacted=redacted,
        trade_allowed_informational=acct.trade_allowed,
    )


@app.get("/api/broker/account", response_model=BrokerAccountResponse)
def broker_account() -> BrokerAccountResponse:
    """Read-only balance/equity summary. Same connect()/redaction pattern as
    /api/broker/status -- never returns connected=true from configuration alone, and
    never a raw traceback on failure."""
    try:
        from mt5.account import account
        from mt5.connection import MT5ConnectionError, connect

        connect()
        acct = account()
    except MT5ConnectionError as exc:
        return BrokerAccountResponse(connected=False, reason_code=f"MT5_NOT_CONNECTED:{exc}")
    except Exception as exc:  # noqa: BLE001 -- never leak a raw traceback to the client
        return BrokerAccountResponse(connected=False, reason_code=f"MT5_STATUS_ERROR:{type(exc).__name__}")

    login_str = str(acct.login)
    redacted = "*" * max(0, len(login_str) - 4) + login_str[-4:]
    return BrokerAccountResponse(
        connected=True,
        environment=ENVIRONMENT_DEMO if acct.is_demo else "LIVE",
        server=acct.server,
        account_redacted=redacted,
        balance=acct.balance,
        equity=acct.equity,
        trade_allowed_informational=acct.trade_allowed,
    )


@app.get("/api/broker/history", response_model=BrokerHistoryResponse)
def broker_history(days: int = 90, limit: int = 100) -> BrokerHistoryResponse:
    """Read-only MT5 closing-deal history; never returns credentials or account name."""
    try:
        return BrokerHistoryResponse(**broker_service.closed_deal_history(days=days, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"reason_code": str(exc)})
    except Exception as exc:  # noqa: BLE001 -- normalize MT5 failures for the UI
        raise HTTPException(status_code=502, detail={"reason_code": f"MT5_HISTORY_ERROR:{type(exc).__name__}"})


@app.get("/api/market-data/candles", response_model=MarketDataCandlesResponse)
def market_data_candles(symbol: str, timeframe: str = "M15", count: int = 100) -> MarketDataCandlesResponse:
    """Read-only real MT5 closed-candle feed (roadmap R2, AG_REAL_MARKET_WATCH_READY_V1
    -- see docs/PROJECT_ROADMAP.md). Reuses broker_service.real_market_data(), which
    itself reuses assistant.market_data.historical_candles / mt5.market_data --  the
    same canonical retrieval and validation already used elsewhere in this codebase.
    Never substitutes synthetic candles on failure: any error fails closed with a
    reason_code, exactly like /api/broker/history above. This route carries no
    strategy, proposal, or execution authority -- it is a market-data observation
    surface only; R3/R4 (canonical strategy + proposal integration) are separate,
    not-yet-implemented roadmap stages."""
    from mt5.connection import MT5ConnectionError
    from mt5.market_data import MarketDataError

    try:
        return MarketDataCandlesResponse(**broker_service.real_market_data(symbol=symbol, timeframe=timeframe, count=count))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"reason_code": str(exc)})
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail={"reason_code": exc.reason_code})
    except MT5ConnectionError as exc:
        raise HTTPException(status_code=502, detail={"reason_code": f"MT5_NOT_CONNECTED:{exc}"})
    except Exception as exc:  # noqa: BLE001 -- never leak a raw traceback to the client
        raise HTTPException(status_code=502, detail={"reason_code": f"MT5_MARKET_DATA_ERROR:{type(exc).__name__}"})


@app.get("/api/system/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    # Reuses telegram_service.get_status()'s outbound-readiness definition -- this used
    # to recompute TelegramGatewayConfig.is_ready() locally, which also requires a
    # non-empty TELEGRAM_ALLOWED_USER_IDS (that flag only gates the separate inbound-
    # callback path in authorization.telegram_gateway) and so under-reported
    # `configured` for an environment with a valid bot token + chat id but no inbound
    # button authorization enabled -- a real, supported configuration. One definition
    # of "configured" now, not two that can silently disagree.
    broker = broker_status()
    telegram_status = telegram_service.get_status()
    return SystemStatusResponse(
        service="AG Profit Trading Assistant",
        status="online",
        application_release=os.environ.get("AG_APPLICATION_RELEASE", DEFAULT_APPLICATION_RELEASE),
        execution_mode=EXECUTION_MODE,
        broker=broker,
        mt5=MT5StatusResponse(connected=broker.connected),
        telegram=TelegramStatusResponse(configured=telegram_status.configured),
    )


@app.get("/api/strategies", response_model=list[StrategyResponse])
def list_strategies() -> list[StrategyResponse]:
    return [StrategyResponse(**s) for s in strategy_service.list_strategies()]


@app.get("/api/strategies/{strategy_id}", response_model=StrategyResponse)
def get_strategy(strategy_id: str) -> StrategyResponse:
    summary = strategy_service.get_strategy(strategy_id)
    if summary is None:
        raise HTTPException(status_code=404, detail={"reason_code": "STRATEGY_NOT_REGISTERED"})
    return StrategyResponse(**summary)


@app.get("/api/validation/{strategy_id}", response_model=ValidationResponse)
def get_validation(strategy_id: str) -> ValidationResponse:
    if not strategy_service.has_validation_adapter(strategy_id):
        raise HTTPException(status_code=404, detail={"reason_code": "NO_VALIDATION_ADAPTER"})
    try:
        record = strategy_service.get_validation_record(strategy_id)
    except Exception as exc:  # noqa: BLE001 -- never leak a raw traceback to the client
        raise HTTPException(
            status_code=502, detail={"reason_code": f"VALIDATION_EVALUATION_ERROR:{type(exc).__name__}"},
        )
    return ValidationResponse(
        **{**record, "gates": [GateResultResponse(**g) for g in record["gates"]]},
    )


@app.get("/api/proposals", response_model=list[ProposalResponse])
def list_proposals(
    proposal_registry: InMemoryProposalRegistry = Depends(get_proposal_registry),
) -> list[ProposalResponse]:
    return [_to_proposal_response(h, p) for h, p in proposal_registry.all().items()]


@app.get("/api/proposals/{proposal_hash}", response_model=ProposalResponse)
def get_proposal(
    proposal_hash: str, proposal_registry: InMemoryProposalRegistry = Depends(get_proposal_registry),
) -> ProposalResponse:
    proposal = proposal_registry.get_by_hash(proposal_hash)
    if proposal is None:
        raise HTTPException(status_code=404, detail={"reason_code": "PROPOSAL_NOT_FOUND"})
    return _to_proposal_response(proposal_hash, proposal)


def _to_canonical_proposal_response(envelope) -> CanonicalProposalResponse:
    """WP9: pure read-model mapping from proposal_envelope.models.CanonicalProposal --
    every field copied verbatim, execution_eligible is always False by construction
    (this route grants no execution authority regardless of upstream state)."""
    return CanonicalProposalResponse(
        proposal_id=envelope.proposal_envelope_id,
        strategy_id=envelope.strategy_id,
        strategy_version=envelope.strategy_version,
        symbol=envelope.symbol,
        market=envelope.market,
        direction=envelope.direction,
        entry=envelope.entry,
        stop=envelope.stop,
        targets=list(envelope.targets),
        watcher_state=envelope.watcher_state,
        proposal_state=envelope.proposal_state,
        execution_authority=envelope.execution_authority,
        execution_eligible=False,
        market_data_mode=envelope.data_provenance.market_data_mode,
        market_data_source=envelope.data_provenance.source,
        market_data_asof=envelope.data_provenance.market_data_asof,
        market_data_fingerprint=envelope.data_provenance.market_data_fingerprint,
        ready_at=envelope.timestamps.state_entered_at,
        expires_at=envelope.timestamps.expires_at,
        version=envelope.version,
        correction_of=envelope.correction_of,
        reasons=list(envelope.reasons),
    )


@app.get("/api/canonical-proposals", response_model=list[CanonicalProposalResponse])
def list_canonical_proposals(
    proposal_ledger: ProposalLedger = Depends(get_proposal_ledger),
) -> list[CanonicalProposalResponse]:
    """WP9 read-only R4 surface (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): the canonical,
    ledger-backed proposal population. Distinct from GET /api/proposals (the execution-
    approval registry backing /api/tickets/*/authorize-demo) -- this route grants no
    execution authority and cannot be used to authorize or execute anything; it exists
    purely so a scanner/dashboard can render OBSERVATION ONLY canonical proposals."""
    return [_to_canonical_proposal_response(p) for p in proposal_ledger.list_active_proposals()]


@app.get("/api/canonical-proposals/{proposal_id:path}", response_model=CanonicalProposalResponse)
def get_canonical_proposal(
    proposal_id: str, proposal_ledger: ProposalLedger = Depends(get_proposal_ledger),
) -> CanonicalProposalResponse:
    envelope = proposal_ledger.get_proposal(proposal_id)
    if envelope is None:
        raise HTTPException(status_code=404, detail={"reason_code": "CANONICAL_PROPOSAL_NOT_FOUND"})
    return _to_canonical_proposal_response(envelope)


@app.get("/api/telegram/status", response_model=TelegramStatusDetailResponse)
def telegram_status() -> TelegramStatusDetailResponse:
    status = telegram_service.get_status()
    return TelegramStatusDetailResponse(
        configured=status.configured, bot_configured=status.bot_configured,
        chat_configured=status.chat_configured, reachable=status.reachable, reason_code=status.reason_code,
    )


@app.post("/api/telegram/test", response_model=TelegramActionResponse)
def telegram_test() -> TelegramActionResponse:
    result = telegram_service.send_test_notification()
    _journal_telegram_action("telegram-test", "telegram_test_notification", result)
    return TelegramActionResponse(success=result.success, reason_code=result.reason_code, message_id=result.message_id)


@app.post("/api/telegram/trades/{approval_id}/notify", response_model=TelegramActionResponse)
def telegram_notify_trade(
    approval_id: str, store: ExecutionApprovalStore = Depends(get_store),
) -> TelegramActionResponse:
    """Identifier-only: the request body carries no order/trade fields. The backend
    loads the canonical ExecutionApproval itself -- a browser can never supply the
    symbol/price/volume/state that ends up in the Telegram message."""
    approval = store.get(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail={"reason_code": "TRADE_NOT_FOUND"})
    result = telegram_service.notify_trade(approval)
    _journal_telegram_action(approval_id, "telegram_trade_notify", result)
    return TelegramActionResponse(success=result.success, reason_code=result.reason_code, message_id=result.message_id)


@app.post("/api/telegram/positions/{ticket}/notify", response_model=TelegramActionResponse)
def telegram_notify_position(ticket: int) -> TelegramActionResponse:
    """Identifier-only, same posture as telegram_notify_trade: `ticket` (the MT5
    position ticket) is the only client input; the position itself is always read
    fresh from the real MT5 terminal, never accepted from the request."""
    try:
        from mt5.account import account, positions
        from mt5.connection import MT5ConnectionError, connect
        from mt5.market_data import get_tick
        from trade_management.position_monitor import normalize_position

        connect()
        raw_positions = positions(ticket=ticket)
        if not raw_positions:
            raise HTTPException(status_code=404, detail={"reason_code": "POSITION_NOT_FOUND"})
        acct = account()
        tick = get_tick(raw_positions[0].symbol)
        position = normalize_position(raw_positions[0], tick, acct)
    except HTTPException:
        raise
    except MT5ConnectionError as exc:
        raise HTTPException(status_code=502, detail={"reason_code": f"MT5_NOT_CONNECTED:{exc}"})
    except Exception as exc:  # noqa: BLE001 -- never leak a raw traceback to the client
        raise HTTPException(status_code=502, detail={"reason_code": f"MT5_STATUS_ERROR:{type(exc).__name__}"})

    result = telegram_service.notify_position(position)
    _journal_telegram_action(f"position-{ticket}", "telegram_position_notify", result)
    return TelegramActionResponse(success=result.success, reason_code=result.reason_code, message_id=result.message_id)


@app.get("/api/tickets", response_model=list[TicketResponse])
def list_tickets(store: ExecutionApprovalStore = Depends(get_store)) -> list[TicketResponse]:
    return [_to_ticket_response(a) for a in _all_approvals(store)]


@app.get("/api/tickets/{approval_id}", response_model=TicketResponse)
def get_ticket(approval_id: str, store: ExecutionApprovalStore = Depends(get_store)) -> TicketResponse:
    approval = store.get(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail={"reason_code": "TICKET_NOT_FOUND"})
    return _to_ticket_response(approval)


@app.post("/api/tickets/{approval_id}/authorize-demo", response_model=AuthorizeDemoResponse)
def authorize_demo(
    approval_id: str,
    request: AuthorizeDemoRequest,
    http_request: Request,
    store: ExecutionApprovalStore = Depends(get_store),
    proposal_registry: InMemoryProposalRegistry = Depends(get_proposal_registry),
    execution_handler=Depends(get_execution_handler),
) -> AuthorizeDemoResponse:
    if request.action != "EXECUTE_DEMO":
        raise HTTPException(status_code=400, detail={"reason_code": "UNSUPPORTED_ACTION"})

    actor_id = http_request.client.host if http_request.client else None
    result = authorize_demo_execution(
        approval_id, store=store, proposal_registry=proposal_registry,
        execution_handler=execution_handler, source=SOURCE_WEB, actor_id=actor_id,
    )
    return AuthorizeDemoResponse(
        approval_id=result.approval_id, success=result.success, state=result.state,
        reason_code=result.reason_code, result_reference=result.result_reference,
    )


@app.get("/api/executions/{execution_id}", response_model=TicketResponse)
def get_execution(execution_id: str, store: ExecutionApprovalStore = Depends(get_store)) -> TicketResponse:
    # This phase's execution identity == approval_id (one approval -> at most one
    # execution attempt) -- see api.execution_service module docstring.
    return get_ticket(execution_id, store)


def _journal_telegram_action(command_id: str, event: str, result) -> None:
    """Additive event record via the existing execution.journal (append-only,
    command_id-keyed) -- same convention as api.execution_service._journal. Never
    includes a token/secret; never raises into the calling route."""
    try:
        from execution.journal import record_event

        record_event(command_id, event, success=result.success, reason_code=result.reason_code, message_id=result.message_id)
    except OSError:  # noqa: BLE001 -- journaling must never crash the response path
        logging.getLogger("api.app").exception("telegram action journal write failed command_id=%s", command_id)


def _to_proposal_response(proposal_hash: str, proposal) -> ProposalResponse:
    return ProposalResponse(
        proposal_hash=proposal_hash, setup_id=proposal.setup_id, strategy_id=proposal.strategy_id,
        symbol=proposal.symbol, direction=proposal.direction, entry=proposal.entry,
        stop_loss=proposal.stop_loss, tp1=proposal.tp1, tp2=proposal.tp2, volume=proposal.volume,
        risk_amount=proposal.risk_amount, risk_percent=proposal.risk_percent,
    )


def _all_approvals(store: ExecutionApprovalStore):
    return [store.get(k) for k in store._records.all().keys()]  # noqa: SLF001 -- read-only, no public "list all" method exists yet on the store


def _to_ticket_response(approval) -> TicketResponse:
    return TicketResponse(
        approval_id=approval.approval_id, setup_id=approval.setup_id,
        environment=approval.environment, state=approval.state,
        created_at=approval.created_at.isoformat(), expires_at=approval.expires_at.isoformat(),
    )
