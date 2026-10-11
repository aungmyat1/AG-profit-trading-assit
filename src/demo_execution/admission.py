"""Pure S1/READY/auth/risk/cost/freshness admission; never accesses a broker."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from demo_execution.authorization import (
    AuthorizationResult,
    load_standing_authorization,
)
from demo_execution.idempotency import ExecutionLedger
from demo_execution.risk import RiskSnapshot, evaluate_risk_caps
from demo_execution.scope import ScopePolicy, ScopePolicyError, load_scope_policy
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


def _blocked(reason: str, ticket: Optional[Mapping[str, Any]] = None, **details: Any) -> AdmissionResult:
    ticket_id = ticket.get("ticket_id") if isinstance(ticket, Mapping) else None
    return AdmissionResult(False, reason, ticket_id if isinstance(ticket_id, str) else None, details=details)


def check_ticket_scope_and_ready(ticket: Mapping[str, Any], scope: ScopePolicy) -> tuple[Optional[str], dict[str, Any]]:
    """Bind S1, candidate identity and the existing D6/owner READY gate exactly."""
    ticket_id = ticket.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        return "TICKET_ID_MISSING", {}
    if ticket.get("strategy_id") != scope.strategy_id:
        return "STRATEGY_SCOPE_MISMATCH", {}
    if str(ticket.get("strategy_version")) != scope.strategy_version:
        return "STRATEGY_VERSION_SCOPE_MISMATCH", {}
    if ticket.get("symbol") != scope.symbol:
        return "SYMBOL_SCOPE_MISMATCH", {}
    if ticket.get("cycle", ticket.get("session")) != scope.session:
        return "SESSION_SCOPE_MISMATCH", {}
    branch = ticket.get("setup")
    if branch is None:
        branch = str(ticket.get("branch") or "").split(":", 1)[0]
    if branch != scope.setup_branch:
        return "LOGIC_SCOPE_NOT_VERIFIED", {"setup_branch": branch}
    if ticket.get("direction") not in scope.directions:
        return "DIRECTION_SCOPE_MISMATCH", {}
    if ticket.get("logic_identity") != scope.logic_identity:
        return "LOGIC_IDENTITY_MISMATCH", {}
    declared_broker_symbol = ticket.get("broker_symbol")
    if declared_broker_symbol is None and isinstance(ticket.get("symbol_meta"), Mapping):
        declared_broker_symbol = ticket["symbol_meta"].get("broker_symbol")
    if declared_broker_symbol is not None and declared_broker_symbol != scope.broker_symbol:
        return "BROKER_SYMBOL_SCOPE_MISMATCH", {}
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
    if any(value is None for value in (now, ticket_close, evaluated_at, observed_at, data_close)):
        return "FRESHNESS_TIMESTAMP_MISSING_OR_INVALID", {}
    assert now is not None and ticket_close is not None and evaluated_at is not None
    assert observed_at is not None and data_close is not None
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
) -> AdmissionResult:
    """Return ADMITTED_PRE_SEND only; this function cannot call a broker or reserve a send."""
    try:
        policy = scope or load_scope_policy(
            scope_config_path,
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
    scope_reason, scope_details = check_ticket_scope_and_ready(ticket, policy)
    authorization: AuthorizationResult = load_standing_authorization(
        policy, ticket, path=authorization_path, now_utc=now_utc,
    )
    risk = evaluate_risk_caps(ticket, policy, risk_snapshot, now_utc=now_utc)
    cost_reason, cost_details = check_cost_gate(ticket, market, policy)
    freshness_reason, freshness_details = check_freshness(ticket, market, policy, now_utc=now_utc)

    # Preserve one stable primary reason (scope first), while recording every independent
    # gate result for which this call supplied enough inputs to evaluate it.
    block_reasons = []
    if scope_reason:
        block_reasons.append(scope_reason)
    if not authorization.authorized:
        block_reasons.append(authorization.reason_code)
    if not risk.allowed:
        block_reasons.append(risk.reason_code)
    if cost_reason:
        block_reasons.append(cost_reason)
    if freshness_reason:
        block_reasons.append(freshness_reason)
    if block_reasons:
        details = {
            "primary_block_reason": block_reasons[0],
            "block_reasons": block_reasons,
            "scope_details": scope_details,
            "authorization_decision_id": authorization.decision_id,
            "risk_snapshot": {
            "server_day": risk.server_day.isoformat() if risk.server_day else None,
            "daily_reset_owner_confirm": risk.daily_reset_owner_confirm,
            "own_positions_on_symbol": risk.own_positions_on_symbol,
            "foreign_positions_on_symbol": risk.foreign_positions_on_symbol,
            },
            **cost_details,
            **freshness_details,
        }
        return _blocked(block_reasons[0], ticket, **details)
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
            **cost_details,
            **freshness_details,
        },
    )


def check_account_mode(account_mode: Optional[str]) -> Optional[str]:
    """Send-time account assertion; source is supplied by the future C11 host adapter."""
    if account_mode is None or not isinstance(account_mode, str) or not account_mode.strip():
        return "ACCOUNT_MODE_UNAVAILABLE"
    return None if account_mode == "DEMO" else "ACCOUNT_NOT_DEMO"


def check_notification_failure_policy(policy: Optional[str]) -> Optional[str]:
    """PENDING_OWNER blocks every new order; no outage behavior is guessed."""
    if policy == "PENDING_OWNER":
        return "NOTIFICATION_FAILURE_POLICY_PENDING_OWNER"
    return "NOTIFICATION_FAILURE_POLICY_UNRESOLVED"


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
        policy = scope or load_scope_policy(
            scope_paths.get("scope_config_path"),
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
        ticket, market, risk_snapshot, now_utc=now_utc, authorization_path=authorization_path,
        scope=policy,
    )
    if not evaluated.admitted:
        return evaluated
    if ticket_store is None:
        return _blocked("TICKET_STORE_UNAVAILABLE", ticket)
    duplicate = ExecutionLedger(ticket_store).inspect(evaluated.ticket_id or "")
    if not duplicate.available:
        return _blocked(duplicate.reason_code, ticket, prior_state=duplicate.prior_state)
    account_reason = check_account_mode(account_mode)
    if account_reason:
        return _blocked(account_reason, ticket)
    notification_reason = check_notification_failure_policy(policy.notification_failure_policy)
    if notification_reason:
        return _blocked(notification_reason, ticket)
    return _blocked("CANONICAL_EXECUTION_ADAPTER_NOT_IMPLEMENTED", ticket)
