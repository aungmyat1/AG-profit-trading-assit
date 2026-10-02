"""Pure Telegram text formatting for normalized messages (no transport/network code)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .message_models import MessageType, NormalizedMessage

MMT = timezone(timedelta(hours=6, minutes=30), name="MMT")


def _yes(value: bool) -> str:
    return "YES" if value else "NO"


def _value(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(str(v) for v in value.values() if v is not None)
    return str(value)


def _section(lines: list[str], label: str, value: Any) -> None:
    if value not in (None, "", (), [], {}):
        lines.extend((label + ":", _value(value), ""))


def format_expiry(value: datetime, *, include_mmt: bool = True) -> str:
    utc = value.astimezone(timezone.utc)
    text = utc.strftime("%H:%M UTC")
    if include_mmt:
        text += "\n" + utc.astimezone(MMT).strftime("%H:%M MMT")
    return text


def format_telegram(message: NormalizedMessage, *, include_mmt: bool = True) -> str:
    """Render only fields already authorized by the normalized model."""
    if message.message_type is MessageType.SYSTEM_STATUS:
        return "AG SYSTEM STATUS\n\n" + (message.system_event or "STATUS UNAVAILABLE")

    if message.message_type is MessageType.INFORMATIONAL_TICKET:
        title = "AG TRADE TICKET — INFORMATIONAL ONLY"
    elif message.message_type is MessageType.OPPORTUNITY_ALERT:
        title = "AG LARGE-SMC OPPORTUNITY"
    elif message.message_type is MessageType.NO_TRADE_SUMMARY:
        title = "AG NO-TRADE SUMMARY"
    else:
        title = "AG BLOCKED ALERT"
    lines = [title, "INFORMATIONAL ONLY", "NOT A BROKER ORDER", ""]
    symbol = " ".join(v for v in (message.canonical_symbol, message.direction) if v)
    if symbol:
        lines.extend((symbol, ""))
    if message.session:
        lines.extend((message.session, ""))
    strategy = " ".join(v for v in (message.strategy_id, message.strategy_version) if v)
    _section(lines, "Strategy", strategy)
    _section(lines, "Strategy Decision", message.strategy_status)
    _section(lines, "Economic Status", message.economic_status)
    _section(lines, "Path", message.context)
    _section(lines, "Location", message.location)
    _section(lines, "Trigger", message.trigger)
    _section(lines, "POI", message.poi)
    _section(lines, "Entry Reference", message.entry_reference)
    _section(lines, "Entry", message.entry_price)
    _section(lines, "Stop", message.stop_loss)
    for index, target in enumerate(message.targets, 1):
        _section(lines, f"TP{index}", target)
    _section(lines, "Invalidation", message.invalidation)
    _section(lines, "Current Price", message.current_price)
    _section(lines, "Distance to POI", message.distance_to_poi)
    _section(lines, "Risk Status", message.risk_status)
    if message.checklist:
        checklist = "\n".join(f"{key.title():<10}{value}" for key, value in message.checklist.items())
        _section(lines, "Checklist", checklist)
    if message.expired:
        lines.extend(("Status:", "EXPIRED — NO LONGER CURRENT", ""))
    elif message.expires_at_utc:
        _section(lines, "Expires", format_expiry(message.expires_at_utc, include_mmt=include_mmt))
    _section(lines, "Result", message.checklist_result)
    if message.reason_codes:
        _section(lines, "Reason", ", ".join(message.reason_codes))
    if message.governance_block:
        _section(lines, "Governance Block", message.governance_block)
    lines.extend(("Setup Valid:", _yes(message.setup_valid), "", "Proposal Eligible:",
                  _yes(message.proposal_eligible), "", "Execution Authorized:", "NO", ""))
    _section(lines, "Source", message.data_source)
    return "\n".join(lines).rstrip()
