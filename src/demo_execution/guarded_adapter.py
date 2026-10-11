"""Authority-guarded boundary in front of the host's canonical C11 execution adapter.

This module owns refusal, not submission. It contains no MT5 import and no order call site
(``tests/test_manual_ticket_report_and_boundary.py::test_no_order_send_call_site_anywhere_in_repo``
scans for them): the host supplies both the read-only live account read and the already-reviewed
canonical adapter that performs the broker operations
(:class:`demo_execution.broker_adapter.CanonicalBrokerAdapter`).

Every call takes an :class:`~demo_execution.authority.ExecutionAuthority` and re-validates it
here, from primary sources, before anything else happens -- a caller's own gate results are never
sufficient on their own:

* the committed scope is re-loaded on every call and its ``enabled`` flag must be true;
* the authority's ticket id, strategy id/version, symbol, session, setup branch, direction, logic
  identity and reserved magic must equal the scope and the ticket;
* the DEMO account identity (login suffix + server + trade_mode) is read live from the host
  inside the guarded step, immediately before the order_check authorization is issued, and again
  before a send is authorized;
* the host-local standing authorization record is re-read and re-validated, and its decision id
  must equal the one the authority names;
* while per-order confirmation is required, a bound, in-window, single-use owner confirmation must
  exist in the append-only ledger -- consumed before a send is authorized;
* the READY, risk and freshness evidence ids must be present, current, and equal to the digests
  recomputed here from the facts the gates were re-run on;
* the duplicate-ticket ledger check runs before order_check, not only before send.

Each accepted step appends one lifecycle evidence row
(:mod:`demo_execution.lifecycle`); an unknown outcome HALTs and must be reconciled, and is never
resubmitted.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from demo_execution.admission import MarketEvidence, evaluate_pre_send_gates
from demo_execution.authority import (
    AUTHORITY_REUSED,
    AUTHORIZATION_DECISION_ID_MISMATCH,
    ExecutionAuthority,
    account_identity_payload,
    authority_window,
    evidence_digest,
    evidence_id_map,
    per_order_confirm_required,
    validate_authority_binding,
    validate_authority_shape,
    validate_authorization_path,
    validate_confirmation_evidence,
    validate_evidence_against_trail,
    validate_evidence_refs,
    validate_live_account,
)
from demo_execution.authorization import load_standing_authorization
from demo_execution.idempotency import ExecutionLedger
from demo_execution.lifecycle import (
    AUTHORIZED,
    BROKER_ACK,
    CHECKED,
    CLOSED,
    HALT,
    HALT_UNKNOWN_RESULT,
    LIFECYCLE_ALREADY_RECONCILED,
    LIFECYCLE_ORDER_INVALID,
    POSITION_TRACKED,
    RECONCILED,
    SENT,
    ExecutionLifecycle,
    LifecycleTrail,
    TransitionResult,
)
from demo_execution.risk import RiskSnapshot
from demo_execution.scope import ScopePolicy, ScopePolicyError, load_scope_policy
from ticket_store.store import TicketStore

LiveAccountReader = Callable[[], Mapping[str, Any]]

ACCOUNT_IDENTITY_UNAVAILABLE = "ACCOUNT_IDENTITY_UNAVAILABLE"
AUTHORIZATION_ID_MISMATCH = "AUTHORIZATION_ID_MISMATCH"
ORDER_CHECK_AUTHORIZATION_EXPIRED = "ORDER_CHECK_AUTHORIZATION_EXPIRED"
ORDER_CHECK_EVIDENCE_MISSING = "ORDER_CHECK_EVIDENCE_MISSING"
ORDER_SEND_AUTHORIZATION_EXPIRED = "ORDER_SEND_AUTHORIZATION_EXPIRED"
CHECKED_ORDER_MISMATCH = "CHECKED_ORDER_MISMATCH"
BROKER_ACK_EVIDENCE_MISSING = "BROKER_ACK_EVIDENCE_MISSING"
POSITION_EVIDENCE_MISSING = "POSITION_EVIDENCE_MISSING"
CLOSE_EVIDENCE_MISSING = "CLOSE_EVIDENCE_MISSING"
RECONCILIATION_EVIDENCE_INVALID = "RECONCILIATION_EVIDENCE_INVALID"
TICKET_ID_MISSING = "TICKET_ID_MISSING"
GUARD_REFUSED = "GUARD_REFUSED"

# Broker identifier spellings the canonical host adapter may return. The guard never invents an
# identifier: when none of these is present the outcome is unknown, so it HALTs.
_ORDER_ID_KEYS = ("broker_order_id", "order_id", "order")
_DEAL_ID_KEYS = ("broker_deal_id", "deal_id", "deal")


@dataclass(frozen=True)
class GuardDecision:
    """Typed result of a guarded call. `reason_codes` keeps every independent refusal reason."""

    admitted: bool
    reason_code: str
    state: Optional[str] = None
    ticket_id: Optional[str] = None
    authorization_id: Optional[str] = None
    reason_codes: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)


def _refused(reasons: tuple[str, ...], details: Mapping[str, Any], *, ticket_id: Optional[str] = None,
             state: Optional[str] = None) -> GuardDecision:
    ordered = tuple(dict.fromkeys(reasons)) or (GUARD_REFUSED,)
    return GuardDecision(False, ordered[0], state, ticket_id, None, ordered, dict(details))


def _first_identifier(source: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    return None


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


class GuardedCanonicalAdapter:
    """Refuses every call unless a re-validated execution authority authorizes exactly that call."""

    def __init__(
        self,
        *,
        ticket_store: TicketStore,
        live_account_reader: LiveAccountReader,
        scope_config_path: Optional[str] = None,
        repo_root: Optional[str] = None,
        registry_path: Optional[str] = None,
        broker_symbol_map_path: Optional[str] = None,
        ready_authority_config_path: Optional[str] = None,
        owner_decision_register_path: Optional[str] = None,
        host_magic_registry_path: Optional[str] = None,
        authorization_path: Optional[str] = None,
    ) -> None:
        if not isinstance(ticket_store, TicketStore):
            raise ValueError("ticket_store must be the append-only TICKET_STORE_V1 writer")
        if not callable(live_account_reader):
            raise ValueError("live_account_reader must be a callable host read of account_info()")
        self._store = ticket_store
        self._account_reader = live_account_reader
        self._authorization_path = authorization_path
        self._scope_paths: dict[str, Any] = {
            "config_path": scope_config_path,
            "repo_root": repo_root,
            "registry_path": registry_path,
            "broker_symbol_map_path": broker_symbol_map_path,
            "ready_authority_config_path": ready_authority_config_path,
            "owner_decision_register_path": owner_decision_register_path,
            "host_magic_registry_path": host_magic_registry_path,
        }

    # ------------------------------------------------------------------ re-validation
    def _load_scope(self) -> tuple[Optional[ScopePolicy], Optional[str]]:
        """The scope is re-read from the committed config on every call, never taken on trust."""
        try:
            return load_scope_policy(**self._scope_paths), None
        except ScopePolicyError as exc:
            return None, exc.reason_code

    def _read_live_account(self) -> Optional[Mapping[str, Any]]:
        try:
            read = self._account_reader()
        except Exception:  # a host read that raises is an unavailable identity, never a default
            return None
        return read if isinstance(read, Mapping) else None

    def _lifecycle(self) -> ExecutionLifecycle:
        return ExecutionLifecycle(self._store)

    def _ledger(self) -> ExecutionLedger:
        return ExecutionLedger(self._store)

    def _revalidate_identity(
        self,
        authority: Any,
        *,
        ticket: Optional[Mapping[str, Any]],
        now_utc: datetime,
        phase: str,
        require_trail_evidence: bool,
        allow_halted: bool = False,
    ) -> tuple[list[str], dict[str, Any], Optional[ScopePolicy], LifecycleTrail]:
        """Checks that apply to every guarded call, in a fixed order.

        `allow_halted` is set only by halt/reconcile: a halted or already-reconciled trail must
        still be reconcilable, because refusing to record the truth leaves the account worse off.
        """
        details: dict[str, Any] = {"phase": phase}
        shape = validate_authority_shape(authority)
        if shape:
            return list(shape), details, None, LifecycleTrail(())
        assert isinstance(authority, ExecutionAuthority)
        details["ticket_id"] = authority.ticket_id
        scope, scope_reason = self._load_scope()
        if scope is None or scope_reason is not None:
            return [scope_reason or "EXECUTION_SCOPE_INVALID"], details, None, LifecycleTrail(())
        details["scope_enabled"] = scope.enabled
        reasons: list[str] = []
        if not scope.enabled:
            reasons.append("EXECUTION_DISABLED")
        reasons.extend(validate_authority_binding(authority, scope, ticket, now_utc=now_utc))
        reasons.extend(validate_authorization_path(authority, scope, self._authorization_path))

        trail = self._lifecycle().trail(authority.ticket_id)
        if trail.reason_code is not None:
            reasons.append(trail.reason_code)
            details["lifecycle_state"] = None
        else:
            details["lifecycle_state"] = trail.current
            if any(row.authority_id == authority.authority_id for row in trail.states):
                reasons.append(AUTHORITY_REUSED)
            if not allow_halted:
                if trail.current == HALT:
                    reasons.append(HALT_UNKNOWN_RESULT)
                elif trail.current == RECONCILED:
                    reasons.append(LIFECYCLE_ALREADY_RECONCILED)
            authorized = trail.state_row(AUTHORIZED)
            if authorized is not None and require_trail_evidence:
                reasons.extend(validate_evidence_against_trail(authority, authorized.evidence))
        return reasons, details, scope, trail

    def _revalidate_pre_trade(
        self,
        authority: ExecutionAuthority,
        scope: ScopePolicy,
        *,
        ticket: Mapping[str, Any],
        market: Optional[MarketEvidence],
        risk_snapshot: Optional[RiskSnapshot],
        now_utc: datetime,
        require_gates: bool,
        require_consumed_confirmation: bool,
        details: dict[str, Any],
    ) -> list[str]:
        """Live account, per-order confirmation, evidence, the gates, standing authorization."""
        reasons: list[str] = []
        live = self._read_live_account()
        if live is None:
            reasons.append(ACCOUNT_IDENTITY_UNAVAILABLE)
        else:
            reasons.extend(validate_live_account(live, authority, scope, now_utc=now_utc))
            details["account"] = account_identity_payload(live, now_utc)

        # The owner confirmation is validated before the gates run, because the canonical gate
        # consumes it: a call that is going to be refused must not spend the owner's single-use
        # confirmation, and a send must see it already consumed.
        confirmation_ok = True
        if per_order_confirm_required(scope):
            confirmation_reasons = validate_confirmation_evidence(
                self._store, authority, ticket, now_utc=now_utc,
                require_consumed=require_consumed_confirmation,
            )
            details["owner_confirmation_id"] = authority.owner_confirmation_id
            if confirmation_reasons:
                reasons.extend(confirmation_reasons)
                confirmation_ok = False
        else:
            details["owner_confirmation"] = "NOT_REQUIRED_BY_COMMITTED_SCOPE"

        if require_gates and confirmation_ok:
            reasons.extend(validate_evidence_refs(authority, scope, ticket, market, risk_snapshot,
                                                  now_utc=now_utc))
            # The store is handed to the gates so the canonical single-use owner confirmation is
            # consumed by its own sanctioned writer, and so the gates' duplicate ledger check sees
            # the same append-only store this guard writes evidence to.
            gates = evaluate_pre_send_gates(
                ticket, market, risk_snapshot, now_utc=now_utc,
                authorization_path=authority.authorization_path, scope=scope,
                ticket_store=self._store,
            )
            if gates.admitted:
                details["planned_volume"] = gates.volume
                details["planned_risk_amount"] = gates.risk_amount
                details["planned_risk_pct"] = gates.details.get("risk_pct")
            else:
                reasons.append(gates.reason_code)
                details["gate_block_reasons"] = list(gates.details.get("block_reasons") or [])
        elif require_gates:
            details["gates"] = "NOT_EVALUATED_OWNER_CONFIRMATION_REFUSED"

        authorization = load_standing_authorization(
            scope, ticket, path=authority.authorization_path, now_utc=now_utc,
        )
        if not authorization.authorized:
            reasons.append(authorization.reason_code)
        else:
            details["authorization_decision_id"] = authorization.decision_id
            if authorization.decision_id != authority.authorization_decision_id:
                reasons.append(AUTHORIZATION_DECISION_ID_MISMATCH)
        return reasons

    def _authorization_expiry(self, scope: ScopePolicy, now_utc: datetime) -> str:
        now = _as_utc(now_utc) or datetime.now(timezone.utc)
        return (now + authority_window(scope)).isoformat()

    def _expired(self, recorded_at: Optional[datetime], scope: ScopePolicy, now_utc: datetime) -> bool:
        recorded = _as_utc(recorded_at)
        now = _as_utc(now_utc)
        return recorded is None or now is None or now - recorded > authority_window(scope)

    # ------------------------------------------------------------------ broker-facing steps
    def authorize_order_check(
        self,
        *,
        authority: Any,
        ticket: Mapping[str, Any],
        market: Optional[MarketEvidence],
        risk_snapshot: Optional[RiskSnapshot],
        now_utc: datetime,
    ) -> GuardDecision:
        """Re-validate everything, then issue the single-use authorization for one order_check.

        The live DEMO account read happens here, inside this call, immediately before the host may
        run order_check; the duplicate-ticket ledger check happens here too, not only before send.
        """
        reasons, details, scope, trail = self._revalidate_identity(
            authority, ticket=ticket, now_utc=now_utc, phase="ORDER_CHECK", require_trail_evidence=False,
        )
        if scope is None:
            return _refused(tuple(reasons), details, ticket_id=getattr(authority, "ticket_id", None))
        assert isinstance(authority, ExecutionAuthority)
        if trail.reason_code is None and trail.current is not None:
            # order_check is the first broker-facing step: an existing trail means this ticket has
            # already been authorized, halted or reconciled, and is never re-authorized.
            reasons.append(LIFECYCLE_ORDER_INVALID)
        # Duplicate ticket id: checked against the ledger before order_check, not only before send.
        claim = self._ledger().inspect(authority.ticket_id)
        details["ledger_check"] = claim.reason_code
        if not claim.available:
            reasons.append(claim.reason_code)
            details["prior_claim_state"] = claim.prior_state
        if reasons:
            # A refused ticket never reaches the live account read or the gate evaluation.
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id)
        reasons.extend(self._revalidate_pre_trade(
            authority, scope, ticket=ticket, market=market, risk_snapshot=risk_snapshot,
            now_utc=now_utc, require_gates=True, require_consumed_confirmation=False, details=details,
        ))
        if reasons:
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id)

        authorization_id = uuid.uuid4().hex
        expires_at = self._authorization_expiry(scope, now_utc)
        evidence = {
            **evidence_id_map(authority),
            "authorization_decision_id": authority.authorization_decision_id,
            "owner_confirmation_id": authority.owner_confirmation_id,
            "account": details.get("account"),
            "planned_volume": details.get("planned_volume"),
            "planned_risk_amount": details.get("planned_risk_amount"),
            "planned_risk_pct": details.get("planned_risk_pct"),
            "expires_at_utc": expires_at,
        }
        recorded = self._lifecycle().append(
            authority.ticket_id, AUTHORIZED, now_utc=now_utc, authority_id=authority.authority_id,
            authorization_id=authorization_id, evidence=evidence,
        )
        if not recorded.recorded:
            return _refused((recorded.reason_code,), details, ticket_id=authority.ticket_id)
        return GuardDecision(True, "ORDER_CHECK_AUTHORIZED", AUTHORIZED, authority.ticket_id,
                             authorization_id, (), {**details, "outcome_id": recorded.details.get("outcome_id"),
                                                    "expires_at_utc": expires_at})

    def record_order_checked(
        self,
        *,
        authority: Any,
        ticket: Mapping[str, Any],
        checked_order: Optional[Mapping[str, Any]],
        now_utc: datetime,
        authorization_id: Optional[str] = None,
    ) -> GuardDecision:
        """Record the order_check result. Refuses an expired authorization or a missing result."""
        reasons, details, scope, trail = self._revalidate_identity(
            authority, ticket=ticket, now_utc=now_utc, phase="ORDER_CHECKED", require_trail_evidence=True,
        )
        if scope is None:
            return _refused(tuple(reasons), details, ticket_id=getattr(authority, "ticket_id", None))
        assert isinstance(authority, ExecutionAuthority)
        prior = trail.state_row(AUTHORIZED)
        if prior is None or prior.authorization_id is None:
            reasons.append(LIFECYCLE_ORDER_INVALID)
        else:
            if authorization_id is not None and authorization_id != prior.authorization_id:
                reasons.append(AUTHORIZATION_ID_MISMATCH)
            if self._expired(prior.recorded_at_utc, scope, now_utc):
                reasons.append(ORDER_CHECK_AUTHORIZATION_EXPIRED)
        if not isinstance(checked_order, Mapping) or not checked_order:
            reasons.append(ORDER_CHECK_EVIDENCE_MISSING)
        reasons.extend(self._revalidate_pre_trade(
            authority, scope, ticket=ticket, market=None, risk_snapshot=None, now_utc=now_utc,
            require_gates=False, require_consumed_confirmation=False, details=details,
        ))
        if reasons:
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id,
                            state=trail.current)
        assert prior is not None
        checked_digest = evidence_digest(dict(checked_order))
        expires_at = self._authorization_expiry(scope, now_utc)
        recorded = self._lifecycle().append(
            authority.ticket_id, CHECKED, now_utc=now_utc, authority_id=authority.authority_id,
            authorization_id=prior.authorization_id,
            evidence={**evidence_id_map(authority), "checked_order_sha256": checked_digest,
                      "expires_at_utc": expires_at},
        )
        if not recorded.recorded:
            return _refused((recorded.reason_code,), details, ticket_id=authority.ticket_id,
                            state=trail.current)
        return GuardDecision(True, "ORDER_CHECK_RECORDED", CHECKED, authority.ticket_id,
                             prior.authorization_id, (),
                             {**details, "checked_order_sha256": checked_digest,
                              "expires_at_utc": expires_at,
                              "outcome_id": recorded.details.get("outcome_id")})

    def authorize_order_send(
        self,
        *,
        authority: Any,
        ticket: Mapping[str, Any],
        checked_order: Optional[Mapping[str, Any]],
        now_utc: datetime,
        authorization_id: Optional[str] = None,
    ) -> GuardDecision:
        """Persist the send claim and issue the single-use authorization for one order_send.

        The account is DEMO-read live again here, the standing authorization is re-read (a
        revocation or emergency stop between check and send blocks the send), the per-order
        confirmation must already be consumed, and the checked order must be byte-identical to the
        one order_check returned.
        """
        reasons, details, scope, trail = self._revalidate_identity(
            authority, ticket=ticket, now_utc=now_utc, phase="ORDER_SEND", require_trail_evidence=True,
        )
        if scope is None:
            return _refused(tuple(reasons), details, ticket_id=getattr(authority, "ticket_id", None))
        assert isinstance(authority, ExecutionAuthority)
        checked_row = trail.state_row(CHECKED)
        if checked_row is None or checked_row.authorization_id is None:
            reasons.append(LIFECYCLE_ORDER_INVALID)
        else:
            if authorization_id is not None and authorization_id != checked_row.authorization_id:
                reasons.append(AUTHORIZATION_ID_MISMATCH)
            if self._expired(checked_row.recorded_at_utc, scope, now_utc):
                reasons.append(ORDER_SEND_AUTHORIZATION_EXPIRED)
            if not isinstance(checked_order, Mapping) or not checked_order \
                    or checked_row.evidence.get("checked_order_sha256") != evidence_digest(dict(checked_order)):
                reasons.append(CHECKED_ORDER_MISMATCH)
        claim = self._ledger().inspect(authority.ticket_id)
        details["ledger_check"] = claim.reason_code
        if not claim.available:
            reasons.append(claim.reason_code)
            details["prior_claim_state"] = claim.prior_state
        if reasons:
            # Nothing is claimed and no account is read for a send that is already refused.
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id, state=trail.current)
        reasons.extend(self._revalidate_pre_trade(
            authority, scope, ticket=ticket, market=None, risk_snapshot=None, now_utc=now_utc,
            require_gates=False, require_consumed_confirmation=True, details=details,
        ))
        if reasons:
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id, state=trail.current)

        # The durable claim is written before the lifecycle evidence: a crash in between leaves a
        # SENDING row, and every later inspection of that ticket halts instead of resubmitting.
        reserved = self._ledger().reserve_before_send(
            authority.ticket_id, strategy_id=scope.strategy_id, symbol=scope.symbol,
            logic_identity=scope.logic_identity, now_utc=now_utc,
        )
        if not reserved.available:
            return _refused((reserved.reason_code,), details, ticket_id=authority.ticket_id,
                            state=trail.current)
        send_authorization_id = uuid.uuid4().hex
        expires_at = self._authorization_expiry(scope, now_utc)
        assert checked_row is not None
        recorded = self._lifecycle().append(
            authority.ticket_id, SENT, now_utc=now_utc, authority_id=authority.authority_id,
            authorization_id=send_authorization_id,
            evidence={**evidence_id_map(authority),
                      "checked_order_sha256": checked_row.evidence.get("checked_order_sha256"),
                      "check_authorization_id": checked_row.authorization_id,
                      "account": details.get("account"),
                      "expires_at_utc": expires_at},
        )
        if not recorded.recorded:
            return _refused((recorded.reason_code,), {**details, "claim": "SENDING_PERSISTED",
                                                      "action_required": "RECONCILE"},
                            ticket_id=authority.ticket_id, state=trail.current)
        return GuardDecision(True, "ORDER_SEND_AUTHORIZED", SENT, authority.ticket_id,
                             send_authorization_id, (),
                             {**details, "claim": reserved.reason_code, "expires_at_utc": expires_at,
                              "outcome_id": recorded.details.get("outcome_id")})

    def record_broker_ack(
        self,
        *,
        authority: Any,
        send_result: Optional[Mapping[str, Any]],
        now_utc: datetime,
        authorization_id: Optional[str] = None,
    ) -> GuardDecision:
        """Record the broker's acknowledgement. No broker identifier means an unknown outcome."""
        reasons, details, scope, trail = self._revalidate_identity(
            authority, ticket=None, now_utc=now_utc, phase="BROKER_ACK", require_trail_evidence=True,
        )
        if scope is None:
            return _refused(tuple(reasons), details, ticket_id=getattr(authority, "ticket_id", None))
        assert isinstance(authority, ExecutionAuthority)
        sent_row = trail.state_row(SENT)
        if sent_row is None or sent_row.authorization_id is None:
            reasons.append(LIFECYCLE_ORDER_INVALID)
        elif authorization_id is not None and authorization_id != sent_row.authorization_id:
            reasons.append(AUTHORIZATION_ID_MISMATCH)
        send_window_expired = sent_row is not None and self._expired(sent_row.recorded_at_utc, scope, now_utc)
        order_id = _first_identifier(send_result, _ORDER_ID_KEYS) if isinstance(send_result, Mapping) else None
        deal_id = _first_identifier(send_result, _DEAL_ID_KEYS) if isinstance(send_result, Mapping) else None
        if reasons:
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id, state=trail.current)
        if send_window_expired:
            # A send was authorized, its window passed and no outcome was reported: unknown.
            return self.halt(authority=authority, ticket_id=authority.ticket_id,
                             reason_code="SEND_ACK_WINDOW_EXPIRED", now_utc=now_utc)
        if not order_id:
            # The broker was asked to submit and no order identifier came back: unknown outcome.
            return self.halt(authority=authority, ticket_id=authority.ticket_id,
                             reason_code="BROKER_ACK_IDENTIFIER_MISSING", now_utc=now_utc)
        evidence = {**evidence_id_map(authority),
                    "retcode": send_result.get("retcode") if isinstance(send_result, Mapping) else None,
                    "send_result_sha256": evidence_digest(dict(send_result or {}))}
        recorded = self._lifecycle().append(
            authority.ticket_id, BROKER_ACK, now_utc=now_utc, authority_id=authority.authority_id,
            authorization_id=sent_row.authorization_id if sent_row else None,
            broker_order_id=order_id, broker_deal_id=deal_id, evidence=evidence,
        )
        if not recorded.recorded:
            return _refused((recorded.reason_code,), details, ticket_id=authority.ticket_id,
                            state=trail.current)
        return GuardDecision(True, "BROKER_ACK_RECORDED", BROKER_ACK, authority.ticket_id,
                             sent_row.authorization_id if sent_row else None, (),
                             {**details, "broker_order_id": order_id, "broker_deal_id": deal_id,
                              "outcome_id": recorded.details.get("outcome_id")})

    # ------------------------------------------------------------------ post-trade evidence
    def record_position_tracked(
        self,
        *,
        authority: Any,
        broker_position_id: Optional[str],
        now_utc: datetime,
    ) -> GuardDecision:
        return self._post_trade_transition(
            authority, POSITION_TRACKED, now_utc=now_utc, phase="POSITION_TRACKED",
            broker_position_id=broker_position_id,
            missing_reason=POSITION_EVIDENCE_MISSING,
        )

    def record_position_closed(
        self,
        *,
        authority: Any,
        broker_deal_id: Optional[str],
        now_utc: datetime,
        broker_order_id: Optional[str] = None,
    ) -> GuardDecision:
        return self._post_trade_transition(
            authority, CLOSED, now_utc=now_utc, phase="CLOSED", broker_deal_id=broker_deal_id,
            broker_order_id=broker_order_id, missing_reason=CLOSE_EVIDENCE_MISSING,
        )

    def _post_trade_transition(
        self,
        authority: Any,
        state: str,
        *,
        now_utc: datetime,
        phase: str,
        missing_reason: str,
        broker_order_id: Optional[str] = None,
        broker_deal_id: Optional[str] = None,
        broker_position_id: Optional[str] = None,
    ) -> GuardDecision:
        """Record a post-trade state. Never blocked by revocation: an open position must stay tracked."""
        reasons, details, scope, trail = self._revalidate_identity(
            authority, ticket=None, now_utc=now_utc, phase=phase, require_trail_evidence=True,
        )
        if scope is None:
            return _refused(tuple(reasons), details, ticket_id=getattr(authority, "ticket_id", None))
        assert isinstance(authority, ExecutionAuthority)
        if state == POSITION_TRACKED and not (isinstance(broker_position_id, str) and broker_position_id.strip()):
            reasons.append(missing_reason)
        if state == CLOSED and not (isinstance(broker_deal_id, str) and broker_deal_id.strip()):
            reasons.append(missing_reason)
        if reasons:
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id, state=trail.current)
        recorded = self._lifecycle().append(
            authority.ticket_id, state, now_utc=now_utc, authority_id=authority.authority_id,
            broker_order_id=broker_order_id, broker_deal_id=broker_deal_id,
            broker_position_id=broker_position_id, evidence=evidence_id_map(authority),
        )
        return self._transition_decision(recorded, details, authority.ticket_id, state, trail.current)

    def reconcile(
        self,
        *,
        authority: Any,
        reconciliation: Optional[Mapping[str, Any]],
        now_utc: datetime,
    ) -> GuardDecision:
        """Record the terminal reconciliation. An UNKNOWN result is refused and stays HALTed."""
        reasons, details, scope, trail = self._revalidate_identity(
            authority, ticket=None, now_utc=now_utc, phase="RECONCILE", require_trail_evidence=True,
            allow_halted=True,
        )
        if scope is None:
            return _refused(tuple(reasons), details, ticket_id=getattr(authority, "ticket_id", None))
        assert isinstance(authority, ExecutionAuthority)
        if not isinstance(reconciliation, Mapping) or reconciliation.get("reconciled") is not True \
                or not isinstance(reconciliation.get("terminal_result"), str) \
                or not reconciliation["terminal_result"].strip() \
                or reconciliation["terminal_result"].strip().upper() == "UNKNOWN":
            reasons.append(RECONCILIATION_EVIDENCE_INVALID)
        if reasons:
            return _refused(tuple(reasons), details, ticket_id=authority.ticket_id, state=trail.current)
        assert isinstance(reconciliation, Mapping)
        order_id = _first_identifier(reconciliation, _ORDER_ID_KEYS)
        deal_id = _first_identifier(reconciliation, _DEAL_ID_KEYS)
        position_id = _first_identifier(reconciliation, ("broker_position_id", "position_id", "position"))
        recorded = self._lifecycle().append(
            authority.ticket_id, RECONCILED, now_utc=now_utc, authority_id=authority.authority_id,
            broker_order_id=order_id, broker_deal_id=deal_id, broker_position_id=position_id,
            terminal_result=str(reconciliation["terminal_result"]).strip(),
            evidence={**evidence_id_map(authority),
                      "reconciliation_sha256": evidence_digest(dict(reconciliation))},
        )
        if not recorded.recorded:
            return self._transition_decision(recorded, details, authority.ticket_id, RECONCILED,
                                             trail.current)
        # The claim ledger is reconciled only when no unknown marker was written. After an unknown
        # outcome the halt is permanent: reconciliation records the truth, it never re-opens a send.
        claim = self._ledger().inspect(authority.ticket_id)
        details["ledger_check"] = claim.reason_code
        if claim.reason_code == "HALT_UNCERTAIN_SEND":
            settled = self._ledger().record_reconciled(
                authority.ticket_id, reconciliation=reconciliation, now_utc=now_utc,
            )
            details["claim_reconciliation"] = settled.reason_code
        else:
            details["claim_reconciliation"] = claim.reason_code
        details["resubmission"] = "NEVER"
        return GuardDecision(True, "RECONCILED", RECONCILED, authority.ticket_id, None, (),
                             {**details, "outcome_id": recorded.details.get("outcome_id"),
                              "broker_order_id": order_id, "broker_deal_id": deal_id})

    def halt(
        self,
        *,
        authority: Any,
        ticket_id: str,
        reason_code: str,
        now_utc: datetime,
    ) -> GuardDecision:
        """Unknown outcome: HALT, mark the claim uncertain when one exists, and require reconcile."""
        reasons, details, _scope, trail = self._revalidate_identity(
            authority, ticket=None, now_utc=now_utc, phase="HALT", require_trail_evidence=False,
            allow_halted=True,
        )
        resolved_ticket = ticket_id if isinstance(ticket_id, str) and ticket_id.strip() \
            else getattr(authority, "ticket_id", None)
        if not (isinstance(resolved_ticket, str) and resolved_ticket.strip()):
            return _refused(tuple(reasons) + (TICKET_ID_MISSING,), details)
        if not (isinstance(reason_code, str) and reason_code.strip()):
            return _refused(tuple(reasons) + ("HALT_REASON_MISSING",), details, ticket_id=resolved_ticket)
        if reasons:
            return _refused(tuple(reasons), details, ticket_id=resolved_ticket, state=trail.current)
        recorded = self._lifecycle().append(
            resolved_ticket, HALT, now_utc=now_utc,
            authority_id=getattr(authority, "authority_id", "") or "",
            reason_code=reason_code.strip(), evidence={"halted_from": trail.current},
        )
        details["halt_reason"] = reason_code.strip()
        claim = self._ledger().inspect(resolved_ticket)
        details["ledger_check"] = claim.reason_code
        if claim.reason_code == "HALT_UNCERTAIN_SEND":
            unknown = self._ledger().record_unknown(resolved_ticket, reason_code=reason_code.strip(),
                                                    now_utc=now_utc)
            details["claim"] = unknown.reason_code
        details["action_required"] = "RECONCILE"
        details["resubmission"] = "NEVER"
        if not recorded.recorded:
            return _refused((recorded.reason_code,), details, ticket_id=resolved_ticket,
                            state=trail.current)
        return GuardDecision(False, HALT_UNKNOWN_RESULT, HALT, resolved_ticket, None,
                             (HALT_UNKNOWN_RESULT,),
                             {**details, "outcome_id": recorded.details.get("outcome_id")})

    # ------------------------------------------------------------------ helpers
    def _transition_decision(self, recorded: TransitionResult, details: Mapping[str, Any],
                             ticket_id: str, state: str,
                             prior_state: Optional[str]) -> GuardDecision:
        if not recorded.recorded:
            return _refused((recorded.reason_code,), dict(details), ticket_id=ticket_id,
                            state=prior_state)
        return GuardDecision(True, f"{state}_RECORDED", state, ticket_id, None, (),
                             {**details, "outcome_id": recorded.details.get("outcome_id")})

    def trail(self, ticket_id: str) -> LifecycleTrail:
        """Read-only view of the recorded evidence trail for one ticket."""
        return self._lifecycle().trail(ticket_id)
