"""Normalizes raw MT5 position rows (mt5.account.positions()) into NormalizedPosition,
and classifies a ticket against the claims store (spec section 6/7). Read-only: this
module never modifies a position.

`current_price` is direction-aware (the price you'd actually exit at): bid for a BUY
(you sell to close), ask for a SELL (you buy to close) -- not the broker's raw
price_current field, which MT5 defines the opposite way round per side.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from mt5.account import Account
from mt5.market_data import Tick

from .claims import Claim
from .models import NormalizedPosition

CLASSIFICATION_FOREIGN = "FOREIGN"
CLASSIFICATION_NEW = "NEW"
CLASSIFICATION_TRACKED = "TRACKED"
CLASSIFICATION_AMBIGUOUS = "AMBIGUOUS"

_POSITION_TYPE_BUY = 0
_POSITION_TYPE_SELL = 1


def normalize_position(raw_position, tick: Tick, account: Account) -> NormalizedPosition:
    """`raw_position` is one row as returned by MetaTrader5.positions_get() /
    mt5.account.positions()."""
    direction = "BUY" if raw_position.type == _POSITION_TYPE_BUY else "SELL"
    current_price = tick.bid if direction == "BUY" else tick.ask

    return NormalizedPosition(
        ticket=int(raw_position.ticket),
        symbol=raw_position.symbol,
        direction=direction,
        volume_initial=float(raw_position.volume),
        volume_current=float(raw_position.volume),
        entry_price=float(raw_position.price_open),
        current_bid=float(tick.bid),
        current_ask=float(tick.ask),
        current_price=float(current_price),
        sl=float(raw_position.sl) if raw_position.sl else None,
        tp=float(raw_position.tp) if raw_position.tp else None,
        profit=float(raw_position.profit),
        swap=float(raw_position.swap),
        commission=None,  # not exposed on MT5 position rows; only on closed deals
        magic=int(raw_position.magic),
        comment=raw_position.comment or "",
        open_time=datetime.fromtimestamp(raw_position.time, tz=timezone.utc),
        account_login=account.login,
        account_server=account.server,
    )


def classify(ticket: int, claims: Dict[int, Claim], position: Optional[NormalizedPosition]) -> str:
    """position=None means MT5 no longer reports this ticket (closed or never existed)."""
    if ticket not in claims:
        return CLASSIFICATION_FOREIGN
    if position is None:
        return CLASSIFICATION_TRACKED  # closed -- reconciliation (state.py) determines CLOSED
    claim = claims[ticket]
    if claim.symbol != position.symbol or claim.direction != position.direction:
        return CLASSIFICATION_AMBIGUOUS
    return CLASSIFICATION_TRACKED
