"""Classify WHY a position disappeared from the broker, using authoritative MT5 deal
history only (mt5.deals.deals_for_position, the read-only history_deals_get wrapper this
package already uses to confirm fills).

Deliberately does NOT infer a stop-loss from a losing P&L: a loss can equally be a manual
close, a margin stop-out, or an EA close, and mislabelling those in an owner-facing alert
is worse than saying UNKNOWN. Only MT5's own DEAL_REASON on the closing (DEAL_ENTRY_OUT)
deal is treated as evidence; anything else resolves to UNKNOWN.

Pure classification + one read-only history call; never mutates broker state.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, Sequence

logger = logging.getLogger("trade_management.close_reason")

CLOSE_REASON_SL = "SL"
CLOSE_REASON_TP = "TP"
CLOSE_REASON_SO = "STOP_OUT"
CLOSE_REASON_MANUAL = "MANUAL"
CLOSE_REASON_EXPERT = "EXPERT"
CLOSE_REASON_UNKNOWN = "UNKNOWN"

# MT5 DEAL_ENTRY_OUT / DEAL_ENTRY_OUT_BY -- the deal(s) that took volume off the position.
_DEAL_ENTRY_OUT = 1
_DEAL_ENTRY_OUT_BY = 3

# MT5 DEAL_REASON_* numeric values (mirrored rather than imported so this module stays
# importable on machines with no MetaTrader5 package -- the values are part of the MT5
# wire contract and do not change).
_REASON_MAP = {
    0: CLOSE_REASON_MANUAL,   # DEAL_REASON_CLIENT
    1: CLOSE_REASON_MANUAL,   # DEAL_REASON_MOBILE
    2: CLOSE_REASON_MANUAL,   # DEAL_REASON_WEB
    3: CLOSE_REASON_EXPERT,   # DEAL_REASON_EXPERT
    4: CLOSE_REASON_SL,       # DEAL_REASON_SL
    5: CLOSE_REASON_TP,       # DEAL_REASON_TP
    6: CLOSE_REASON_SO,       # DEAL_REASON_SO (stop out)
}


def _default_reader(ticket: int) -> Sequence:
    from mt5.deals import deals_for_position  # imported lazily: MetaTrader5 may be absent

    return deals_for_position(ticket)


def resolve_close_reason(
    ticket: int,
    deals_reader: Optional[Callable[[int], Sequence]] = None,
) -> str:
    """Return one of the CLOSE_REASON_* constants for a position that is gone from the
    broker. Any failure (no MT5, history unavailable, no closing deal, unmapped reason
    code) resolves to CLOSE_REASON_UNKNOWN -- never raises, never guesses."""
    reader = deals_reader or _default_reader
    try:
        rows = list(reader(ticket))
    except Exception as exc:  # noqa: BLE001 -- classification must never break reconciliation
        logger.warning("close reason lookup failed ticket=%s: %s", ticket, exc)
        return CLOSE_REASON_UNKNOWN

    closing = [r for r in rows if _entry_of(r) in (_DEAL_ENTRY_OUT, _DEAL_ENTRY_OUT_BY)]
    if not closing:
        return CLOSE_REASON_UNKNOWN

    raw_reason = getattr(closing[-1], "reason", None)
    try:
        return _REASON_MAP.get(int(raw_reason), CLOSE_REASON_UNKNOWN)
    except (TypeError, ValueError):
        return CLOSE_REASON_UNKNOWN


def _entry_of(row) -> Optional[int]:
    try:
        return int(getattr(row, "entry"))
    except (AttributeError, TypeError, ValueError):
        return None
