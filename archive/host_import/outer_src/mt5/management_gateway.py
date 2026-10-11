"""The ONLY module allowed to call order_check/order_send for an already-open
position's modify/partial-close/close (spec section 1's frozen architectural
principle -- trade_management/rules.py decides WHAT should happen; this module is the
only place that can make it happen).

Forbidden here, structurally: opening new exposure, placing pending entry orders,
increasing position size, reversing position (spec section 17). There is no function in
this module that can create a new position from scratch -- every call requires an
existing `position` ticket.

Gated independently from the (paused, untouched) entry-side execution/mt5_gateway by
config/trading.yaml's own `trade_management:` block (mode: DRY_RUN|LIVE +
allow_live_management), not by execution/'s `mode`/`allow_order_send`/
`allow_live_trading` flags -- see config/trading.yaml's comments. Default is DRY_RUN:
every function below constructs the exact broker request and returns it without calling
order_check/order_send unless BOTH gate values are explicitly set.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import MetaTrader5 as mt5
import yaml

from mt5.account import account as get_account
from mt5.account_guard import verify_configured_account

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "trading.yaml"
)
_CONFIG_PATH = os.environ.get("AG_TRADING_CONFIG_PATH", _DEFAULT_CONFIG_PATH)


class ManagementGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewayResult:
    dry_run: bool
    request: dict
    executed: bool = False
    retcode: Optional[int] = None
    comment: Optional[str] = None
    volume_before: Optional[float] = None
    volume_after: Optional[float] = None
    violation: Optional[str] = None


def _live_management_allowed() -> bool:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    tm = config.get("trade_management", {}) or {}
    return tm.get("mode") == "LIVE" and tm.get("allow_live_management") is True


def _current_volume(ticket: int) -> Optional[float]:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return None
    return float(positions[0].volume)


def modify_position_sl(ticket: int, symbol: str, new_sl: float, keep_tp: Optional[float] = None) -> GatewayResult:
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": symbol,
        "sl": new_sl,
        "tp": keep_tp if keep_tp is not None else 0.0,
    }
    return _send(ticket, request, expect_volume_change=False)


def partial_close_position(ticket: int, symbol: str, direction: str, volume: float, price: float) -> GatewayResult:
    """`price` is the caller's already-known direction-aware exit price (e.g.
    NormalizedPosition.current_price) -- the gateway does not re-fetch a tick itself,
    so a dry-run preview never needs a live connection to construct its request."""
    return _close_deal(ticket, symbol, direction, volume, price)


def close_position(ticket: int, symbol: str, direction: str, volume: float, price: float) -> GatewayResult:
    return _close_deal(ticket, symbol, direction, volume, price)


def _close_deal(ticket: int, symbol: str, direction: str, volume: float, price: float) -> GatewayResult:
    order_type = mt5.ORDER_TYPE_SELL if direction == "BUY" else mt5.ORDER_TYPE_BUY
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": ticket,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": 20,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    return _send(ticket, request, expect_volume_change=True, expected_reduction=volume)


def _send(
    ticket: int,
    request: dict,
    expect_volume_change: bool,
    expected_reduction: Optional[float] = None,
) -> GatewayResult:
    if not _live_management_allowed():
        return GatewayResult(dry_run=True, request=request)

    identity_mismatch = verify_configured_account()
    if identity_mismatch is not None:
        return GatewayResult(dry_run=False, request=request, comment=identity_mismatch)
    try:
        if not get_account().is_demo:
            return GatewayResult(dry_run=False, request=request, comment="LIVE_MANAGEMENT_DISABLED")
    except Exception as exc:  # noqa: BLE001 - fail closed before broker mutation
        return GatewayResult(
            dry_run=False,
            request=request,
            comment=f"ACCOUNT_STATE_UNAVAILABLE: {exc}",
        )

    volume_before = _current_volume(ticket)

    check_result = mt5.order_check(request)
    if check_result is None or check_result.retcode != 0:
        code, message = mt5.last_error()
        return GatewayResult(
            dry_run=False,
            request=request,
            executed=False,
            retcode=getattr(check_result, "retcode", None),
            comment=f"ORDER_CHECK_FAILED: ({code}) {message}",
            volume_before=volume_before,
        )

    result = mt5.order_send(request)
    if result is None:
        code, message = mt5.last_error()
        return GatewayResult(
            dry_run=False,
            request=request,
            executed=False,
            comment=f"ORDER_SEND_FAILED: ({code}) {message}",
            volume_before=volume_before,
        )

    volume_after = _current_volume(ticket)
    violation = None
    if volume_before is not None and volume_after is not None:
        if volume_after > volume_before + 1e-9:
            violation = "CRITICAL_MANAGEMENT_VIOLATION: position volume increased"
        elif expect_volume_change and expected_reduction is not None:
            expected_after = volume_before - expected_reduction
            if abs(volume_after - expected_after) > 1e-6 and result.retcode == mt5.TRADE_RETCODE_DONE:
                violation = "STATE_RECONCILIATION_REQUIRED: volume after close does not match request"

    return GatewayResult(
        dry_run=False,
        request=request,
        executed=(result.retcode == mt5.TRADE_RETCODE_DONE),
        retcode=result.retcode,
        comment=result.comment,
        volume_before=volume_before,
        volume_after=volume_after,
        violation=violation,
    )
