"""Pass-through canonical rendering and opt-in HTTPS Bot API delivery.

No canonical builder import: evaluation, market data and authority stay upstream.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)
STATUSES = frozenset({"WATCH_READY", "INFO_ONLY_STALE", "INFO_ONLY_INSUFFICIENT_REMAINING_R",
                      "INFO_ONLY_POLICY_UNRESOLVED", "NO_TRADE", "EXPIRED", "MISSED",
                      "BLOCKED", "INSUFFICIENT_DATA", "OUT_OF_SESSION"})
STATE_PENDING = "pending"
STATE_SENT = "sent"
STATE_DELIVERED = "DELIVERED"
STATE_UNCERTAIN = "DELIVERY_UNCERTAIN"
DELIVERED_STATES = frozenset({STATE_SENT, STATE_DELIVERED})


def value(ticket, *path):
    current = ticket
    for key in path:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            return "SCHEMA_GAP: " + ".".join(path)
        current = current[key]
    # Keep each source fact on one line, including session-summary reasons.
    return " ".join(str(current).splitlines())


def validate(ticket):
    if ticket.get("schema") != "AG_CANONICAL_TICKET_V1":
        raise ValueError("Unsupported canonical schema")
    if ticket.get("decision") not in STATUSES:
        raise ValueError("Unsupported canonical decision")
    if not isinstance(ticket.get("ticket_id"), str) or not ticket["ticket_id"]:
        raise ValueError("SCHEMA_GAP: ticket_id")


def footer(ticket):
    return [f"Logic: {value(ticket, 'logic_status')}",
            f"Edge: {value(ticket, 'economic_edge')} ({value(ticket, 'economic_status')})",
            f"Actionability: {value(ticket, 'actionability', 'decision')} / "
            f"{value(ticket, 'actionability', 'reason')}", "EXECUTION: DISABLED"]


def render_ticket(ticket):
    validate(ticket)
    lines = [f"Ticket: {ticket['ticket_id']}",
             f"{value(ticket, 'instrument')} | {ticket['decision']} | {value(ticket, 'direction')}",
             f"Session: {value(ticket, 'session_date')} / {value(ticket, 'session')}",
             f"Reason: {value(ticket, 'reason_code')}", "Levels (supplied prices only):"]
    for label, key in (("TP2", "tp2"), ("TP1", "tp1"), ("NOW", "current_send"),
                       ("ENTRY", "entry_reference"), ("SL", "sl")):
        lines.append(f"{label:<5} +---------------- {value(ticket, 'prices', key)}")
    lines += [f"Remaining R TP1: {value(ticket, 'risk', 'remaining_R_tp1')}",
              f"Remaining R TP2: {value(ticket, 'risk', 'remaining_R_tp2')}"]
    return "\n".join(lines + footer(ticket))


def render_summary(tickets, uncertain=()):
    tickets = list(tickets)
    for ticket in tickets:
        validate(ticket)
    if tickets and len({(t.get("session_date"), t.get("session")) for t in tickets}) != 1:
        raise ValueError("Summary must contain exactly one session")
    lines = ["Session summary", f"Rows: {len(tickets)}"]
    for index, ticket in enumerate(tickets, 1):
        lines.append(f"{index}. {ticket['ticket_id']} | {value(ticket, 'instrument')} | "
                     f"{ticket['decision']} | {value(ticket, 'reason_code')} | "
                     + " | ".join(footer(ticket)[:3]))
    uncertain = list(uncertain)
    if uncertain:
        lines.append("Uncertain delivery:")
        for item in uncertain:
            identity = item["identity"] if isinstance(item, dict) else item[0]
            status = item.get("status", "") if isinstance(item, dict) else item[1]
            lines.append(f"- {identity} | {status} | {STATE_UNCERTAIN}")
    lines += ["Logic: see each row", "Edge: see each row", "Actionability: see each row",
              "EXECUTION: DISABLED"]
    return "\n".join(lines)


@dataclass(frozen=True)
class Config:
    enabled: bool = False
    token: str = ""
    chat_id: str = ""
    owner_chat_ids: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls):
        return cls(os.getenv("TELEGRAM_DELIVERY_ENABLED", "false").lower() == "true",
                   os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
                   os.getenv("TELEGRAM_CHAT_ID", "").strip(),
                   frozenset(x.strip() for x in os.getenv("TELEGRAM_OWNER_CHAT_IDS", "").split(",") if x.strip()))


def bot_api(token, chat_id, message):
    body = json.dumps({"chat_id": chat_id, "text": message}).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    if result.get("ok") is not True:
        raise RuntimeError("Telegram rejected message")


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class Sender:
    def __init__(self, store_path, config=None, transport=bot_api, sleep=time.sleep, attempts=3):
        if str(store_path) == ":memory:":
            raise ValueError("Persistent dedupe store required")
        if not 1 <= attempts <= 5:
            raise ValueError("attempts must be 1..5")
        self.path = Path(store_path)
        self.config = config if config is not None else Config.from_env()
        self.transport, self.sleep, self.attempts = transport, sleep, attempts

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("CREATE TABLE IF NOT EXISTS sent (kind TEXT, identity TEXT, status TEXT, "
                   "state TEXT, actor TEXT, updated_at TEXT, error_class TEXT, "
                   "PRIMARY KEY(kind, identity, status))")
        cols = {row[1] for row in db.execute("PRAGMA table_info(sent)")}
        if "error_class" not in cols:
            db.execute("ALTER TABLE sent ADD COLUMN error_class TEXT")
        if "actor" not in cols:
            db.execute("ALTER TABLE sent ADD COLUMN actor TEXT")
        if "updated_at" not in cols:
            db.execute("ALTER TABLE sent ADD COLUMN updated_at TEXT")
        return db

    def list_uncertain(self):
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path, timeout=15) as db:
            rows = db.execute(
                "SELECT kind, identity, status, error_class FROM sent WHERE state=?",
                (STATE_UNCERTAIN,),
            ).fetchall()
        return [{"kind": k, "identity": i, "status": s, "error_class": e} for k, i, s, e in rows]

    def _send(self, kind, identity, status, message, *, force=False, actor="", allow_duplicate=False):
        cfg = self.config
        if not cfg.enabled:
            LOG.info("Telegram delivery disabled")
            return "disabled"
        if not cfg.token.strip() or not cfg.chat_id.strip() or cfg.chat_id not in cfg.owner_chat_ids:
            LOG.error("Telegram delivery blocked: missing credentials or owner allowlist")
            return "blocked"
        # Bot API limit is UTF-16 code units. Never truncate or split a session.
        if len(message.encode("utf-16-le")) // 2 > 4096:
            LOG.error("Telegram delivery blocked: message exceeds 4096 units")
            return "blocked"
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT state FROM sent WHERE kind=? AND identity=? AND status=?",
                                 (kind, identity, status)).fetchone()
                if row:
                    if force and row[0] == STATE_UNCERTAIN:
                        LOG.info("Owner force resend actor=%s when=%s identity=%s",
                                 actor or "unspecified", _utc_now(), identity)
                    elif force and row[0] in DELIVERED_STATES and allow_duplicate:
                        LOG.info("Owner allow-duplicate resend actor=%s when=%s identity=%s",
                                 actor or "unspecified", _utc_now(), identity)
                    elif force:
                        LOG.error("Force resend refused: state=%s identity=%s actor=%s when=%s",
                                  row[0], identity, actor or "unspecified", _utc_now())
                        return "refused"
                    else:
                        LOG.info("Telegram dedupe: %s", row[0])
                        return "duplicate"
                else:
                    if force:
                        LOG.error("Force resend refused: no UNCERTAIN claim identity=%s actor=%s",
                                  identity, actor or "unspecified")
                        return "refused"
                    # Durable claim before network: a crash/ambiguous timeout cannot resend on restart.
                    db.execute(
                        "INSERT INTO sent (kind, identity, status, state, actor, updated_at, error_class) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (kind, identity, status, STATE_PENDING, actor, _utc_now(), None),
                    )
                    db.commit()
                    db.execute("BEGIN IMMEDIATE")
                for attempt in range(self.attempts):
                    try:
                        self.transport(cfg.token, cfg.chat_id, message)
                        db.execute("UPDATE sent SET state=?, actor=?, updated_at=?, error_class=? "
                                   "WHERE kind=? AND identity=? AND status=?",
                                   (STATE_DELIVERED, actor, _utc_now(), None, kind, identity, status))
                        db.commit()
                        return "sent"
                    except urllib.error.HTTPError as error:
                        LOG.error("Telegram HTTP failure: status=%s attempt=%s", error.code, attempt + 1)
                        # Explicit rejection is safe to retry; ambiguous network failures are not.
                        if error.code not in (429, 500, 502, 503, 504) or attempt + 1 == self.attempts:
                            break
                        self.sleep(2 ** attempt)
                    except Exception as error:
                        # Persist class name only — never the message (may contain token URL).
                        LOG.error("Telegram delivery ambiguous; automatic resend suppressed")
                        db.execute("UPDATE sent SET state=?, actor=?, updated_at=?, error_class=? "
                                   "WHERE kind=? AND identity=? AND status=?",
                                   (STATE_UNCERTAIN, actor, _utc_now(), type(error).__name__,
                                    kind, identity, status))
                        db.commit()
                        return "uncertain"
                return "failed"
        except (OSError, sqlite3.Error):
            LOG.error("Telegram dedupe persistence failure; delivery stopped")
            return "failed"

    def send_ticket(self, ticket):
        validate(ticket)
        # Routing uses canonical decisions; presentation may be OTHER for policy-unresolved.
        if ticket["decision"] != "WATCH_READY" and not ticket["decision"].startswith("INFO_ONLY_"):
            return "summary_only"
        return self._send("ticket", ticket["ticket_id"], ticket["decision"], render_ticket(ticket))

    def send_summary(self, tickets):
        tickets = list(tickets)
        message = render_summary(tickets, uncertain=self.list_uncertain())
        if not tickets:
            raise ValueError("Session identity requires at least one ticket")
        identity = json.dumps([tickets[0]["session_date"], tickets[0]["session"]], separators=(",", ":"))
        return self._send("session", identity, "", message)

    def resend_ticket(self, ticket, *, force, actor, allow_duplicate=False):
        if not force:
            raise ValueError("owner-invoked --force required")
        if not actor or not str(actor).strip():
            raise ValueError("owner actor is an audit label and is required")
        cfg = self.config
        if not cfg.enabled or cfg.chat_id not in cfg.owner_chat_ids:
            LOG.error("Telegram force resend refused: not owner-invoked")
            return "blocked"
        validate(ticket)
        if ticket["decision"] != "WATCH_READY" and not ticket["decision"].startswith("INFO_ONLY_"):
            return "summary_only"
        LOG.info("Force resend requested actor=%s when=%s ticket_id=%s allow_duplicate=%s",
                 actor, _utc_now(), ticket["ticket_id"], allow_duplicate)
        return self._send("ticket", ticket["ticket_id"], ticket["decision"],
                          render_ticket(ticket), force=True, actor=actor,
                          allow_duplicate=allow_duplicate)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="telegram_delivery")
    sub = parser.add_subparsers(dest="command", required=True)
    resend = sub.add_parser("resend", help="Owner-only forced resend of an uncertain ticket")
    resend.add_argument("--ticket-id", required=True)
    resend.add_argument("--force", action="store_true")
    resend.add_argument("--store", required=True)
    resend.add_argument("--ticket-file", required=True, help="JSON object or array containing the ticket")
    resend.add_argument("--actor", default=os.getenv("USER", "owner"),
                        help="Audit label only; not authentication")
    resend.add_argument("--allow-duplicate", action="store_true",
                        help="Permit force resend when state is already DELIVERED")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.ticket_file).read_text())
    tickets = payload if isinstance(payload, list) else [payload]
    ticket = next((t for t in tickets if t.get("ticket_id") == args.ticket_id), None)
    if ticket is None:
        raise SystemExit("ticket-id not found")
    result = Sender(args.store).resend_ticket(
        ticket, force=args.force, actor=args.actor, allow_duplicate=args.allow_duplicate)
    print(result)
    return result


if __name__ == "__main__":
    main()
