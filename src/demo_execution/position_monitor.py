"""DEMO reconciliation monitor and restart recovery (AGP-AUTODEMO-D1). Read-only at the broker.

Each cycle reads `positions_get`, `history_deals_get` and `history_orders_get` once over the current
VT server day (vt_day) from the injected MT5 module, and matches broker positions/deals/orders to
lifecycle tickets by the canonical comment tag ("AG " + sha256(ticket_id)[:16]) plus the scope magic
number. Per ticket it reports OPEN / CLOSED (SL, TP or MANUAL) / MISSING / UNKNOWN, and every broker
position carrying one of our magic numbers with no ticket is an ORPHAN.

Safety actions are limited to evidence and the stop:
* ORPHAN, MISSING, a quantity or price mismatch, or a send still UNKNOWN past its timeout engages the
  durable emergency stop (no new orders) and sends one alert through the injected Telegram callable.
  Nothing is ever closed, modified, cancelled or re-sent here (there is no such call in this module).
* An unknown send (HALT after SENT, or a SENDING claim) is resolved from broker history: a tagged deal
  -> RECONCILED FILLED; a tagged order in a rejected/cancelled/expired state with no deal ->
  RECONCILED REJECTED; otherwise it stays UNKNOWN. The claim ledger keeps its unknown marker, so a
  resolved ticket can never be sent again.
* Restart recovery: every ticket the crash left before BROKER_ACK is HALTed (a SENDING claim is marked
  uncertain), so a restarted process resumes at reconcile, never at send. A ticket halted before its
  SENDING claim is RECONCILED NOT_SENT -- the canonical adapter refuses any send without that claim.

The monitor writes only HALT and RECONCILED lifecycle rows and the emergency latch; order steps stay in
the guarded adapter and the single canonical writer.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from demo_execution import emergency, vt_day
from demo_execution import events as ev
from demo_execution.idempotency import SENDING, UNCERTAIN, ExecutionLedger
from demo_execution.lifecycle import (
    AUTHORIZED,
    BROKER_ACK,
    CHECKED,
    CLOSED,
    HALT,
    LIFECYCLE_KIND,
    POSITION_TRACKED,
    RECONCILED,
    SENT,
    ExecutionLifecycle,
    LifecycleTrail,
)
from ticket_store.store import TicketStore

OPEN = "OPEN"
CLOSED_STATE = "CLOSED"
ORPHAN = "ORPHAN"
MISSING = "MISSING"
UNKNOWN = "UNKNOWN"
PENDING = "PENDING"
RESOLVED_FILLED = "FILLED"
RESOLVED_REJECTED = "REJECTED"
NOT_SENT = "NOT_SENT"
CLOSE_SL, CLOSE_TP, CLOSE_MANUAL = "SL", "TP", "MANUAL"

BROKER_DATA_UNAVAILABLE = "BROKER_DATA_UNAVAILABLE"
SERVER_DAY_UNAVAILABLE = "MONITOR_SERVER_DAY_UNAVAILABLE"
POSITION_ORPHAN = "POSITION_ORPHAN"
POSITION_MISSING = "POSITION_MISSING"
POSITION_QUANTITY_MISMATCH = "POSITION_QUANTITY_MISMATCH"
POSITION_PRICE_MISMATCH = "POSITION_PRICE_MISMATCH"
POSITION_AFTER_CLOSE = "POSITION_AFTER_CLOSE"
SEND_UNKNOWN_TIMEOUT = "SEND_UNKNOWN_TIMEOUT"
RESTART_RECOVERY = "RESTART_RECOVERY"

DEFAULT_UNKNOWN_TIMEOUT = timedelta(minutes=15)
DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1
DEAL_REASON_SL, DEAL_REASON_TP = 4, 5
ORDER_STATES_NOT_FILLED = frozenset({2, 5, 6})          # CANCELED, REJECTED, EXPIRED
_VOLUME_TOL = 1e-9
_SYSTEM_AUTHORITY = "DEMO_RECONCILIATION_MONITOR"

AlertSink = Callable[[Mapping[str, Any]], Any]


def comment_tag(ticket_id: str) -> str:
    """The canonical adapter's comment prefix for a ticket (shape tag follows after a space)."""
    return "AG " + hashlib.sha256(ticket_id.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class MonitorReport:
    status: str
    server_day: Optional[str] = None
    tickets: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    orphans: tuple[Mapping[str, Any], ...] = ()
    emergency_reasons: tuple[str, ...] = ()
    emergency_engaged: bool = False
    alerts: tuple[Mapping[str, Any], ...] = ()


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name, None)


def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _tagged(obj: Any, tag: str) -> bool:
    comment = _get(obj, "comment")
    return isinstance(comment, str) and (comment == tag or comment.startswith(tag + " "))


def _ticket_ids(store: TicketStore) -> list[str]:
    seen: dict[str, None] = {}
    for row in store.outcomes():
        if row.get("outcome_kind") == LIFECYCLE_KIND and isinstance(row.get("ticket_id"), str):
            seen.setdefault(row["ticket_id"], None)
    return list(seen)


def _last_authority(trail: LifecycleTrail) -> str:
    return trail.states[-1].authority_id if trail.states else _SYSTEM_AUTHORITY


# ------------------------------------------------------------------ restart recovery
def recover_after_restart(store: TicketStore, *, now_utc: datetime) -> dict[str, str]:
    """HALT every ticket left before BROKER_ACK; a later cycle reconciles it. Never resumes a send."""
    lifecycle, ledger, out = ExecutionLifecycle(store), ExecutionLedger(store), {}
    for ticket_id in _ticket_ids(store):
        trail = lifecycle.trail(ticket_id)
        if trail.reason_code is not None or trail.current not in (AUTHORIZED, CHECKED, SENT):
            continue
        halted = lifecycle.append(ticket_id, HALT, now_utc=now_utc, authority_id=_last_authority(trail),
                                  reason_code=RESTART_RECOVERY, evidence={"halted_from": trail.current})
        claim = ledger.inspect(ticket_id)
        if claim.prior_state == SENDING:
            ledger.record_unknown(ticket_id, reason_code=RESTART_RECOVERY, now_utc=now_utc)
        out[ticket_id] = halted.reason_code
    return out


# ------------------------------------------------------------------ the cycle
def run_cycle(mt5: Any, store: TicketStore, scopes: Sequence[Any], *, metadata: Mapping[str, Any],
              now_utc: datetime, alert: Optional[AlertSink] = None,
              event_sink: Optional[ev.EventSink] = None,
              unknown_timeout: timedelta = DEFAULT_UNKNOWN_TIMEOUT) -> MonitorReport:
    """One read-only reconciliation cycle. Broker data that cannot be read changes nothing."""
    now = now_utc.astimezone(timezone.utc) if isinstance(now_utc, datetime) and now_utc.tzinfo else None
    day = vt_day.server_day(now, metadata) if now else None
    clock_now = vt_day.server_clock(now, metadata) if now else None
    if day is None or clock_now is None:
        return MonitorReport(SERVER_DAY_UNAVAILABLE)
    lifecycle, ledger = ExecutionLifecycle(store), ExecutionLedger(store)
    trails = {ticket_id: lifecycle.trail(ticket_id) for ticket_id in _ticket_ids(store)}
    # Server-day window (server-clock wall times, tz-tagged UTC), widened back to the oldest send still
    # tracked or unresolved, so a send just before server midnight (or a position opened on an earlier
    # day) is still matched after the day rolls over.
    start = datetime.combine(day, datetime.min.time())
    for trail in trails.values():
        sent = trail.state_row(SENT)
        if sent is not None and (_tracking(trail) or trail.current in (SENT, HALT)):
            sent_clock = vt_day.server_clock(sent.recorded_at_utc, metadata)
            if sent_clock is not None and sent_clock < start:
                start = sent_clock
    window = (start.replace(tzinfo=timezone.utc), clock_now.replace(tzinfo=timezone.utc))
    try:
        positions = mt5.positions_get()
        deals = mt5.history_deals_get(*window)
        orders = mt5.history_orders_get(*window)
    except Exception:  # noqa: BLE001 -- a disconnected terminal is unavailable evidence, never a default
        positions = deals = orders = None
    if positions is None or deals is None or orders is None:
        return MonitorReport(BROKER_DATA_UNAVAILABLE, day.isoformat())

    magics = {int(s.magic_number) for s in scopes}
    point = {int(s.magic_number): float(s.point_size) for s in scopes}
    tickets, problems, claimed_positions = {}, [], set()
    for ticket_id, trail in trails.items():
        tag = comment_tag(ticket_id)
        mine_deals = [d for d in deals if _tagged(d, tag) and _get(d, "magic") in magics]
        mine_positions = [p for p in positions if _tagged(p, tag) and _get(p, "magic") in magics]
        report: dict[str, Any] = {"lifecycle": trail.current}
        if trail.reason_code is not None:
            report["state"] = UNKNOWN
            report["reason"] = trail.reason_code
        elif _tracking(trail):
            report.update(_track_open(trail, mine_positions, mine_deals, deals, point))
        elif trail.current in (CLOSED, RECONCILED):
            report["state"] = CLOSED_STATE if trail.current == CLOSED else (
                trail.states[-1].terminal_result or RECONCILED)
            if mine_positions:
                report["problem"] = POSITION_AFTER_CLOSE
        elif trail.current in (SENT, HALT):
            report.update(_resolve_unknown(ticket_id, trail, ledger, lifecycle, mine_deals, orders, tag,
                                           magics, now, unknown_timeout, event_sink))
        else:
            report["state"] = PENDING
        for position in mine_positions:
            claimed_positions.add(_get(position, "ticket"))
        if report.get("problem"):
            problems.append((report["problem"], ticket_id))
        tickets[ticket_id] = report

    orphans = tuple({"position": _get(p, "ticket"), "symbol": _get(p, "symbol"), "magic": _get(p, "magic"),
                     "comment": _get(p, "comment"), "volume": _get(p, "volume")}
                    for p in positions if _get(p, "magic") in magics and _get(p, "ticket") not in claimed_positions)
    problems += [(POSITION_ORPHAN, str(o["position"])) for o in orphans]
    alerts: list[Mapping[str, Any]] = []
    engaged = emergency.status(store).engaged
    if problems and not engaged:
        # Engaged once; the latch stays until the owner clears it, so the alert is not repeated.
        reasons = tuple(dict.fromkeys(reason for reason, _ in problems))
        engaged = emergency.engage(store, reason_code=reasons[0], now_utc=now,
                                   evidence={"problems": [list(p) for p in problems]})
        message = {"kind": "DEMO_EMERGENCY_STOP", "server_day": day.isoformat(), "reasons": list(reasons),
                   "items": [list(p) for p in problems], "broker_action": "NONE"}
        alerts.append({**message, "delivered": _deliver(alert, message)})
    return MonitorReport("OK", day.isoformat(), tickets, orphans,
                         tuple(dict.fromkeys(r for r, _ in problems)), engaged, tuple(alerts))


def _tracking(trail: LifecycleTrail) -> bool:
    """A sent position the broker should hold: acknowledged, or reconciled FILLED by this monitor."""
    if trail.reason_code is not None:
        return False
    if trail.current in (BROKER_ACK, POSITION_TRACKED):
        return True
    return (trail.current == RECONCILED and trail.state_row(CLOSED) is None
            and (trail.states[-1].terminal_result or "").upper() == RESOLVED_FILLED)


def _deliver(alert: Optional[AlertSink], message: Mapping[str, Any]) -> Any:
    if alert is None:
        return "NO_ALERT_SINK"
    try:
        return alert(message)
    except Exception as exc:  # noqa: BLE001 -- the stop is already engaged; delivery failure is reported
        return f"ALERT_FAILED:{type(exc).__name__}"


def _track_open(trail: LifecycleTrail, mine_positions: list, mine_deals: list, deals: Iterable[Any],
                point: Mapping[int, float]) -> dict[str, Any]:
    fill = trail.state_row(BROKER_ACK) or trail.state_row(RECONCILED)
    authorized = trail.state_row(AUTHORIZED)
    expected_volume = _num((fill.evidence if fill else {}).get("volume")) \
        or _num((authorized.evidence if authorized else {}).get("planned_volume"))
    expected_price = _num((fill.evidence if fill else {}).get("price"))
    if mine_positions:
        position = mine_positions[0]
        out: dict[str, Any] = {"state": OPEN, "broker_position_id": _get(position, "ticket")}
        volume, price = _num(_get(position, "volume")), _num(_get(position, "price_open"))
        tolerance = point.get(_get(position, "magic"), 0.0) / 2
        if len(mine_positions) > 1 or expected_volume is None or volume is None \
                or abs(volume - expected_volume) > _VOLUME_TOL:
            out["problem"] = POSITION_QUANTITY_MISMATCH
        elif expected_price is not None and (price is None or abs(price - expected_price) > tolerance):
            out["problem"] = POSITION_PRICE_MISMATCH
        return out
    entry = next((d for d in mine_deals if _get(d, "entry") == DEAL_ENTRY_IN), None)
    tracked = trail.state_row(POSITION_TRACKED)
    position_id = _get(entry, "position_id") if entry is not None else None
    for row in (tracked, trail.state_row(RECONCILED)):
        if position_id is None and row is not None:
            position_id = row.broker_position_id
    closing = [d for d in deals if position_id is not None and _get(d, "entry") == DEAL_ENTRY_OUT
               and str(_get(d, "position_id")) == str(position_id)]
    if closing:
        reason = _get(closing[-1], "reason")
        how = CLOSE_SL if reason == DEAL_REASON_SL else CLOSE_TP if reason == DEAL_REASON_TP else CLOSE_MANUAL
        return {"state": CLOSED_STATE, "close": how, "broker_deal_id": _get(closing[-1], "ticket"),
                "broker_position_id": position_id}
    return {"state": MISSING, "problem": POSITION_MISSING}


def _resolve_unknown(ticket_id: str, trail: LifecycleTrail, ledger: ExecutionLedger,
                     lifecycle: ExecutionLifecycle, mine_deals: list, orders: Iterable[Any], tag: str,
                     magics: set, now: datetime, timeout: timedelta,
                     event_sink: Optional[ev.EventSink]) -> dict[str, Any]:
    claim = ledger.inspect(ticket_id)
    sending = claim.prior_state in (SENDING, UNCERTAIN)
    halted_from = (trail.state_row(HALT).evidence.get("halted_from") if trail.state_row(HALT) else trail.current)
    if trail.current == SENT:
        sent = trail.state_row(SENT)
        try:
            expires = datetime.fromisoformat(str(sent.evidence.get("expires_at_utc"))) if sent else None
        except ValueError:
            expires = None
        if expires is not None and expires.tzinfo is not None and now < expires:
            # The guarded send is still inside its own window: in flight, not yet unknown.
            return {"state": PENDING, "in_flight_until_utc": expires.isoformat()}
        # Still SENT with no ack after its window: halt first so nothing can follow but reconciliation.
        lifecycle.append(ticket_id, HALT, now_utc=now, authority_id=_last_authority(trail),
                         reason_code="SEND_UNKNOWN_RECONCILE", evidence={"halted_from": SENT})
        if claim.prior_state == SENDING:
            ledger.record_unknown(ticket_id, reason_code="SEND_UNKNOWN_RECONCILE", now_utc=now)
        trail = lifecycle.trail(ticket_id)
    entry = next((d for d in mine_deals if _get(d, "entry") == DEAL_ENTRY_IN), None)
    rejected = next((o for o in orders if _tagged(o, tag) and _get(o, "magic") in magics
                     and _get(o, "state") in ORDER_STATES_NOT_FILLED), None)
    authority_id = _last_authority(trail)
    if entry is not None:
        recorded = lifecycle.append(
            ticket_id, RECONCILED, now_utc=now, authority_id=authority_id, terminal_result=RESOLVED_FILLED,
            broker_order_id=str(_get(entry, "order")), broker_deal_id=str(_get(entry, "ticket")),
            broker_position_id=str(_get(entry, "position_id")),
            evidence={"source": "history_deals_get", "volume": _get(entry, "volume"), "price": _get(entry, "price")})
        if recorded.recorded:
            ev.emit(event_sink, ev.LifecycleEvent(ev.FILLED, ticket_id, now.isoformat(),
                                                  broker_order_id=str(_get(entry, "order")),
                                                  broker_deal_id=str(_get(entry, "ticket")),
                                                  broker_position_id=str(_get(entry, "position_id"))))
        return {"state": RESOLVED_FILLED, "resolution": recorded.reason_code, "resubmission": "NEVER"}
    if rejected is not None:
        recorded = lifecycle.append(ticket_id, RECONCILED, now_utc=now, authority_id=authority_id,
                                    terminal_result=RESOLVED_REJECTED, broker_order_id=str(_get(rejected, "ticket")),
                                    evidence={"source": "history_orders_get", "order_state": _get(rejected, "state")})
        return {"state": RESOLVED_REJECTED, "resolution": recorded.reason_code, "resubmission": "NEVER"}
    if not sending and halted_from in (AUTHORIZED, CHECKED):
        # No SENDING claim: the canonical adapter cannot have sent (SEND_CLAIM_MISSING).
        recorded = lifecycle.append(ticket_id, RECONCILED, now_utc=now, authority_id=authority_id,
                                    terminal_result=NOT_SENT, evidence={"halted_from": halted_from})
        return {"state": NOT_SENT, "resolution": recorded.reason_code}
    halt_row = trail.state_row(HALT)
    since = halt_row.recorded_at_utc if halt_row else now
    out: dict[str, Any] = {"state": UNKNOWN, "unknown_since_utc": since.isoformat(), "resubmission": "NEVER"}
    if now - since >= timeout:
        out["problem"] = SEND_UNKNOWN_TIMEOUT
    return out
