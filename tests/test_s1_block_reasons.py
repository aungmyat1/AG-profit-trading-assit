"""AGP-S1-BLOCK-REASON-FIX-R1: distinct S1 scope block reasons (all BLOCKED) and no silent S1 session.

Market data and Telegram transport are mocked; nothing touches a broker."""
from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import test_canonical_fx_delivery as h  # noqa: E402

from strategy_engine.session import Candle  # noqa: E402
from telegram_delivery.adapter import (  # noqa: E402
    BLOCK_EXPLANATIONS,
    render_cycle_status,
)
from v1_tickets import daily_evaluator as de  # noqa: E402
from v1_tickets import fx as fx_tickets  # noqa: E402

cfd = h.cfd
UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 7)
AT = dt.datetime(2026, 10, 7, 7, 16, 8, tzinfo=UTC)
BAR = Candle(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), 1.1665, 1.1670, 1.1660, 1.1666)
CODES = ("SCOPE_NOT_S1", "SCOPE_IDENTITY_MISMATCH", "BRANCH_OUTSIDE_VERIFIED_SCOPE")


def _sig(regime="RANGE", setup="SWEEP", status="SIGNAL"):
    return types.SimpleNamespace(status=status, reason_code="ENGINE_CODE", regime=regime, setup=setup, signal_id="s1",
                                 box_high=1.1720, box_low=1.1660, box_mid=1.1690,
                                 signal_timestamp=dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), direction="LONG",
                                 entry=1.1665, stop_loss=1.16515, risk_distance=0.00135)


def _ticket(symbol="GBPUSD", cycle="ASIAN_LONDON"):
    return fx_tickets.build_fx_ticket(symbol, cycle, DAY, [], 2, [BAR], data_source="MT5_VT_MARKETS_DEMO",
                                      evaluated_at=AT, data_close=AT, spread=0.00015, runtime_scope=True)


def test_every_code_has_an_explanation():
    assert all(code in BLOCK_EXPLANATIONS for code in CODES)


def test_evaluator_scope_not_s1(tmp_path):
    r = de.evaluate_fx_pair("EURUSD", "LONDON_NEWYORK", now=AT, day=DAY, archive_root=str(tmp_path),
                            candle_provider=lambda *_: pytest.fail("no data before the scope gate"),
                            ticket_source="LIVE")
    assert (r.decision, r.canonical["reason_code"]) == ("BLOCKED", "SCOPE_NOT_S1")
    assert "outside S1" in r.canonical["engine_detail"]["detail"]


def test_evaluator_scope_identity_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(de.v1_fx, "symbol_scope_verified", lambda *a, **k: False)
    r = de.evaluate_fx_pair("GBPUSD", "ASIAN_LONDON", now=AT, day=DAY, archive_root=str(tmp_path),
                            candle_provider=lambda *_: pytest.fail("no data before the identity gate"),
                            ticket_source="LIVE")
    assert (r.decision, r.canonical["reason_code"]) == ("BLOCKED", "SCOPE_IDENTITY_MISMATCH")


def test_fx_identity_path_is_recoded_scope_identity_mismatch_for_s1(monkeypatch):
    monkeypatch.setattr(fx_tickets, "symbol_scope_verified", lambda *a, **k: False)
    raw = _ticket()
    assert raw["reason_code"] == "LOGIC_SCOPE_NOT_VERIFIED"          # fx.py stays byte-identical (ASW 1.1.3 identity)
    t = de.scope_block_reason(raw)
    assert (t["decision"], t["reason_code"], t["block_reasons"]) == (
        "BLOCKED", "SCOPE_IDENTITY_MISMATCH", ["SCOPE_IDENTITY_MISMATCH"])


def test_fx_identity_path_is_recoded_scope_not_s1_for_other_scopes(monkeypatch):
    monkeypatch.setattr(fx_tickets, "symbol_scope_verified", lambda *a, **k: False)
    assert de.scope_block_reason(_ticket("USDJPY"))["reason_code"] == "SCOPE_NOT_S1"


def test_fx_branch_path_is_recoded_branch_outside_verified_scope(monkeypatch):
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: _sig(regime="TREND", setup="TREND"))
    t = de.scope_block_reason(_ticket())
    assert (t["decision"], t["reason_code"], t["emitted_branch"]) == (
        "BLOCKED", "BRANCH_OUTSIDE_VERIFIED_SCOPE", "TREND_TREND")
    assert (t["regime"], t["setup"]) == ("TREND", "TREND")


def test_recoding_leaves_every_other_ticket_untouched():
    for t in ({"decision": "NO_TRADE", "reason_code": "X"}, {"decision": "BLOCKED", "reason_code": "SPREAD_TOO_WIDE"}):
        assert de.scope_block_reason(t) is t


def test_fx_py_is_byte_identical_to_the_registered_asw_v113_identity():
    from v1_tickets.authority import load_registry, logic_identity
    rec = load_registry()["ST_ASIAN_SWEEP_5R_V1"]["candidate_versions"]["1.1.3"]["logic_verified_identity"]
    assert logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.3")["digest"] == rec


def test_cycle_status_message_is_compact_ascii():
    msg = render_cycle_status({"instrument": "GBPUSD", "session": "ASIAN_LONDON", "session_date": "2026-10-14",
                               "decision": "BLOCKED", "reason_code": "BRANCH_OUTSIDE_VERIFIED_SCOPE",
                               "created_at": "2026-10-14T07:01:00+00:00",
                               "engine_detail": {"detail": "emitted branch TREND_TREND — x",
                                                 "regime": "TREND", "setup": "TREND"}})
    assert msg.isascii() and len(msg.splitlines()) <= 8
    assert "reason: BRANCH_OUTSIDE_VERIFIED_SCOPE --" in msg and "engine: regime=TREND setup=TREND" in msg


def _branch_blocked(monkeypatch):
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: _sig(regime="TREND", setup="TREND"))
    return h.signal_provider()


def _no_trade(monkeypatch):
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: _sig(status="NO_SIGNAL"))
    return h.signal_provider()


@pytest.mark.parametrize("make_provider,live_decision", [
    (lambda mp: h.signal_provider(), None),        # suppressed READY (LIVE resolves the actionability policy)
    (lambda mp: cfd.failure_provider("MT5_PACKAGE_MISSING", "MetaTrader5 package unavailable"), "INSUFFICIENT_DATA"),
    (_branch_blocked, "BLOCKED"),                  # runtime branch gate applies to LIVE only
    (_no_trade, "NO_TRADE"),
])
@pytest.mark.parametrize("source", ["LIVE", "REPLAY"])
def test_scheduled_s1_cycle_never_ends_summary_only(tmp_path, monkeypatch, make_provider, live_decision, source):
    send, calls = h.sender(tmp_path)
    results, lines, journal, _, _ = h.run(tmp_path, send=send, provider=make_provider(monkeypatch), source=source)
    s1 = next(r for r in results if (r.instrument, r.session) == ("GBPUSD", "ASIAN_LONDON"))
    if source == "LIVE" and live_decision:
        assert s1.decision == live_decision
    if source == "LIVE" and live_decision == "BLOCKED":
        assert s1.canonical["engine_detail"]["reason_code"] == "BRANCH_OUTSIDE_VERIFIED_SCOPE"
    events = [e for e in h.events(journal, h.NOW.date(), "ASIAN_LONDON")
              if e["stage"] == "RESULT" and e["symbol"] == "GBPUSD"]
    assert events and all(e["delivery_state"] != "summary_only" for e in events)
    # Exactly one Telegram message for the S1 cycle: its alert, or else its compact cycle status.
    sent = [a for kind in ("ticket", "cycle") for a in send.delivery_attempts(kind, [s1.ticket_id])
            if a.get("message_id")]
    assert len(sent) == 1
    status = [m for _, m in calls if m.startswith("S1 CYCLE | GBPUSD ASIAN_LONDON")]
    assert not status or f"decision: {s1.decision}" in status[0]
