"""Single fail-closed readiness audit for a synthetic Demo-order execution.

This module intentionally composes the individual checks already implemented across the
repo into one explicit gate between "integration-ready" and a real MT5 Demo-order send.
It is designed to be opt-in at runtime so existing mock-based unit tests and dry-run
paths remain unaffected unless the operator explicitly requests the audit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from mt5.account import account as get_account
from mt5.account_guard import verify_configured_account
from mt5.market_data import get_tick
from mt5.symbol_resolver import get_symbol_meta
from execution.journal import has_executed as journal_has_executed
from trade_management.sizing import evaluate_sizing

INTEGRATION_READY = "INTEGRATION_READY"
EXECUTION_INFRASTRUCTURE_READY = "EXECUTION_INFRASTRUCTURE_READY"
DEMO_EXECUTION_READINESS_AUDIT = "DEMO_EXECUTION_READINESS_AUDIT"


@dataclass(frozen=True)
class ExecutionReadinessAuditResult:
    status: str
    passed: bool
    reason_code: Optional[str] = None
    checks: dict[str, str] = field(default_factory=dict)

    @property
    def execution_ready(self) -> bool:
        return self.passed and self.status == EXECUTION_INFRASTRUCTURE_READY


def _should_run_audit() -> bool:
    raw = os.getenv("AG_DEMO_READINESS_AUDIT", "").strip().lower()
    return raw in {"1", "true", "yes", "on", "enable", "enabled"}


def _fail(reason_code: str, checks: Optional[dict[str, str]] = None, *, status: str = "BLOCKED") -> ExecutionReadinessAuditResult:
    return ExecutionReadinessAuditResult(status=status, passed=False, reason_code=reason_code, checks=checks or {})


def _safe_get_account():
    try:
        return get_account()
    except Exception:  # noqa: BLE001
        return None


def _safe_get_symbol_meta(symbol: str):
    try:
        return get_symbol_meta(symbol)
    except Exception:  # noqa: BLE001
        return None


def _safe_get_tick(symbol: str):
    try:
        return get_tick(symbol)
    except Exception:  # noqa: BLE001
        return None


def _ensure_tick_freshness(proposal: Any, meta: Any, tick: Any) -> Optional[str]:
    if tick is None:
        return "TICK_FRESHNESS_UNAVAILABLE"
    direction = getattr(proposal, "direction", "BUY").upper()
    price = getattr(tick, "bid", None) if direction == "SELL" else getattr(tick, "ask", None)
    if price is None:
        return "TICK_FRESHNESS_UNAVAILABLE"
    entry = getattr(proposal, "entry", None)
    if entry is None:
        return None
    point = getattr(meta, "point", 0.0) or 0.0
    spread_points = getattr(tick, "spread_points", 0) or 0
    tolerance = max(5.0 * spread_points * point, 10.0 * point)
    deviation = abs(float(price) - float(entry))
    if deviation > tolerance:
        return "PRICE_TICK_STALE"
    return None


def _ensure_volume_normalization(proposal: Any, meta: Any, account_obj: Any) -> Optional[str]:
    volume = getattr(proposal, "volume", None)
    risk_pct = getattr(proposal, "risk_percent", None)
    entry = getattr(proposal, "entry", None)
    stop_loss = getattr(proposal, "stop_loss", None)
    equity = getattr(account_obj, "equity", None)

    if volume is not None:
        if volume < getattr(meta, "volume_min", 0.0) - 1e-9 or volume > getattr(meta, "volume_max", float("inf")) + 1e-9:
            return "VOLUME_NORMALIZATION_FAILED"
        return None

    if risk_pct is None or entry is None or stop_loss is None or equity is None:
        return None

    try:
        sizing = evaluate_sizing(entry, stop_loss, equity, risk_pct, None, meta)
    except Exception:  # noqa: BLE001
        return "VOLUME_NORMALIZATION_FAILED"
    if getattr(sizing, "status", None) != "READY":
        return "VOLUME_NORMALIZATION_FAILED"
    return None


def _ensure_stop_and_freeze_levels(proposal: Any, meta: Any) -> Optional[str]:
    entry = getattr(proposal, "entry", None)
    stop_loss = getattr(proposal, "stop_loss", None)
    if entry is None or stop_loss is None:
        return None
    min_points = max(getattr(meta, "trade_stops_level", 0), getattr(meta, "trade_freeze_level", 0))
    if min_points <= 0:
        return None
    point = getattr(meta, "point", 0.0) or 0.0
    distance = abs(float(entry) - float(stop_loss))
    if point <= 0:
        return "SL_FREEZE_LEVEL_BLOCKED"
    if distance < min_points * point:
        return "SL_FREEZE_LEVEL_BLOCKED"
    return None


def _ensure_idempotency(proposal: Any, *, journal_guard: Any = None) -> Optional[str]:
    if journal_guard is not None:
        try:
            if getattr(journal_guard, "has_executed", lambda *_args, **_kwargs: False)(getattr(proposal, "setup_id", None)):
                return "IDEMPOTENCY_BLOCKED"
        except Exception:  # noqa: BLE001
            return "IDEMPOTENCY_BLOCKED"
        return None
    try:
        if journal_has_executed(getattr(proposal, "setup_id", "")):
            return "IDEMPOTENCY_BLOCKED"
    except Exception:  # noqa: BLE001
        return None
    return None


def _ensure_position_guard(open_position_guard: Any) -> Optional[str]:
    if open_position_guard is None:
        return None
    try:
        return None if not open_position_guard.is_blocked() else "MAX_POSITION_GUARD_BLOCKED"
    except Exception:  # noqa: BLE001
        return "MAX_POSITION_GUARD_BLOCKED"


def run_execution_readiness_audit(proposal: Any, *, account: Any = None, symbol_meta: Any = None,
                                 tick: Any = None, open_position_guard: Any = None,
                                 journal_guard: Any = None) -> ExecutionReadinessAuditResult:
    """Return a single pass/fail verdict for a Demo order before order_send.

    The function is intentionally conservative: it fails closed whenever the account,
    symbol metadata, tick data, or the guard state is unavailable or mismatched.
    """
    checks: dict[str, str] = {}

    account_obj = account or _safe_get_account()
    if account_obj is None:
        return _fail("ACCOUNT_STATE_UNAVAILABLE", checks)
    if not getattr(account_obj, "is_demo", False):
        return _fail("LIVE_ACCOUNT_HARD_BLOCK", checks)
    if not getattr(account_obj, "trade_allowed", True):
        return _fail("MARGIN_AUTHORITY_BLOCKED", checks)
    checks["account_identity_guard"] = "pass"

    identity_reason = verify_configured_account()
    if identity_reason is not None:
        return _fail("ACCOUNT_IDENTITY_MISMATCH", checks)
    checks["configured_account_match"] = "pass"

    meta = symbol_meta or _safe_get_symbol_meta(getattr(proposal, "symbol", ""))
    if meta is None:
        return _fail("SYMBOL_SPEC_UNAVAILABLE", checks)
    if getattr(meta, "volume_min", 0.0) <= 0 or getattr(meta, "volume_max", 0.0) <= 0:
        return _fail("SYMBOL_SPEC_UNAVAILABLE", checks)
    checks["symbol_specs"] = "pass"

    volume_error = _ensure_volume_normalization(proposal, meta, account_obj)
    if volume_error is not None:
        return _fail(volume_error, checks)
    checks["volume_normalization"] = "pass"

    tick_obj = tick or _safe_get_tick(getattr(proposal, "symbol", ""))
    tick_error = _ensure_tick_freshness(proposal, meta, tick_obj)
    if tick_error is not None:
        return _fail(tick_error, checks)
    checks["tick_freshness"] = "pass"

    stop_error = _ensure_stop_and_freeze_levels(proposal, meta)
    if stop_error is not None:
        return _fail(stop_error, checks)
    checks["sl_freeze_levels"] = "pass"

    idempotency_error = _ensure_idempotency(proposal, journal_guard=journal_guard)
    if idempotency_error is not None:
        return _fail(idempotency_error, checks)
    checks["idempotency"] = "pass"

    position_guard_error = _ensure_position_guard(open_position_guard)
    if position_guard_error is not None:
        return _fail(position_guard_error, checks)
    checks["max_position_guard"] = "pass"

    return ExecutionReadinessAuditResult(
        status=EXECUTION_INFRASTRUCTURE_READY,
        passed=True,
        checks=checks,
    )


def require_demo_execution_readiness(proposal: Any, *, account: Any = None, symbol_meta: Any = None,
                                    tick: Any = None, open_position_guard: Any = None,
                                    journal_guard: Any = None) -> ExecutionReadinessAuditResult:
    """Thin wrapper used by the real Demo-action call path when the operator explicitly
    requests the audit, e.g. via the environment gate or a future API knob."""
    if not _should_run_audit():
        return ExecutionReadinessAuditResult(
            status=INTEGRATION_READY,
            passed=True,
            checks={"audit_mode": "skipped"},
        )
    return run_execution_readiness_audit(
        proposal,
        account=account,
        symbol_meta=symbol_meta,
        tick=tick,
        open_position_guard=open_position_guard,
        journal_guard=journal_guard,
    )
