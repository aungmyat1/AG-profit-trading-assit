"""The single canonical MT5 order_check / order_send call site (C14 DEMO execution, B').

Implements :class:`demo_execution.broker_adapter.CanonicalBrokerAdapter`. It is the ONLY place in the
repository that calls ``order_check`` or ``order_send`` (one call site each;
``tests/test_demo_execution_canonical_adapter.py`` enforces exactly one). It sits behind
:class:`demo_execution.guarded_adapter.GuardedCanonicalAdapter`: the guard re-validates the execution
authority, the scope, the standing authorization, the owner confirmation and the gates, and issues a
single-use step authorization; this adapter then re-validates again, from primary sources,
immediately before it touches the broker:

* the step authorization is the one the guard recorded for exactly this ticket and step
  (AUTHORIZED for order_check, SENT for order_send), is the latest lifecycle row and is not expired;
* the scope selected for the authority is ``enabled`` and matches the authority's identity tuple;
* the live terminal account is read here and must be the pinned DEMO account (login suffix, server,
  trade_mode DEMO) -- a REAL or unreadable account refuses;
* the committed order-shape policy must be OWNER_APPROVED (it ships PROPOSED: inert);
* for order_send, the checked order must be byte-identical to the one sealed at CHECKED.

The terminal module is injected by the host (``mt5=``); nothing here imports MetaTrader5. Every
refusal returns a mapping with ``refused: True`` and a ``reason_code`` and never calls the broker.
An order_send that raises or returns nothing is reported as an unknown outcome (the guard HALTs and
it is reconciled, never resubmitted). No retry, no resubmission, no other broker mutation.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import yaml

from demo_execution.authority import (
    ExecutionAuthority,
    evidence_digest,
    per_order_confirm_required,
    validate_authority_shape,
    validate_confirmation_evidence,
    validate_live_account,
)
from demo_execution.idempotency import SENDING, ExecutionLedger
from demo_execution.lifecycle import AUTHORIZED, SENT, ExecutionLifecycle
from demo_execution.scope import (
    ScopePolicy,
    ScopePolicyError,
    resolve_ticket_scope_policy,
)
from ticket_store.store import TicketStore

_REPO_ROOT = Path(__file__).resolve().parents[2]
ORDER_SHAPE_PATH = _REPO_ROOT / "config" / "demo_execution_order_shape.yaml"
ORDER_SHAPE_SCHEMA = "AGP_DEMO_ORDER_SHAPE_V1"

ADAPTER_REFUSED = "ADAPTER_REFUSED"
STEP_AUTHORIZATION_INVALID = "STEP_AUTHORIZATION_INVALID"
STEP_AUTHORIZATION_EXPIRED = "STEP_AUTHORIZATION_EXPIRED"
STEP_AUTHORIZATION_NOT_LATEST = "STEP_AUTHORIZATION_NOT_LATEST"
SCOPE_NOT_ENABLED = "EXECUTION_DISABLED"
SCOPE_AUTHORITY_MISMATCH = "AUTHORITY_SCOPE_MISMATCH"
ACCOUNT_MODE_NOT_DEMO = "ACCOUNT_MODE_NOT_DEMO"
ORDER_SHAPE_NOT_APPROVED = "ORDER_SHAPE_NOT_APPROVED"
ORDER_REQUEST_INVALID = "ORDER_REQUEST_INVALID"
CHECKED_ORDER_MISMATCH = "CHECKED_ORDER_MISMATCH"
QUOTE_UNAVAILABLE = "QUOTE_UNAVAILABLE"
BROKER_CALL_RAISED = "BROKER_CALL_RAISED"
BROKER_RESULT_MISSING = "BROKER_RESULT_MISSING"
SEND_CLAIM_MISSING = "SEND_CLAIM_MISSING"

_FILLING = {"FOK": "ORDER_FILLING_FOK", "IOC": "ORDER_FILLING_IOC", "RETURN": "ORDER_FILLING_RETURN"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _refused(reason: str, **details: Any) -> dict[str, Any]:
    return {"refused": True, "reason_code": reason, **details}


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _as_dict(result: Any) -> Optional[dict[str, Any]]:
    """MT5 returns named tuples (``_asdict``); nested request tuples are flattened too."""
    if result is None:
        return None
    if isinstance(result, Mapping):
        raw = dict(result)
    elif hasattr(result, "_asdict"):
        raw = dict(result._asdict())
    else:
        return None
    return {k: (_as_dict(v) if hasattr(v, "_asdict") else v) for k, v in raw.items()}


def load_order_shape(path: Optional[str | Path] = None) -> dict[str, Any]:
    """The committed DEMO order shape. Anything but an exact OWNER_APPROVED policy refuses."""
    try:
        raw = yaml.safe_load(Path(path or ORDER_SHAPE_PATH).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {"approved": False}
    if not isinstance(raw, dict) or raw.get("schema") != ORDER_SHAPE_SCHEMA:
        return {"approved": False}
    order = raw.get("order") if isinstance(raw.get("order"), dict) else {}
    tag = raw.get("deviation_tag")
    ok = (raw.get("status") == "OWNER_APPROVED" and isinstance(raw.get("owner_decision_id"), str)
          and raw["owner_decision_id"].strip() and isinstance(raw.get("shape_id"), str)
          and raw["shape_id"].strip() and isinstance(tag, str) and tag.isascii() and tag.isalnum()
          and 1 <= len(tag) <= 8 and raw.get("analytics_exclusion") is True
          and order.get("action") == "DEAL"
          and order.get("take_profit_leg") in (1, 2) and order.get("filling") in _FILLING)
    return {"approved": bool(ok), "take_profit_leg": order.get("take_profit_leg"),
            "filling": order.get("filling"), "owner_decision_id": raw.get("owner_decision_id"),
            "shape_id": raw.get("shape_id"), "deviation_tag": tag,
            "analytics_exclusion": raw.get("analytics_exclusion") is True,
            "account_margin_mode": raw.get("account_margin_mode")}


def _comment(ticket_id: str, tag: Optional[str] = None) -> str:
    # MT5 comments are at most 31 characters: a short ticket digest plus the shape deviation tag.
    base = "AG " + hashlib.sha256(ticket_id.encode("utf-8")).hexdigest()[:16]
    return f"{base} {tag}"[:31] if tag else base


def _shape_fields(shape: Mapping[str, Any]) -> dict[str, Any]:
    """Recorded on every broker result: the order deviates from the contract's leg split and is
    excluded from strategy analytics; the margin mode is whatever the policy records (UNKNOWN until
    host-verified)."""
    return {"shape_id": shape.get("shape_id"), "shape_deviation_tag": shape.get("deviation_tag"),
            "analytics_exclusion": bool(shape.get("analytics_exclusion")),
            "account_margin_mode": shape.get("account_margin_mode") or "UNKNOWN"}


class MT5CanonicalAdapter:
    """CanonicalBrokerAdapter over an injected MT5 terminal module (DEMO only)."""

    def __init__(self, *, mt5: Any, ticket_store: TicketStore,
                 order_shape_path: Optional[str | Path] = None,
                 clock: Callable[[], datetime] = _utc_now,
                 **scope_paths: Any) -> None:
        if not isinstance(ticket_store, TicketStore):
            raise ValueError("ticket_store must be the append-only TICKET_STORE_V1 writer")
        self._mt5 = mt5
        self._store = ticket_store
        self._shape_path = order_shape_path
        self._clock = clock
        self._scope_paths = scope_paths

    # ------------------------------------------------------------------ re-validation
    def _scope(self, authority: ExecutionAuthority) -> tuple[Optional[ScopePolicy], Optional[str]]:
        binding = {"strategy_id": authority.strategy_id, "strategy_version": authority.strategy_version,
                   "symbol": authority.symbol, "session": authority.session}
        paths = dict(self._scope_paths)
        try:
            scope = resolve_ticket_scope_policy(binding, config_path=paths.pop("scope_config_path", None), **paths)
        except ScopePolicyError as exc:
            return None, exc.reason_code
        if not scope.enabled:
            return None, SCOPE_NOT_ENABLED
        if (scope.strategy_id, scope.strategy_version, scope.symbol, scope.session, scope.setup_branch,
                scope.logic_identity, scope.magic_number) != (
                authority.strategy_id, authority.strategy_version, authority.symbol, authority.session,
                authority.setup_branch, authority.logic_identity, authority.magic_number):
            return None, SCOPE_AUTHORITY_MISMATCH
        return scope, None

    def _step(self, authority: ExecutionAuthority, authorization: Any, state: str,
              now: datetime) -> tuple[Optional[Any], Optional[str]]:
        if not isinstance(authorization, Mapping) or authorization.get("ticket_id") != authority.ticket_id \
                or authorization.get("state") != state or not authorization.get("authorization_id"):
            return None, STEP_AUTHORIZATION_INVALID
        trail = ExecutionLifecycle(self._store).trail(authority.ticket_id)
        if trail.reason_code is not None or trail.current != state:
            return None, STEP_AUTHORIZATION_NOT_LATEST
        row = trail.state_row(state)
        if row is None or row.authorization_id != authorization["authorization_id"] \
                or row.authority_id != authority.authority_id:
            return None, STEP_AUTHORIZATION_INVALID
        try:
            expires = datetime.fromisoformat(str(row.evidence.get("expires_at_utc")))
        except ValueError:
            return None, STEP_AUTHORIZATION_INVALID
        if expires.tzinfo is None or now >= expires:
            return None, STEP_AUTHORIZATION_EXPIRED
        return row, None

    def _demo_account(self, authority: ExecutionAuthority, scope: ScopePolicy, account_mode: Any,
                      now: datetime) -> Optional[str]:
        if account_mode != "DEMO":
            return ACCOUNT_MODE_NOT_DEMO
        try:
            info = _as_dict(self._mt5.account_info())
        except Exception:  # noqa: BLE001 -- an unreadable account is never a default
            info = None
        if not info:
            return "ACCOUNT_IDENTITY_UNAVAILABLE"
        login = str(info.get("login") or "")
        live = {"login_suffix": login[-len(scope.account_login_suffix):] if login else None,
                "server": info.get("server"), "trade_mode": info.get("trade_mode"), "observed_at_utc": now}
        reasons = validate_live_account(live, authority, scope, now_utc=now)
        return reasons[0] if reasons else None

    def _preflight(self, authority: Any, authorization: Any, state: str, account_mode: Any):
        now = self._clock()
        if validate_authority_shape(authority):
            return None, None, None, _refused(ADAPTER_REFUSED, reasons=list(validate_authority_shape(authority)))
        row, reason = self._step(authority, authorization, state, now)
        if reason:
            return None, None, None, _refused(reason)
        scope, reason = self._scope(authority)
        if reason:
            return None, None, None, _refused(reason)
        reason = self._demo_account(authority, scope, account_mode, now)
        if reason:
            return None, None, None, _refused(reason)
        shape = load_order_shape(self._shape_path)
        if not shape["approved"]:
            return None, None, None, _refused(ORDER_SHAPE_NOT_APPROVED)
        return row, scope, shape, None

    # ------------------------------------------------------------------ request
    def build_request(self, authority: ExecutionAuthority, ticket: Mapping[str, Any], scope: ScopePolicy,
                      shape: Mapping[str, Any], volume: Any) -> tuple[Optional[dict], Optional[str]]:
        """One market DEAL from the ticket's levels, the guard-planned volume and the scope."""
        long = authority.direction == "LONG"
        tp = {t.get("leg"): t.get("price") for t in ticket.get("targets") or [] if isinstance(t, Mapping)}
        sl, target, vol = _finite(ticket.get("stop_loss")), _finite(tp.get(shape["take_profit_leg"])), _finite(volume)
        try:
            tick = _as_dict(self._mt5.symbol_info_tick(scope.broker_symbol))
        except Exception:  # noqa: BLE001
            tick = None
        price = _finite((tick or {}).get("ask" if long else "bid"))
        if price is None or price <= 0:
            return None, QUOTE_UNAVAILABLE
        if sl is None or target is None or vol is None or vol <= 0 \
                or not ((sl < price < target) if long else (target < price < sl)):
            return None, ORDER_REQUEST_INVALID
        mt5 = self._mt5
        return {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": scope.broker_symbol, "volume": vol,
            "type": mt5.ORDER_TYPE_BUY if long else mt5.ORDER_TYPE_SELL, "price": price,
            "sl": sl, "tp": target, "deviation": int(scope.slippage_limit_points),
            "magic": int(scope.magic_number), "comment": _comment(authority.ticket_id, shape.get("deviation_tag")),
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": getattr(mt5, _FILLING[shape["filling"]]),
        }, None

    # ------------------------------------------------------------------ broker steps
    def order_check(self, *, authority: ExecutionAuthority, authorization: Mapping[str, Any],
                    ticket: Mapping[str, Any], account_mode: str) -> Mapping[str, Any]:
        row, scope, shape, refusal = self._preflight(authority, authorization, AUTHORIZED, account_mode)
        if refusal:
            return refusal
        request, reason = self.build_request(authority, ticket, scope, shape, row.evidence.get("planned_volume"))
        if reason:
            return _refused(reason)
        try:
            result = _as_dict(self._mt5.order_check(request))
        except Exception as exc:  # noqa: BLE001 -- a raised check is a refused check, nothing was sent
            return _refused(BROKER_CALL_RAISED, error_class=type(exc).__name__)
        if result is None:
            return _refused(BROKER_RESULT_MISSING)
        # The sealed request travels with the result: order_send must send exactly this request.
        return {**{k: v for k, v in result.items() if k != "request"}, "request": request, **_shape_fields(shape)}

    def order_send(self, *, authority: ExecutionAuthority, authorization: Mapping[str, Any],
                   ticket: Mapping[str, Any], checked_order: Mapping[str, Any],
                   account_mode: str) -> Mapping[str, Any]:
        row, scope, shape, refusal = self._preflight(authority, authorization, SENT, account_mode)
        if refusal:
            return refusal
        if not isinstance(checked_order, Mapping) \
                or row.evidence.get("checked_order_sha256") != evidence_digest(dict(checked_order)) \
                or not isinstance(checked_order.get("request"), Mapping):
            return _refused(CHECKED_ORDER_MISMATCH)
        # The durable SENDING claim must already exist (written by the guard before SENT): a crash
        # after the broker call then halts on restart instead of resubmitting.
        claim = ExecutionLedger(self._store).inspect(authority.ticket_id)
        if claim.prior_state != SENDING or claim.reason_code != "HALT_UNCERTAIN_SEND":
            return _refused(SEND_CLAIM_MISSING)
        # Per-scope owner confirmation: required -> the single-use confirmation must be consumed;
        # not required -> the standing authorization the guard re-validated is the only grant.
        if per_order_confirm_required(scope):
            reasons = validate_confirmation_evidence(self._store, authority, ticket, now_utc=self._clock(),
                                                     require_consumed=True)
            if reasons:
                return _refused(reasons[0])
        request = dict(checked_order["request"])
        try:
            result = _as_dict(self._mt5.order_send(request))
        except Exception as exc:  # noqa: BLE001 -- outcome unknown: the guard HALTs, never resends
            return {"unknown_outcome": True, "reason_code": BROKER_CALL_RAISED, "error_class": type(exc).__name__,
                    **_shape_fields(shape)}
        if result is None:
            return {"unknown_outcome": True, "reason_code": BROKER_RESULT_MISSING, **_shape_fields(shape)}
        return {**{k: v for k, v in result.items() if k != "request"}, **_shape_fields(shape)}

    # The orchestration layer uses semantic names so the physical MT5 order call sites stay here.
    check_order = order_check
    send_order = order_send

    def reconcile(self, *, authority: ExecutionAuthority, ticket_id: str,
                  send_result: Mapping[str, Any]) -> Mapping[str, Any]:
        """Read-only: the deals of the order the send reported, matched by magic + comment.
        No order id or no matching deal -> UNKNOWN (the ticket stays HALTed; never resubmitted)."""
        comment = _comment(ticket_id, load_order_shape(self._shape_path).get("deviation_tag"))
        order_id = None
        for key in ("broker_order_id", "order_id", "order"):
            value = (send_result or {}).get(key) if isinstance(send_result, Mapping) else None
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                order_id = value
                break
        if order_id is None:
            return {"reconciled": False, "terminal_result": "UNKNOWN"}
        try:
            deals = self._mt5.history_deals_get(ticket=order_id) or ()
        except Exception:  # noqa: BLE001
            deals = ()
        mine = [d for d in (_as_dict(x) for x in deals) if d
                and d.get("magic") == authority.magic_number and d.get("comment") == comment]
        if not mine:
            return {"reconciled": False, "terminal_result": "UNKNOWN"}
        deal = mine[0]
        return {"reconciled": True, "terminal_result": "FILLED", "broker_deal_id": deal.get("ticket"),
                "broker_order_id": deal.get("order"), "broker_position_id": deal.get("position_id"),
                "volume": deal.get("volume"), "price": deal.get("price")}
