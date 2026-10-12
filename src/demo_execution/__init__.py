"""Fail-closed, broker-free C14 DEMO admission components for the scoped S1 lane.

This package intentionally contains no MT5 gateway and never submits an order. The
C11 canonical host execution import must supply that boundary after separate review.
What this package owns is the refusal side of that boundary: the execution-authority
object, its re-validation, the guarded call sequencing, the append-only lifecycle
evidence trail, and the host magic registry that keeps the reserved S1 magic distinct
from every magic already in use on the host.
"""
from demo_execution.admission import (
    AdmissionResult,
    MarketEvidence,
    evaluate_pre_send_gates,
    prepare_canonical_handoff,
)
from demo_execution.authority import (
    AccountIdentity,
    EvidenceRef,
    ExecutionAuthority,
    build_authority,
    per_order_confirm_required,
    validate_authority_binding,
    validate_authority_shape,
    validate_confirmation_evidence,
    validate_evidence_refs,
    validate_live_account,
)
from demo_execution.authorization import (
    AuthorizationResult,
    load_standing_authorization,
)
from demo_execution.confirmation import (
    OwnerConfirmationCheck,
    append_owner_confirmation,
    check_and_consume_owner_confirmation,
)
from demo_execution.guarded_adapter import GuardDecision, GuardedCanonicalAdapter
from demo_execution.host_magics import (
    HostMagicRegistryError,
    load_host_magics,
    reserved_magic_conflict,
)
from demo_execution.idempotency import ExecutionLedger, LedgerCheck
from demo_execution.lifecycle import (
    LIFECYCLE_STATES,
    ExecutionLifecycle,
    LifecycleState,
    LifecycleTrail,
    TransitionResult,
)
from demo_execution.risk import (
    OpenPosition,
    RiskAssessment,
    RiskSnapshot,
    evaluate_risk_caps,
)
from demo_execution.scope import ScopePolicy, ScopePolicyError, load_scope_policy

__all__ = [
    "AccountIdentity",
    "AdmissionResult",
    "AuthorizationResult",
    "EvidenceRef",
    "ExecutionAuthority",
    "ExecutionLedger",
    "ExecutionLifecycle",
    "GuardDecision",
    "GuardedCanonicalAdapter",
    "HostMagicRegistryError",
    "LedgerCheck",
    "LIFECYCLE_STATES",
    "LifecycleState",
    "LifecycleTrail",
    "MarketEvidence",
    "OpenPosition",
    "OwnerConfirmationCheck",
    "RiskAssessment",
    "RiskSnapshot",
    "ScopePolicy",
    "ScopePolicyError",
    "TransitionResult",
    "append_owner_confirmation",
    "build_authority",
    "check_and_consume_owner_confirmation",
    "evaluate_pre_send_gates",
    "evaluate_risk_caps",
    "load_host_magics",
    "load_scope_policy",
    "load_standing_authorization",
    "per_order_confirm_required",
    "prepare_canonical_handoff",
    "reserved_magic_conflict",
    "validate_authority_binding",
    "validate_authority_shape",
    "validate_confirmation_evidence",
    "validate_evidence_refs",
    "validate_live_account",
]
