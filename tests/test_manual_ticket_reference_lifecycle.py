"""I7: an incomplete reference box before its window closes is REFERENCE_NOT_READY (lifecycle),
never DATA_ERROR; missing/malformed bars after the window closes stay DATA_ERROR. Offline."""
from __future__ import annotations

import dataclasses
import datetime as dt
import math

from v1_tickets.fx import REFERENCE_NOT_READY, build_fx_ticket, session_windows_utc
from v1_tickets.logic_gate import is_blocking, order_block_reasons
from v1_tickets.scan_record import TICKET_BLOCKED, build_scan_record, classify_fx_ticket

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


def test_reference_not_ready_is_never_a_block_reason_or_warning():
    assert not is_blocking(REFERENCE_NOT_READY)
    assert order_block_reasons([REFERENCE_NOT_READY]) == []
    now = REF_END - dt.timedelta(minutes=6)
    st, stage, reason = state(ticket(now), now)
    rec = build_scan_record(run_id="r", session="ASIAN_LONDON", symbol="EURUSD", strategy_id="S",
                            strategy_version="1", window=(TRADE_START, TRADE_END), data_close=now, state=st,
                            stage=stage, stop_reason=reason, now=now)
    assert rec.state == REFERENCE_NOT_READY and rec.state != TICKET_BLOCKED
    assert rec.block_reasons == () and rec.warnings == () and rec.primary_block_reason is None


def _rec(symbol, now, st, stage, reason, run_id="fx:r1"):
    return build_scan_record(run_id=run_id, session="ASIAN_LONDON", symbol=symbol, strategy_id="S",
                             strategy_version="1", window=(TRADE_START, TRADE_END), data_close=now, state=st,
                             stage=stage, stop_reason=reason, now=now)


def test_daily_report_counts_reference_not_ready_as_its_own_category(tmp_path):
    """REFERENCE_NOT_READY is a lifecycle category in the coverage report: not NOT_RUN, not
    DATA_ERROR, not TICKET_BLOCKED; and it contributes no block reason or warning."""
    from v1_tickets.manual_report import build_report, render_report
    from v1_tickets.scan_record import write_scan_record
    journal = str(tmp_path / "j")
    now = REF_END - dt.timedelta(minutes=6)                               # reference box still open
    st, stage, reason = state(ticket(now), now)
    records = [
        _rec("EURUSD", now, st, stage, reason),                                     # lifecycle
        _rec("GBPUSD", now, TICKET_BLOCKED, "DATA", "DATA_ERROR:MT5_DOWN"),          # data error
        _rec("USDJPY", now, TICKET_BLOCKED, "LOGIC_GATE", "LOGIC_GATE_FAIL:L2"),     # blocked
    ]                                                                               # XAUUSD: no record -> NOT_RUN
    for r in records:
        write_scan_record(journal, r)
    rep = build_report(journal, DAY, now=now, expected={("S@1", "ASIAN_LONDON"): ["EURUSD", "GBPUSD", "USDJPY",
                                                                                 "XAUUSD"]})
    counts = rep["state_counts"]
    assert counts[REFERENCE_NOT_READY] == 1
    assert counts["DATA_ERROR"] == 1 and counts[TICKET_BLOCKED] == 1 and counts["NOT_RUN"] == 1
    assert sum(counts.values()) == 4                                       # each symbol counted exactly once
    eur = next(s for s in rep["session_states"] if s["symbol"] == "EURUSD")
    assert eur["state"] == REFERENCE_NOT_READY and eur["stage"] == "SESSION"
    assert f"{REFERENCE_NOT_READY} 1" in render_report(rep)
    assert records[0].block_reasons == () and records[0].warnings == ()
    assert all(REFERENCE_NOT_READY not in r.block_reasons + r.warnings for r in records)


def test_manual_ticket_before_reference_close_has_no_block_reasons_or_warnings():
    from v1_tickets import manual_ticket as mt
    owner = {"risk_pct": 0.5, "risk_status": "SET", "cost_warn_R": 0.25,
             "cost_block_R": 0.25, "warn_status": "SET"}
    now = REF_END - dt.timedelta(minutes=6)
    closed = [c for c in CANDLES if c.time + dt.timedelta(minutes=15) <= now]
    box = [c for c in closed if REF_START <= c.time < REF_END]
    t = mt.build_manual_ticket("EURUSD", "ASIAN_LONDON", DAY, box, 24, [], now=now, data_close=now,
                               spread=0.00002, owner=owner, commission_r=0.0)
    assert t["state"] == REFERENCE_NOT_READY and t["ticket_status"] == REFERENCE_NOT_READY
    assert t["block_reasons"] == [] and t["warnings"] == [] and t["primary_block_reason"] is None
    assert t["owner_accept_allowed"] is False
