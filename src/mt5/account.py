"""Account state. Read-only. Requires mt5.connection.connect() already called."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import MetaTrader5 as mt5

# ACCOUNT_MARGIN_MODE_RETAIL_HEDGING == 2 in the MT5 constants; the other two
# (RETAIL_NETTING=0, EXCHANGE=1) both net same-symbol positions. trade_management's
# gateway only needs the hedging/non-hedging distinction (spec section 20), not the
# three-way split.
_MARGIN_MODE_RETAIL_HEDGING = 2


class AccountError(RuntimeError):
    pass


@dataclass(frozen=True)
class Account:
    login: int
    server: str
    is_demo: bool
    balance: float
    equity: float
    trade_allowed: bool
    is_hedging_account: bool


def account() -> Account:
    info = mt5.account_info()
    if info is None:
        code, message = mt5.last_error()
        raise AccountError(f"ACCOUNT_INFO_UNAVAILABLE: ({code}) {message}")
    # ACCOUNT_TRADE_MODE_DEMO == 0. account_type/trade_mode is not a safe live-account
    # interlock by itself (docs/setup/MT5_MCP_SETUP.md 'Known defects') -- treat this as informational.
    return Account(
        login=info.login,
        server=info.server,
        is_demo=(info.trade_mode == 0),
        balance=info.balance,
        equity=info.equity,
        trade_allowed=info.trade_allowed,
        is_hedging_account=(getattr(info, "margin_mode", None) == _MARGIN_MODE_RETAIL_HEDGING),
    )


def positions(symbol: Optional[str] = None, ticket: Optional[int] = None) -> Sequence:
    """Raw MT5 position rows (positions_get() namedtuples) -- read-only. Callers that
    need the project's normalized shape should go through
    trade_management.position_monitor.normalize_position(), not reinterpret these
    fields themselves. Returns an empty sequence when there are no matching positions
    (MT5 returns an empty tuple, not None, for that case); None only signals a real
    query failure."""
    if ticket is not None:
        raw = mt5.positions_get(ticket=ticket)
    elif symbol is not None:
        raw = mt5.positions_get(symbol=symbol)
    else:
        raw = mt5.positions_get()

    if raw is None:
        code, message = mt5.last_error()
        raise AccountError(f"POSITIONS_GET_FAILED: ({code}) {message}")
    return list(raw)
