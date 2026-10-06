"""Manual Trade Ticket V1 Phase 6 -- owner decision capture (append-only).

A dedicated manual-ticket decision contract; src/contracts/v1.py (immutable V1) is not
changed. One decision per ticket, appended to the existing journal store
(journal/ticket_delivery/manual/owner_decisions.jsonl); a second decision for the same
ticket is refused, nothing is ever rewritten.

TAKEN records what the owner actually did by hand in MT5 -- the system never places it.
It is accepted only for a ticket that was TICKET_READY and filled before valid_until.
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

from v1_tickets.manual_ticket import ticket_path
from v1_tickets.scan_record import append_jsonl, read_jsonl

SCHEMA = "AG_MANUAL_TICKET_DECISION_V1"
TAKEN, SKIPPED, MISSED, EXPIRED = "TAKEN", "SKIPPED", "MISSED", "EXPIRED"
DECISIONS = (TAKEN, SKIPPED, MISSED, EXPIRED)
SKIP_REASONS = ("NEWS", "DISAGREE_CONTEXT", "COST_TOO_HIGH", "TIME", "OTHER")
DECISION_FILE = os.path.join("ticket_delivery", "manual", "owner_decisions.jsonl")


class DecisionError(ValueError):
    pass


@dataclass(frozen=True)
class ManualTicketDecision:
    ticket_id: str
    decision: str
    recorded_at: str
    source: str = "OWNER"                 # OWNER | AUTO_EXPIRY
    fill_time: Optional[str] = None
    actual_fill: Optional[float] = None
    actual_sl: Optional[float] = None
    actual_tp: Optional[float] = None
    deviation_note: Optional[str] = None
    skip_reason: Optional[str] = None
    note: Optional[str] = None
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise DecisionError(f"decision {self.decision!r} not in {DECISIONS}")
        if self.decision == TAKEN and (self.actual_fill is None or self.actual_sl is None or not self.fill_time):
            raise DecisionError("TAKEN requires fill_time, actual_fill and actual_sl")
        if self.decision == SKIPPED:
            if self.skip_reason not in SKIP_REASONS:
                raise DecisionError(f"SKIPPED requires skip_reason in {SKIP_REASONS}")
            if self.skip_reason == "OTHER" and not self.note:
                raise DecisionError("skip_reason OTHER requires a note")
        if self.decision != TAKEN and any(v is not None for v in (self.actual_fill, self.actual_sl, self.actual_tp)):
            raise DecisionError(f"{self.decision} cannot carry fill prices")


def decision_path(journal: str) -> str:
    return os.path.join(journal, DECISION_FILE)


def load_decisions(journal: str) -> Dict[str, Dict[str, Any]]:
    return {d["ticket_id"]: d for d in read_jsonl(decision_path(journal))}


def _decision_version(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The TICKET_READY version the owner was shown, else the latest line (it may later expire)."""
    ready = [t for t in rows if t.get("state") == "TICKET_READY"]
    return ready[-1] if ready else (rows[-1] if rows else None)


def decision_ticket(journal: str, ticket_id: str, day: dt.date) -> Optional[Dict[str, Any]]:
    return _decision_version([t for t in read_jsonl(ticket_path(journal, day)) if t.get("ticket_id") == ticket_id])


def _parse(ts: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(ts)
    if t.tzinfo is None:
        raise DecisionError(f"timestamp {ts!r} must be timezone-aware")
    return t.astimezone(dt.timezone.utc)


def record_decision(journal: str, ticket: Dict[str, Any], decision: ManualTicketDecision) -> Dict[str, Any]:
    if decision.ticket_id != ticket.get("ticket_id"):
        raise DecisionError("decision ticket_id does not match the ticket")
    if decision.ticket_id in load_decisions(journal):
        raise DecisionError("DECISION_ALREADY_RECORDED: append-only, one decision per ticket")
    if ticket.get("direction") is None:
        raise DecisionError("ticket has no order fields; nothing to decide")
    if decision.decision == TAKEN:
        if ticket.get("state") != "TICKET_READY":
            raise DecisionError(f"TAKEN refused: ticket state {ticket.get('state')} is not TICKET_READY")
        if _parse(decision.fill_time) >= _parse(ticket["valid_until"]):
            raise DecisionError("TAKEN refused: fill_time is at/after valid_until (ticket EXPIRED)")
    entry = {**asdict(decision), "strategy": ticket.get("strategy"), "symbol": ticket.get("symbol"),
             "session": ticket.get("session"), "session_date": ticket.get("session_date"),
             "ticket_state": ticket.get("state"), "ticket_content_hash": ticket.get("content_hash")}
    append_jsonl(decision_path(journal), entry)
    return entry


def expire_undecided(journal: str, tickets: Iterable[Dict[str, Any]], now: dt.datetime) -> List[Dict[str, Any]]:
    """Auto EXPIRED at valid_until for every TICKET_READY ticket without an owner decision."""
    decided = load_decisions(journal)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for t in tickets:
        grouped.setdefault(t["ticket_id"], []).append(t)
    out = []
    for t in (_decision_version(rows) for rows in grouped.values()):
        if t.get("state") != "TICKET_READY" or t["ticket_id"] in decided or not t.get("valid_until"):
            continue
        if now >= _parse(t["valid_until"]):
            out.append(record_decision(journal, t, ManualTicketDecision(
                ticket_id=t["ticket_id"], decision=EXPIRED, recorded_at=now.isoformat(), source="AUTO_EXPIRY")))
    return out
