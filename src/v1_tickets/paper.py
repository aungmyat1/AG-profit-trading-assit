"""Fail-closed paper-trade projection for informational V1 FX tickets.

This module never talks to MT5 and never sizes or sends an order.  It creates an
R-multiple paper ledger entry only when an FX ticket is still fresh, complete, based on
host-captured symbol metadata, and has passed the live-spread gate.  Everything else is
explicitly ineligible with machine-readable reasons.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, Iterable, Tuple

from post_asian_pilot.report_archive import write_report

PAPER_STATUS = "OPEN"
_REQUIRED = (
    "strategy_id", "strategy_version", "symbol", "cycle", "session_date", "signal_id",
    "signal_close_utc", "direction", "entry_order_type", "entry", "stop_loss",
    "risk_distance", "targets", "evaluated_at", "metadata_status", "spread_check",
)


def _aware(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp is not timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def _missing(ticket: Dict[str, Any], names: Iterable[str]) -> list[str]:
    return [name for name in names if ticket.get(name) in (None, "", [])]


def paper_eligibility(ticket: Dict[str, Any], now: dt.datetime) -> Tuple[bool, list[str], dt.datetime | None]:
    """Return ``(eligible, reasons, valid_until_utc)`` without mutating the ticket."""
    reasons: list[str] = []
    if ticket.get("decision") != "READY":
        reasons.append("DECISION_NOT_READY")
    missing = _missing(ticket, _REQUIRED)
    if missing:
        reasons.extend(f"MISSING_{name.upper()}" for name in missing)
    if ticket.get("metadata_status") != "HOST_CAPTURED":
        reasons.append("METADATA_NOT_HOST_CAPTURED")
    if ticket.get("data_source") != "MT5_VT_MARKETS_DEMO":
        reasons.append("DATA_SOURCE_NOT_MT5_DEMO")
    if ticket.get("spread_check") != "PASS":
        reasons.append("SPREAD_NOT_PASSED")
    if ticket.get("entry_order_type") != "MARKET":
        reasons.append("ENTRY_ORDER_TYPE_NOT_MARKET")

    valid_until = None
    try:
        signal_close = _aware(str(ticket["signal_close_utc"]))
        # The freshness contract is 15 minutes after the qualifying bar closes.  The
        # strategy's fixed 15:00 GMT invalidation can only shorten that validity.
        signal_expiry = signal_close + dt.timedelta(minutes=15)
        session_expiry = dt.datetime.combine(
            dt.date.fromisoformat(str(ticket["session_date"])), dt.time(15, 0), tzinfo=dt.timezone.utc,
        )
        valid_until = min(signal_expiry, session_expiry)
        at = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
        at = at.astimezone(dt.timezone.utc)
        if signal_close > at:
            reasons.append("SIGNAL_CLOSE_IN_FUTURE")
        if at > valid_until:
            reasons.append("TICKET_EXPIRED")
    except (KeyError, TypeError, ValueError):
        reasons.append("INVALID_VALIDITY_TIMESTAMP")

    try:
        entry, stop, risk = float(ticket["entry"]), float(ticket["stop_loss"]), float(ticket["risk_distance"])
        direction = ticket.get("direction")
        # Ticket prices are rounded to broker digits while risk_distance comes from the
        # engine, so allow only a small (1%) rounding tolerance rather than exact equality.
        if (risk <= 0 or abs(abs(entry - stop) - risk) > max(1e-12, risk * 0.01)
                or (direction == "LONG" and stop >= entry) or (direction == "SHORT" and stop <= entry)):
            reasons.append("INVALID_RISK_GEOMETRY")
        if direction not in ("LONG", "SHORT"):
            reasons.append("INVALID_DIRECTION")
        targets = ticket.get("targets") or []
        target_fields = ("leg", "volume_pct", "type", "price")
        if (len(targets) != 2 or any(any(t.get(field) is None for field in target_fields) for t in targets)
                or [t.get("leg") for t in targets] != [1, 2]
                or abs(sum(float(t["volume_pct"]) for t in targets) - 1.0) > 1e-9):
            reasons.append("INCOMPLETE_TARGETS")
        elif any((direction == "LONG" and float(t["price"]) <= entry)
                 or (direction == "SHORT" and float(t["price"]) >= entry) for t in targets):
            reasons.append("INVALID_TARGET_GEOMETRY")
    except (KeyError, TypeError, ValueError):
        reasons.append("INVALID_PRICE_FIELDS")

    # Stable order and no duplicate reason codes makes archives deterministic.
    reasons = list(dict.fromkeys(reasons))
    return not reasons, reasons, valid_until


def build_paper_trade(ticket: Dict[str, Any], now: dt.datetime) -> Dict[str, Any] | None:
    """Project one eligible READY ticket into an un-sized, 1R paper trade."""
    eligible, _, valid_until = paper_eligibility(ticket, now)
    if not eligible or valid_until is None:
        return None
    return {
        "schema": "AG_PAPER_TRADE_V1",
        "label": "PAPER TRADE ONLY -- NO BROKER ORDER",
        "paper_trade_id": (
            f"{ticket['strategy_id']}:{ticket['strategy_version']}:{ticket['symbol']}:"
            f"{ticket['cycle']}:{ticket['signal_id']}:PAPER"
        ),
        "status": PAPER_STATUS,
        "opened_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "valid_until_utc": valid_until.isoformat(),
        "strategy_id": ticket["strategy_id"],
        "strategy_version": ticket["strategy_version"],
        "symbol": ticket["symbol"],
        "cycle": ticket["cycle"],
        "session_date": ticket["session_date"],
        "direction": ticket["direction"],
        "entry": ticket["entry"],
        "stop_loss": ticket["stop_loss"],
        "targets": ticket["targets"],
        "risk_distance": ticket["risk_distance"],
        "risk_unit": "1R",
        "position_size": "NOT_APPLICABLE_R_MULTIPLE_PAPER_TRADE",
        "source_ticket": ticket,
    }


def archive_paper_trade(record: Dict[str, Any], root: str) -> str:
    """Persist an eligible paper trade using the existing immutable archive mechanism."""
    report_type = os.path.join(
        "paper_trades", record["strategy_id"], record["symbol"], record["cycle"],
    )
    return write_report(report_type, dt.date.fromisoformat(record["session_date"]), record, root=root)
