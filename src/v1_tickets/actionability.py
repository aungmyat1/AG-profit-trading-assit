"""Actionability gate (Phase D).

Maps an already-produced strategy/V1-ticket signal to one of the owner-facing
deterministic decisions:

    WATCH_READY
    INFO_ONLY_STALE
    INFO_ONLY_INSUFFICIENT_REMAINING_R
    NO_TRADE
    EXPIRED
    MISSED
    BLOCKED
    INSUFFICIENT_DATA
    OUT_OF_SESSION

Owner freshness policy (mission):
    freshness_age = send_ts - trigger_bar_close_ts
    WATCH-ready only when freshness is within 2 x trigger timeframe completed bars.

For ST_ASIAN_SWEEP_5R_V1 and ST_LIQUIDITY_SWEEP_RETEST_V1 the trigger timeframe is M15 (FX)
and M5 (crypto).  A 2-bar window is therefore 30 min / 10 min respectively.

Remaining-R policy: informational WATCH_READY requires price to still have at least
MIN_REMAINING_R of R-space before TP1 is reached (fail-closed conservative default of
1.0 R when no owner-signed threshold exists on the contract).  When TP1 has already been
taken out or price blew past SL, the ticket falls to MISSED or EXPIRED.

This module never changes strategy logic or prices.  It is a pure classification over a
precomputed ticket plus a `current_price` (None means the caller has no live quote ->
BLOCKED/INSUFFICIENT_DATA), and never calls a broker.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

# Trigger timeframe for each supported strategy -> timedelta of one bar.
TRIGGER_TF: Dict[str, dt.timedelta] = {
    "ST_ASIAN_SWEEP_5R_V1": dt.timedelta(minutes=15),
    "ST_LIQUIDITY_SWEEP_RETEST_V1": dt.timedelta(minutes=5),
}
# WATCH_READY freshness multiplier: N completed bars of the trigger TF after signal close.
FRESHNESS_BARS = 2
# Minimum remaining R before TP1 for informational WATCH_READY.  Without an owner-signed
# value we fail closed to 1.0 R (owner sees INFO_ONLY_INSUFFICIENT_REMAINING_R otherwise).
MIN_REMAINING_R = 1.0

WATCH_READY = "WATCH_READY"
INFO_ONLY_STALE = "INFO_ONLY_STALE"
INFO_ONLY_INSUFFICIENT_REMAINING_R = "INFO_ONLY_INSUFFICIENT_REMAINING_R"
NO_TRADE = "NO_TRADE"
EXPIRED = "EXPIRED"
MISSED = "MISSED"
BLOCKED = "BLOCKED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
OUT_OF_SESSION = "OUT_OF_SESSION"

ACTIONABILITY_VERSION = "AG_ACTIONABILITY_V1"


def _parse(ts: Any) -> Optional[dt.datetime]:
    if ts is None:
        return None
    if isinstance(ts, dt.datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
    try:
        t = dt.datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _trigger_bar_close(ticket: Dict[str, Any]) -> Optional[dt.datetime]:
    """Close time of the trigger bar, in priority order: explicit signal_close_utc from
    guards; signal_timestamp + one trigger TF; legacy data_close."""
    close = _parse(ticket.get("signal_close_utc"))
    if close is not None:
        return close
    sig_ts = _parse(ticket.get("signal_timestamp"))
    tf = TRIGGER_TF.get(ticket.get("strategy_id", ""))
    if sig_ts is not None and tf is not None:
        return sig_ts + tf
    return _parse(ticket.get("data_close"))


def _prices(ticket: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Returns {entry, sl, tp1, tp2, direction} preferring the manual-ticket canonical
    names then falling back to the legacy V1 ticket keys."""
    entry = _to_float(ticket.get("entry"))
    sl = _to_float(ticket.get("stop_loss") or ticket.get("sl"))
    tp1 = _to_float(ticket.get("tp1"))
    tp2 = _to_float(ticket.get("tp2"))
    if tp1 is None or tp2 is None:
        targets = ticket.get("targets") or []
        for leg in targets:
            price = _to_float(leg.get("price"))
            if leg.get("leg") == 1 and tp1 is None:
                tp1 = price
            if leg.get("leg") == 2 and tp2 is None:
                tp2 = price
    return {"entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
            "direction": ticket.get("direction")}


def _r_distances(prices: Dict[str, Optional[float]], current: Optional[float]) -> Dict[str, Optional[float]]:
    entry, sl, tp1, tp2, direction = (
        prices["entry"], prices["sl"], prices["tp1"], prices["tp2"], prices["direction"])
    if entry is None or sl is None or direction not in ("LONG", "SHORT"):
        return {"risk": None, "remaining_to_tp1": None, "remaining_to_tp2": None,
                "moved": None, "initial_rr1": None, "initial_rr2": None}
    risk = abs(entry - sl)
    if risk <= 0:
        return {"risk": 0, "remaining_to_tp1": None, "remaining_to_tp2": None,
                "moved": None, "initial_rr1": None, "initial_rr2": None}
    sign = 1.0 if direction == "LONG" else -1.0
    initial_rr1 = abs(tp1 - entry) / risk if tp1 is not None else None
    initial_rr2 = abs(tp2 - entry) / risk if tp2 is not None else None
    if current is None:
        return {"risk": risk, "remaining_to_tp1": initial_rr1, "remaining_to_tp2": initial_rr2,
                "moved": 0.0, "initial_rr1": initial_rr1, "initial_rr2": initial_rr2}
    moved = sign * (current - entry) / risk      # how much price has moved in our favor in R
    # Remaining R to each target = (target - current) / risk, signed by direction.
    rem1 = sign * (tp1 - current) / risk if tp1 is not None else None
    rem2 = sign * (tp2 - current) / risk if tp2 is not None else None
    return {"risk": risk, "remaining_to_tp1": rem1, "remaining_to_tp2": rem2,
            "moved": moved, "initial_rr1": initial_rr1, "initial_rr2": initial_rr2}


def evaluate_actionability(
    ticket: Dict[str, Any],
    *,
    now: dt.datetime,
    current_price: Optional[float] = None,
    window_end: Optional[dt.datetime] = None,
    min_remaining_r: float = MIN_REMAINING_R,
) -> Dict[str, Any]:
    """Classify an already-produced V1/manual ticket into an owner-facing decision.

    Pure: no I/O, no broker, no network.  Returns a dict with `actionability_decision`,
    `actionability_reason`, `freshness_age_s`, `remaining_r`, and supporting geometry.
    Does not mutate `ticket`.
    """
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    decision = ticket.get("decision")
    reason_code = ticket.get("reason_code")
    strategy_id = ticket.get("strategy_id", "")

    # Lifecycle / hard data / session states map 1:1 first.
    if decision == "REFERENCE_NOT_READY":
        return _out(OUT_OF_SESSION, "REFERENCE_WINDOW_NOT_CLOSED", ticket, now, current_price, window_end)
    if decision == "DATA_ERROR":
        return _out(INSUFFICIENT_DATA, reason_code or "DATA_ERROR", ticket, now, current_price, window_end)
    if decision == "BLOCKED":
        return _out(BLOCKED, reason_code or "BLOCKED", ticket, now, current_price, window_end)
    if decision == "NO_TRADE":
        # Distinguish EXPIRED when the window has closed.
        win_end = window_end or _trade_window_end(ticket)
        if win_end is not None and now >= win_end and reason_code in (
                "NO_SETUP_BY_WINDOW_END", "NO_QUALIFIED_SWEEP_IN_WINDOW"):
            return _out(NO_TRADE, reason_code, ticket, now, current_price, window_end)
        return _out(NO_TRADE, reason_code or "NO_TRADE", ticket, now, current_price, window_end)

    # At this point a signal exists (READY or a gate-withheld READY -> STALE / SPREAD_TOO_WIDE).
    trigger_close = _trigger_bar_close(ticket)
    tf = TRIGGER_TF.get(strategy_id)
    if tf is None or trigger_close is None:
        return _out(INSUFFICIENT_DATA, "TRIGGER_TIMEFRAME_UNKNOWN", ticket, now, current_price, window_end)

    freshness_limit = FRESHNESS_BARS * tf
    age = now - trigger_close
    age_s = age.total_seconds()

    prices = _prices(ticket)
    geom = _r_distances(prices, current_price)

    # Session expiry: past the trade window invalidation (15:00 GMT for FX).
    win_end = window_end or _trade_window_end(ticket)
    if win_end is not None and now >= win_end:
        return _out(EXPIRED, "TRADE_WINDOW_CLOSED", ticket, now, current_price, window_end,
                    trigger_close=trigger_close, prices=prices, geom=geom, age_s=age_s)

    # Stale signal (beyond freshness window): INFO_ONLY_STALE, but record that the
    # signal was valid at trigger time.
    if age > freshness_limit:
        return _out(INFO_ONLY_STALE, "FRESHNESS_EXCEEDED", ticket, now, current_price, window_end,
                    trigger_close=trigger_close, prices=prices, geom=geom, age_s=age_s)

    # Need live current_price for remaining-R geometry; without it we cannot declare WATCH_READY.
    if current_price is None or prices["entry"] is None or geom["risk"] is None:
        return _out(INSUFFICIENT_DATA, "CURRENT_PRICE_MISSING", ticket, now, current_price, window_end,
                    trigger_close=trigger_close, prices=prices, geom=geom, age_s=age_s)

    entry, sl = prices["entry"], prices["sl"]
    long = prices["direction"] == "LONG"
    # MISSED: price has already blown through SL (invalidated before we could watch).
    if sl is not None and ((long and current_price <= sl) or (not long and current_price >= sl)):
        return _out(MISSED, "SL_TOUCHED_BEFORE_WATCH", ticket, now, current_price, window_end,
                    trigger_close=trigger_close, prices=prices, geom=geom, age_s=age_s)
    # EXPIRED setup-equivalent: price already past TP1 -> no remaining R to TP1.
    rem1 = geom["remaining_to_tp1"]
    if rem1 is not None and rem1 <= 0:
        return _out(MISSED, "TP1_ALREADY_REACHED", ticket, now, current_price, window_end,
                    trigger_close=trigger_close, prices=prices, geom=geom, age_s=age_s)
    # Insufficient remaining R to TP1.
    if rem1 is not None and rem1 < min_remaining_r:
        return _out(INFO_ONLY_INSUFFICIENT_REMAINING_R, "REMAINING_R_BELOW_THRESHOLD",
                    ticket, now, current_price, window_end, trigger_close=trigger_close,
                    prices=prices, geom=geom, age_s=age_s)

    # Spread / legacy gates that withheld READY become INFO_ONLY (they record their own reason).
    legacy = ticket.get("decision")
    if legacy in ("STALE", "SPREAD_TOO_WIDE"):
        return _out(INFO_ONLY_STALE if legacy == "STALE" else BLOCKED,
                    ticket.get("reason_code") or legacy,
                    ticket, now, current_price, window_end,
                    trigger_close=trigger_close, prices=prices, geom=geom, age_s=age_s)
    if ticket.get("spread_check") not in (None, "PASS"):
        return _out(BLOCKED, ticket.get("spread_check") or "SPREAD_NOT_EVALUATED",
                    ticket, now, current_price, window_end, trigger_close=trigger_close,
                    prices=prices, geom=geom, age_s=age_s)

    return _out(WATCH_READY, "WATCH_READY", ticket, now, current_price, window_end,
                trigger_close=trigger_close, prices=prices, geom=geom, age_s=age_s)


def _trade_window_end(ticket: Dict[str, Any]) -> Optional[dt.datetime]:
    win = ticket.get("window_utc") or {}
    trade = win.get("trade")
    if isinstance(trade, (list, tuple)) and len(trade) == 2:
        return _parse(trade[1])
    inv = ticket.get("valid_until")
    return _parse(inv)


def _out(
    decision: str, reason: str, ticket: Dict[str, Any], now: dt.datetime,
    current_price: Optional[float], window_end: Optional[dt.datetime],
    *, trigger_close: Optional[dt.datetime] = None, prices: Optional[Dict[str, Any]] = None,
    geom: Optional[Dict[str, Any]] = None, age_s: Optional[float] = None,
) -> Dict[str, Any]:
    if trigger_close is None:
        trigger_close = _trigger_bar_close(ticket)
    if prices is None:
        prices = _prices(ticket)
    if geom is None:
        geom = _r_distances(prices, current_price)
    if age_s is None and trigger_close is not None:
        age_s = (now - trigger_close).total_seconds()
    tf = TRIGGER_TF.get(ticket.get("strategy_id", ""))
    return {
        "actionability_decision": decision,
        "actionability_reason": reason,
        "actionability_version": ACTIONABILITY_VERSION,
        "policy_version": "OWNER_FRESHNESS_2xBAR;MIN_REMAINING_R_1.0",
        "evaluated_at": now.isoformat(),
        "trigger_bar_close_utc": trigger_close.isoformat() if trigger_close else None,
        "send_timestamp_utc": now.isoformat(),
        "freshness_age_s": round(max(0.0, age_s), 1) if age_s is not None else None,
        "freshness_limit_s": int((FRESHNESS_BARS * tf).total_seconds()) if tf else None,
        "freshness_status": "PASS" if (decision == WATCH_READY or (
            age_s is not None and tf is not None and age_s <= (FRESHNESS_BARS * tf).total_seconds()
        )) else "FAIL",
        "current_price": current_price,
        "entry_reference_price": prices["entry"],
        "reference_price": prices["entry"],
        "initial_rr_tp1": round(geom["initial_rr1"], 3) if geom.get("initial_rr1") is not None else None,
        "initial_rr_tp2": round(geom["initial_rr2"], 3) if geom.get("initial_rr2") is not None else None,
        "remaining_r_tp1": round(geom["remaining_to_tp1"], 3) if geom.get("remaining_to_tp1") is not None else None,
        "remaining_r_tp2": round(geom["remaining_to_tp2"], 3) if geom.get("remaining_to_tp2") is not None else None,
        "risk_distance": geom.get("risk"),
        "valid_at_trigger": _valid_at_trigger(ticket),
        "actionability_at_send": decision,
    }


def _valid_at_trigger(ticket: Dict[str, Any]) -> bool:
    """A signal was valid at trigger when the engine produced a SIGNAL regardless of
    downstream gates. Gate-withheld READY (STALE/SPREAD_TOO_WIDE) is still valid_at_trigger."""
    return ticket.get("suppressed_decision") == "READY" or ticket.get("decision") == "READY"
