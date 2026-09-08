"""Sanitized Pydantic response models. No field here may ever carry a credential --
see tests/test_api.py::test_no_response_model_field_named_like_a_secret for a static
guard against that regressing."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class BrokerStatusResponse(BaseModel):
    connected: bool
    broker: Optional[str] = None
    environment: Optional[str] = None
    server: Optional[str] = None
    account_redacted: Optional[str] = None
    trade_allowed_informational: Optional[bool] = None
    reason_code: Optional[str] = None


class TicketResponse(BaseModel):
    approval_id: str
    setup_id: str
    strategy_id: Optional[str] = None
    symbol: Optional[str] = None
    direction: Optional[str] = None
    environment: str
    state: str
    created_at: str
    expires_at: str


class AuthorizeDemoRequest(BaseModel):
    action: str = "EXECUTE_DEMO"


class AuthorizeDemoResponse(BaseModel):
    approval_id: str
    success: bool
    state: str
    reason_code: Optional[str] = None
    result_reference: Optional[str] = None


class ErrorResponse(BaseModel):
    reason_code: str
    message: str
