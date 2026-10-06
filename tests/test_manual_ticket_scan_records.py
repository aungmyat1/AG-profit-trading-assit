"""Manual Trade Ticket V1 Phase 3: every scheduled run writes one scan record per configured
symbol, and a missing record (NOT_RUN) is distinguishable from "ran, no setup"."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

from v1_tickets.scan_record import (
    NO_SETUP, NOT_RUN, TICKET_BLOCKED, TICKET_READY, WATCH, adapterless_scan_records, build_scan_record,
    classify_fx_ticket, coverage, read_jsonl, scan_path, write_scan_record,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "host"))
import live_candles_smoke as smoke  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
END = dt.datetime(2026, 10, 6, 11, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


@pytest.mark.parametrize("ticket,now,expected", [
    ({"decision": "NO_TRADE", "reason_code": "NO_SETUP_BY_WINDOW_END"}, NOW, (WATCH, "ENGINE")),
    ({"decision": "NO_TRADE", "reason_code": "NO_SETUP_BY_WINDOW_END"}, END, (NO_SETUP, "ENGINE")),
    ({"decision": "NO_TRADE", "reason_code": "AMBIGUOUS_DUAL_SWEEP"}, NOW, (NO_SETUP, "ENGINE")),
    ({"decision": "DATA_ERROR", "reason_code": "X"}, NOW, (TICKET_BLOCKED, "DATA")),
    ({"decision": "STALE", "reason_code": "STALE_DATA", "suppressed_decision": "NO_TRADE"}, NOW, (TICKET_BLOCKED, "DATA")),
    ({"decision": "STALE", "reason_code": "STALE_SIGNAL", "suppressed_decision": "READY"}, NOW, (TICKET_BLOCKED, "TICKET")),
    ({"decision": "REFERENCE_NOT_READY", "reason_code": "REFERENCE_NOT_READY"}, NOW, ("REFERENCE_NOT_READY", "SESSION")),
    ({"decision": "READY", "reason_code": "UPPER_SWEEP_STRICT_PENETRATION"}, NOW, (TICKET_READY, "TICKET")),
    ({"decision": "SOMETHING_NEW"}, NOW, (TICKET_BLOCKED, "ENGINE")),
])
def test_classification_is_exhaustive_and_fails_closed(ticket, now, expected):
    assert classify_fx_ticket(ticket, now=now, window_end=END)[:2] == expected


def test_missing_record_is_not_run_not_no_setup(tmp_path):
    rec = build_scan_record(run_id="r1", session="ASIAN_LONDON", symbol="EURUSD", strategy_id="S", strategy_version="1",
                            window=(NOW, END), data_close=NOW - dt.timedelta(seconds=30), state=NO_SETUP,
                            stage="ENGINE", stop_reason="NO_VALID_SWEEP", now=NOW)
    write_scan_record(str(tmp_path), rec)
    rows = read_jsonl(scan_path(str(tmp_path), NOW.date()))
    assert rows[0]["data_freshness_s"] == 30.0 and rows[0]["session_anchor_tz"] == "UTC"
    cov = coverage(rows, "r1", [("S@1", "ASIAN_LONDON", "EURUSD"), ("S@1", "ASIAN_LONDON", "GBPUSD")])
    assert cov == {("S@1", "ASIAN_LONDON", "EURUSD"): NO_SETUP, ("S@1", "ASIAN_LONDON", "GBPUSD"): NOT_RUN}
    assert coverage(rows, "other-run", [("S@1", "ASIAN_LONDON", "EURUSD")])[("S@1", "ASIAN_LONDON", "EURUSD")] == NOT_RUN


def test_session_trade_v1_records_are_blocked_by_missing_adapter():
    recs = adapterless_scan_records(run_id="r", cycle="ASIAN_LONDON", now=NOW)
    assert {r.symbol for r in recs} == {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD.crp"}
    assert all(r.state == TICKET_BLOCKED and r.stop_reason == "STRATEGY_ADAPTER_NOT_IMPLEMENTED"
               and r.stage_reached == "AUTHORITY" and r.strategy == "SESSION_TRADE_V1@1" for r in recs)
    assert adapterless_scan_records(run_id="r", cycle="LONDON_NEWYORK", now=NOW) == []     # UNSIGNED cycle


def test_every_scheduled_run_records_every_configured_symbol(tmp_path):
    journal = str(tmp_path / "j")
    smoke.run_fx(lambda *a: [], NOW, journal, gated=False, notify=False)     # no data: still recorded
    rows = read_jsonl(scan_path(journal, NOW.date()))
    run_id = smoke.fx_run_id(NOW)
    expected = [("ST_ASIAN_SWEEP_5R_V1@1.1.1", c, s) for c in ("ASIAN_LONDON", "LONDON_NEWYORK")
                for s in smoke.fx_symbols()]
    expected += [("SESSION_TRADE_V1@1", "ASIAN_LONDON", s) for s in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD.crp")]
    cov = coverage(rows, run_id, expected)
    assert NOT_RUN not in cov.values() and len(rows) == len(expected)
    assert all(r["state"] == TICKET_BLOCKED for r in rows)


def test_scan_record_carries_ordered_block_reasons():
    rec = build_scan_record(run_id="r", session="ASIAN_LONDON", symbol="EURUSD", strategy_id="S", strategy_version="1",
                            window=None, data_close=None, state=TICKET_BLOCKED, stage="LOGIC_GATE",
                            stop_reason="LOGIC_GATE_FAIL:L2", now=NOW,
                            block_reasons=["STALE_SIGNAL", "LOGIC_GATE_FAIL:L2"])
    assert rec.block_reasons == ("LOGIC_GATE_FAIL:L2", "SIGNAL_STALE")
    assert rec.primary_block_reason == "LOGIC_GATE_FAIL:L2" == rec.stop_reason


@pytest.mark.parametrize("raiser,status,error", [
    (smoke.tg.TelegramSendError("send failed (HTTP 401)"), "FAILED", "send failed (HTTP 401)"),
    (RuntimeError("boom https://api.telegram.org/botSECRET123/sendMessage"), "ERROR", "RuntimeError"),
])
def test_telegram_failure_never_hides_scan_records_and_is_traced(tmp_path, monkeypatch, raiser, status, error):
    """A4 / TELEGRAM_DELIVERY_TRACE_R1: scan records persist first; a delivery failure is recorded
    separately, never raised, and carries no token/URL/message text."""
    from test_manual_ticket_logic_gate import CANDLES     # recorded EURUSD M15; used only to drive the loop
    monkeypatch.delenv("AG_EVIDENCE_ROOT")                 # committed host metadata -> tickets, not DATA_ERROR
    now = dt.datetime(2026, 6, 23, 7, 20, tzinfo=UTC)
    fetch = lambda symbol, tf, n: CANDLES                  # noqa: E731
    logged = []
    monkeypatch.setattr(smoke, "log_line", lambda name, msg: logged.append(msg))
    monkeypatch.setattr(smoke.tg, "should_send", lambda *a, **k: True)

    def boom(text, session=None):
        raise raiser
    monkeypatch.setattr(smoke.tg, "send_message", boom)
    quiet, loud = str(tmp_path / "quiet"), str(tmp_path / "loud")
    smoke.run_fx(fetch, now, quiet, gated=False, notify=False)
    smoke.run_fx(fetch, now, loud, gated=False, notify=True)
    quiet_rows, loud_rows = read_jsonl(scan_path(quiet, now.date())), read_jsonl(scan_path(loud, now.date()))
    assert len(loud_rows) == len(quiet_rows) == 12      # 4 symbols x 2 cycles + 4 SESSION_TRADE_V1 visibility
    path = tmp_path / "loud" / smoke.DELIVERY_DIR / f"{now.date().isoformat()}.jsonl"
    rows = read_jsonl(str(path))
    assert len(rows) == 8 and all(r["status"] == status and r["error"] == error and r["channel"] == "telegram" for r in rows)
    assert {r["ref"].split(":")[0] for r in rows} == {"fx"}
    assert "SECRET123" not in path.read_text() and not any("SECRET123" in m for m in logged)


def test_telegram_policy_off_is_recorded_as_not_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke.tg, "should_send", lambda *a, **k: False)
    assert smoke._notify("TICKET", "READY", "text", ".", journal=str(tmp_path), ref="x", now=NOW) == "NOT_SENT_POLICY"
    rows = read_jsonl(str(tmp_path / smoke.DELIVERY_DIR / f"{NOW.date().isoformat()}.jsonl"))
    assert rows == [{"channel": "telegram", "kind": "TICKET", "value": "READY", "ref": "x", "status": "NOT_SENT_POLICY",
                     "error": None, "recorded_at": NOW.isoformat()}]


def test_scan_record_keeps_warnings_out_of_block_reasons():
    rec = build_scan_record(run_id="r", session="ASIAN_LONDON", symbol="EURUSD", strategy_id="S", strategy_version="1",
                            window=None, data_close=None, state=TICKET_READY, stage="TICKET", stop_reason=None,
                            now=NOW, block_reasons=["L5_WARN"], warnings=["L5_WARN"])
    assert rec.block_reasons == () and rec.warnings == ("L5_WARN",) and rec.primary_block_reason is None


def test_setup_window_open_is_lifecycle_never_a_reason_or_blocked():
    from v1_tickets import scan_record as sr
    from v1_tickets.logic_gate import LIFECYCLE_STATES, is_blocking, order_block_reasons
    assert {f"SETUP_WINDOW_OPEN:{r}" for r in sr._OPEN_WINDOW_REASONS} <= LIFECYCLE_STATES   # kept in sync
    st, stage, reason = classify_fx_ticket({"decision": "NO_TRADE", "reason_code": "NO_SETUP_BY_WINDOW_END"},
                                           now=NOW, window_end=END)
    assert (st, reason) == (WATCH, "SETUP_WINDOW_OPEN:NO_SETUP_BY_WINDOW_END") and st != TICKET_BLOCKED
    assert not is_blocking(reason) and order_block_reasons([reason]) == []
    rec = build_scan_record(run_id="r", session="ASIAN_LONDON", symbol="XAUUSD", strategy_id="S", strategy_version="1",
                            window=(NOW, END), data_close=NOW, state=st, stage=stage, stop_reason=reason, now=NOW)
    assert rec.block_reasons == () and rec.warnings == () and rec.primary_block_reason is None
    assert rec.state == WATCH and rec.stop_reason == reason                 # still visible as the scan's reason


@pytest.mark.parametrize("kind,value", [
    ("TICKET", "REFERENCE_NOT_READY"), ("TICKET", "NO_TRADE"), ("TICKET", "SETUP_WINDOW_OPEN:NO_SETUP_BY_WINDOW_END"),
    ("TICKET", "WATCH"), ("MANUAL_TICKET", "REFERENCE_NOT_READY"), ("MANUAL_TICKET", "WATCH"),
    ("MANUAL_TICKET", "SETUP_WINDOW_OPEN:NO_SETUP_BY_WINDOW_END"),
])
def test_lifecycle_states_never_send_even_with_every_scope_enabled(tmp_path, kind, value):
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY, MANUAL_TICKET_READY]\n")
    assert not smoke.tg.should_send(kind, value, str(tmp_path))
    assert not smoke.tg.should_send(kind, value, str(tmp_path / "no_override"))   # production default: ARCHIVE_ONLY


def test_scheduled_run_in_lifecycle_states_sends_nothing_but_records_everything(tmp_path, monkeypatch):
    """Before the reference box closes (REFERENCE_NOT_READY) and with the trade window open and no
    setup yet (WATCH / SETUP_WINDOW_OPEN): scan records + delivery trace only, zero sends."""
    from test_manual_ticket_logic_gate import CANDLES
    monkeypatch.delenv("AG_EVIDENCE_ROOT")
    monkeypatch.setattr(smoke, "log_line", lambda *a: None)
    every = {"mode": smoke.tg.MESSAGE_DELIVERY, "scopes": smoke.tg.SCOPES + smoke.tg.MANUAL_SCOPES}
    monkeypatch.setattr(smoke.tg, "load_mode", lambda root=".": every)
    sent = []
    monkeypatch.setattr(smoke.tg, "send_message", lambda text, session=None: sent.append(text))
    journal = str(tmp_path / "j")
    for now in (dt.datetime(2026, 6, 15, 6, 50, tzinfo=UTC),       # LONDON_NEWYORK reference (06-11) still open
                dt.datetime(2026, 6, 15, 7, 50, tzinfo=UTC)):      # ASIAN_LONDON: no setup yet, trade window open
        fetch = lambda symbol, tf, n, now=now: [c for c in CANDLES if c.time + dt.timedelta(minutes=15) <= now]  # noqa: E731
        smoke.run_fx(fetch, now, journal, gated=False, notify=True)
    rows = read_jsonl(scan_path(journal, dt.date(2026, 6, 15)))
    al = [r for r in rows if r["strategy"].startswith("ST_ASIAN")]
    assert {r["state"] for r in al} >= {"REFERENCE_NOT_READY", WATCH}
    assert all(r["block_reasons"] == [] and r["warnings"] == [] for r in al if r["state"] in ("REFERENCE_NOT_READY", WATCH))
    assert sent == []
    trace = read_jsonl(str(tmp_path / "j" / smoke.DELIVERY_DIR / "2026-06-15.jsonl"))
    assert trace and all(t["status"] == "NOT_SENT_POLICY" for t in trace)
