"""Builds MarketContext -- strategy-neutral runtime inputs, reused across whatever
strategy the Strategy Manager dispatches to. Reuses existing mt5/ read-only functions;
does not fetch M15 candles, session boxes, or any capability-layer analysis itself --
those are each strategy's own concern (per its own adapter), avoiding "unnecessary
calculation of Order Blocks/FVG/full structural analysis" the mission's section 7 warns
against.

Fails closed: any missing/stale account or tick data returns a CONTEXT_FAILED
MarketContext with a reason code, never a guessed value.
"""
from __future__ import annotations

from datetime import datetime, timezone

from mt5.account import Account, AccountError, account as get_account
from mt5.market_data import MarketDataError, check_freshness, get_tick

from assistant.models import CONTEXT_FAILED, CONTEXT_READY, MarketContext

MAX_TICK_AGE_SECONDS = 120


def build_context(symbol: str) -> MarketContext:
    now = datetime.now(timezone.utc)

    try:
        acct: Account = get_account()
    except AccountError as exc:
        return _failed(symbol, now, ("ACCOUNT_INFO_UNAVAILABLE", str(exc)))

    try:
        tick = get_tick(symbol)
    except MarketDataError as exc:
        return _failed(symbol, now, (exc.reason_code,))

    staleness = check_freshness(tick.time_utc, now, MAX_TICK_AGE_SECONDS)
    if staleness:
        return _failed(symbol, now, (staleness,))

    return MarketContext(
        symbol=symbol,
        broker_resolved_symbol=symbol,  # mt5.symbol_resolver.resolve() unimplemented -- not needed
                                         # while the connected account's Market Watch is unsuffixed
        timestamp_utc=now,
        session_date=now.date(),
        account_login=acct.login,
        account_server=acct.server,
        account_is_demo=acct.is_demo,
        current_bid=tick.bid,
        current_ask=tick.ask,
        tick_time_utc=tick.time_utc,
        status=CONTEXT_READY,
    )


def _failed(symbol: str, now: datetime, reason_codes) -> MarketContext:
    return MarketContext(
        symbol=symbol, broker_resolved_symbol=symbol, timestamp_utc=now, session_date=now.date(),
        account_login=0, account_server="", account_is_demo=False,
        current_bid=float("nan"), current_ask=float("nan"), tick_time_utc=now,
        status=CONTEXT_FAILED, reason_codes=tuple(reason_codes),
    )
