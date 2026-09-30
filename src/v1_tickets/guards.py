"""READY gates shared by the V1 FX and crypto ticket builders (audit 2). Pure: no broker, no network.

The frozen engines decide; these gates only withhold a READY they produced, never create one:
- data or signal older than STALE_AFTER (15 min) -> decision STALE;
- spread > MAX_SPREAD_RISK_FRACTION (15%) of the stop distance -> decision SPREAD_TOO_WIDE;
- spread not measurable -> decision NO_TRADE, reason SPREAD_NOT_EVALUATED (fail closed).
A withheld decision keeps its levels for audit and records `suppressed_decision`.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

STALE_AFTER = dt.timedelta(minutes=15)
MAX_SPREAD_RISK_FRACTION = 0.15
STALE = "STALE"
SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
SPREAD_NOT_EVALUATED = "SPREAD_NOT_EVALUATED"


def is_stale(close_time: Optional[dt.datetime], now: dt.datetime) -> bool:
    """True when `close_time` is unknown or more than STALE_AFTER before `now`."""
    return close_time is None or now - close_time > STALE_AFTER


def spread_check(spread: Optional[float], risk: Optional[float]) -> Dict[str, Any]:
    if spread is None or risk is None or not risk > 0 or spread < 0:
        return {"spread_check": "NOT_EVALUATED", "spread": spread}
    fraction = spread / risk
    return {"spread_check": "PASS" if fraction <= MAX_SPREAD_RISK_FRACTION else SPREAD_TOO_WIDE,
            "spread": spread, "spread_risk_fraction": round(fraction, 4),
            "spread_max_risk_fraction": MAX_SPREAD_RISK_FRACTION}


def _withhold(ticket: Dict[str, Any], decision: str, reason: str, reason_key: str) -> Dict[str, Any]:
    out = {**ticket, "decision": decision, "suppressed_decision": ticket.get("decision")}
    if reason_key == "reason_codes":
        out["reason_codes"] = [reason] + [r for r in ticket.get("reason_codes") or [] if r != reason]
    else:
        out["engine_reason_code"], out["reason_code"] = ticket.get("reason_code"), reason
    return out


def gate_ready(ticket: Dict[str, Any], *, now: dt.datetime, data_close: Optional[dt.datetime],
               signal_close: Optional[dt.datetime], spread: Optional[float], risk: Optional[float],
               reason_key: str = "reason_code") -> Dict[str, Any]:
    """Stale data turns any evaluated decision (READY/WATCH/NO_TRADE) into STALE; the signal
    and spread gates apply to READY only. `data_close` None skips the data-age gate (caller has
    no live bar); `signal_close` None is STALE."""
    if data_close is not None and is_stale(data_close, now) and ticket.get("decision") in ("READY", "WATCH", "NO_TRADE"):
        return _withhold(ticket, STALE, "STALE_DATA", reason_key)
    if ticket.get("decision") != "READY":
        return ticket
    ticket = {**ticket, **spread_check(spread, risk),
              "signal_close_utc": signal_close.isoformat() if signal_close else None}
    if is_stale(signal_close, now):
        return _withhold(ticket, STALE, "STALE_SIGNAL", reason_key)
    if ticket["spread_check"] == SPREAD_TOO_WIDE:
        return _withhold(ticket, SPREAD_TOO_WIDE, SPREAD_TOO_WIDE, reason_key)
    if ticket["spread_check"] != "PASS":
        return _withhold(ticket, "NO_TRADE", SPREAD_NOT_EVALUATED, reason_key)
    return ticket
