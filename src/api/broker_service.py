"""Read-only MT5 account history for the local API.

Broker deal history is authoritative. This module never places, modifies, or closes an
order and returns only sanitized closed-deal fields needed by the local frontend.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def closed_deal_history(*, days: int = 90, limit: int = 100) -> dict:
    if not 1 <= days <= 3650:
        raise ValueError("days must be between 1 and 3650")
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    import MetaTrader5 as mt5
    from mt5.connection import MT5ConnectionError, connect

    connect()
    account = mt5.account_info()
    if account is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"ACCOUNT_INFO_FAILED: ({code}) {message}")

    now = datetime.now(timezone.utc)
    deals = mt5.history_deals_get(now - timedelta(days=days), now)
    if deals is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"HISTORY_DEALS_GET_FAILED: ({code}) {message}")

    closing = [deal for deal in deals if int(deal.entry) != 0]
    selected = closing[-limit:]
    rows = [
        {
            "ticket": int(deal.ticket),
            "position_id": int(deal.position_id),
            "time": datetime.fromtimestamp(deal.time, timezone.utc).isoformat(),
            "symbol": deal.symbol,
            "side": "BUY" if int(deal.type) == int(mt5.DEAL_TYPE_BUY) else "SELL",
            "volume": float(deal.volume),
            "price": float(deal.price),
            "profit": float(deal.profit),
            "commission": float(deal.commission),
            "swap": float(deal.swap),
            "fee": float(deal.fee),
            "comment": deal.comment,
        }
        for deal in reversed(selected)
    ]
    realized = sum(row["profit"] + row["commission"] + row["swap"] + row["fee"] for row in rows)
    login = str(account.login)
    return {
        "account_redacted": "*" * max(0, len(login) - 4) + login[-4:],
        "server": account.server,
        "environment": "DEMO" if int(account.trade_mode) == int(mt5.ACCOUNT_TRADE_MODE_DEMO) else "LIVE",
        "lookback_days": days,
        "total_closing_deals": len(closing),
        "returned_deals": len(rows),
        "realized_net": round(realized, 2),
        "deals": rows,
    }
