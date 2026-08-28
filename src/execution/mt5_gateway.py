"""Thin adapter over mt5/ for order_check / order_send when OPENING a new position --
the only place in execution/ allowed to call into the mt5 package for order placement.
Implemented 2026-08-28 (Execution authority restructure); modeled directly on
mt5.management_gateway._send()'s dry-run/live pattern -- see that module for the
precedent this one deliberately mirrors rather than reinvents.

Structurally the OPEN-side counterpart to mt5.management_gateway.py, which remains the
only module allowed to call order_check/order_send for an EXISTING position's
modify/partial-close/close. Neither module's authority overlaps the other's.

Must never be called directly by strategy_engine/, assistant/, or any skill; only
execution/executor.py calls this, and only after gate checks (explicit user command,
config, account) have all passed -- see execution/executor.py::execute().

Gated by config/trading.yaml's `mode` / `execution.allow_order_check` /
`execution.allow_order_send` / `account.allow_live_trading` -- independent of
mt5.management_gateway's own `trade_management:` block. Default is DRY_RUN-equivalent:
every function below constructs the exact broker request and returns it without calling
order_check/order_send unless the config explicitly allows AND (the connected account
reads as demo OR allow_live_trading is explicitly true) -- is_demo alone is documented
elsewhere (mt5/account.py) as "not a safe live-account interlock by itself", so this
gateway requires agreement between the config flag and the live account read, not
either alone.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
import yaml

from mt5.account import account as get_account
from execution.models import OrderSendResult

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "trading.yaml")

# side -> MT5 order type for a MARKET open. LIMIT support deferred (not requested this
# pass; ORDER_TYPE_BUY_LIMIT/SELL_LIMIT would need a pending-order lifecycle this repo
# doesn't otherwise model yet).
_ORDER_TYPE_MAP = {
    ("BUY", "MARKET"): "ORDER_TYPE_BUY",
    ("SELL", "MARKET"): "ORDER_TYPE_SELL",
}


class Mt5GatewayError(RuntimeError):
    pass


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _order_send_allowed() -> bool:
    config = _load_config()
    if config.get("mode") != "TRADING":
        return False
    execution_cfg = config.get("execution", {}) or {}
    if execution_cfg.get("allow_order_send") is not True:
        return False
    return True


def _order_check_allowed() -> bool:
    config = _load_config()
    execution_cfg = config.get("execution", {}) or {}
    return execution_cfg.get("allow_order_check") is True


def _account_authorized_for_send() -> Optional[str]:
    """Returns None if the connected account may receive a real order_send, else a
    reason_code. Defense-in-depth on top of config: requires the live account to read
    as demo, UNLESS allow_live_trading is explicitly true in config too."""
    config = _load_config()
    allow_live_trading = (config.get("account", {}) or {}).get("allow_live_trading") is True
    try:
        acct = get_account()
    except Exception as exc:  # noqa: BLE001 -- surfaced as a reason_code, not a crash
        return f"ACCOUNT_STATE_UNAVAILABLE: {exc}"
    if acct.is_demo:
        return None
    if allow_live_trading:
        return None
    return "LIVE_EXECUTION_DISABLED"


@dataclass(frozen=True)
class GatewayCheckResult:
    passed: bool
    reason_code: str
    request: dict
    broker_retcode: Optional[int] = None
    broker_comment: Optional[str] = None


def order_check(request: dict) -> GatewayCheckResult:
    if not _order_check_allowed():
        return GatewayCheckResult(passed=False, reason_code="ORDER_CHECK_NOT_ALLOWED", request=request)
    result = mt5.order_check(request)
    if result is None or result.retcode != 0:
        code, message = mt5.last_error()
        return GatewayCheckResult(
            passed=False,
            reason_code="ORDER_CHECK_FAILED",
            request=request,
            broker_retcode=getattr(result, "retcode", None),
            broker_comment=f"({code}) {message}",
        )
    return GatewayCheckResult(passed=True, reason_code="ORDER_CHECK_PASS", request=request,
                               broker_retcode=result.retcode)


def order_open(
    symbol: str,
    side: str,  # "BUY" / "SELL"
    order_type: str,  # "MARKET"
    volume: float,
    sl: Optional[float],
    tp: Optional[float],
    magic_number: int,
    comment: str,
    entry: Optional[float] = None,
    deviation_points: int = 20,
) -> OrderSendResult:
    if (side, order_type) not in _ORDER_TYPE_MAP:
        return OrderSendResult(
            status="REJECTED", reason_code="UNSUPPORTED_ORDER_TYPE", symbol=symbol, side=side,
            requested_volume=volume, sl=sl, tp=tp, request=None,
        )

    mt5_order_type = getattr(mt5, _ORDER_TYPE_MAP[(side, order_type)])

    price = entry
    if price is None:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderSendResult(
                status="REJECTED", reason_code="STALE_MARKET_DATA", symbol=symbol, side=side,
                requested_volume=volume, sl=sl, tp=tp, request=None,
            )
        price = tick.ask if side == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5_order_type,
        "price": price,
        "sl": sl if sl is not None else 0.0,
        "tp": tp if tp is not None else 0.0,
        "deviation": deviation_points,
        "magic": magic_number,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    if not _order_send_allowed():
        return OrderSendResult(
            status="REJECTED", reason_code="DRY_RUN", symbol=symbol, side=side,
            requested_volume=volume, requested_price=price, sl=sl, tp=tp, request=request,
        )

    account_block_reason = _account_authorized_for_send()
    if account_block_reason is not None:
        return OrderSendResult(
            status="REJECTED", reason_code=account_block_reason, symbol=symbol, side=side,
            requested_volume=volume, requested_price=price, sl=sl, tp=tp, request=request,
        )

    check_result = mt5.order_check(request)
    if check_result is None or check_result.retcode != 0:
        code, message = mt5.last_error()
        return OrderSendResult(
            status="REJECTED", reason_code="ORDER_CHECK_FAILED", symbol=symbol, side=side,
            requested_volume=volume, requested_price=price, sl=sl, tp=tp, request=request,
            broker_retcode=getattr(check_result, "retcode", None),
            broker_comment=f"({code}) {message}",
        )

    result = mt5.order_send(request)
    if result is None:
        code, message = mt5.last_error()
        return OrderSendResult(
            status="REJECTED", reason_code="ORDER_SEND_FAILED", symbol=symbol, side=side,
            requested_volume=volume, requested_price=price, sl=sl, tp=tp, request=request,
            broker_comment=f"({code}) {message}",
        )

    executed = result.retcode == mt5.TRADE_RETCODE_DONE
    return OrderSendResult(
        status="EXECUTED" if executed else "REJECTED",
        reason_code="ORDER_SEND_DONE" if executed else "BROKER_REJECTED",
        symbol=symbol,
        side=side,
        requested_volume=volume,
        filled_volume=getattr(result, "volume", None) if executed else None,
        requested_price=price,
        fill_price=getattr(result, "price", None) if executed else None,
        sl=sl,
        tp=tp,
        ticket=getattr(result, "order", None) if executed else None,
        deal_id=getattr(result, "deal", None) if executed else None,
        broker_retcode=result.retcode,
        broker_comment=result.comment,
        timestamp=datetime.now(timezone.utc),
        request=request,
    )
