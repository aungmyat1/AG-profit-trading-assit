"""Local fallback for environments where the real MetaTrader5 package is not installed.

This project contains many modules that import MetaTrader5 unconditionally. In a non-Windows
or non-MT5 environment those imports would otherwise fail before the project can even
validate its safety gates or CLI wrappers. The fallback intentionally raises a clear error
when any real broker operation is invoked, rather than silently returning fake success.
"""

from __future__ import annotations


class MT5StubOperationAttempted(RuntimeError):
    """Raised when code attempts to use the broker API in a non-MT5 environment."""


_TIMEFRAME_VALUES = {
    "TIMEFRAME_M1": 1,
    "TIMEFRAME_M5": 5,
    "TIMEFRAME_M15": 15,
    "TIMEFRAME_M30": 30,
    "TIMEFRAME_H1": 16385,
    "TIMEFRAME_H4": 16388,
    "TIMEFRAME_D1": 16408,
    "TIMEFRAME_W1": 32769,
    "ORDER_TIME_GTC": 0,
    "ORDER_FILLING_IOC": 1,
    "TRADE_ACTION_DEAL": 1,
    "TRADE_ACTION_SLTP": 6,
    "TRADE_RETCODE_DONE": 10009,
    "ORDER_TYPE_BUY": 0,
    "ORDER_TYPE_SELL": 1,
    "DEAL_TYPE_BUY": 0,
    "DEAL_TYPE_SELL": 1,
    "ACCOUNT_TRADE_MODE_DEMO": 0,
    "ACCOUNT_TRADE_MODE_REAL": 2,
}


def _raise(name: str):
    def _handler(*args, **kwargs):
        raise MT5StubOperationAttempted(
            f"MetaTrader5.{name}() was called, but the real MetaTrader5 package is not available "
            "in this environment. This project intentionally refuses to emulate broker behavior."
        )

    return _handler


for _name, _value in _TIMEFRAME_VALUES.items():
    globals()[_name] = _value

for _name in [
    "initialize",
    "shutdown",
    "terminal_info",
    "symbol_info",
    "symbol_select",
    "copy_rates_range",
    "copy_rates_from_pos",
    "last_error",
    "positions_total",
    "positions_get",
    "orders_total",
    "orders_get",
    "order_send",
    "history_orders_get",
    "history_deals_get",
    "trade_buy",
    "trade_sell",
    "trade_cancel",
    "trade_modify",
    "trade_close",
    "refresh_rates",
]:
    globals()[_name] = _raise(_name)
