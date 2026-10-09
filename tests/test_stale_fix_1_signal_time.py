"""STALE-FIX-1: a signal age is measured only from the engine's own signal timestamp.

A SIGNAL without that timestamp (box-direction entry_1) fails closed as DATA_ERROR /
SIGNAL_TIME_UNAVAILABLE -- it never borrows the first trade-session bar and is never READY.
The session digest keeps that cause distinct from an acquisition DATA_ERROR."""
from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "host"))

import canonical_fx_delivery as cfd  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from v1_tickets import fx  # noqa: E402
from test_canonical_fx_delivery import run, sender, signal_provider  # noqa: E402

UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 7)
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)


def _sig(signal_timestamp):
    return types.SimpleNamespace(status="SIGNAL", reason_code="BOX_DIRECTION_V1", regime="TREND", setup="TREND",
                                 signal_id="s1", box_high=1.1720, box_low=1.1660, box_mid=1.1690,
                                 signal_timestamp=signal_timestamp, direction="LONG", entry=1.1690,
                                 stop_loss=1.1660, risk_distance=0.0030)


def _build(monkeypatch, sig, now=NOW):
    monkeypatch.setattr(fx, "evaluate", lambda *a, **k: sig)
    bar = Candle(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), 1.1690, 1.1695, 1.1685, 1.1690)
    return fx.build_fx_ticket("EURUSD", "ASIAN_LONDON", DAY, [], 2, [bar], data_source="FIXTURE",
                              evaluated_at=now, data_close=now, spread=0.00002)


def test_fallback_is_gone_from_source():
    assert "post_session_candles[0]" not in (REPO / "src" / "v1_tickets" / "fx.py").read_text(encoding="utf-8")


def test_signal_without_engine_time_is_data_error_never_ready(monkeypatch):
    t = _build(monkeypatch, _sig(None))
    assert (t["decision"], t["reason_code"]) == ("DATA_ERROR", fx.SIGNAL_TIME_UNAVAILABLE)
    assert t["engine_reason_code"] == "BOX_DIRECTION_V1" and t["signal_close_utc"] is None
    assert t["signal_time_source"] == fx.SIGNAL_TIME_MISSING
    assert (t["direction"], t["entry"], t["stop_loss"]) == ("LONG", 1.169, 1.166)   # levels kept for audit
    assert "suppressed_decision" not in t                                         # not a downgraded READY


def test_signal_with_engine_time_keeps_its_engine_signal_close(monkeypatch, tmp_path):
    on = tmp_path / "on.yaml"
    on.write_text("strategies:\n  ST_ASIAN_SWEEP_5R_V1:\n    ready: 'ON'\n")
    import v1_tickets.ready_authority as ra
    monkeypatch.setattr(ra, "CONFIG_PATH", str(on))
    t = _build(monkeypatch, _sig(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC)))
    assert t["signal_time_source"] == fx.SIGNAL_TIME_ENGINE
    assert t["signal_close_utc"] == "2026-10-07T07:15:00+00:00" and t["decision"] == "READY"
    # A stale engine time is still STALE, measured from the engine bar -- not from any trade bar.
    late = _build(monkeypatch, _sig(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC)),
                  now=dt.datetime(2026, 10, 7, 9, 0, tzinfo=UTC))
    assert late["decision"] == "STALE" and late["signal_close_utc"] == "2026-10-07T07:15:00+00:00"


def test_error_and_no_signal_tickets_are_not_applicable(monkeypatch):
    err = fx.build_fx_error_ticket("EURUSD", "ASIAN_LONDON", DAY, evaluated_at=NOW, reason_code="NO_CANDLE_DATA")
    assert err["signal_time_source"] == fx.SIGNAL_TIME_NOT_APPLICABLE
    no_trade = _build(monkeypatch, types.SimpleNamespace(**{**vars(_sig(None)), "status": "NO_TRADE",
                                                           "reason_code": "NO_SETUP_BY_WINDOW_END"}))
    assert no_trade["decision"] == "NO_TRADE" and no_trade["signal_time_source"] == fx.SIGNAL_TIME_NOT_APPLICABLE


def _digest_row(journal, send, symbol="EURUSD"):
    digest = cfd.build_session_summary(journal, session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    return next(r for r in digest["per_instrument"] if r["symbol"] == symbol)


def test_digest_reports_signal_time_unavailable_from_the_event_row(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "evaluate", lambda *a, **k: _sig(None))
    send, calls = sender(tmp_path, enabled=False)
    results, _, journal, _, _ = run(tmp_path, send=send)
    assert all(r.decision != "WATCH_READY" for r in results) and calls == []
    row = _digest_row(journal, send)
    assert row["reason_code"] == fx.SIGNAL_TIME_UNAVAILABLE and row["acquisition_error_code"] is None


def test_digest_reports_acquisition_data_error_distinctly(tmp_path):
    send, _ = sender(tmp_path, enabled=False)
    _, _, journal, _, _ = run(tmp_path, send=send, data_source="NONE",
                              provider=cfd.failure_provider("MT5_PACKAGE_MISSING", "MetaTrader5 package unavailable"))
    row = _digest_row(journal, send)
    assert row["acquisition_error_code"] == "MT5_PACKAGE_MISSING"
    assert row["reason_code"] != fx.SIGNAL_TIME_UNAVAILABLE and row["reason_code"]


def test_digest_takes_reason_code_from_the_event_row(tmp_path):
    """Event row wins over the stored block_reasons (which may lead with an engine code)."""
    import json
    import os
    from ticket_store.store import REPLAY, TicketStore, build_evaluation
    send, _ = sender(tmp_path, enabled=False)
    journal = str(tmp_path / "journal")
    day = NOW.date().isoformat()
    tid = f"ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|{day}"
    TicketStore(os.path.join(journal, "ticket_store")).append_evaluation(build_evaluation(
        ticket_id=tid, strategy="ST_ASIAN_SWEEP_5R_V1@1.1.1", source=REPLAY, symbol="EURUSD",
        session="ASIAN_LONDON", evaluated_at_utc=NOW.isoformat(), state="INSUFFICIENT_DATA",
        block_reasons=["BOX_DIRECTION_V1"]))
    path = cfd._session_event_path(journal, day, "ASIAN_LONDON")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "TICKET_DELIVERY", "stage": "RESULT", "ticket_id": tid,
                            "decision": "INSUFFICIENT_DATA", "symbol": "EURUSD", "source": "REPLAY",
                            "recorded_at_utc": NOW.isoformat(), "reason_code": fx.SIGNAL_TIME_UNAVAILABLE,
                            "acquisition_error_code": None}) + "\n")
    assert _digest_row(journal, send)["reason_code"] == fx.SIGNAL_TIME_UNAVAILABLE


def test_digest_reason_matches_the_selected_live_record_not_a_later_replay_event(tmp_path):
    """S02: LIVE and REPLAY share ticket id, decision and timestamp but differ in reason.

    _latest_record selects LIVE; the REPLAY event is appended last. The digest must report the
    LIVE event's reason, not the most recently recorded event for (ticket_id, decision).
    """
    import json
    import os
    from ticket_store.store import LIVE, REPLAY, TicketStore, build_evaluation
    send, _ = sender(tmp_path, enabled=False)
    journal = str(tmp_path / "journal")
    day = NOW.date().isoformat()
    tid = f"ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|{day}"
    store = TicketStore(os.path.join(journal, "ticket_store"))
    for source, reason in ((LIVE, "LIVE_STORE_REASON"), (REPLAY, "REPLAY_STORE_REASON")):
        store.append_evaluation(build_evaluation(
            ticket_id=tid, strategy="ST_ASIAN_SWEEP_5R_V1@1.1.1", source=source, symbol="EURUSD",
            session="ASIAN_LONDON", evaluated_at_utc=NOW.isoformat(), state="INSUFFICIENT_DATA",
            block_reasons=[reason]))
    path = cfd._session_event_path(journal, day, "ASIAN_LONDON")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for source, reason in (("LIVE", fx.SIGNAL_TIME_UNAVAILABLE), ("REPLAY", "REPLAY_EVENT_REASON")):
            f.write(json.dumps({"event_type": "TICKET_DELIVERY", "stage": "RESULT", "ticket_id": tid,
                                "decision": "INSUFFICIENT_DATA", "symbol": "EURUSD", "source": source,
                                "recorded_at_utc": NOW.isoformat(), "reason_code": reason,
                                "acquisition_error_code": None}) + "\n")
    row = _digest_row(journal, send)
    assert row["source"] == "LIVE"
    assert row["reason_code"] == fx.SIGNAL_TIME_UNAVAILABLE


def test_digest_without_a_source_matched_event_falls_back_to_the_selected_record(tmp_path):
    """S02: a REPLAY-only event never lends its reason to the selected LIVE record."""
    import json
    import os
    from ticket_store.store import LIVE, TicketStore, build_evaluation
    send, _ = sender(tmp_path, enabled=False)
    journal = str(tmp_path / "journal")
    day = NOW.date().isoformat()
    tid = f"ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|{day}"
    TicketStore(os.path.join(journal, "ticket_store")).append_evaluation(build_evaluation(
        ticket_id=tid, strategy="ST_ASIAN_SWEEP_5R_V1@1.1.1", source=LIVE, symbol="EURUSD",
        session="ASIAN_LONDON", evaluated_at_utc=NOW.isoformat(), state="INSUFFICIENT_DATA",
        block_reasons=["LIVE_STORE_REASON"]))
    path = cfd._session_event_path(journal, day, "ASIAN_LONDON")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "TICKET_DELIVERY", "stage": "RESULT", "ticket_id": tid,
                            "decision": "INSUFFICIENT_DATA", "symbol": "EURUSD", "source": "REPLAY",
                            "recorded_at_utc": NOW.isoformat(), "reason_code": "REPLAY_EVENT_REASON",
                            "acquisition_error_code": None}) + "\n")
    assert _digest_row(journal, send)["reason_code"] == "LIVE_STORE_REASON"
