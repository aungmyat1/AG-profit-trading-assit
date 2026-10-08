"""Pass-through canonical rendering and opt-in HTTPS Bot API delivery.

No canonical builder import: evaluation, market data and authority stay upstream.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from telegram_delivery.scope_policy import resolve as resolve_immediate_scope

LOG = logging.getLogger(__name__)
STATUSES = frozenset({"WATCH_READY", "INFO_ONLY_STALE", "INFO_ONLY_INSUFFICIENT_REMAINING_R",
                      "INFO_ONLY_POLICY_UNRESOLVED", "INFO_ONLY_SUPPRESSED", "NO_TRADE",
                      "EXPIRED", "MISSED", "BLOCKED", "INSUFFICIENT_DATA", "OUT_OF_SESSION"})
STATE_PENDING = "pending"
STATE_SENT = "sent"
STATE_DELIVERED = "DELIVERED"
STATE_UNCERTAIN = "DELIVERY_UNCERTAIN"
STATE_FAILED = "DELIVERY_FAILED"


class DeliveryInProgress(Exception):
    """Another process holds the delivery-key lock."""
DELIVERED_STATES = frozenset({STATE_SENT, STATE_DELIVERED})


def value(ticket, *path):
    current = ticket
    for key in path:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            return "SCHEMA_GAP: " + ".".join(path)
        current = current[key]
    # Keep each source fact on one line, including session-summary reasons.
    return " ".join(str(current).splitlines())


def _known_decision(decision):
    return isinstance(decision, str) and decision in STATUSES


def _informational_scope(decision):
    """WATCH_READY and non-suppressed INFO_ONLY_* -- gated by the C16 scope flag."""
    return isinstance(decision, str) and decision != "INFO_ONLY_SUPPRESSED" and (
        decision == "WATCH_READY" or decision.startswith("INFO_ONLY_"))


def validate(ticket):
    if ticket.get("schema") != "AG_CANONICAL_TICKET_V1":
        raise ValueError("Unsupported canonical schema")
    if not _known_decision(ticket.get("decision")):
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
            lines.append(f"- possibly undelivered: {identity} | {status} | {STATE_UNCERTAIN}")
    lines += ["Logic: see each row", "Edge: see each row", "Actionability: see each row",
              "EXECUTION: DISABLED"]
    return "\n".join(lines)


def render_session_summary(summary):
    """Render one deterministic per-session digest from already-aggregated durable facts."""
    if summary.get("schema") != "AGP_HOST_TICKET_DELIVERY_R1_SESSION_SUMMARY_V1":
        raise ValueError("Unsupported session summary schema")
    session_date, session = summary.get("session_date"), summary.get("session")
    if not isinstance(session_date, str) or not session_date or not isinstance(session, str) or not session:
        raise ValueError("SCHEMA_GAP: session identity")
    expected, recorded = summary.get("expected_evaluations"), summary.get("recorded_evaluations")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
        raise ValueError("SCHEMA_GAP: expected_evaluations")
    if not isinstance(recorded, int) or isinstance(recorded, bool) or recorded < 0 or recorded > expected:
        raise ValueError("Invalid recorded_evaluations")
    terminal = summary.get("terminal_counts") or {}
    delivery = summary.get("delivery_counts") or {}
    lines = ["Canonical FX session summary -- INFORMATIONAL",
             f"Session: {session_date} / {session}",
             f"Durable evaluations: {recorded}/{expected}",
             f"Session status: {value(summary, 'status')}", "Terminal outcomes:"]
    nonzero = [(state, terminal.get(state, 0)) for state in sorted(STATUSES) if terminal.get(state, 0)]
    compatibility_count = summary.get("compatibility_error_count", terminal.get("COMPATIBILITY_ERROR", 0))
    if compatibility_count:
        nonzero.append(("COMPATIBILITY_ERROR", compatibility_count))
    lines += [f"- {state}: {count}" for state, count in nonzero] or ["- none recorded"]
    missed = list(summary.get("missed_pairs") or ())
    missed_count = summary.get("missed_count", len(missed))
    if not isinstance(missed_count, int) or isinstance(missed_count, bool) or missed_count < 0:
        raise ValueError("Invalid missed_count")
    lines.append(f"Missing scheduled evaluations (MISSED): {missed_count}")
    for item in missed:
        lines.append(f"- MISSED {item.get('symbol', 'SCHEMA_GAP')} | {item.get('reason_code', 'SCHEMA_GAP')}")
    out_of_session = list(summary.get("out_of_session_pairs") or ())
    lines.append(f"Out-of-session pairs: {len(out_of_session)}")
    for item in out_of_session:
        lines.append(f"- OUT_OF_SESSION {item.get('symbol', 'SCHEMA_GAP')} | "
                     f"{item.get('reason_code', 'SCHEMA_GAP')}")
    lines.append(f"Data failures: {summary.get('data_failure_count', 0)}")
    lines.append(f"Delivery enabled: {str(bool(summary.get('delivery_enabled', False))).lower()}")
    lines.append(f"TICKET_STORE persistence failures: {summary.get('persistence_failure_count', 0)}")
    lines.append(f"Compatibility errors: {summary.get('compatibility_error_count', 0)}")
    for label, key in (("SUCCEEDED", "succeeded"), ("FAILED", "failed"),
                       ("UNCERTAIN", "uncertain"), ("DISABLED", "disabled"),
                       ("BLOCKED", "blocked"), ("SUMMARY_ONLY", "summary_only"),
                       ("PERSISTENCE_FAILED", "persistence_failed"), ("NOT_ATTEMPTED", "not_attempted")):
        count = delivery.get(key, 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"Invalid delivery count {key}")
        lines.append(f"Delivery {label}: {count}")
    uncertain = list(summary.get("uncertain_deliveries") or ())
    if uncertain:
        lines.append("Possibly undelivered (no automatic retry):")
        for item in sorted(uncertain, key=lambda x: (str(x.get("identity", "")), str(x.get("status", "")))):
            lines.append(f"- {item.get('identity', 'SCHEMA_GAP')} | {item.get('status', STATE_UNCERTAIN)}")
    lines.append("EXECUTION: DISABLED")
    return "\n".join(lines)


@dataclass(frozen=True)
class Config:
    enabled: bool = False
    token: str = ""
    chat_id: str = ""
    owner_chat_ids: frozenset[str] = frozenset()
    # C16 (OWNER_DECISION_REGISTER, PENDING_OWNER): WATCH_READY and non-suppressed INFO_ONLY_*
    # are informational. They are sent (scheduled or owner-resent) only when this default-OFF
    # flag is explicitly enabled; otherwise they stay archive/summary-only.
    watch_info_scope: bool = False
    immediate_scopes: frozenset[str] = frozenset()
    scope_error: str | None = None

    @classmethod
    def from_env(cls, root="."):
        scope = resolve_immediate_scope(root, sender="canonical")
        return cls(os.getenv("TELEGRAM_DELIVERY_ENABLED", "false").lower() == "true",
                   os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
                   os.getenv("TELEGRAM_CHAT_ID", "").strip(),
                   frozenset(x.strip() for x in os.getenv("TELEGRAM_OWNER_CHAT_IDS", "").split(",") if x.strip()),
                   immediate_scopes=frozenset(scope["effective"]), scope_error=scope["error"])


def bot_api(token, chat_id, message):
    """Use monospace HTML; fallback only after an explicit HTML-format rejection.

    A timeout/reset may follow acceptance and must propagate to the durable journal.
    Never try a fallback for ambiguous transport failures or unrelated API errors.
    """
    def post(text, parse_mode=None):
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)
        if result.get("ok") is not True:
            raise urllib.error.HTTPError("<redacted>", result.get("error_code", 500),
                                         "Telegram rejected message", {},
                                         io.BytesIO(json.dumps(result).encode()))

    try:
        post("<pre>" + html.escape(message, quote=False) + "</pre>", "HTML")
    except urllib.error.HTTPError as error:
        # Telegram explicitly rejects malformed/unsupported HTML with HTTP 400.
        # Do not downgrade authorization, chat, length, rate-limit or server errors.
        description = ""
        if error.code == 400 and error.fp is not None:
            try:
                description = json.loads(error.read()).get("description", "").lower()
            except (ValueError, TypeError, AttributeError):
                pass
        if error.code != 400 or not any(term in description for term in (
                "can't parse entities", "cannot parse entities", "unsupported start tag",
                "parse_mode", "parse mode")):
            raise
        LOG.warning("Telegram HTML rejected; falling back to plain text")
        post(message)


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
        db.execute(
            "CREATE TABLE IF NOT EXISTS compatibility_errors ("
            "kind TEXT NOT NULL, identity TEXT NOT NULL, error_code TEXT NOT NULL, "
            "observed_decision TEXT NOT NULL, expected_decisions TEXT NOT NULL, created_at TEXT NOT NULL, "
            "PRIMARY KEY(kind, identity, observed_decision))"
        )
        return db

    def _record_compatibility_error(self, ticket):
        decision = ticket.get("decision")
        observed = str(decision)[:120] if decision is not None else "<missing>"
        identity = ticket.get("ticket_id")
        if not isinstance(identity, str) or not identity:
            identity = "unkeyed:" + hashlib.sha256(
                json.dumps(ticket, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest()
        expected = json.dumps(sorted(STATUSES), separators=(",", ":"))
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO compatibility_errors "
                    "(kind, identity, error_code, observed_decision, expected_decisions, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("ticket", identity, "UNKNOWN_CANONICAL_DECISION", observed, expected, _utc_now()),
                )
            LOG.error("Canonical delivery compatibility error: UNKNOWN_CANONICAL_DECISION identity=%s", identity)
            return "compatibility_error"
        except (OSError, sqlite3.Error):
            LOG.error("Canonical compatibility diagnostic persistence failed; delivery stopped")
            return "compatibility_error_unpersisted"

    def compatibility_errors(self):
        if not self.path.exists():
            return []
        with self._connect() as db:
            rows = db.execute(
                "SELECT kind, identity, error_code, observed_decision, expected_decisions, created_at "
                "FROM compatibility_errors ORDER BY created_at, identity"
            ).fetchall()
        return [{"kind": kind, "identity": identity, "error_code": code,
                 "observed_decision": observed, "expected_decisions": json.loads(expected),
                 "created_at": created}
                for kind, identity, code, observed, expected, created in rows]

    @contextmanager
    def _key_lock(self, kind, identity, status):
        # A separate SQLite lock per key serializes retries/recovery of that key,
        # without blocking unrelated tickets in the main journal during network I/O.
        directory = Path(str(self.path) + ".locks")
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps([kind, identity, status]).encode()).hexdigest()
        lock = sqlite3.connect(directory / (key + ".sqlite"), timeout=0)
        try:
            try:
                lock.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                if error.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise DeliveryInProgress from error
                raise
            yield
        finally:
            lock.rollback()
            lock.close()

    @staticmethod
    def _recover_pending(db, kind, identity, status):
        # Caller holds the key lock: a surviving pending claim has no active sender.
        db.execute("UPDATE sent SET state=?, updated_at=?, error_class=? "
                   "WHERE kind=? AND identity=? AND status=? AND state=?",
                   (STATE_UNCERTAIN, _utc_now(), "InterruptedSend", kind, identity,
                    status, STATE_PENDING))

    def list_uncertain(self):
        if not self.path.exists():
            return []
        with self._connect() as db:
            rows = db.execute("SELECT kind, identity, status FROM sent WHERE state=?",
                              (STATE_PENDING,)).fetchall()
            for kind, identity, status in rows:
                try:
                    with self._key_lock(kind, identity, status):
                        self._recover_pending(db, kind, identity, status)
                        db.commit()
                except DeliveryInProgress:
                    continue  # An active request is not a crash-left pending claim.
            rows = db.execute(
                "SELECT kind, identity, status, error_class FROM sent WHERE state=?",
                (STATE_UNCERTAIN,),
            ).fetchall()
        return [{"kind": k, "identity": i, "status": s, "error_class": e} for k, i, s, e in rows]

    def delivery_attempts(self, kind, identities=()):
        """Read durable attempt state without creating a journal or exposing credentials."""
        if not self.path.exists():
            return []
        identities = tuple(sorted(set(identities)))
        with self._connect() as db:
            if identities:
                marks = ",".join("?" for _ in identities)
                rows = db.execute(
                    f"SELECT identity, status, state, error_class, updated_at FROM sent "
                    f"WHERE kind=? AND identity IN ({marks}) ORDER BY identity, status",
                    (kind, *identities),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT identity, status, state, error_class, updated_at FROM sent "
                    "WHERE kind=? ORDER BY identity, status", (kind,)
                ).fetchall()
        return [{"identity": i, "status": s, "state": state, "error_class": error, "updated_at": at}
                for i, s, state, error, at in rows]

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
            with self._key_lock(kind, identity, status), self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self._recover_pending(db, kind, identity, status)
                row = db.execute("SELECT state FROM sent WHERE kind=? AND identity=? AND status=?",
                                 (kind, identity, status)).fetchone()
                if row:
                    if force and row[0] in (STATE_UNCERTAIN, STATE_FAILED):
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
                # Commit both new claims and forced-resend claims before network.
                if force:
                    db.execute("UPDATE sent SET state=?, actor=?, updated_at=?, error_class=NULL "
                               "WHERE kind=? AND identity=? AND status=?",
                               (STATE_PENDING, actor, _utc_now(), kind, identity, status))
                db.commit()
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
                        # A 5xx may follow acceptance: preserve ambiguity without another send.
                        if error.code >= 500:
                            db.execute("UPDATE sent SET state=?, updated_at=?, error_class=? "
                                       "WHERE kind=? AND identity=? AND status=?",
                                       (STATE_UNCERTAIN, _utc_now(), "HTTPError", kind, identity, status))
                            db.commit()
                            return "uncertain"
                        if error.code != 429 or attempt + 1 == self.attempts:
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
                db.execute("UPDATE sent SET state=?, updated_at=?, error_class=? "
                           "WHERE kind=? AND identity=? AND status=?",
                           (STATE_FAILED, _utc_now(), "HTTPError", kind, identity, status))
                db.commit()
                return "failed"
        except DeliveryInProgress:
            LOG.info("Telegram dedupe: delivery already in progress")
            return "duplicate"
        except (OSError, sqlite3.Error):
            LOG.error("Telegram dedupe persistence failure; delivery stopped")
            return "failed"

    def send_ticket(self, ticket):
        # The canonical store is written upstream before this router is called. Unknown taxonomy
        # values fail closed and leave a durable compatibility diagnostic in this adapter journal.
        if not _known_decision(ticket.get("decision")):
            return self._record_compatibility_error(ticket)
        validate(ticket)
        if self.config.scope_error:
            LOG.error("Telegram scope rejected: %s", self.config.scope_error)
            return "blocked"
        # The authority-suppressed READY is durable but must never become an immediate alert.
        if ticket["decision"] == "INFO_ONLY_SUPPRESSED":
            return "summary_only"
        # Other INFO_ONLY states remain explicitly informational (the renderer stamps execution
        # disabled); terminal non-alert decisions are visible through the session summary only.
        if ticket["decision"] != "WATCH_READY" and not ticket["decision"].startswith("INFO_ONLY_"):
            return "summary_only"
        if self.config.immediate_scopes and ticket["decision"] not in self.config.immediate_scopes:
            return "summary_only"
        # Same C16 scope flag as owner resend: informational states stay summary-only unless enabled.
        if not self.config.watch_info_scope:
            return "summary_only"
        return self._send("ticket", ticket["ticket_id"], ticket["decision"], render_ticket(ticket))

    def send_summary(self, tickets):
        tickets = list(tickets)
        message = render_summary(tickets, uncertain=self.list_uncertain())
        if not tickets:
            raise ValueError("Session identity requires at least one ticket")
        identity = json.dumps([tickets[0]["session_date"], tickets[0]["session"]], separators=(",", ":"))
        return self._send("session", identity, "", message)

    def send_session_summary(self, summary):
        message = render_session_summary(summary)
        identity = json.dumps([summary["session_date"], summary["session"]], separators=(",", ":"))
        return self._send("session_summary", identity, "AGP_HOST_TICKET_DELIVERY_R1", message)

    def resend_ticket(self, ticket, *, force, actor, allow_duplicate=False):
        if not force:
            raise ValueError("owner-invoked --force required")
        if not actor or not str(actor).strip():
            raise ValueError("owner actor is an audit label and is required")
        cfg = self.config
        if not cfg.enabled or cfg.chat_id not in cfg.owner_chat_ids:
            LOG.error("Telegram force resend refused: not owner-invoked")
            return "blocked"
        if not _known_decision(ticket.get("decision")):
            return self._record_compatibility_error(ticket)
        validate(ticket)
        if cfg.scope_error:
            LOG.error("Telegram scope rejected: %s", cfg.scope_error)
            return "blocked"
        if ticket["decision"] == "INFO_ONLY_SUPPRESSED":
            return "summary_only"
        if ticket["decision"] != "WATCH_READY" and not ticket["decision"].startswith("INFO_ONLY_"):
            return "summary_only"
        if _informational_scope(ticket["decision"]) and not cfg.watch_info_scope:
            LOG.error("Telegram force resend refused: C16 informational scope not enabled")
            return "SCOPE_NOT_ENABLED"
        if cfg.immediate_scopes and ticket["decision"] not in cfg.immediate_scopes:
            LOG.error("Telegram force resend refused: decision is outside tracked immediate scope")
            return "SCOPE_NOT_ENABLED"
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
