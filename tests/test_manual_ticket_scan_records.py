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
