"""I7: an incomplete reference box before its window closes is REFERENCE_NOT_READY (lifecycle),
never DATA_ERROR; missing/malformed bars after the window closes stay DATA_ERROR. Offline."""
from __future__ import annotations

import dataclasses
import datetime as dt
import math

from v1_tickets.fx import REFERENCE_NOT_READY, build_fx_ticket, session_windows_utc
from v1_tickets.scan_record import classify_fx_ticket

from test_manual_ticket_logic_gate import CANDLES

UTC = dt.timezone.utc
DAY = dt.date(2026, 6, 17)                     # recorded EURUSD session with a complete 24-bar Asian box
W = session_windows_utc(DAY)["ASIAN_LONDON"]
REF_START, REF_END = W["ref"]
TRADE_START, TRADE_END = W["trade"]


def ticket(now, session=None, expected=24):
    closed = [c for c in CANDLES if c.time + dt.timedelta(minutes=15) <= now]
    box = session if session is not None else [c for c in closed if REF_START <= c.time < REF_END]
    post = [c for c in closed if TRADE_START <= c.time < TRADE_END]
    return build_fx_ticket("EURUSD", "ASIAN_LONDON", DAY, box, expected, post, data_source="FIXTURE",
                           evaluated_at=now, data_close=now, spread=0.00002)


def state(t, now):
    return classify_fx_ticket(t, now=now, window_end=TRADE_END)


def test_before_reference_completion_is_reference_not_ready_not_data_error():
    now = REF_END - dt.timedelta(minutes=6)    # 23/24 bars closed
    t = ticket(now)
    assert t["decision"] == REFERENCE_NOT_READY and t["reason_code"] == REFERENCE_NOT_READY
    assert state(t, now) == (REFERENCE_NOT_READY, "SESSION", REFERENCE_NOT_READY)
    assert "entry" not in t and "stop_loss" not in t


def test_no_reference_bars_yet_is_reference_not_ready():
    now = REF_START + dt.timedelta(minutes=1)
    assert ticket(now, session=[])["decision"] == REFERENCE_NOT_READY


def test_exactly_at_completion_the_engine_runs():
    t = ticket(REF_END)
    assert t["decision"] not in (REFERENCE_NOT_READY, "DATA_ERROR")


def test_after_completion_valid_box_is_evaluated():
    now = dt.datetime.combine(DAY, dt.time(7, 20), tzinfo=UTC)
    t = ticket(now)
    assert t["decision"] not in (REFERENCE_NOT_READY, "DATA_ERROR")


def test_missing_candle_after_completion_stays_data_error():
    box = [c for c in CANDLES if REF_START <= c.time < REF_END]
    t = ticket(REF_END + dt.timedelta(minutes=30), session=box[:12] + box[13:])     # one bar missing
    assert t["decision"] == "DATA_ERROR" and t["reason_code"] != REFERENCE_NOT_READY


def test_insufficient_history_after_completion_stays_data_error():
    t = ticket(REF_END + dt.timedelta(minutes=30), session=[])
    assert t["decision"] == "DATA_ERROR"


def test_malformed_candle_is_never_reference_not_ready():
    box = [c for c in CANDLES if REF_START <= c.time < REF_END]
    bad = box[:5] + [dataclasses.replace(box[5], high=math.nan)] + box[6:]
    before = ticket(REF_END - dt.timedelta(minutes=6), session=bad[:-1])
    after = ticket(REF_END + dt.timedelta(minutes=30), session=bad)
    assert before["decision"] == REFERENCE_NOT_READY           # the clock, not the data, decides pre-close
    assert after["decision"] != REFERENCE_NOT_READY             # post-close data quality is the engine's call
