"""AGP-AUTODEMO-D1: reconciliation monitor, emergency stop, unknown-send resolution, restart recovery,
freshness at send, disconnects, evidence ids and lifecycle events. Fake MT5 + simulated clock only."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_execution_boundary_fixtures import (  # noqa: E402
    NOW,
    REPO,
    TICKET_ID,
    authority_for,
    boundary,
)

from demo_execution import emergency  # noqa: E402
from demo_execution import events as ev  # noqa: E402
from demo_execution import position_monitor as PM  # noqa: E402
from demo_execution.idempotency import ExecutionLedger  # noqa: E402
from demo_execution.lifecycle import AUTHORIZED, HALT, RECONCILED, SENT  # noqa: E402

UTC = timezone.utc
METADATA = json.loads((REPO / "config/symbol_metadata/host_captured/GBPUSD.json").read_text())
CHECKED_ORDER = {"retcode": 0, "volume": 0.5, "price": 1.3001, "order": 111}
TAG = PM.comment_tag(TICKET_ID)


def at(fixture, seconds):
    return fixture["now"] + timedelta(seconds=seconds)


class FakeMT5:
    """Read-only fake terminal; any other attribute (order_send, position_close, ...) fails the test."""

    def __init__(self, positions=(), deals=(), orders=(), down=False):
        self.positions, self.deals, self.orders, self.down, self.calls = list(positions), list(deals), \
            list(orders), down, []

    def _read(self, name, value, *args):
        self.calls.append((name, args))
        if self.down:
            raise ConnectionError("terminal disconnected")
        return tuple(value)

    def positions_get(self):
        return self._read("positions_get", self.positions)

    @staticmethod
    def _within(items, date_from, date_to):
        lo, hi = (int((d.replace(tzinfo=None) - datetime(1970, 1, 1)).total_seconds()) for d in (date_from, date_to))
        return [x for x in items if getattr(x, "time", None) is None or lo <= x.time <= hi]

    def history_deals_get(self, date_from, date_to):
        return self._read("history_deals_get", self._within(self.deals, date_from, date_to), date_from, date_to)

    def history_orders_get(self, date_from, date_to):
        return self._read("history_orders_get", self.orders, date_from, date_to)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        raise AssertionError(f"monitor made a non read-only MT5 call: {name}")


def position(fixture, *, volume=0.5, price=1.3001, comment=None, magic=None, ticket=900):
    return SimpleNamespace(ticket=ticket, symbol=fixture["scope"].broker_symbol, volume=volume, price_open=price,
                           magic=fixture["scope"].magic_number if magic is None else magic,
                           comment=f"{TAG} SHAPEDEV" if comment is None else comment)


def server_epoch(at_utc):
    """Independent of vt_day: VT server clock = UTC+3 before 2026-11-01T06:00Z (US DST end), UTC+2 after."""
    offset = timedelta(hours=3 if at_utc < datetime(2026, 11, 1, 6, tzinfo=UTC) else 2)
    return int(((at_utc + offset).replace(tzinfo=None) - datetime(1970, 1, 1)).total_seconds())


def deal(fixture, *, entry=0, reason=3, ticket=222, position_id=900, comment=None, volume=0.5, price=1.3001,
         when=None):
    return SimpleNamespace(ticket=ticket, order=111, position_id=position_id, entry=entry, reason=reason,
                           time=None if when is None else server_epoch(when),
                           magic=fixture["scope"].magic_number, volume=volume, price=price,
                           comment=f"{TAG} SHAPEDEV" if comment is None else comment)


def cycle(fixture, mt5, now, **kw):
    alerts = kw.pop("alerts", [])
    return PM.run_cycle(mt5, fixture["store"], [fixture["scope"]], metadata=METADATA, now_utc=now,
                        alert=alerts.append, **kw)


def to_checked(fixture):
    guard, ticket = fixture["guard"], fixture["ticket"]
    check = guard.authorize_order_check(authority=authority_for(fixture), ticket=ticket, market=fixture["market"],
                                        risk_snapshot=fixture["risk_snapshot"], now_utc=fixture["now"])
    assert check.admitted, check.reason_codes
    rec = guard.record_order_checked(authority=authority_for(fixture, now=at(fixture, 1)), ticket=ticket,
                                     checked_order=CHECKED_ORDER, now_utc=at(fixture, 1))
    assert rec.admitted, rec.reason_codes
    return check


def send(fixture, seconds=2):
    return fixture["guard"].authorize_order_send(authority=authority_for(fixture, now=at(fixture, seconds)),
                                                 ticket=fixture["ticket"], checked_order=CHECKED_ORDER,
                                                 now_utc=at(fixture, seconds))


def to_ack(fixture, result=None):
    to_checked(fixture)
    assert send(fixture).admitted
    ack = fixture["guard"].record_broker_ack(
        authority=authority_for(fixture, now=at(fixture, 3)),
        send_result=result or {"retcode": 10009, "order": 111, "deal": 222, "price": 1.3001, "volume": 0.5},
        now_utc=at(fixture, 3))
    assert ack.admitted, ack.reason_codes


# --------------------------------------------------------------------------- 1. monitor states

def test_comment_tag_matches_the_canonical_adapter():
    from demo_execution.mt5_canonical_adapter import _comment
    assert _comment(TICKET_ID, "SHAPEDEV") == f"{TAG} SHAPEDEV"
    assert TAG == "AG " + hashlib.sha256(TICKET_ID.encode()).hexdigest()[:16]


def test_open_position_matches_by_tag_and_magic(tmp_path):
    fixture = boundary(tmp_path)
    to_ack(fixture)
    mt5, alerts = FakeMT5(positions=[position(fixture)], deals=[deal(fixture)]), []
    report = cycle(fixture, mt5, at(fixture, 60), alerts=alerts)
    assert report.status == "OK" and report.tickets[TICKET_ID]["state"] == PM.OPEN
    assert not report.emergency_reasons and alerts == [] and not emergency.status(fixture["store"]).engaged
    assert {name for name, _ in mt5.calls} == {"positions_get", "history_deals_get", "history_orders_get"}


@pytest.mark.parametrize("reason, kind", [(4, PM.CLOSE_SL), (5, PM.CLOSE_TP), (0, PM.CLOSE_MANUAL)])
def test_closed_position_reports_sl_tp_or_manual(tmp_path, reason, kind):
    fixture = boundary(tmp_path)
    to_ack(fixture)
    closing = deal(fixture, entry=1, reason=reason, ticket=333, comment="[sl 1.29910]")
    report = cycle(fixture, FakeMT5(deals=[deal(fixture), closing]), at(fixture, 60))
    assert report.tickets[TICKET_ID]["state"] == PM.CLOSED_STATE and report.tickets[TICKET_ID]["close"] == kind
    assert not report.emergency_engaged


# --------------------------------------------------------------------------- 2. emergency stop + alert

@pytest.mark.parametrize("make, reason", [
    (lambda f: FakeMT5(deals=[deal(f)]), PM.POSITION_MISSING),
    (lambda f: FakeMT5(positions=[position(f, volume=0.7)]), PM.POSITION_QUANTITY_MISMATCH),
    (lambda f: FakeMT5(positions=[position(f, price=1.3011)]), PM.POSITION_PRICE_MISMATCH),
])
def test_missing_or_mismatch_engages_stop_and_alerts_once(tmp_path, make, reason):
    fixture = boundary(tmp_path)
    to_ack(fixture)
    alerts = []
    report = cycle(fixture, make(fixture), at(fixture, 60), alerts=alerts)
    assert reason in report.emergency_reasons and report.emergency_engaged
    assert len(alerts) == 1 and alerts[0]["broker_action"] == "NONE" and reason in alerts[0]["reasons"]
    again = cycle(fixture, make(fixture), at(fixture, 120), alerts=alerts)
    assert reason in again.emergency_reasons and len(alerts) == 1          # latched: no repeat alert


def test_orphan_position_engages_stop_and_blocks_new_orders(tmp_path):
    fixture = boundary(tmp_path)
    alerts = []
    foreign_comment = position(fixture, comment="AG 0000000000000000 SHAPEDEV", ticket=777)
    report = cycle(fixture, FakeMT5(positions=[foreign_comment]), NOW, alerts=alerts)
    assert report.orphans[0]["position"] == 777 and PM.POSITION_ORPHAN in report.emergency_reasons
    assert emergency.status(fixture["store"]).engaged and len(alerts) == 1
    check = fixture["guard"].authorize_order_check(authority=authority_for(fixture), ticket=fixture["ticket"],
                                                   market=fixture["market"], risk_snapshot=fixture["risk_snapshot"],
                                                   now_utc=NOW)
    assert check.admitted is False and "EMERGENCY_STOP_ENGAGED" in check.reason_codes
    # A foreign-magic position is not ours and never an orphan.
    other = boundary(tmp_path / "b")
    assert cycle(other, FakeMT5(positions=[position(other, magic=4242)]), NOW).orphans == ()


def test_emergency_stop_blocks_a_pending_send_and_only_the_owner_clears_it(tmp_path):
    fixture = boundary(tmp_path)
    to_checked(fixture)
    assert emergency.engage(fixture["store"], reason_code="TEST", now_utc=at(fixture, 1))
    refused = send(fixture)
    assert refused.admitted is False and "EMERGENCY_STOP_ENGAGED" in refused.reason_codes
    assert ExecutionLedger(fixture["store"]).inspect(TICKET_ID).available           # nothing claimed
    assert not emergency.clear(fixture["store"], owner_decision_id="", now_utc=at(fixture, 2))
    assert emergency.clear(fixture["store"], owner_decision_id="OWNER-TEST", now_utc=at(fixture, 2))
    assert not emergency.status(fixture["store"]).engaged


def test_execution_alert_text_is_compact_ascii(monkeypatch, tmp_path):
    from telegram_delivery.adapter import Config, Sender
    sent = []
    sender = Sender(tmp_path / "tg.sqlite", config=Config(enabled=False, token="", chat_id="", owner_chat_ids=()))
    monkeypatch.setattr(sender, "_send", lambda kind, identity, status, message: sent.append(
        (kind, identity, status, message)) or "sent")
    alert = {"server_day": "2026-11-01", "reasons": ["POSITION_ORPHAN"], "items": [["POSITION_ORPHAN", "777"]]}
    assert sender.send_execution_alert(alert) == "sent"
    kind, identity, status, message = sent[0]
    assert kind == "exec_alert" and status == "EMERGENCY_STOP" and message.isascii()
    assert "AG DEMO EMERGENCY STOP" in message and "POSITION_ORPHAN:777" in message and "NONE" in message


# --------------------------------------------------------------------------- 3. unknown send resolution

def _unknown(fixture, sink=None):
    if sink is not None:
        fixture["guard"]._event_sink = sink
    to_checked(fixture)
    assert send(fixture).admitted
    halted = fixture["guard"].record_broker_ack(authority=authority_for(fixture, now=at(fixture, 3)),
                                                send_result={"retcode": 10009}, now_utc=at(fixture, 3))
    assert halted.state == HALT


def test_unknown_send_resolves_to_filled_and_is_never_resent(tmp_path):
    fixture, seen = boundary(tmp_path), []
    _unknown(fixture, seen.append)
    assert [e.kind for e in seen] == [ev.SENT, ev.SEND_UNKNOWN]
    report = cycle(fixture, FakeMT5(positions=[position(fixture)], deals=[deal(fixture)]), at(fixture, 60),
                   event_sink=seen.append)
    assert report.tickets[TICKET_ID]["state"] == PM.RESOLVED_FILLED and seen[-1].kind == ev.FILLED
    trail = fixture["guard"].trail(TICKET_ID)
    assert trail.current == RECONCILED and trail.states[-1].terminal_result == "FILLED"
    assert not ExecutionLedger(fixture["store"]).inspect(TICKET_ID).available     # permanently halted
    assert send(fixture, 61).admitted is False
    # The resolved position is tracked from then on.
    later = cycle(fixture, FakeMT5(positions=[position(fixture)], deals=[deal(fixture)]), at(fixture, 120))
    assert later.tickets[TICKET_ID]["state"] == PM.OPEN and not later.emergency_reasons


def test_unknown_send_resolves_to_rejected(tmp_path):
    fixture = boundary(tmp_path)
    _unknown(fixture)
    rejected = SimpleNamespace(ticket=111, magic=fixture["scope"].magic_number, comment=f"{TAG} SHAPEDEV", state=5)
    report = cycle(fixture, FakeMT5(orders=[rejected]), at(fixture, 60))
    assert report.tickets[TICKET_ID]["state"] == PM.RESOLVED_REJECTED
    assert fixture["guard"].trail(TICKET_ID).states[-1].terminal_result == "REJECTED"


def test_still_unknown_past_timeout_engages_stop(tmp_path):
    fixture = boundary(tmp_path)
    _unknown(fixture)
    alerts = []
    early = cycle(fixture, FakeMT5(), at(fixture, 60), alerts=alerts)
    assert early.tickets[TICKET_ID]["state"] == PM.UNKNOWN and not early.emergency_reasons and alerts == []
    late = cycle(fixture, FakeMT5(), at(fixture, 3 + 15 * 60), alerts=alerts)
    assert PM.SEND_UNKNOWN_TIMEOUT in late.emergency_reasons and len(alerts) == 1
    assert fixture["guard"].trail(TICKET_ID).current == HALT                       # still unknown, never resent


def test_a_send_inside_its_window_is_in_flight_not_unknown(tmp_path):
    fixture = boundary(tmp_path)
    to_checked(fixture)
    assert send(fixture).admitted
    assert cycle(fixture, FakeMT5(), at(fixture, 30)).tickets[TICKET_ID]["state"] == PM.PENDING
    expires = datetime.fromisoformat(fixture["guard"].trail(TICKET_ID).state_row(SENT).evidence["expires_at_utc"])
    report = cycle(fixture, FakeMT5(deals=[deal(fixture)]), expires + timedelta(seconds=1))
    assert report.tickets[TICKET_ID]["state"] == PM.RESOLVED_FILLED


# --------------------------------------------------------------------------- 4. restart recovery

def test_restart_before_send_resumes_at_reconcile_as_not_sent(tmp_path):
    fixture = boundary(tmp_path)
    to_checked(fixture)
    assert PM.recover_after_restart(fixture["store"], now_utc=at(fixture, 2)) == {TICKET_ID: "LIFECYCLE_RECORDED"}
    refused = send(fixture, 3)
    assert refused.admitted is False and ExecutionLedger(fixture["store"]).inspect(TICKET_ID).available
    report = cycle(fixture, FakeMT5(), at(fixture, 4))
    assert report.tickets[TICKET_ID]["state"] == PM.NOT_SENT
    assert fixture["guard"].trail(TICKET_ID).states[-1].terminal_result == "NOT_SENT"


def test_restart_after_send_claim_halts_and_reconciles_never_resends(tmp_path):
    fixture = boundary(tmp_path)
    to_checked(fixture)
    assert send(fixture).admitted                                                    # crash after SENDING
    PM.recover_after_restart(fixture["store"], now_utc=at(fixture, 5))
    trail = fixture["guard"].trail(TICKET_ID)
    assert trail.current == HALT and trail.state_row(HALT).reason_code == PM.RESTART_RECOVERY
    assert ExecutionLedger(fixture["store"]).inspect(TICKET_ID).reason_code == "HALT_UNKNOWN_RESULT"
    assert send(fixture, 6).admitted is False
    report = cycle(fixture, FakeMT5(deals=[deal(fixture)], positions=[position(fixture)]), at(fixture, 7))
    assert report.tickets[TICKET_ID]["state"] == PM.RESOLVED_FILLED


def test_restart_leaves_acknowledged_tickets_to_the_monitor(tmp_path):
    fixture = boundary(tmp_path)
    to_ack(fixture)
    assert PM.recover_after_restart(fixture["store"], now_utc=at(fixture, 5)) == {}


# --------------------------------------------------------------------------- 5. freshness at send

def test_catch_up_after_downtime_never_sends_an_expired_signal(tmp_path):
    fixture = boundary(tmp_path)
    to_checked(fixture)
    late = send(fixture, 13 * 60)                     # valid_until = now + 12 min
    assert late.admitted is False and "TICKET_EXPIRED" in late.reason_codes
    assert ExecutionLedger(fixture["store"]).inspect(TICKET_ID).available           # nothing claimed


def test_a_stale_signal_without_expiry_is_refused_at_send(tmp_path):
    from demo_execution.admission import check_signal_freshness_at_send
    fixture = boundary(tmp_path)
    scope, ticket = fixture["scope"], dict(fixture["ticket"])
    ticket.pop("valid_until")
    ttl = scope.signal_expiry_minutes
    assert check_signal_freshness_at_send(ticket, scope, now_utc=NOW) is None
    assert check_signal_freshness_at_send(ticket, scope, now_utc=NOW + timedelta(minutes=ttl)) \
        == "SIGNAL_STALE_AT_SEND"


# --------------------------------------------------------------------------- 6. disconnects

def test_monitor_fails_closed_when_the_terminal_is_disconnected(tmp_path):
    fixture = boundary(tmp_path)
    to_ack(fixture)
    report = cycle(fixture, FakeMT5(down=True), at(fixture, 60))
    assert report.status == PM.BROKER_DATA_UNAVAILABLE and report.tickets == {}
    assert not emergency.status(fixture["store"]).engaged                          # nothing inferred
    assert cycle(fixture, FakeMT5(positions=[position(fixture)]), at(fixture, 90)).tickets[TICKET_ID]["state"] \
        == PM.OPEN                                                                  # reconciled on reconnect


def test_live_account_unreadable_at_check_or_send_fails_closed(tmp_path):
    fixture = boundary(tmp_path)
    fixture["guard"]._account_reader = lambda: (_ for _ in ()).throw(ConnectionError("down"))
    check = fixture["guard"].authorize_order_check(authority=authority_for(fixture), ticket=fixture["ticket"],
                                                   market=fixture["market"], risk_snapshot=fixture["risk_snapshot"],
                                                   now_utc=NOW)
    assert check.admitted is False and "ACCOUNT_IDENTITY_UNAVAILABLE" in check.reason_codes
    fixture = boundary(tmp_path / "b")
    to_checked(fixture)
    fixture["guard"]._account_reader = lambda: None
    refused = send(fixture)
    assert refused.admitted is False and "ACCOUNT_IDENTITY_UNAVAILABLE" in refused.reason_codes
    assert ExecutionLedger(fixture["store"]).inspect(TICKET_ID).available


# --------------------------------------------------------------------------- 7. evidence ids

def test_admission_and_send_risk_evidence_ids_are_recorded(tmp_path):
    fixture = boundary(tmp_path)
    to_checked(fixture)
    assert send(fixture).admitted
    trail = fixture["guard"].trail(TICKET_ID)
    authorized, sent = trail.state_row(AUTHORIZED).evidence, trail.state_row(SENT).evidence
    assert authorized["risk_evidence_id"] == fixture["authority"].risk_evidence.evidence_id   # authority-minted
    assert authorized["admission_risk_evidence_id"] and sent["send_risk_evidence_id"]
    assert authorized["admission_risk_evidence_id"] != sent["send_risk_evidence_id"]         # two fresh builds


# --------------------------------------------------------------------------- 8. lifecycle events

def test_lifecycle_events_for_c3_builders(tmp_path):
    fixture, seen = boundary(tmp_path), []
    fixture["guard"]._event_sink = seen.append
    to_ack(fixture)
    guard = fixture["guard"]
    assert guard.record_position_tracked(authority=authority_for(fixture, now=at(fixture, 4)),
                                         broker_position_id="900", now_utc=at(fixture, 4)).admitted
    assert guard.record_position_closed(authority=authority_for(fixture, now=at(fixture, 5)),
                                        broker_deal_id="333", now_utc=at(fixture, 5)).admitted
    assert [e.kind for e in seen] == [ev.SENT, ev.BROKER_ACK, ev.CLOSED]
    assert seen[1].broker_order_id == "111" and seen[2].broker_deal_id == "333"

    rejected, seen2 = boundary(tmp_path / "r"), []
    rejected["guard"]._event_sink = seen2.append
    check = rejected["guard"].authorize_order_check(authority=authority_for(rejected), ticket=rejected["ticket"],
                                                    market=rejected["market"],
                                                    risk_snapshot=rejected["risk_snapshot"], now_utc=NOW)
    assert check.admitted
    rec = rejected["guard"].record_order_checked(authority=authority_for(rejected, now=at(rejected, 1)),
                                                 ticket=rejected["ticket"], checked_order={"retcode": 10006},
                                                 now_utc=at(rejected, 1))
    assert rec.admitted is False and [e.kind for e in seen2] == [ev.CHECK_REJECTED]


def test_a_failing_event_sink_never_changes_an_order_step(tmp_path):
    fixture = boundary(tmp_path)
    fixture["guard"]._event_sink = lambda event: (_ for _ in ()).throw(RuntimeError("telegram down"))
    to_ack(fixture)
    assert fixture["guard"].trail(TICKET_ID).current == "BROKER_ACK"


# --------------------------------------------------------------------------- DST day (2026-11-01)

@pytest.mark.parametrize("now, day, midnight", [
    (datetime(2026, 11, 1, 21, 59, tzinfo=UTC), "2026-11-01", datetime(2026, 11, 1, tzinfo=UTC)),
    (datetime(2026, 11, 1, 22, 0, tzinfo=UTC), "2026-11-02", datetime(2026, 11, 2, tzinfo=UTC)),
])
def test_cycle_uses_the_vt_server_day_across_the_dst_reset(tmp_path, now, day, midnight):
    fixture = boundary(tmp_path, now=now)
    mt5 = FakeMT5()
    report = cycle(fixture, mt5, now)
    assert report.server_day == day
    _, (lo, _hi) = next(c for c in mt5.calls if c[0] == "history_deals_get")
    assert lo == midnight                                         # server-clock midnight window start


def test_full_lifecycle_and_resolution_on_the_dst_day(tmp_path):
    now = datetime(2026, 11, 1, 21, 50, tzinfo=UTC)               # sends just before the winter midnight
    fixture = boundary(tmp_path, now=now)
    _unknown(fixture)
    filled = deal(fixture, when=now + timedelta(seconds=2))    # server clock 23:50 on 2026-11-01
    stale = deal(fixture, ticket=1, when=now - timedelta(days=2))  # before the widened window: not read
    mt5 = FakeMT5(deals=[stale, filled], positions=[position(fixture)])
    report = cycle(fixture, mt5, datetime(2026, 11, 1, 22, 5, tzinfo=UTC))    # next server day already
    assert report.server_day == "2026-11-02" and report.tickets[TICKET_ID]["state"] == PM.RESOLVED_FILLED
    _, (lo, _hi) = next(c for c in mt5.calls if c[0] == "history_deals_get")
    assert lo < datetime(2026, 11, 2, tzinfo=UTC)               # widened back to the unresolved send
    assert fixture["guard"].trail(TICKET_ID).states[-1].broker_deal_id == "222"
