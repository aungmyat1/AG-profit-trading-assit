"""Minimum HTTP API (AG_DEMO_EXECUTION_GATEWAY_PHASE_D2_API_AND_EXECUTION_WIRING_V1
section 9). Thin HTTP adapter only -- every domain decision is delegated to
authorization.store / api.execution_service; this module owns no trading semantics.

Binding: 127.0.0.1 only by default (see scripts/run_api.py, not yet added -- this
module just declares the app; a future run script is responsible for the actual
uvicorn bind-address choice, per section 27's "prefer 127.0.0.1" instruction).
CORS is intentionally NOT configured here with a wildcard; a future web/ integration
pass must set an explicit allowed-origin list, never "*", for this router.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException

from authorization.models import ENVIRONMENT_DEMO
from authorization.store import ExecutionApprovalStore
from authorization.telegram_gateway import ExecutionHandlerResult

from .execution_service import InMemoryProposalRegistry, SOURCE_WEB, authorize_demo_execution
from .schemas import (
    AuthorizeDemoRequest,
    AuthorizeDemoResponse,
    BrokerStatusResponse,
    HealthResponse,
    TicketResponse,
)

app = FastAPI(title="AG Profit Trading -- Demo Execution Gateway API", version="0.1.0")

# Process-wide singletons for this minimal app. A real deployment may want these
# constructed per-request from a persistent path instead -- kept simple/overridable
# here (see tests/test_api.py's dependency_overrides) rather than adding a DI
# framework this phase doesn't need.
_default_store = ExecutionApprovalStore()
_default_registry = InMemoryProposalRegistry()


def get_store() -> ExecutionApprovalStore:
    return _default_store


def get_proposal_registry() -> InMemoryProposalRegistry:
    return _default_registry


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
    store: ExecutionApprovalStore = Depends(get_store),
    proposal_registry: InMemoryProposalRegistry = Depends(get_proposal_registry),
    execution_handler=Depends(get_execution_handler),
) -> AuthorizeDemoResponse:
    if request.action != "EXECUTE_DEMO":
        raise HTTPException(status_code=400, detail={"reason_code": "UNSUPPORTED_ACTION"})

    result = authorize_demo_execution(
        approval_id, store=store, proposal_registry=proposal_registry,
        execution_handler=execution_handler, source=SOURCE_WEB,
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


def _all_approvals(store: ExecutionApprovalStore):
    return [store.get(k) for k in store._records.all().keys()]  # noqa: SLF001 -- read-only, no public "list all" method exists yet on the store


def _to_ticket_response(approval) -> TicketResponse:
    return TicketResponse(
        approval_id=approval.approval_id, setup_id=approval.setup_id,
        environment=approval.environment, state=approval.state,
        created_at=approval.created_at.isoformat(), expires_at=approval.expires_at.isoformat(),
    )
