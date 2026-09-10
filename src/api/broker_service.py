"""Read-only MT5 account history and market data for the local API.

Broker deal history and market data are authoritative. This module never places,
modifies, or closes an order and returns only sanitized closed-deal / closed-candle
fields needed by the local frontend.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Roadmap R2 (AG_REAL_MARKET_WATCH_READY_V1): a freshness allowance per timeframe for
# real_market_data() below -- deliberately generous (weekend closures, broker feed
# gaps) since this is a read-only observation signal, not an execution-time freshness
# gate. Matches the timeframe keys mt5.market_data._TIMEFRAMES supports.
_FRESHNESS_MAX_AGE_SECONDS = {
    "M1": 5 * 60, "M5": 15 * 60, "M15": 45 * 60, "M30": 90 * 60,
    "H1": 3 * 60 * 60, "H4": 10 * 60 * 60, "D1": 30 * 60 * 60,
}


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


def real_market_data(*, symbol: str, timeframe: str, count: int = 100) -> dict:
    """Roadmap R2 (AG_REAL_MARKET_WATCH_READY_V1): real, closed-bar-only MT5 candles
    for scanner/watch display. Reuses mt5.market_data.get_latest_candles via
    assistant.market_data.historical_candles -- the SAME canonical retrieval,
    UTC-normalization, and monotonic/OHLC/insufficient-history validation the
    assistant Market Data skill already relies on. This function never substitutes
    synthetic candles: any non-OK status is raised as MarketDataError and the caller
    (api.app) must fail closed, exactly like closed_deal_history()'s ValueError
    convention above -- never silently returned as if it were real data.
    """
    from assistant.market_data import historical_candles
    from mt5.account import account
    from mt5.connection import connect
    from mt5.market_data import MarketDataError, check_freshness

    if not 1 <= count <= 500:
        raise ValueError("count must be between 1 and 500")

    connect()
    acct = account()

    result = historical_candles(symbol, timeframe, count=count)
    if result.status != "OK":
        raise MarketDataError(result.status, f"{symbol} {timeframe}: {result.status}")

    last_closed = result.candles[-1]
    now_utc = datetime.now(timezone.utc)
    max_age = _FRESHNESS_MAX_AGE_SECONDS.get(timeframe, 3600)
    freshness = check_freshness(last_closed.time, now_utc, max_age) or "OK"

    return {
        "source": "MT5",
        "broker": acct.server,
        "environment": "DEMO" if acct.is_demo else "LIVE",
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_count": result.candle_count,
        "last_closed_candle_at": last_closed.time.isoformat(),
        "freshness": freshness,
        "candles": [
            {
                "time": c.time.isoformat(), "open": c.open, "high": c.high,
                "low": c.low, "close": c.close, "volume": c.volume,
            }
            for c in result.candles
        ],
    }
