"""Large-SMC crypto watch (BTCUSD/ETHUSD) session summaries (owner mission 2026-10-10).

The crypto watch journals each evaluation to its own window journal and emits one summary per window
through the shared FX summary delivery path (`_process_due_summary`): opportunities sent plus
per-reason rejection counts. An empty window still gets a zero-count summary. The FX summary never
counts crypto, so a crypto rejection inside an FX window is counted once, in the crypto summary only.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import canonical_fx_delivery as cfd  # noqa: E402
import live_candles_smoke as lcs  # noqa: E402
from test_canonical_fx_delivery import events, sender  # noqa: E402

UTC = dt.timezone.utc
SAT = dt.date(2026, 10, 10)                    # Saturday
WED = dt.date(2026, 10, 7)                     # Wednesday


def at(day, hh, mm):
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=UTC)


def record(journal, when, session, symbol, state, reasons=(), deliveries=()):
    cfd.record_lsmc_crypto_evaluation(str(journal), now=when, session=session, symbol=symbol, state=state,
                                      reason_codes=reasons, deliveries=deliveries)


def due(journal, now, send, session):
    return lcs.lsmc_crypto_summary_lines(now, str(journal), session, sender=send)


def test_weekend_window_counts_opportunities_sent_and_rejections_per_reason(tmp_path):
    journal = tmp_path / "j"
    send, calls = sender(tmp_path)
    assert due(journal, at(SAT, 20, 0), send, cfd.LSMC_CRYPTO_WEEKEND) == []          # starts catch-up; not due
    W = cfd.LSMC_CRYPTO_WEEKEND
    record(journal, at(SAT, 20, 50), W, "BTCUSD", "IDLE", ["NO_BIAS"])
    record(journal, at(SAT, 21, 5), W, "ETHUSD", "IDLE", ["NO_VALID_POI"])
    record(journal, at(SAT, 21, 20), W, "ETHUSD", "IDLE", ["NO_BIAS"])
    record(journal, at(SAT, 22, 0), W, "BTCUSD", "DATA_ERROR", ["M5_DATA_STALE"])
    record(journal, at(SAT, 22, 30), W, "BTCUSD", "OPPORTUNITY", ["D30_BADGE_ECONOMICS_NOT_EVALUATED"],
           [{"to_state": "OPPORTUNITY", "status": "SENT", "reference_id": "opp-1"}])
    record(journal, at(SAT, 22, 35), W, "BTCUSD", "OPPORTUNITY", [],
           [{"to_state": "OPPORTUNITY", "status": "SENT", "reference_id": "opp-1"}])          # same alert: once
    record(journal, at(SAT, 23, 20), W, "BTCUSD", "IDLE", ["NO_BIAS"])                       # after window end

    assert due(journal, at(SAT, 23, 40), send, W) == []                                # window end + grace not reached
    lines = due(journal, at(SAT, 23, 50), send, W)
    assert lines == [f"LSMC_CRYPTO_SUMMARY {SAT} {W} status=COMPLETE delivery=sent"]
    summary = cfd.build_lsmc_crypto_summary(str(journal), session_date=SAT, session=W,
                                            window=lcs.lsmc_weekend_window(SAT), sender=send)
    assert summary["evaluations"] == 6 and summary["opportunities_sent"] == 1
    assert summary["rejection_counts"] == {"M5_DATA_STALE": 1, "NO_BIAS": 2, "NO_VALID_POI": 1}
    assert summary["instruments"] == ["BTCUSD", "ETHUSD"] and summary["execution_authorized"] is False
    message = calls[-1][1]
    assert "Opportunities sent: 1" in message and "- NO_BIAS: 2" in message and "- M5_DATA_STALE: 1" in message
    assert due(journal, at(SAT, 23, 59), send, W) == []                                # sent once, never resent
    assert len(calls) == 1


def test_empty_window_still_sends_a_zero_count_summary(tmp_path):
    journal = tmp_path / "j"
    send, calls = sender(tmp_path)
    W = cfd.LSMC_CRYPTO_WEEKEND
    assert due(journal, at(SAT, 20, 0), send, W) == []
    lines = due(journal, at(SAT, 23, 50), send, W)
    assert lines == [f"LSMC_CRYPTO_SUMMARY {SAT} {W} status=EMPTY_WINDOW delivery=sent"]
    message = calls[-1][1]
    assert "Evaluations: 0" in message and "Opportunities sent: 0" in message and "Rejections by reason:\n- none" in message
    # A weekday has no weekend window: nothing due, nothing invented.
    assert lcs.lsmc_weekend_window(SAT + dt.timedelta(days=2)) is None


def test_crypto_rejection_inside_an_fx_window_is_counted_once_in_the_crypto_summary_only(tmp_path):
    journal = tmp_path / "j"
    send, calls = sender(tmp_path)
    D = cfd.LSMC_CRYPTO_DAY
    assert due(journal, at(WED, 0, 5), send, D) == []
    assert cfd.process_due_session_summaries(at(WED, 0, 5), journal=str(journal), sender=send) == []
    # 08:00 UTC lies inside the FX ASIAN_LONDON trade window (07:00-11:00).
    fx_window = cfd.session_windows_utc(WED)["ASIAN_LONDON"]["trade"]
    inside = at(WED, 8, 0)
    assert fx_window[0] <= inside < fx_window[1]
    record(journal, inside, D, "BTCUSD", "IDLE", ["NO_BIAS"])

    # FX summary for that window: crypto never appears (FX instruments only, no crypto events).
    fx = cfd.build_session_summary(str(journal), session_date=WED, session="ASIAN_LONDON", sender=send)
    assert "BTCUSD" not in fx["expected_instruments"] and fx["recorded_evaluations"] == 0
    assert all(item["symbol"] != "BTCUSD" for item in fx["per_instrument"])
    assert not any(e.get("event_type") == "LSMC_EVALUATION" for e in events(journal, WED, "ASIAN_LONDON"))

    # Crypto summary for the UTC day counts it exactly once.
    crypto = cfd.build_lsmc_crypto_summary(str(journal), session_date=WED, session=D,
                                           window=lcs.lsmc_crypto_day_window(WED), sender=send)
    assert crypto["evaluations"] == 1 and crypto["rejection_counts"] == {"NO_BIAS": 1}
    lines = due(journal, at(WED + dt.timedelta(days=1), 0, 40), send, D)
    assert lines == [f"LSMC_CRYPTO_SUMMARY {WED} {D} status=COMPLETE delivery=sent"]
    assert sum("- NO_BIAS: 1" in message for _, message in calls) == 1


def test_run_lsmc_journals_each_crypto_evaluation_into_its_window(tmp_path):
    class Feed:
        symbols = {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"}

        def fetch_bundle(self, symbol, req):
            raise RuntimeError("no data in test")

    journal = str(tmp_path / "j")
    lcs.run_lsmc(lambda s, tf, n: [], at(SAT, 21, 0), journal, crypto_feed=Feed(), notify=False, fx=False,
                 window="WEEKEND")
    rows = [e for e in events(journal, SAT, cfd.LSMC_CRYPTO_WEEKEND) if e.get("event_type") == "LSMC_EVALUATION"]
    assert [(r["symbol"], r["state"], r["reason_codes"]) for r in rows] == [
        ("BTCUSD", "DATA_ERROR", ["RuntimeError"]), ("ETHUSD", "DATA_ERROR", ["RuntimeError"])]


def test_crypto_symbol_set_matches_the_lsmc_contract():
    from large_smc_watch.contract import CRYPTO_SYMBOLS
    assert tuple(cfd.LSMC_CRYPTO_SYMBOLS) == tuple(CRYPTO_SYMBOLS) == lcs.LSMC_CRYPTO_SYMBOLS


def test_each_crypto_rejection_appears_in_exactly_one_summary_across_the_utc_day(tmp_path):
    """Whole UTC day: both FX session summaries plus the crypto day summary. FX summaries are
    FX-only (canonical_fx_delivery.build_session_summary keeps V1_FX_SYMBOLS rows only), so every
    crypto rejection -- inside either FX window or outside both -- is counted once, by crypto."""
    import json
    journal = tmp_path / "j"
    send, calls = sender(tmp_path)
    D = cfd.LSMC_CRYPTO_DAY
    assert due(journal, at(WED, 0, 5), send, D) == []
    assert cfd.process_due_session_summaries(at(WED, 0, 5), journal=str(journal), sender=send) == []
    rejections = [(at(WED, 8, 0), "BTCUSD", "NO_BIAS"),            # inside ASIAN_LONDON trade window
                  (at(WED, 13, 0), "ETHUSD", "NO_VALID_POI"),      # inside LONDON_NEWYORK trade window
                  (at(WED, 20, 0), "BTCUSD", "M5_DATA_STALE")]     # outside both FX windows
    for when, symbol, reason in rejections:
        record(journal, when, D, symbol, "IDLE" if reason != "M5_DATA_STALE" else "STALE", [reason])

    fx_summaries = [cfd.build_session_summary(str(journal), session_date=WED, session=s, sender=send)
                    for s in cfd.V1_CYCLES]
    crypto = cfd.build_lsmc_crypto_summary(str(journal), session_date=WED, session=D,
                                           window=lcs.lsmc_crypto_day_window(WED), sender=send)
    for when, symbol, reason in rejections:
        in_fx = sum(symbol in json.dumps(fx) for fx in fx_summaries)
        in_crypto = crypto["rejection_counts"].get(reason, 0)
        assert (in_fx, in_crypto) == (0, 1), (when, symbol, reason)
    assert crypto["evaluations"] == len(rejections) == sum(crypto["rejection_counts"].values())

    # Delivered messages for the whole day: FX summaries never name a crypto symbol.
    later = at(WED + dt.timedelta(days=1), 0, 40)
    cfd.process_due_session_summaries(later, journal=str(journal), sender=send)
    due(journal, later, send, D)
    fx_messages = [m for _, m in calls if m.startswith("Canonical FX session summary")]
    crypto_messages = [m for _, m in calls if m.startswith("Large-SMC crypto watch summary")]
    assert len(fx_messages) == 2 and len(crypto_messages) == 1
    assert not any(s in m for m in fx_messages for s in cfd.LSMC_CRYPTO_SYMBOLS)


def _fail_mt5(monkeypatch, failure):
    from contextlib import contextmanager, nullcontext

    @contextmanager
    def busy():
        raise lcs.Mt5Busy("held")
        yield

    monkeypatch.setattr(lcs, "single_instance", lambda name: nullcontext())
    monkeypatch.setattr(lcs, "import_mt5", lambda: None if failure == "MT5_PACKAGE_MISSING" else
                        type("MT5", (), {"shutdown": staticmethod(lambda: None)})())
    monkeypatch.setattr(lcs, "mt5_access_lock", busy if failure == "MT5_BUSY" else nullcontext)
    monkeypatch.setattr(lcs, "mt5_initialize", lambda *a: (failure != "MT5_INITIALIZE_FAILED", "init"))
    monkeypatch.setattr(lcs, "require_demo_account", lambda *a: (failure != "DEMO_ACCOUNT_REQUIRED", "demo"))


@pytest.mark.parametrize("failure", ["MT5_PACKAGE_MISSING", "MT5_INITIALIZE_FAILED", "DEMO_ACCOUNT_REQUIRED",
                                     "MT5_BUSY"])
@pytest.mark.parametrize("mode,session,now", [("lsmc", cfd.LSMC_CRYPTO_DAY, at(WED, 0, 40)),
                                              ("lsmc-weekend", cfd.LSMC_CRYPTO_WEEKEND, at(SAT, 21, 0))])
def test_mt5_failure_still_journals_crypto_data_error_and_processes_due_summaries(monkeypatch, mode, session, now,
                                                                                  failure):
    recorded, processed, logged = [], [], []
    _fail_mt5(monkeypatch, failure)
    monkeypatch.setattr(lcs, "utcnow", lambda: now)
    monkeypatch.setattr(lcs, "record_lsmc_crypto_evaluation",
                        lambda journal, **kw: recorded.append((kw["session"], kw["symbol"], kw["state"],
                                                               kw["reason_codes"])))
    monkeypatch.setattr(lcs, "lsmc_crypto_summary_lines",
                        lambda run_now, journal, s, sender=None: processed.append(s) or [f"SUMMARY {s}"])
    monkeypatch.setattr(lcs, "log_line", lambda name, message: logged.append(message))

    lcs.main(["--mode", mode])
    assert recorded == [(session, s, "DATA_ERROR", [failure]) for s in lcs.LSMC_CRYPTO_SYMBOLS]
    assert processed == [session] and f"SUMMARY {session}" in logged
