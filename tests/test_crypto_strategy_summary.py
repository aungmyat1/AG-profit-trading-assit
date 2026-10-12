"""Crypto strategy (BTCUSD/ETHUSD) window summaries and scope-status stamping (OD1012-ROUTING).

One report-only summary per active crypto ticket window (CRYPTO_DAY weekdays, CRYPTO_WEEKEND
Sat/Sun), sent once through the shared `_process_due_summary` path after the window end plus
grace. Outcomes come only from the ticket archive; a missing record is NO_RECORD. Transport is
always faked; nothing touches MT5, a broker or the network.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import canonical_fx_delivery as cfd  # noqa: E402
import live_candles_smoke as lcs  # noqa: E402
from test_canonical_fx_delivery import events, sender  # noqa: E402

from host_delivery import telegram_message as tg  # noqa: E402
from telegram_delivery.adapter import render_crypto_strategy_summary, render_session_summary  # noqa: E402
from ticket_delivery.archive import CycleDecisionRecord, archive_cycle_decision  # noqa: E402
from ticket_delivery.archive_reader import latest_cycle_decision  # noqa: E402
from v1_tickets.crypto import ACTIVE_CONFIG, load_ticket_config  # noqa: E402

UTC = dt.timezone.utc
WED, SAT = dt.date(2026, 10, 7), dt.date(2026, 10, 10)
CONFIG = load_ticket_config(ACTIVE_CONFIG, str(ROOT))


def at(day, hh, mm):
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=UTC)


def archive(journal, *, strategy, version, symbol, cycle, trading_date, when, state, window=None, reasons=()):
    record = CycleDecisionRecord(
        strategy_id=strategy, strategy_version=version, application_release="TEST", symbol=symbol,
        cycle=cycle, trading_date=trading_date, cycle_state=state, evaluation_time_utc=when.isoformat(),
        payload={"window": window} if window else {}, reason_codes=tuple(reasons))
    return archive_cycle_decision(record, root=str(Path(journal) / "ticket_delivery" / "archive"))


def research(journal, symbol, when, state, window="WEEKDAY", reasons=("NO_SWEEP",)):
    return archive(journal, strategy="ST_LIQUIDITY_SWEEP_RETEST_V1", version="2.0.0", symbol=symbol,
                   cycle="DAILY_WINDOW", trading_date=when.date() - dt.timedelta(days=1), when=when,
                   state=state, window=window, reasons=reasons)


def due(journal, now, send):
    return lcs.crypto_strategy_summary_lines(now, str(journal), CONFIG, sender=send)


def test_research_symbol_map_matches_active_crypto_config():
    assert {v: k for k, v in cfd.CRYPTO_RESEARCH_SYMBOL.items()} == CONFIG["venue"]["symbols"]


def test_window_follows_active_config_weekday_and_weekend():
    day = cfd.crypto_strategy_window(CONFIG, WED, cfd.CRYPTO_DAY)
    assert day is not None and day[1] > day[0]
    assert cfd.crypto_strategy_window(CONFIG, SAT, cfd.CRYPTO_DAY) is None
    assert cfd.crypto_strategy_window(CONFIG, WED, cfd.CRYPTO_WEEKEND) is None
    weekend = cfd.crypto_strategy_window(CONFIG, SAT, cfd.CRYPTO_WEEKEND)
    assert weekend is not None and weekend[0].date() == SAT


def test_weekday_summary_due_once_after_window_end_plus_grace(tmp_path):
    send, calls = sender(tmp_path)
    start, end = cfd.crypto_strategy_window(CONFIG, WED, cfd.CRYPTO_DAY)
    assert due(tmp_path, start - dt.timedelta(hours=1), send) == []          # scheduler start
    research(tmp_path, "BTCUSDT", start + dt.timedelta(minutes=2), "NO_TRADE")
    assert due(tmp_path, end + cfd.SUMMARY_GRACE, send) == []                # not yet due
    lines = due(tmp_path, end + cfd.SUMMARY_GRACE + dt.timedelta(minutes=1), send)
    assert lines == [f"CRYPTO_STRATEGY_SUMMARY {WED.isoformat()} CRYPTO_DAY status=INCOMPLETE_NO_RECORD delivery=sent"]
    assert due(tmp_path, end + dt.timedelta(hours=3), send) == []            # never re-sent
    assert len(calls) == 1
    text = calls[0][1]
    assert "REPORT ONLY — NON-ACTIONABLE" in text
    assert "- BTCUSD: STALE_IDENTITY | REPORT_ONLY (STALE_IDENTITY) [branches=SHORT]" in text
    assert "- BTCUSD RESEARCH ST_LIQUIDITY_SWEEP_RETEST_V1: NO_TRADE (NO_SWEEP)" in text
    assert "- ETHUSD RESEARCH ST_LIQUIDITY_SWEEP_RETEST_V1: NO_RECORD (-)" in text
    assert "No broker order. Execution not authorized." in text
    results = [e for e in events(tmp_path, WED, cfd.CRYPTO_DAY) if e.get("stage") == "RESULT"]
    assert [r["delivery_state"] for r in results] == ["sent"]


def test_records_outside_window_or_other_window_are_no_record(tmp_path):
    start, end = cfd.crypto_strategy_window(CONFIG, WED, cfd.CRYPTO_DAY)
    research(tmp_path, "BTCUSDT", start - dt.timedelta(minutes=5), "READY")          # before the window
    research(tmp_path, "ETHUSDT", start + dt.timedelta(minutes=5), "READY", window="WEEKEND")
    send, _ = sender(tmp_path, enabled=False)
    summary = cfd.build_crypto_strategy_summary(str(tmp_path), session_date=WED, session=cfd.CRYPTO_DAY,
                                                window=(start, end), sender=send)
    assert [i["research"]["decision"] for i in summary["per_instrument"]] == ["NO_RECORD", "NO_RECORD"]
    assert summary["status"] == "INCOMPLETE_NO_RECORD" and summary["execution_authorized"] is False


def test_latest_correction_wins_and_ccfd_source_is_read(tmp_path):
    start, end = cfd.crypto_strategy_window(CONFIG, SAT, cfd.CRYPTO_WEEKEND)
    for symbol in ("BTCUSDT", "ETHUSDT"):
        research(tmp_path, symbol, start + dt.timedelta(minutes=1), "NO_TRADE", window="WEEKEND")
        research(tmp_path, symbol, start + dt.timedelta(minutes=16), "BLOCKED", window="WEEKEND",
                 reasons=("STALE",))
    archive(tmp_path, strategy="ST_CRYPTO_CFD_SWEEP_RETEST_V1", version="1.0.0", symbol="BTCUSD",
            cycle="WEEKEND", trading_date=start.date(), when=start + dt.timedelta(minutes=3), state="WATCH")
    send, _ = sender(tmp_path, enabled=False)
    summary = cfd.build_crypto_strategy_summary(str(tmp_path), session_date=SAT, session=cfd.CRYPTO_WEEKEND,
                                                window=(start, end), sender=send)
    btc, eth = summary["per_instrument"]
    assert (btc["research"]["decision"], btc["research"]["reason_codes"]) == ("BLOCKED", ["STALE"])
    assert (btc["ccfd"]["decision"], eth["ccfd"]["decision"]) == ("WATCH", "NO_RECORD")
    assert summary["status"] == "COMPLETE"
    assert "- BTCUSD CCFD ST_CRYPTO_CFD_SWEEP_RETEST_V1: WATCH (-)" in render_crypto_strategy_summary(summary)


def test_disabled_sender_records_disabled_and_never_transports(tmp_path):
    def forbidden(*_):
        raise AssertionError("transport must not be called while delivery is disabled")
    send, _ = sender(tmp_path, enabled=False, transport=forbidden)
    start, end = cfd.crypto_strategy_window(CONFIG, SAT, cfd.CRYPTO_WEEKEND)
    due(tmp_path, start - dt.timedelta(hours=1), send)
    lines = due(tmp_path, end + cfd.SUMMARY_GRACE + dt.timedelta(minutes=1), send)
    assert lines == [f"CRYPTO_STRATEGY_SUMMARY {SAT.isoformat()} CRYPTO_WEEKEND "
                     "status=INCOMPLETE_NO_RECORD delivery=disabled"]


def test_archive_reader_missing_is_none(tmp_path):
    assert latest_cycle_decision(str(tmp_path), "X", "BTCUSD", "WEEKDAY", WED) is None


def test_fx_session_summary_stamps_scope_status_within_telegram_limit(tmp_path):
    send, _ = sender(tmp_path, enabled=False)
    summary = cfd.build_session_summary(str(tmp_path), session_date=WED, session="ASIAN_LONDON", sender=send)
    assert [s["symbol"] for s in summary["scope_statuses"]] == ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    assert {s["route"] for s in summary["scope_statuses"]} == {"REPORT_ONLY"}
    text = render_session_summary(summary)
    assert "REPORT ONLY — NON-ACTIONABLE" in text
    assert "- GBPUSD: LOGIC_VERIFIED | REPORT_ONLY (READY_AUTHORITY_OFF_D6) [branch=RANGE_SWEEP]" in text
    assert "- EURUSD: SUSPENDED | REPORT_ONLY (L3_REPAINT_UNRESOLVED_2026-07-31)" in text
    assert len(text.encode("utf-16-le")) // 2 <= 4096


def test_render_rejects_a_routable_scope():
    send_summary = {"schema": "AGP_HOST_TICKET_DELIVERY_R1_SESSION_SUMMARY_V1", "session_date": "2026-10-07",
                    "session": "ASIAN_LONDON", "expected_evaluations": 0, "recorded_evaluations": 0,
                    "status": "COMPLETE", "scope_statuses": [{"symbol": "GBPUSD", "route": "DEMO_ORDER"}]}
    try:
        render_session_summary(send_summary)
    except ValueError as exc:
        assert "route" in str(exc)
    else:
        raise AssertionError("a DEMO_ORDER route must never render in a status report")


def test_lsmc_alert_carries_status_stamp():
    alert = {"symbol": "EURUSD", "to_state": "NEAR_POI", "alert_level": "WATCH", "strategy_id": "ST_LARGE_SMC_V1",
             "strategy_version": "1.1.0", "reference_id": "ref-1", "payload": {}}
    text = tg.format_alert(alert)
    assert ("STATUS: UNVERIFIED (ENTRY_LOGIC_NOT_VERIFIED; detection=LOGIC_VERIFIED) "
            "· REPORT ONLY — NOT AN ENTRY") in text
    unknown = tg.format_alert({**alert, "symbol": "AUDUSD"})
    assert "STATUS: UNVERIFIED (REGISTRY_ENTRY_MISSING)" in unknown
