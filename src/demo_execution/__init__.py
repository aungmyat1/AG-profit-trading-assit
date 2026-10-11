"""Fail-closed, broker-free C14 DEMO admission components for the scoped S1 lane.

This package intentionally contains no MT5 gateway and never submits an order. The
C11 canonical host execution import must supply that boundary after separate review.
"""
from demo_execution.admission import (
    AdmissionResult,
    MarketEvidence,
    evaluate_pre_send_gates,
    prepare_canonical_handoff,
)
from demo_execution.authorization import (
    AuthorizationResult,
    load_standing_authorization,
)
from demo_execution.idempotency import ExecutionLedger, LedgerCheck
from demo_execution.risk import (
    OpenPosition,
    RiskAssessment,
    RiskSnapshot,
    evaluate_risk_caps,
)
from demo_execution.scope import ScopePolicy, ScopePolicyError, load_scope_policy

__all__ = [
    "AdmissionResult",
    "AuthorizationResult",
    "ExecutionLedger",
    "LedgerCheck",
    "MarketEvidence",
    "OpenPosition",
    "RiskAssessment",
    "RiskSnapshot",
    "ScopePolicy",
    "ScopePolicyError",
    "evaluate_pre_send_gates",
    "evaluate_risk_caps",
    "load_scope_policy",
    "load_standing_authorization",
    "prepare_canonical_handoff",
]
