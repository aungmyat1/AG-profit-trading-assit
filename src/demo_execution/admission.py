"""Broker-free S1/READY/auth/owner-confirm/risk/cost/freshness/idempotency admission."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from demo_execution.authorization import (
    AuthorizationResult,
    load_standing_authorization,
)
from demo_execution.confirmation import check_and_consume_owner_confirmation
from demo_execution.idempotency import ExecutionLedger
from demo_execution.notification import (
    check_notification_failure_policy as check_notification_failure_policy,
)
from demo_execution.notification import (
    notification_gate,
)
from demo_execution.risk import RiskSnapshot, evaluate_risk_caps
from demo_execution.scope import (
    ScopePolicy,
    ScopePolicyError,
    resolve_ticket_scope_policy,
)
from ticket_store.store import TicketStore


@dataclass(frozen=True)
class MarketEvidence:
    """Host-provided quote/bar facts. Constructing this object performs no acquisition."""

    broker_symbol: str
    bid: Optional[float]
    ask: Optional[float]
    observed_at_utc: Optional[datetime]
    data_close_utc: Optional[datetime]


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    reason_code: str
    ticket_id: Optional[str] = None
    volume: Optional[float] = None
    risk_amount: Optional[float] = None
    details: Mapping[str, Any] = field(default_factory=dict)
    block_reasons: tuple[str, ...] = ()


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _blocked(
    reason: str,
    ticket: Optional[Mapping[str, Any]] = None,
    *,
    block_reasons: Optional[list[str] | tuple[str, ...]] = None,
    **details: Any,
) -> AdmissionResult:
    ticket_id = ticket.get("ticket_id") if isinstance(ticket, Mapping) else None
    reasons = tuple(dict.fromkeys((reason, *(block_reasons or ()))))
    details["primary_block_reason"] = reason
    details["block_reasons"] = list(reasons)
    return AdmissionResult(
        False,
        reason,
        ticket_id if isinstance(ticket_id, str) else None,
        details=details,
        block_reasons=reasons,
    )


def check_ticket_scope(ticket: Mapping[str, Any], scope: ScopePolicy) -> tuple[list[str], dict[str, Any]]:
    """Check every scope identity field, preserving their primary/order precedence."""
    reasons: list[str] = []
    details: dict[str, Any] = {}
    ticket_id = ticket.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        reasons.append("TICKET_ID_MISSING")
    if ticket.get("strategy_id") != scope.strategy_id:
        reasons.append("STRATEGY_SCOPE_MISMATCH")
    if str(ticket.get("strategy_version")) != scope.strategy_version:
        reasons.append("STRATEGY_VERSION_SCOPE_MISMATCH")
    if ticket.get("symbol") != scope.symbol:
        reasons.append("SYMBOL_SCOPE_MISMATCH")
    if ticket.get("cycle", ticket.get("session")) != scope.session:
        reasons.append("SESSION_SCOPE_MISMATCH")
    branch = ticket.get("setup")
    if branch is None:
        branch = str(ticket.get("branch") or "").split(":", 1)[0]
    if branch != scope.setup_branch:
        reasons.append("LOGIC_SCOPE_NOT_VERIFIED")
        details["setup_branch"] = branch
    if ticket.get("direction") not in scope.directions:
        reasons.append("DIRECTION_SCOPE_MISMATCH")
    if ticket.get("logic_identity") != scope.logic_identity:
        reasons.append("LOGIC_IDENTITY_MISMATCH")
    declared_broker_symbol = ticket.get("broker_symbol")
    if declared_broker_symbol is None and isinstance(ticket.get("symbol_meta"), Mapping):
        declared_broker_symbol = ticket["symbol_meta"].get("broker_symbol")
    if declared_broker_symbol is not None and declared_broker_symbol != scope.broker_symbol:
        reasons.append("BROKER_SYMBOL_SCOPE_MISMATCH")
    return reasons, details


def check_ticket_ready(ticket: Mapping[str, Any], scope: ScopePolicy) -> tuple[Optional[str], dict[str, Any]]:
    """Apply the existing D6/owner READY gate separately from S1 scope."""
    if ticket.get("decision") != "READY":
        return str(ticket.get("reason_code") or "TICKET_NOT_READY"), {
            "ticket_decision": ticket.get("decision"),
        }

    try:
        from v1_tickets.ready_authority import apply_ready_authority

        checked = apply_ready_authority(
            dict(ticket),
            str(scope.ready_authority_config_path),
            str(scope.registry_path),
            contract_path=str(scope.contract_path),
            owner_register_path=str(scope.owner_decision_register_path),
        )
    except Exception as exc:  # validation errors must not create READY authority
        return "READY_OWNER_BINDING_INVALID", {"error_type": type(exc).__name__}
    if checked.get("decision") != "READY":
        return str(checked.get("reason_code") or "READY_OWNER_BINDING_BLOCKED"), {
            "suppressed_decision": checked.get("suppressed_decision"),
            "ready_authority": checked.get("ready_authority"),
        }
    return None, {"ready_owner_binding": "PASS"}


def check_ticket_scope_and_ready(ticket: Mapping[str, Any], scope: ScopePolicy) -> tuple[Optional[str], dict[str, Any]]:
    """Compatibility helper that reports scope before READY, as the gate order requires."""
    scope_reasons, scope_details = check_ticket_scope(ticket, scope)
    if scope_reasons:
        return scope_reasons[0], scope_details
    return check_ticket_ready(ticket, scope)


def check_cost_gate(ticket: Mapping[str, Any], market: Optional[MarketEvidence],
                    scope: ScopePolicy) -> tuple[Optional[str], dict[str, Any]]:
    """Use current host-supplied spread/price facts and the S1 contract's existing limits."""
    if market is None:
        return "COST_EVIDENCE_MISSING", {}
    if market.broker_symbol != scope.broker_symbol:
        return "BROKER_SYMBOL_SCOPE_MISMATCH", {}
    bid, ask = market.bid, market.ask
    if (isinstance(bid, bool) or isinstance(ask, bool) or not isinstance(bid, (int, float))
            or not isinstance(ask, (int, float)) or not math.isfinite(float(bid))
            or not math.isfinite(float(ask)) or float(bid) <= 0 or float(ask) < float(bid)):
        return "MARKET_QUOTE_INVALID", {}
    entry = ticket.get("entry")
    stop = ticket.get("stop_loss", ticket.get("sl"))
    if (isinstance(entry, bool) or isinstance(stop, bool) or not isinstance(entry, (int, float))
            or not isinstance(stop, (int, float)) or not math.isfinite(float(entry))
            or not math.isfinite(float(stop)) or float(entry) <= 0 or float(stop) <= 0
            or abs(float(entry) - float(stop)) <= 0):
        return "RISK_TICKET_GEOMETRY_INVALID", {}
    spread = float(ask) - float(bid)
    spread_pips = spread / scope.pip_size
    spread_fraction = spread / abs(float(entry) - float(stop))
    if spread_pips > scope.max_spread_allowed_pips + 1e-12:
        return "COST_SPREAD_LIMIT", {"spread_pips": spread_pips}
    if spread_fraction > scope.max_spread_fraction_of_stop + 1e-12:
        return "COST_STOP_FRACTION_LIMIT", {"spread_risk_fraction": spread_fraction}
    point = scope.point_size
    executable_price = float(ask) if ticket.get("direction") == "LONG" else float(bid)
    slippage_points = abs(executable_price - float(entry)) / point
    if slippage_points > scope.slippage_limit_points + 1e-9:
        return "EXECUTION_SLIPPAGE_LIMIT", {"slippage_points": slippage_points}
    return None, {
        "spread_pips": spread_pips,
        "spread_risk_fraction": spread_fraction,
        "slippage_points": slippage_points,
        "cost_basis": "CURRENT_SPREAD_ONLY_PER_REGISTERED_S1_CONTRACT",
    }


def check_freshness(ticket: Mapping[str, Any], market: Optional[MarketEvidence],
                    scope: ScopePolicy, *, now_utc: datetime) -> tuple[Optional[str], dict[str, Any]]:
    if market is None:
        return "FRESHNESS_EVIDENCE_MISSING", {}
    now = _as_utc(now_utc)
    ticket_close = _as_utc(ticket.get("signal_close_utc"))
    evaluated_at = _as_utc(ticket.get("evaluated_at"))
    observed_at = _as_utc(market.observed_at_utc)
    data_close = _as_utc(market.data_close_utc)
    raw_valid_until = ticket.get("valid_until", ticket.get("valid_until_utc"))
    valid_until = _as_utc(raw_valid_until) if raw_valid_until is not None else None
    if any(value is None for value in (now, ticket_close, evaluated_at, observed_at, data_close)):
        return "FRESHNESS_TIMESTAMP_MISSING_OR_INVALID", {}
    if raw_valid_until is not None and valid_until is None:
        return "FRESHNESS_TIMESTAMP_MISSING_OR_INVALID", {}
    assert now is not None and ticket_close is not None and evaluated_at is not None
    assert observed_at is not None and data_close is not None
    if valid_until is not None and now >= valid_until:
        return "TICKET_EXPIRED", {"valid_until_utc": valid_until.isoformat()}
    if any(value > now for value in (ticket_close, evaluated_at, observed_at, data_close)):
        return "FRESHNESS_TIMESTAMP_IN_FUTURE", {}
    ttl = timedelta(minutes=scope.signal_expiry_minutes)
    if any(now - value > ttl for value in (ticket_close, evaluated_at, observed_at, data_close)):
        return "MARKET_DATA_STALE", {}
    if data_close < ticket_close or observed_at < data_close:
        return "FRESHNESS_ORDER_INVALID", {}
    return None, {"signal_age_seconds": (now - ticket_close).total_seconds(),
                  "quote_age_seconds": (now - observed_at).total_seconds()}


def evaluate_pre_send_gates(
    ticket: Mapping[str, Any],
    market: Optional[MarketEvidence],
    risk_snapshot: Optional[RiskSnapshot],
    *,
    now_utc: datetime,
    authorization_path: Optional[str] = None,
    scope: Optional[ScopePolicy] = None,
    scope_config_path: Optional[str] = None,
    repo_root: Optional[str] = None,
    registry_path: Optional[str] = None,
    broker_symbol_map_path: Optional[str] = None,
    ready_authority_config_path: Optional[str] = None,
    owner_decision_register_path: Optional[str] = None,
    ticket_store: Optional[TicketStore] = None,
) -> AdmissionResult:
    """Evaluate ordered broker-free gates and report every applicable block reason."""
    try:
        policy = scope or resolve_ticket_scope_policy(
            ticket,
            config_path=scope_config_path,
            repo_root=repo_root,
            registry_path=registry_path,
            broker_symbol_map_path=broker_symbol_map_path,
            ready_authority_config_path=ready_authority_config_path,
            owner_decision_register_path=owner_decision_register_path,
        )
    except ScopePolicyError as exc:
        return _blocked(exc.reason_code, ticket)
    if not policy.enabled:
        return _blocked("EXECUTION_DISABLED", ticket)
    if not isinstance(ticket, Mapping):
        return _blocked("TICKET_INVALID")

    block_reasons: list[str] = []
    gate_details: dict[str, Any] = {}

    def add_reasons(*reasons: Optional[str]) -> None:
        for reason in reasons:
            if reason and reason not in block_reasons:
                block_reasons.append(reason)

    # 1. Scope: keep every mismatch, in deterministic scope-check order, at the front.
    scope_reasons, scope_details = check_ticket_scope(ticket, policy)
    add_reasons(*scope_reasons)
    gate_details["scope"] = {
        "status": "BLOCKED" if scope_reasons else "PASS",
        **scope_details,
    }

    # 2. READY / owner binding.
    ready_reason, ready_details = check_ticket_ready(ticket, policy)
    add_reasons(ready_reason)
    gate_details["ready"] = {
        "status": "BLOCKED" if ready_reason else "PASS",
        **ready_details,
    }

    # 3. Standing authorization is independently evaluated even when an earlier gate blocks.
    authorization: AuthorizationResult = load_standing_authorization(
        policy, ticket, path=authorization_path, now_utc=now_utc,
    )
    if not authorization.authorized:
        add_reasons(authorization.reason_code)
    gate_details["authorization"] = {
        "status": "PASS" if authorization.authorized else "BLOCKED",
        "reason_code": authorization.reason_code,
        "decision_id": authorization.decision_id,
    }

    notification_reason = notification_gate(policy.notification_failure_policy, ticket_store, ticket, now_utc)
    gate_details["notification"] = {"status": "BLOCKED" if notification_reason else "PASS",
                                    "reason_code": notification_reason}

    # 4. Per-order confirmation. A valid record is consumed once only after all earlier
    # gates pass; when they fail, confirmation is inspected read-only for full diagnostics.
    confirmation_id: Optional[str] = None
    gate_details["per_order_confirm_required"] = policy.per_order_confirm_required
    if policy.per_order_confirm_required:
        confirmation = check_and_consume_owner_confirmation(
            ticket_store,
            ticket,
            now_utc=now_utc,
            consume=not block_reasons and notification_reason is None,
        )
        add_reasons(*confirmation.reason_codes)
        confirmation_id = confirmation.confirmation_id
        gate_details["owner_confirmation"] = {
            "status": confirmation.status,
            "confirmation_id": confirmation.confirmation_id,
        }
    else:
        gate_details["owner_confirmation"] = {"status": "SKIPPED_BY_CONFIG"}

    # 5. Risk, cost and freshness are all evaluated, even when an earlier gate blocks.
    risk = evaluate_risk_caps(ticket, policy, risk_snapshot, now_utc=now_utc)
    if not risk.allowed:
        add_reasons(risk.reason_code)
    gate_details["risk"] = {
        "status": "PASS" if risk.allowed else "BLOCKED",
        "reason_code": risk.reason_code,
        "risk_pct": risk.planned_risk_pct,
        "server_day": risk.server_day.isoformat() if risk.server_day else None,
        "daily_reset_owner_confirm": risk.daily_reset_owner_confirm,
        "own_positions_on_symbol": risk.own_positions_on_symbol,
        "foreign_positions_on_symbol": risk.foreign_positions_on_symbol,
    }

    cost_reason, cost_details = check_cost_gate(ticket, market, policy)
    add_reasons(cost_reason)
    gate_details["cost"] = {
        "status": "BLOCKED" if cost_reason else "PASS",
        "reason_code": cost_reason,
        **cost_details,
    }

    freshness_reason, freshness_details = check_freshness(ticket, market, policy, now_utc=now_utc)
    add_reasons(freshness_reason)
    # AGP-TQ-D1 defence in depth: the same fail-closed target geometry as the canonical READY boundary.
    from v1_tickets.target_geometry import ticket_geometry_violation, ticket_levels
    geometry_reason = ticket_geometry_violation(ticket)
    add_reasons(geometry_reason)
    gate_details["target_geometry"] = {"status": "BLOCKED" if geometry_reason else "PASS",
                                       "reason_code": geometry_reason, **ticket_levels(ticket)}
    gate_details["freshness"] = {
        "status": "BLOCKED" if freshness_reason else "PASS",
        "reason_code": freshness_reason,
        **freshness_details,
    }

    add_reasons(notification_reason)

    # 6. Idempotency is last in the requested admission order.
    if ticket_store is None:
        idempotency_reason = "TICKET_STORE_UNAVAILABLE"
        prior_state = None
    else:
        duplicate = ExecutionLedger(ticket_store).inspect(str(ticket.get("ticket_id") or ""))
        idempotency_reason = None if duplicate.available else duplicate.reason_code
        prior_state = duplicate.prior_state
    add_reasons(idempotency_reason)
    gate_details["idempotency"] = {
        "status": "PASS" if idempotency_reason is None else "BLOCKED",
        "reason_code": idempotency_reason or "IDEMPOTENCY_KEY_AVAILABLE",
        "prior_state": prior_state,
    }

    if block_reasons:
        return _blocked(
            block_reasons[0],
            ticket,
            block_reasons=block_reasons,
            gate_details=gate_details,
        )

    return AdmissionResult(
        True,
        "ADMITTED_PRE_SEND",
        ticket_id=str(ticket["ticket_id"]),
        volume=risk.planned_volume,
        risk_amount=risk.planned_risk_amount,
        details={
            "risk_pct": risk.planned_risk_pct,
            "daily_reset_basis": policy.daily_reset_basis,
            "daily_reset_owner_confirm": policy.daily_reset_owner_confirm,
            "authorization_decision_id": authorization.decision_id,
            "owner_confirmation_id": confirmation_id,
            "per_order_confirm_required": policy.per_order_confirm_required,
            "block_reasons": [],
            "gate_details": gate_details,
            **cost_details,
            **freshness_details,
        },
    )


def check_account_mode(account_mode: Optional[str]) -> Optional[str]:
    """Send-time account assertion; source is supplied by the future C11 host adapter."""
    if account_mode is None or not isinstance(account_mode, str) or not account_mode.strip():
        return "ACCOUNT_MODE_UNAVAILABLE"
    return None if account_mode == "DEMO" else "ACCOUNT_NOT_DEMO"


def prepare_canonical_handoff(
    ticket: Mapping[str, Any],
    market: Optional[MarketEvidence],
    risk_snapshot: Optional[RiskSnapshot],
    *,
    account_mode: Optional[str],
    ticket_store: Optional[TicketStore],
    now_utc: datetime,
    authorization_path: Optional[str] = None,
    scope: Optional[ScopePolicy] = None,
    **scope_paths: Any,
) -> AdmissionResult:
    """Apply final guards, but stop before the intentionally absent C11 broker adapter."""
    try:
        policy = scope or resolve_ticket_scope_policy(
            ticket,
            config_path=scope_paths.get("scope_config_path"),
            repo_root=scope_paths.get("repo_root"),
            registry_path=scope_paths.get("registry_path"),
            broker_symbol_map_path=scope_paths.get("broker_symbol_map_path"),
            ready_authority_config_path=scope_paths.get("ready_authority_config_path"),
            owner_decision_register_path=scope_paths.get("owner_decision_register_path"),
        )
    except ScopePolicyError as exc:
        return _blocked(exc.reason_code, ticket)
    if not isinstance(ticket, Mapping):
        return _blocked("TICKET_INVALID")
    evaluated = evaluate_pre_send_gates(
        ticket,
        market,
        risk_snapshot,
        now_utc=now_utc,
        authorization_path=authorization_path,
        scope=policy,
        ticket_store=ticket_store,
    )
    if not evaluated.admitted:
        return evaluated

    # These are later send-time assertions, not substitutes for the ordered admission gates.
    account_reason = check_account_mode(account_mode)
    notification_reason = notification_gate(policy.notification_failure_policy, ticket_store, ticket, now_utc)
    send_reasons = [reason for reason in (account_reason, notification_reason) if reason]
    if send_reasons:
        return _blocked(
            send_reasons[0],
            ticket,
            block_reasons=send_reasons,
            gate_details={
                **evaluated.details.get("gate_details", {}),
                "account_mode": "BLOCKED" if account_reason else "PASS",
                "notification_failure_policy": "BLOCKED" if notification_reason else "PASS",
            },
        )
    return _blocked("CANONICAL_EXECUTION_ADAPTER_NOT_IMPLEMENTED", ticket)
