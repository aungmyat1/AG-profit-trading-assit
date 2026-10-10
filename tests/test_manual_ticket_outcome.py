"""Manual Trade Ticket V1 Phase 7: VIRTUAL_FORWARD outcome resolver (read-only, offline)."""
from __future__ import annotations

import datetime as dt

import pytest

from strategy_engine.session import Candle
from v1_tickets import manual_ticket as mt
from v1_tickets.outcome import (
    AMBIGUOUS, DATA_INSUFFICIENT, EXPIRY, NOT_RESOLVABLE, SL, TP1, outcome_path, resolve_day, resolve_levels,
)
from v1_tickets.owner_decision import ManualTicketDecision, record_decision
from v1_tickets.scan_record import read_jsonl

from test_manual_ticket_build import META, OWNER, READY_DAY, l2_pass, manual  # noqa: F401
from test_manual_ticket_logic_gate import CANDLES

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 6, 17, 7, 15, tzinfo=UTC)
H = dt.datetime(2026, 6, 17, 15, 0, tzinfo=UTC)
M5 = dt.timedelta(minutes=5)
NOW = dt.datetime(2026, 6, 18, 6, 0, tzinfo=UTC)


def bar(i, o, h, lo, c):
    return Candle(T0 + i * M5, o, h, lo, c)


def lv(bars, **kw):
    args = dict(direction="LONG", entry=1.1000, sl=1.0990, tp1=1.1020, start=T0, horizon=H, bars=bars, tf=M5,
                now=NOW, cost_r=0.1)
    return resolve_levels(**{**args, **kw})


def test_first_touch_tp1_with_mfe_mae_and_net_after_cost():
    r = lv([bar(0, 1.1, 1.1005, 1.0995, 1.1), bar(1, 1.1, 1.1021, 1.0998, 1.102)])
    assert r["result"] == TP1 and r["gross_R"] == 2.0 and r["net_R"] == 1.9
    assert r["mae_R"] == 0.5 and r["mfe_R"] == 2.1


def test_first_touch_sl_and_short_direction():
    assert lv([bar(0, 1.1, 1.1001, 1.0989, 1.0995)])["result"] == SL
    r = lv([bar(0, 1.1, 1.1011, 1.0999, 1.1)], direction="SHORT", sl=1.1010, tp1=1.0980)
    assert r["result"] == SL and r["gross_R"] == -1.0


def test_same_bar_tp_and_sl_is_ambiguous_not_guessed():
    r = lv([bar(0, 1.1, 1.1025, 1.0985, 1.1)])
    assert r["result"] == AMBIGUOUS and r["gross_R"] is None and r["net_R"] is None


def test_expiry_marks_to_last_close_before_horizon():
    n = int((H - T0) / M5)
    bars = [bar(i, 1.1, 1.1005, 1.0995, 1.1005) for i in range(n)]
    r = lv(bars)
    assert r["result"] == EXPIRY and r["gross_R"] == 0.5


def test_unresolvable_inputs_fail_closed():
    assert lv([], sl=1.1000)["result"] == NOT_RESOLVABLE
    assert lv([])["result"] == DATA_INSUFFICIENT
    assert lv([bar(0, 1.1, 1.1005, 1.0995, 1.1)])["result"] == DATA_INSUFFICIENT       # ends before horizon
    unclosed = lv([bar(0, 1.1, 1.1021, 1.0995, 1.1)], now=T0 + dt.timedelta(minutes=2))
    assert unclosed["result"] == DATA_INSUFFICIENT                                       # no look-ahead


def test_resolve_day_covers_taken_and_shadow_tickets_idempotently(stub_symbol_verified, tmp_path, l2_pass):  # noqa: F811
    journal = str(tmp_path / "j")
    ready = manual(READY_DAY, "07:20", owner=OWNER, balance=10000.0, meta=META)
    mt.archive_manual_ticket(journal, ready)
    stored = read_jsonl(mt.ticket_path(journal, dt.date(2026, 6, 23)))[-1]
    record_decision(journal, stored, ManualTicketDecision(
        ticket_id=ready["ticket_id"], decision="TAKEN", recorded_at="2026-06-23T08:00:00+00:00",
        fill_time="2026-06-23T07:22:00+00:00", actual_fill=1.14295, actual_sl=1.14351))
    shadow = manual("2026-06-17", "07:20")                    # real v1.1.1 ticket: blocked, no decision
    mt.archive_manual_ticket(journal, shadow)

    m15 = dt.timedelta(minutes=15)
    for day in (dt.date(2026, 6, 17), dt.date(2026, 6, 23)):
        s = resolve_day(journal, day, lambda sym: CANDLES, now=dt.datetime.combine(day, dt.time(23), UTC), tf=m15)
        assert len(s["resolved"]) == 1, s
        assert resolve_day(journal, day, lambda sym: CANDLES, now=dt.datetime.combine(day, dt.time(23), UTC),
                           tf=m15)["resolved"] == []                      # idempotent
    taken = read_jsonl(outcome_path(journal, dt.date(2026, 6, 23)))[0]
    assert taken["tag"] == "VIRTUAL_FORWARD" and taken["executed_by_system"] is False
    assert taken["is_demo_or_live_performance"] is False
    assert taken["raw_proposal"]["state"] == "TICKET_READY" and taken["owner_decision"]["decision"] == "TAKEN"
    assert taken["virtual_outcome"]["result"] in (TP1, SL, EXPIRY, AMBIGUOUS) and "owner_trade_outcome" in taken
    sh = read_jsonl(outcome_path(journal, dt.date(2026, 6, 17)))[0]
    assert sh["owner_decision"] is None and sh["raw_proposal"]["state"] == "TICKET_BLOCKED"
    assert sh["cost_basis"] == "SPREAD_ONLY_COMMISSION_NOT_AVAILABLE"
    from ticket_store.store import TicketStore, REPLAY
    stored_outcomes = TicketStore(str(__import__("os").path.join(journal, "ticket_store"))).outcomes()
    assert {o["source"] for o in stored_outcomes} == {REPLAY}
    assert {o["outcome_kind"] for o in stored_outcomes} == {"VIRTUAL_FORWARD"}


def test_before_horizon_stays_pending(tmp_path):
    journal = str(tmp_path / "j")
    mt.archive_manual_ticket(journal, manual("2026-06-23", "07:20"))
    s = resolve_day(journal, dt.date(2026, 6, 23), lambda sym: CANDLES,
                    now=dt.datetime(2026, 6, 23, 14, 0, tzinfo=UTC), tf=dt.timedelta(minutes=15))
    assert s["resolved"] == [] and s["pending"][0][1] == "BEFORE_HORIZON"


def test_host_daily_jobs_resolve_once_per_day_and_survive_data_errors(tmp_path):
    from test_host_go_live_kit import smoke
    journal = str(tmp_path / "j")
    mt.archive_manual_ticket(journal, manual("2026-06-23", "07:20"))
    calls = []

    def broken(*a):
        calls.append(a)
        raise RuntimeError("no data")
    now = dt.datetime(2026, 6, 24, 6, 0, tzinfo=UTC)
    lines = smoke.run_manual_jobs(broken, now, journal)
    assert any("MANUAL_RESOLVER 2026-06-23 ERROR" in ln for ln in lines)
    assert smoke.run_manual_jobs(broken, now + dt.timedelta(minutes=15), journal) == []     # once per UTC day
