"""Fail-closed Telegram confirmation callbacks for archived manual TICKET_READY tickets.

This module records owner intent only. It has no broker/execution imports or calls.
"""
from __future__ import annotations

import base64
import datetime as dt
import glob
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml

from v1_tickets.code_identity import code_sha
from v1_tickets.owner_decision import ACCEPTED, REJECTED, DecisionError, ManualTicketDecision, decision_path, load_decisions, record_decision
from v1_tickets.scan_record import read_jsonl

UTC = dt.timezone.utc
MMT = dt.timezone(dt.timedelta(hours=6, minutes=30))
TICKET_DIR = os.path.join("ticket_delivery", "manual", "tickets")
REGISTRY_PATH = "strategies/registry.yaml"
TICKET_DELIVERY_CONFIG = "config/ticket_delivery.yaml"
EXECUTION_CONFIG = "config/trading.yaml"
BLOCKED_NOT_AUTHORIZED = "BLOCKED_NOT_AUTHORIZED"


def _parse_utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(UTC)


def _ticket_data(ticket: Dict[str, Any], action: str) -> bytes:
    return "\0".join((ticket["ticket_id"], str(ticket["strategy_id"]),
                      str(ticket["strategy_version"]), str(ticket["code_sha"]),
                      str(ticket["valid_until"]), action)).encode("utf-8")


def callback_data(ticket: Dict[str, Any], action: str, secret: str) -> str:
    """Return a Telegram-safe opaque callback token bound to the full archived identity."""
    if action not in ("accept", "reject") or not secret:
        raise ValueError("invalid callback action or missing callback secret")
    digest = hmac.new(secret.encode("utf-8"), _ticket_data(ticket, action), hashlib.sha256).digest()[:18]
    token = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"v1:{'a' if action == 'accept' else 'r'}:{token}"


def allowed_chat_ids(root: str = ".") -> frozenset[str]:
    """Read explicit destination authorization; absent/malformed config authorizes nobody."""
    try:
        raw = yaml.safe_load(Path(root, TICKET_DELIVERY_CONFIG).read_text(encoding="utf-8")) or {}
        values = raw.get("telegram_destination", {}).get("authorized_chat_ids", ())
        if not isinstance(values, (list, tuple)):
            return frozenset()
        return frozenset(str(v) for v in values if isinstance(v, (str, int)) and str(v))
    except (OSError, TypeError, yaml.YAMLError):
        return frozenset()


def render_confirmation(ticket: Dict[str, Any], secret: str) -> tuple[str, Dict[str, Any]]:
    """Render only canonical engine ticket fields and add buttons to TICKET_READY tickets."""
    if ticket.get("state") != "TICKET_READY":
        raise ValueError("confirmation controls require TICKET_READY")
    expires = _parse_utc(ticket["valid_until"])
    targets = ticket.get("targets") or []
    tp1 = ticket.get("tp1", next((x.get("price") for x in targets if x.get("leg") == 1), None))
    tp2 = ticket.get("tp2", next((x.get("price") for x in targets if x.get("leg") == 2), None))
    freshness = ticket.get("data_freshness_s")
    if freshness is None:
        freshness = "UNKNOWN"
    freshness = f"{freshness}s; L6 {(ticket.get('logic_gate') or {}).get('L6', {}).get('status', 'UNKNOWN')}"
    text = "\n".join((
        f"{ticket.get('symbol', '-')}, {ticket.get('session', '-')}, {ticket.get('direction', '-')}",
        f"Entry {ticket.get('entry', '-')} | SL {ticket.get('sl', ticket.get('stop_loss', '-'))} | TP1 {tp1 or '-'} | TP2 {tp2 or '-'}",
        f"R {ticket.get('risk_distance', ticket.get('stop_distance', '-'))} | Spread {ticket.get('spread', ticket.get('cost_in_R', '-'))}",
        f"Freshness {freshness}",
        f"Strategy {ticket.get('strategy_id', '-')} v{ticket.get('strategy_version', '-')}",
        f"Logic status {ticket.get('logic_status', 'UNKNOWN')}",
        "NOT EDGE-VERIFIED",
        f"Expires {expires:%Y-%m-%d %H:%M UTC} / {expires.astimezone(MMT):%Y-%m-%d %H:%M MMT}",
    ))
    callback_ticket = dict(ticket)
    callback_ticket.setdefault("code_sha", code_sha())
    keyboard = {"inline_keyboard": [[
        {"text": "Accept", "callback_data": callback_data(callback_ticket, "accept", secret)},
        {"text": "Reject", "callback_data": callback_data(callback_ticket, "reject", secret)},
    ]]}
    return text, keyboard


def send_confirmation(text: str, reply_markup: Dict[str, Any], *, root: str = ".",
                      session: Optional[Any] = None) -> None:
    """Send the manual TICKET_READY message with its inline controls; never polls or executes."""
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    if chat_id not in allowed_chat_ids(root):
        raise RuntimeError("Telegram destination is not allowlisted")
    if session is None:
        import requests as session  # noqa: N813
    try:
        response = session.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=10,
                                data={"chat_id": chat_id, "text": text[:4000],
                                      "disable_web_page_preview": True,
                                      "reply_markup": json.dumps(reply_markup, separators=(",", ":"))})
        ok = response.status_code == 200 and bool((response.json() or {}).get("ok"))
    except Exception as exc:  # noqa: BLE001 -- never surface the token-bearing URL
        raise RuntimeError(f"confirmation send failed ({type(exc).__name__})") from None
    if not ok:
        raise RuntimeError(f"confirmation send failed (HTTP {getattr(response, 'status_code', '?')})")


def _archived_tickets(journal: str) -> Iterable[Dict[str, Any]]:
    for path in sorted(glob.glob(os.path.join(journal, TICKET_DIR, "*.jsonl"))):
        yield from read_jsonl(path)


def execution_handoff(ticket: Dict[str, Any], *, root: str = ".") -> Dict[str, str]:
    """Canonical handoff stub; execution is deliberately disabled and broker-free."""
    try:
        registry = yaml.safe_load(Path(root, REGISTRY_PATH).read_text(encoding="utf-8")) or {}
        strategies = registry.get("strategies", {})
        entry = strategies.get(ticket.get("strategy_id"), {})
        if entry.get("demo_authorized") is not True:
            return {"status": BLOCKED_NOT_AUTHORIZED, "reason": "STRATEGY_DEMO_NOT_AUTHORIZED"}
        trading = yaml.safe_load(Path(root, EXECUTION_CONFIG).read_text(encoding="utf-8")) or {}
        if (trading.get("execution") or {}).get("allow_order_send") is not True:
            return {"status": BLOCKED_NOT_AUTHORIZED, "reason": "EXECUTION_ORDER_SEND_DISABLED"}
    except (OSError, TypeError, yaml.YAMLError):
        return {"status": BLOCKED_NOT_AUTHORIZED, "reason": "AUTHORITY_CONFIG_UNAVAILABLE"}
    return {"status": BLOCKED_NOT_AUTHORIZED, "reason": "HANDOFF_NOT_IMPLEMENTED"}


def handle_callback(*, callback: str, chat_id: str, journal: str, now: dt.datetime,
                    root: str = ".", secret: Optional[str] = None, host_online: bool = True,
                    chat_allowlist: Optional[Iterable[str]] = None) -> str:
    """Validate and record one owner decision. Repeated identical taps are idempotent."""
    if chat_id not in (frozenset(str(x) for x in chat_allowlist) if chat_allowlist is not None else allowed_chat_ids(root)):
        return "Confirmation refused: chat is not authorized."
    if not host_online:
        return "Confirmation refused: host is offline; no decision was recorded."
    key = secret if secret is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
    parts = callback.split(":")
    if not key or len(parts) != 3 or parts[0] != "v1" or parts[1] not in ("a", "r"):
        return "Confirmation refused: invalid callback data."
    action = "accept" if parts[1] == "a" else "reject"
    matched = None
    for ticket in _archived_tickets(journal):
        if ticket.get("state") != "TICKET_READY":
            continue
        try:
            if hmac.compare_digest(callback, callback_data(ticket, action, key)):
                matched = ticket
                break
        except (KeyError, ValueError):
            continue
    if matched is None:
        return "Confirmation refused: ticket identity or callback signature is invalid."
    if matched.get("code_sha") != code_sha():
        return "Confirmation refused: ticket code SHA does not match this host version."
    try:
        if now.astimezone(UTC) >= _parse_utc(matched["valid_until"]):
            return "Confirmation refused: ticket has expired; no decision was recorded."
    except (KeyError, ValueError):
        return "Confirmation refused: ticket expiry is invalid; no decision was recorded."
    existing = load_decisions(journal).get(matched["ticket_id"])
    decision = ACCEPTED if action == "accept" else REJECTED
    if existing:
        if existing.get("decision") == decision:
            if decision == REJECTED:
                return "Reject already recorded; no execution handoff was made."
            handoff = execution_handoff(matched, root=root)
            return f"Accept already recorded; {handoff['status']}: {handoff['reason']}."
        return "Confirmation refused: a different owner decision is already recorded."
    try:
        record_decision(journal, matched, ManualTicketDecision(
            ticket_id=matched["ticket_id"], decision=decision, recorded_at=now.astimezone(UTC).isoformat()))
    except DecisionError as exc:
        return f"Confirmation refused: {str(exc)}."
    if decision == REJECTED:
        return "Rejected and recorded; no execution handoff was made."
    handoff = execution_handoff(matched, root=root)
    return f"Accepted and recorded; {handoff['status']}: {handoff['reason']}."


def process_callback_update(update: Dict[str, Any], *, journal: str, now: dt.datetime,
                            root: str = ".", session: Optional[Any] = None,
                            host_online: bool = True) -> str:
    """Handle one Telegram callback update and show the result to its originating chat."""
    query = update.get("callback_query") or {}
    message = query.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    callback_id = str(query.get("id", ""))
    result = handle_callback(callback=str(query.get("data", "")), chat_id=chat_id,
                             journal=journal, now=now, root=root, host_online=host_online)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not callback_id:
        return result
    if session is None:
        import requests as session  # noqa: N813
    try:
        session.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", timeout=10,
                     data={"callback_query_id": callback_id, "text": result[:200], "show_alert": True})
    except Exception:  # noqa: BLE001 -- sanitize token-bearing URL; result remains available to caller
        return result
    return result
