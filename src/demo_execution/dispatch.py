"""One READY ticket -> one guarded DEMO order attempt (C14 item 1: cycle-to-guard dispatch).

Drives the fixed guarded sequence for a single ticket and nothing else:

    authorize_order_check -> broker.check_order -> record_order_checked
    -> authorize_order_send -> broker.send_order -> record_broker_ack | halt

The broker is injected as a :class:`demo_execution.broker_adapter.CanonicalBrokerAdapter`; this
module never imports :mod:`demo_execution.mt5_canonical_adapter` (only the host orchestration
outside this repository constructs it -- ``tests/test_demo_execution_bypass.py``). It decides
nothing itself: every gate, the scope ``enabled`` flag, the standing authorization, the owner
confirmation and the live DEMO account are re-validated by the guard and again by the adapter.
Each guarded call gets a fresh single-use authority id. The first refusal stops the attempt; an
order_send that is refused after the durable send claim, raises, or reports an unknown outcome
HALTs the ticket (reconcile later, never resubmit). There is no retry anywhere.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from demo_execution.admission import MarketEvidence
from demo_execution.authority import AccountIdentity, ExecutionAuthority, build_authority
from demo_execution.authorization import load_standing_authorization
from demo_execution.broker_adapter import CanonicalBrokerAdapter
from demo_execution.guarded_adapter import GuardDecision, GuardedCanonicalAdapter
from demo_execution.lifecycle import HALT
from demo_execution.risk import RiskSnapshot
from demo_execution.scope import ScopePolicyError, resolve_ticket_scope_policy

# Terminal stages of one dispatch attempt.
SCOPE_REFUSED = "SCOPE_REFUSED"
AUTHORIZATION_REFUSED = "AUTHORIZATION_REFUSED"
ORDER_CHECK_REFUSED = "ORDER_CHECK_REFUSED"
ORDER_CHECK_BROKER_REFUSED = "ORDER_CHECK_BROKER_REFUSED"
ORDER_CHECK_RECORD_REFUSED = "ORDER_CHECK_RECORD_REFUSED"
ORDER_SEND_REFUSED = "ORDER_SEND_REFUSED"
HALTED = "HALTED"
HALT_FAILED = "HALT_FAILED"
BROKER_ACK_RECORDED = "BROKER_ACK_RECORDED"

BROKER_CALL_RAISED = "BROKER_CALL_RAISED"
SEND_REFUSED_AFTER_CLAIM = "SEND_REFUSED_AFTER_CLAIM"


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of one attempt. `order_send_called` is True once the broker send was invoked."""

    stage: str
    reason_code: str
    ticket_id: Optional[str]
    order_send_called: bool = False
    reason_codes: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _step_authorization(decision: GuardDecision) -> dict[str, Any]:
    return {"ticket_id": decision.ticket_id, "state": decision.state,
            "authorization_id": decision.authorization_id}


def _stop(stage: str, decision: GuardDecision, *, sent: bool = False) -> DispatchResult:
    return DispatchResult(stage, decision.reason_code, decision.ticket_id, sent,
                          decision.reason_codes or (decision.reason_code,), dict(decision.details))


def _halt_result(decision: GuardDecision, *, sent: bool) -> DispatchResult:
    """Report HALTED only when the append-only lifecycle confirms the persisted HALT state."""
    return _stop(HALTED if decision.state == HALT else HALT_FAILED, decision, sent=sent)


def dispatch_demo_order(
    *,
    guard: GuardedCanonicalAdapter,
    broker: CanonicalBrokerAdapter,
    ticket: Mapping[str, Any],
    market: Optional[MarketEvidence],
    risk_snapshot: Optional[RiskSnapshot],
    account: AccountIdentity,
    authorization_path: str,
    owner_confirmation_id: Optional[str] = None,
    clock: Callable[[], datetime] = _utc_now,
    scope_config_path: Optional[str] = None,
    **scope_paths: Any,
) -> DispatchResult:
    """Attempt exactly one guarded DEMO order for `ticket`. Refusals never reach the broker.

    `scope_config_path` / `scope_paths` must be the same paths the guard was built with.
    `owner_confirmation_id` is the id of the owner's Confirm for this ticket (required by the guard
    while the scope's ``per_order_confirm_required`` is true).
    """
    ticket_id = str(ticket.get("ticket_id") or "") or None
    now = clock()
    try:
        scope = resolve_ticket_scope_policy(ticket, config_path=scope_config_path, **scope_paths)
    except ScopePolicyError as exc:
        return DispatchResult(SCOPE_REFUSED, exc.reason_code, ticket_id, reason_codes=(exc.reason_code,))
    if not scope.enabled:
        return DispatchResult(SCOPE_REFUSED, "EXECUTION_DISABLED", ticket_id, reason_codes=("EXECUTION_DISABLED",))

    standing = load_standing_authorization(scope, ticket, path=authorization_path, now_utc=now)
    if not standing.authorized or not standing.decision_id:
        return DispatchResult(AUTHORIZATION_REFUSED, standing.reason_code, ticket_id,
                              reason_codes=(standing.reason_code,))

    base = build_authority(
        ticket=ticket, scope=scope, market=market, risk_snapshot=risk_snapshot, now_utc=now,
        authority_id=uuid.uuid4().hex, account=account, authorization_path=authorization_path,
        authorization_decision_id=standing.decision_id, owner_confirmation_id=owner_confirmation_id,
    )

    def fresh(at: datetime) -> ExecutionAuthority:
        # Every guarded call needs its own single-use authority id; the evidence ids stay bound.
        return replace(base, authority_id=uuid.uuid4().hex, issued_at_utc=at)

    check = guard.authorize_order_check(authority=base, ticket=ticket, market=market,
                                        risk_snapshot=risk_snapshot, now_utc=now)
    if not check.admitted:
        return _stop(ORDER_CHECK_REFUSED, check)
    account_mode = (check.details.get("account") or {}).get("trade_mode")

    try:
        checked = broker.check_order(authority=base, authorization=_step_authorization(check),
                                     ticket=ticket, account_mode=account_mode)
    except Exception as exc:  # noqa: BLE001 -- nothing was sent; the AUTHORIZED step just expires
        return DispatchResult(ORDER_CHECK_BROKER_REFUSED, BROKER_CALL_RAISED, ticket_id,
                              reason_codes=(BROKER_CALL_RAISED,), details={"error_class": type(exc).__name__})
    if not isinstance(checked, Mapping) or checked.get("refused"):
        reason = (checked or {}).get("reason_code") if isinstance(checked, Mapping) else None
        reason = reason or "BROKER_RESULT_MISSING"
        return DispatchResult(ORDER_CHECK_BROKER_REFUSED, reason, ticket_id, reason_codes=(reason,))

    at = clock()
    recorded = guard.record_order_checked(authority=fresh(at), ticket=ticket, checked_order=checked,
                                          now_utc=at, authorization_id=check.authorization_id)
    if not recorded.admitted:
        return _stop(ORDER_CHECK_RECORD_REFUSED, recorded)

    at = clock()
    send_authority = fresh(at)
    send = guard.authorize_order_send(authority=send_authority, ticket=ticket, checked_order=checked,
                                      now_utc=at, authorization_id=check.authorization_id)
    if not send.admitted:
        return _stop(ORDER_SEND_REFUSED, send)

    try:
        result: Any = broker.send_order(authority=send_authority, authorization=_step_authorization(send),
                                       ticket=ticket, checked_order=checked, account_mode=account_mode)
    except Exception as exc:  # noqa: BLE001 -- outcome unknown: HALT, never resend
        result = {"unknown_outcome": True, "reason_code": BROKER_CALL_RAISED, "error_class": type(exc).__name__}

    at = clock()
    if not isinstance(result, Mapping) or result.get("unknown_outcome") or result.get("refused"):
        # The durable SENDING claim already exists: any outcome but an acknowledged send halts.
        reason = "BROKER_RESULT_MISSING"
        if isinstance(result, Mapping):
            reason = result.get("reason_code") or reason
            if result.get("refused"):
                reason = f"{SEND_REFUSED_AFTER_CLAIM}:{reason}"
        halted = guard.halt(authority=fresh(at), ticket_id=send_authority.ticket_id, reason_code=reason, now_utc=at)
        return _halt_result(halted, sent=not (isinstance(result, Mapping) and result.get("refused")))

    ack = guard.record_broker_ack(authority=fresh(at), send_result=result, now_utc=at,
                                  authorization_id=send.authorization_id)
    if not ack.admitted and ack.state != HALT:
        # A real send whose acknowledgement could not be recorded is an unknown outcome too.
        at = clock()
        ack = guard.halt(authority=fresh(at), ticket_id=send_authority.ticket_id,
                         reason_code=f"BROKER_ACK_NOT_RECORDED:{ack.reason_code}", now_utc=at)
    if not ack.admitted:
        return _halt_result(ack, sent=True)
    return DispatchResult(BROKER_ACK_RECORDED, ack.reason_code, ack.ticket_id, True, (),
                          {**dict(ack.details), "send_result": dict(result)})
