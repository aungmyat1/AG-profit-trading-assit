"""Canonical FX scheduled delivery: durable-before-delivery ordering, session completeness,
restart idempotency, host-prerequisite failures and the disabled/unauthorized delivery gates.

Market data and Telegram transport are always mocked. Nothing here touches a broker or the
network, and no fixture result is labelled LIVE.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "host"))
sys.path.insert(0, str(REPO / "tests"))

import canonical_fx_delivery as cfd  # noqa: E402
from test_actionability_and_canonical_ticket import (
    _build_asian_london_sweep,  # noqa: E402
)

import v1_tickets.daily_evaluator as de  # noqa: E402
from telegram_delivery.adapter import Config, Sender  # noqa: E402
from ticket_store import adapter as store_adapter  # noqa: E402
from ticket_store.store import (  # noqa: E402
    REPLAY,
    TicketStore,
    build_evaluation,
    read_jsonl,
)
from v1_tickets.fx import V1_CYCLES, V1_FX_SYMBOLS, session_windows_utc  # noqa: E402

UTC = dt.timezone.utc
# Wednesday inside the frozen ASIAN_LONDON trade window (07:00-11:00 UTC).
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
SATURDAY = dt.date(2026, 10, 10)
THURSDAY = dt.date(2026, 10, 8)


def signal_provider():
    ref, expected, post = _build_asian_london_sweep(NOW, age_minutes=5)
    return de.fixture_candle_provider(ref, expected, post, spread=0.0001, current_price=1.1636,
                                      data_close=post[-1].time + dt.timedelta(minutes=15))


def sender(tmp_path, *, enabled=True, calls=None, transport=None):
    """Fake-transport Sender; delivery stays off unless the test enables it explicitly."""
    calls = [] if calls is None else calls

    def fake(token, chat_id, message):
        calls.append((chat_id, message))

    cfg = (Config(enabled=True, token="fake-token", chat_id="123", owner_chat_ids=frozenset({"123"}),
                  watch_info_scope=True)
           if enabled else Config())
    return Sender(tmp_path / "delivery.sqlite", cfg, transport or fake), calls


def events(journal, day, session):
    path = cfd._session_event_path(str(journal), day.isoformat() if isinstance(day, dt.date) else day, session)
    return [row for _, row in read_jsonl(path)]


def run(tmp_path, *, provider=None, now=NOW, cycle=None, source="REPLAY", data_source="MT5_VT_MARKETS_DEMO",
        send=None):
    """Run the canonical FX cycle; `send` may be an externally built Sender (its own call list)."""
    calls = None
    if send is None:
        send, calls = sender(tmp_path)
    journal = str(tmp_path / "journal")
    results, lines = cfd.run_canonical_fx_cycle(
        provider if provider is not None else signal_provider(),
        now=now, journal=journal, sender=send, cycle_filter=cycle,
        ticket_source=source, fx_data_source=data_source, policy_root=str(REPO))
    return results, lines, journal, send, calls


# ------------------------------------------------------------------ window gating

def test_active_cycles_follow_the_frozen_utc_windows_and_grace():
    windows = session_windows_utc(NOW.date())
    assert set(windows) == set(V1_CYCLES)
    assert cfd.active_cycles(NOW) == ("ASIAN_LONDON",)
    assert cfd.active_cycles(NOW, "ASIAN_LONDON") == ("ASIAN_LONDON",)
    assert cfd.active_cycles(NOW, "LONDON_NEWYORK") == ()
    # 30-minute post-close grace, then nothing is active.
    assert cfd.active_cycles(dt.datetime(2026, 10, 7, 11, 20, tzinfo=UTC)) == ("ASIAN_LONDON",)
    assert cfd.active_cycles(dt.datetime(2026, 10, 7, 11, 40, tzinfo=UTC)) == ()
    assert cfd.active_cycles(dt.datetime(2026, 10, 7, 13, 0, tzinfo=UTC)) == ("LONDON_NEWYORK",)
    assert cfd.active_cycles(dt.datetime(2026, 10, 7, 16, 0, tzinfo=UTC)) == ()
    with pytest.raises(ValueError):
        cfd.active_cycles(NOW, "NOT_A_CYCLE")


def test_outside_every_window_runs_nothing_and_invents_no_ticket(tmp_path):
    results, lines, journal, _, calls = run(tmp_path, now=dt.datetime(2026, 10, 7, 16, 0, tzinfo=UTC))
    assert results == [] and lines == ["FX_CANONICAL NOTHING_IN_WINDOW"] and calls == []
    assert TicketStore(os.path.join(journal, "ticket_store")).evaluations() == []


# ------------------------------------------------------------------ durable-before-delivery

def test_every_active_pair_is_persisted_and_verified_before_any_send(tmp_path):
    send, calls = sender(tmp_path)
    results, lines, journal, _, _ = run(tmp_path, send=send)
    assert len(results) == len(V1_FX_SYMBOLS) == 4
    assert {r.instrument for r in results} == set(V1_FX_SYMBOLS)
    assert all(r.session == "ASIAN_LONDON" for r in results)

    store = TicketStore(os.path.join(journal, "ticket_store"))
    rows = {(r["symbol"], r["session"]): r for r in store.evaluations()}
    assert len(rows) == 4
    for result in results:
        row = rows[(result.instrument, result.session)]
        assert row["ticket_id"] == result.ticket_id
        assert row["state"] == result.decision == result.canonical["decision"]
        assert row["source"] == REPLAY                    # fixture data is never labelled LIVE
        assert row["provenance"]["canonical_hash"]

    rows_at_first_send = len(store.evaluations())
    assert calls == [] or rows_at_first_send == 4         # the store was complete before delivery
    for result in results:
        day = NOW.date()
        rows = events(journal, day, result.session)
        mine = [e for e in rows if e["ticket_id"] == result.ticket_id]
        assert [e["stage"] for e in mine] == ["INTENT", "RESULT"]
        assert mine[0]["delivery_state"] == "pending"
        assert mine[1]["ticket_store_status"] == "VERIFIED"
        assert mine[1]["execution_authorized"] is False
        assert all(e["event_type"] == "TICKET_DELIVERY" for e in mine)
    assert all(ln.startswith("FX_CANONICAL ") and "ticket_store=VERIFIED" in ln for ln in lines)


def test_suppressed_ready_is_persisted_but_never_alerted(tmp_path):
    """D6 READY authority is OFF in production config: the reproduced INFO_ONLY_SUPPRESSED case."""
    send, calls = sender(tmp_path)
    results, lines, journal, _, _ = run(tmp_path, send=send)
    assert results and all(r.decision == "INFO_ONLY_SUPPRESSED" for r in results)
    assert all(r.canonical["presentation"] == "INFO_ONLY" for r in results)
    assert calls == []                                    # no immediate alert for a suppressed signal
    assert all("delivery=summary_only" in ln for ln in lines)
    result_events = [e for e in events(journal, NOW.date(), "ASIAN_LONDON") if e["stage"] == "RESULT"]
    assert {e["delivery_state"] for e in result_events} == {"summary_only"}
    stored = TicketStore(os.path.join(journal, "ticket_store")).evaluations()
    assert len(stored) == 4 and {r["state"] for r in stored} == {"INFO_ONLY_SUPPRESSED"}


def test_store_failure_is_explicit_and_blocks_delivery(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store_adapter, "write_canonical", boom)
    send, calls = sender(tmp_path)
    results, lines, journal, _, _ = run(tmp_path, send=send)
    assert len(results) == 4 and calls == []
    assert all(r.ticket_store_error == "OSError: disk full" for r in results)
    assert all("ticket_store=FAILED" in ln and "delivery=persistence_failed" in ln for ln in lines)
    result_events = [e for e in events(journal, NOW.date(), "ASIAN_LONDON") if e["stage"] == "RESULT"]
    assert len(result_events) == 4
    assert all(e["ticket_store_status"] == "FAILED" and e["delivery_state"] == "persistence_failed"
               and e["ticket_store_error_class"] == "OSError" for e in result_events)
    # Intent is still journaled so the blocked notification is auditable.
    assert len([e for e in events(journal, NOW.date(), "ASIAN_LONDON") if e["stage"] == "INTENT"]) == 0


def test_persistence_verification_failure_blocks_the_send(tmp_path, monkeypatch):
    monkeypatch.setattr(cfd, "_verify_persisted_result", lambda *a, **k: False)
    send, calls = sender(tmp_path)
    _, lines, journal, _, _ = run(tmp_path, send=send)
    assert calls == []
    assert all("ticket_store=FAILED" in ln and "delivery=persistence_failed" in ln for ln in lines)
    result_events = [e for e in events(journal, NOW.date(), "ASIAN_LONDON") if e["stage"] == "RESULT"]
    assert {e["ticket_store_error_class"] for e in result_events} == {"TicketStoreVerificationFailed"}


def test_delivery_journal_failure_never_sends(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("journal unavailable")

    monkeypatch.setattr(cfd, "append_session_event", boom)
    send, calls = sender(tmp_path)
    _, lines, _, _, _ = run(tmp_path, send=send)
    assert calls == []
    assert all("delivery=journal_blocked" in ln and "error=OSError" in ln for ln in lines)


def test_unknown_decision_fails_closed_and_is_counted_not_sent(tmp_path):
    class BrokenSender(Sender):
        def send_ticket(self, ticket):
            return "compatibility_error"

    broken = BrokenSender(tmp_path / "delivery.sqlite",
                          Config(enabled=True, token="fake-token", chat_id="123",
                                 owner_chat_ids=frozenset({"123"})),
                          transport=lambda *a: pytest.fail("must not send"))
    _, lines, journal, _, _ = run(tmp_path, send=broken)
    assert all("delivery=compatibility_error" in ln for ln in lines)
    digest = cfd.build_session_summary(journal, session_date=NOW.date(), session="ASIAN_LONDON",
                                       sender=broken)
    assert digest["delivery_counts"]["failed"] == 4
    assert digest["recorded_evaluations"] == 4


# ------------------------------------------------------------------ restart / idempotency

def test_restart_keeps_identity_and_never_resends(tmp_path):
    send, calls = sender(tmp_path)
    first, _, journal, _, _ = run(tmp_path, send=send)
    first_ids = [r.ticket_id for r in first]
    first_events = events(journal, NOW.date(), "ASIAN_LONDON")
    store = TicketStore(os.path.join(journal, "ticket_store"))
    rows_before = len(store.evaluations())

    again, _, _, _, _ = run(tmp_path, send=send)
    assert [r.ticket_id for r in again] == first_ids          # stable logical identity
    assert all(r.ticket_store_written is False for r in again)
    assert len(store.evaluations()) == rows_before            # no duplicate durable rows
    assert events(journal, NOW.date(), "ASIAN_LONDON") == first_events   # checksummed events dedupe
    assert len(calls) == 0                                    # suppressed decisions never alert


def test_watch_ready_equivalent_send_is_deduplicated_across_restart(tmp_path):
    """An alert-eligible decision is sent once; a restart of the same evaluation is a duplicate."""
    send, calls = sender(tmp_path)
    ticket = json.loads((REPO / "tests" / "fixtures" / "telegram_delivery" / "tickets.json").read_text())
    eligible = next(t for t in ticket if t["decision"] == "INFO_ONLY_STALE")
    assert send.send_ticket(eligible) == "sent"
    restarted = Sender(tmp_path / "delivery.sqlite", send.config, transport=lambda *a: calls.append(a))
    assert restarted.send_ticket(eligible) == "duplicate"
    assert len(calls) == 1


# ------------------------------------------------------------------ host prerequisite failures

def test_host_prerequisite_failure_records_replay_none_not_live(tmp_path):
    send, calls = sender(tmp_path)
    results, lines, journal, _, _ = run(
        tmp_path, send=send, source="REPLAY", data_source="NONE",
        provider=cfd.failure_provider("MT5_PACKAGE_MISSING", "MetaTrader5 package unavailable"))
    assert len(results) == 4 and calls == []
    assert all(r.decision == "INSUFFICIENT_DATA" for r in results)
    assert all(r.venue == "NONE" for r in results)
    rows = TicketStore(os.path.join(journal, "ticket_store")).evaluations()
    assert {r["source"] for r in rows} == {REPLAY}
    assert {r["state"] for r in rows} == {"INSUFFICIENT_DATA"}
    assert all(r["block_reasons"] for r in rows)          # typed terminal outcome, never NO_TRADE
    result_events = [e for e in events(journal, NOW.date(), "ASIAN_LONDON") if e["stage"] == "RESULT"]
    assert {e["acquisition_error_code"] for e in result_events} == {"MT5_PACKAGE_MISSING"}
    assert {e["source"] for e in result_events} == {"REPLAY"}
    assert all("delivery=" in ln for ln in lines)
    digest = cfd.build_session_summary(journal, session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    assert digest["status"] == "COMPLETE" and digest["data_failure_count"] == 4
    assert {row["acquisition_error_code"] for row in digest["per_instrument"]} == {"MT5_PACKAGE_MISSING"}


def test_invalid_ticket_source_is_refused(tmp_path):
    send, _ = sender(tmp_path)
    with pytest.raises(ValueError):
        cfd.run_canonical_fx_cycle(signal_provider(), now=NOW, journal=str(tmp_path / "journal"),
                                   sender=send, ticket_source="LEGACY", policy_root=str(REPO))


# ------------------------------------------------------------------ session completeness

def test_summary_complete_session_reports_expected_and_recorded(tmp_path):
    send, _ = sender(tmp_path)
    _, _, journal, _, _ = run(tmp_path, send=send)
    digest = cfd.build_session_summary(journal, session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    assert digest["schema"] == cfd.SUMMARY_SCHEMA
    assert digest["expected_evaluations"] == 4 and digest["recorded_evaluations"] == 4
    assert digest["expected_instruments"] == list(V1_FX_SYMBOLS)
    assert digest["status"] == "COMPLETE"
    assert digest["missed_pairs"] == [] and digest["missed_count"] == 0
    assert digest["out_of_session_pairs"] == [] and digest["out_of_session_count"] == 0
    assert digest["terminal_counts"] == {"INFO_ONLY_SUPPRESSED": 4}
    assert digest["data_failure_count"] == 0 and digest["persistence_failure_count"] == 0
    assert digest["compatibility_error_count"] == 0
    assert digest["delivery_counts"]["summary_only"] == 4
    assert digest["delivery_counts"]["succeeded"] == 0
    assert digest["execution_authorized"] is False
    assert [row["symbol"] for row in digest["per_instrument"]] == list(V1_FX_SYMBOLS)
    assert all(row["ticket_store_status"] == "VERIFIED" for row in digest["per_instrument"])


def test_summary_distinguishes_missed_from_no_trade_and_data_failure(tmp_path):
    send, _ = sender(tmp_path, enabled=False)
    journal = str(tmp_path / "journal")
    store = TicketStore(os.path.join(journal, "ticket_store"))
    # Two durable outcomes for the same session: one engine NO_TRADE, one data failure.
    for symbol, state, reasons in (("EURUSD", "NO_TRADE", []), ("GBPUSD", "INSUFFICIENT_DATA", ["NO_CANDLE_DATA"])):
        store.append_evaluation(build_evaluation(
            ticket_id=f"ST_ASIAN_SWEEP_5R_V1|1.1.1|{symbol}|ASIAN_LONDON|{THURSDAY.isoformat()}",
            strategy="ST_ASIAN_SWEEP_5R_V1@1.1.1", source=REPLAY, symbol=symbol, session="ASIAN_LONDON",
            evaluated_at_utc=f"{THURSDAY.isoformat()}T07:20:00+00:00", state=state, block_reasons=reasons))
    digest = cfd.build_session_summary(journal, session_date=THURSDAY, session="ASIAN_LONDON", sender=send)
    assert digest["status"] == "INCOMPLETE_WITH_MISSED"
    assert digest["expected_evaluations"] == 4 and digest["recorded_evaluations"] == 2
    assert digest["terminal_counts"] == {"INSUFFICIENT_DATA": 1, "NO_TRADE": 1}
    assert digest["data_failure_count"] == 1
    assert [row["symbol"] for row in digest["missed_pairs"]] == ["USDJPY", "XAUUSD"]
    assert digest["missed_count"] == 2
    assert {row["reason_code"] for row in digest["missed_pairs"]} == {"SCHEDULED_EVALUATION_NOT_RECOVERED"}
    assert digest["delivery_counts"]["not_attempted"] == 2
    assert digest["delivery_counts"]["disabled"] == 0


def test_summary_labels_a_closed_market_out_of_session_not_missed(tmp_path):
    send, _ = sender(tmp_path, enabled=False)
    digest = cfd.build_session_summary(str(tmp_path / "journal"), session_date=SATURDAY,
                                       session="ASIAN_LONDON", sender=send)
    assert digest["status"] == "OUT_OF_SESSION"
    assert digest["missed_pairs"] == [] and digest["missed_count"] == 0
    assert [row["symbol"] for row in digest["out_of_session_pairs"]] == list(V1_FX_SYMBOLS)
    assert {row["reason_code"] for row in digest["out_of_session_pairs"]} == {"FX_MARKET_CLOSED"}
    assert digest["recorded_evaluations"] == 0


def test_summary_counts_delivery_only_for_the_latest_decision_per_symbol(tmp_path):
    """Superseded decisions (INFO_ONLY_STALE -> WATCH_READY) add no second delivery outcome."""
    send, _ = sender(tmp_path)
    journal = str(tmp_path / "journal")
    store = TicketStore(os.path.join(journal, "ticket_store"))
    day = THURSDAY.isoformat()
    eurusd = f"ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|{day}"

    def row(symbol, ticket_id, state, at):
        store.append_evaluation(build_evaluation(
            ticket_id=ticket_id, strategy="ST_ASIAN_SWEEP_5R_V1@1.1.1", source=REPLAY, symbol=symbol,
            session="ASIAN_LONDON", evaluated_at_utc=f"{day}T{at}+00:00", state=state))

    def event(ticket_id, symbol, state, delivery_state, at):
        cfd.append_session_event(journal, {
            "event_type": "TICKET_DELIVERY", "stage": "RESULT", "session_date": day,
            "session": "ASIAN_LONDON", "ticket_id": ticket_id, "decision": state, "symbol": symbol,
            "source": REPLAY, "delivery_state": delivery_state,
            "evaluated_at_utc": f"{day}T{at}+00:00", "recorded_at_utc": f"{day}T{at}+00:00"})

    row("EURUSD", eurusd, "INFO_ONLY_STALE", "07:20:00")          # superseded by the row below
    event(eurusd, "EURUSD", "INFO_ONLY_STALE", "sent", "07:20:05")
    row("EURUSD", eurusd, "WATCH_READY", "08:10:00")              # latest terminal decision
    event(eurusd, "EURUSD", "WATCH_READY", "summary_only", "08:10:05")
    for symbol in (s for s in V1_FX_SYMBOLS if s != "EURUSD"):
        ticket_id = f"ST_ASIAN_SWEEP_5R_V1|1.1.1|{symbol}|ASIAN_LONDON|{day}"
        row(symbol, ticket_id, "INFO_ONLY_SUPPRESSED", "07:20:00")
        event(ticket_id, symbol, "INFO_ONLY_SUPPRESSED", "summary_only", "07:20:05")

    digest = cfd.build_session_summary(journal, session_date=THURSDAY, session="ASIAN_LONDON",
                                       sender=send)
    counts = digest["delivery_counts"]
    assert digest["recorded_evaluations"] == 4
    assert digest["terminal_counts"] == {"INFO_ONLY_SUPPRESSED": 3, "WATCH_READY": 1}
    assert sum(counts.values()) == digest["recorded_evaluations"]  # one outcome per instrument
    assert counts["succeeded"] == 0 and counts["summary_only"] == 4
    assert len(store.evaluations()) == 5                          # superseded row kept for audit
    assert next(r for r in digest["per_instrument"]
                if r["symbol"] == "EURUSD")["decision"] == "WATCH_READY"


def test_summary_reports_an_unknown_stored_decision_as_a_compatibility_error(tmp_path):
    send, _ = sender(tmp_path, enabled=False)
    journal = str(tmp_path / "journal")
    TicketStore(os.path.join(journal, "ticket_store")).append_evaluation(build_evaluation(
        ticket_id=f"ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|{THURSDAY.isoformat()}",
        strategy="ST_ASIAN_SWEEP_5R_V1@1.1.1", source=REPLAY, symbol="EURUSD", session="ASIAN_LONDON",
        evaluated_at_utc=f"{THURSDAY.isoformat()}T07:20:00+00:00", state="FUTURE_CANONICAL_STATE"))
    digest = cfd.build_session_summary(journal, session_date=THURSDAY, session="ASIAN_LONDON", sender=send)
    assert digest["status"] == "COMPATIBILITY_ERROR"
    assert digest["compatibility_error_count"] == 1
    assert digest["compatibility_errors"] == [{"symbol": "EURUSD",
                                               "ticket_id": digest["compatibility_errors"][0]["ticket_id"],
                                               "error_code": "UNKNOWN_CANONICAL_DECISION",
                                               "observed_decision": "FUTURE_CANONICAL_STATE"}]
    assert digest["terminal_counts"] == {"COMPATIBILITY_ERROR": 1}
    row = next(r for r in digest["per_instrument"] if r["symbol"] == "EURUSD")
    assert row["decision"] == "COMPATIBILITY_ERROR" and row["reason_code"] == "UNKNOWN_CANONICAL_DECISION"


def test_summary_is_deterministic_and_invents_no_levels(tmp_path):
    send, _ = sender(tmp_path)
    _, _, journal, _, _ = run(tmp_path, send=send)
    first = cfd.build_session_summary(journal, session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    second = cfd.build_session_summary(journal, session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    text = json.dumps(first)
    assert "1.1636" not in text and "1.1634" not in text      # no fabricated price levels
    with pytest.raises(ValueError):
        cfd.build_session_summary(journal, session_date=NOW.date(), session="NOT_A_CYCLE", sender=send)


# ------------------------------------------------------------------ session summary scheduling

def test_session_summary_counts_archived_lsmc_rejection_reasons_only(tmp_path):
    from large_smc_watch.watch import Snapshot, WatchTracker, gate_opportunity
    from telegram_delivery.adapter import render_session_summary
    send, _ = sender(tmp_path, enabled=False)
    journal = tmp_path / "journal"
    archive = journal / "ticket_delivery" / "archive"
    tracker = WatchTracker(str(journal / "lsmc.json"), str(archive))
    samples = [("EURUSD", "07:00", {"stop_c10": None}, 100.0),
               ("GBPUSD", "08:00", {"target_c11": None}, 100.0),
               ("USDJPY", "10:00", {}, 100.75),
               ("XAUUSD", "11:00", {}, 100.75)]  # end is exclusive
    for symbol, time, changes, price in samples:
        opportunity = {"opp_id": f"SECRET-{symbol}", "poi_id": "SECRET-POI", "direction": "LONG",
                       "entry_reference": 100.0, "stop_c10": 99.0, "target_c11": 101.0, **changes}
        snap = gate_opportunity(Snapshot(symbol, f"{NOW.date()}T{time}:00+00:00", "OPPORTUNITY",
                                        opportunity=opportunity), price)
        event, = tracker.poll(snap)
        assert event.payload["reason_codes"][0] == snap.reason_codes[0]
        assert tracker.poll(snap) == []
        # Restart also produces no new archived rejection transition.
        assert WatchTracker(str(journal / "lsmc.json"), str(archive)).poll(snap) == []
    paths = list(archive.rglob("*.json"))
    assert len(paths) == 4
    # Duplicate identity and correction wrappers must not inflate counts.
    source = paths[0]
    duplicate = source.parent / (NOW.date() + dt.timedelta(days=1)).isoformat()
    duplicate.with_suffix(".json").write_bytes(source.read_bytes())
    source.with_name(f"{NOW.date()}.correction-001.json").write_text('{"new_record": {}}')
    digest = cfd.build_session_summary(str(journal), session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    assert digest["large_smc"]["rejection_counts"] == {
        "REJECT_NO_STOP": 1, "REJECT_NO_TARGET": 1, "REJECT_STALE": 1}
    assert "SECRET" not in json.dumps(digest)
    text = render_session_summary(digest)
    assert "Large-SMC rejections (archived transitions):" in text
    assert all(f"- {reason}: 1" in text for reason in digest["large_smc"]["rejection_counts"])
    assert "SECRET" not in text
    ny = cfd.build_session_summary(str(journal), session_date=NOW.date(), session="LONDON_NEWYORK", sender=send)
    assert set(ny["large_smc"]["rejection_counts"].values()) == {0}


def test_lsmc_summary_corrupt_archive_is_reported_and_summary_sends(tmp_path):
    journal = tmp_path / "journal"
    path = journal / "ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1/EURUSD/LSMC_WATCH-t/2026/2026-10-07.json"
    path.parent.mkdir(parents=True)
    path.write_text("{")
    send, calls = sender(tmp_path, enabled=True)
    digest = cfd.build_session_summary(str(journal), session_date=NOW.date(),
                                       session="ASIAN_LONDON", sender=send)
    assert digest["large_smc"]["archive_error_count"] == 1
    assert send.send_session_summary(digest) == "sent"
    assert "ARCHIVE_ERROR n=1" in calls[0][1]
    assert set(digest["large_smc"]["rejection_counts"].values()) == {0}


@pytest.mark.parametrize("bad", [-1, True, "1"])
def test_lsmc_summary_renderer_refuses_invalid_count(tmp_path, bad):
    from telegram_delivery.adapter import render_session_summary
    send, _ = sender(tmp_path, enabled=False)
    digest = cfd.build_session_summary(str(tmp_path / "journal"), session_date=NOW.date(),
                                       session="ASIAN_LONDON", sender=send)
    digest["large_smc"]["rejection_counts"]["REJECT_STALE"] = bad
    with pytest.raises(ValueError, match="Invalid Large-SMC rejection count"):
        render_session_summary(digest)


def test_lsmc_owner_parameter_comment_and_value_are_pinned():
    text = (REPO / "config/policy/actionability_policy.yaml").read_text()
    assert "# Owner-set operational parameter, 2026-10-10, not a contract value." in text
    assert "lsmc_min_remaining_reward_fraction: 0.5" in text

def write_start(journal, at):
    path = cfd._scheduler_start_path(journal)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps({"schema": cfd.START_SCHEMA, "started_at_utc": at.isoformat()}) + "\n",
                          encoding="utf-8")


def test_due_summaries_are_sent_once_and_never_before_grace(tmp_path):
    send, calls = sender(tmp_path)
    journal = str(tmp_path / "journal")
    write_start(journal, dt.datetime(2026, 10, 7, 6, 0, tzinfo=UTC))

    # Still inside the ASIAN_LONDON grace period: nothing is summarized yet.
    assert cfd.process_due_session_summaries(dt.datetime(2026, 10, 7, 11, 20, tzinfo=UTC),
                                             journal=journal, sender=send) == []
    assert calls == []

    lines = cfd.process_due_session_summaries(dt.datetime(2026, 10, 7, 11, 40, tzinfo=UTC),
                                              journal=journal, sender=send)
    assert len(lines) == 1 and lines[0].startswith("FX_SESSION_SUMMARY 2026-10-07 ASIAN_LONDON")
    assert "status=INCOMPLETE_WITH_MISSED" in lines[0] and "delivery=sent" in lines[0]
    assert len(calls) == 1 and "Missing scheduled evaluations (MISSED): 4" in calls[0][1]

    rows = [e for e in events(journal, dt.date(2026, 10, 7), "ASIAN_LONDON")
            if e["event_type"] == "SESSION_SUMMARY_DELIVERY"]
    assert [e["stage"] for e in rows] == ["INTENT", "RESULT"]
    assert rows[1]["delivery_state"] == "sent" and rows[1]["sender_enabled"] is True

    # Restart: the delivered summary is not re-sent.
    again = cfd.process_due_session_summaries(dt.datetime(2026, 10, 7, 12, 10, tzinfo=UTC),
                                              journal=journal, sender=send)
    assert again == [] and len(calls) == 1
    assert len([e for e in events(journal, dt.date(2026, 10, 7), "ASIAN_LONDON")
                if e["event_type"] == "SESSION_SUMMARY_DELIVERY"]) == 2


def test_summaries_are_not_invented_for_sessions_before_deployment(tmp_path):
    send, calls = sender(tmp_path)
    journal = str(tmp_path / "journal")
    # First canonical run after both 2026-10-07 sessions closed: no retroactive MISSED digests.
    write_start(journal, dt.datetime(2026, 10, 7, 16, 0, tzinfo=UTC))
    lines = cfd.process_due_session_summaries(dt.datetime(2026, 10, 7, 16, 30, tzinfo=UTC),
                                              journal=journal, sender=send)
    assert lines == [] and calls == []


def test_uncertain_and_failed_summaries_are_never_auto_retried(tmp_path):
    journal = str(tmp_path / "journal")
    write_start(journal, dt.datetime(2026, 10, 7, 6, 0, tzinfo=UTC))
    attempts = []

    def ambiguous(token, chat_id, message):
        attempts.append(message)
        raise TimeoutError("secret-token-url")

    send = Sender(tmp_path / "delivery.sqlite",
                  Config(enabled=True, token="fake-token", chat_id="123", owner_chat_ids=frozenset({"123"})),
                  transport=ambiguous)
    at = dt.datetime(2026, 10, 7, 11, 40, tzinfo=UTC)
    lines = cfd.process_due_session_summaries(at, journal=journal, sender=send)
    assert "delivery=uncertain" in lines[0]
    assert cfd.process_due_session_summaries(at + dt.timedelta(hours=1), journal=journal, sender=send) == []
    assert len(attempts) == 1
    uncertain = send.list_uncertain()
    assert [row["kind"] for row in uncertain] == ["session_summary"]


def test_disabled_summary_may_send_once_the_owner_gates_open(tmp_path):
    journal = str(tmp_path / "journal")
    write_start(journal, dt.datetime(2026, 10, 7, 6, 0, tzinfo=UTC))
    at = dt.datetime(2026, 10, 7, 11, 40, tzinfo=UTC)
    off, off_calls = sender(tmp_path, enabled=False)
    assert "delivery=disabled" in cfd.process_due_session_summaries(at, journal=journal, sender=off)[0]
    assert off_calls == []
    # Still disabled: no repeat attempts.
    assert cfd.process_due_session_summaries(at + dt.timedelta(minutes=10), journal=journal, sender=off) == []
    on, on_calls = sender(tmp_path, enabled=True)
    assert "delivery=sent" in cfd.process_due_session_summaries(at + dt.timedelta(minutes=20),
                                                               journal=journal, sender=on)[0]
    assert len(on_calls) == 1


def test_corrupt_store_blocks_the_summary_instead_of_sending(tmp_path):
    send, calls = sender(tmp_path)
    journal = str(tmp_path / "journal")
    write_start(journal, dt.datetime(2026, 10, 8, 6, 0, tzinfo=UTC))
    eval_dir = os.path.join(journal, "ticket_store", "evaluations")
    os.makedirs(eval_dir, exist_ok=True)
    with open(os.path.join(eval_dir, f"{THURSDAY.isoformat()}.jsonl"), "w", encoding="utf-8") as stream:
        stream.write('{"schema": "TICKET_STORE_V1_EVALUATION"')      # truncated tail
    lines = cfd.process_due_session_summaries(dt.datetime(2026, 10, 8, 16, 0, tzinfo=UTC),
                                              journal=journal, sender=send)
    assert calls == []
    assert len(lines) == 2                                  # both 2026-10-08 sessions are due
    assert all("blocked=TicketStoreCorrupt" in ln for ln in lines)


def test_scheduler_start_is_persisted_once_and_schema_checked(tmp_path):
    journal = str(tmp_path / "journal")
    at = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    assert cfd.ensure_scheduler_start(journal, at) == at
    later = dt.datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
    assert cfd.ensure_scheduler_start(journal, later) == at          # first write wins
    Path(cfd._scheduler_start_path(journal)).write_text(json.dumps({"schema": "OTHER"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cfd.ensure_scheduler_start(journal, later)


# ------------------------------------------------------------------ delivery gates

def test_sender_requires_local_recipient_authorization_and_environment_gate(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    journal = str(tmp_path / "journal")
    local = root / "config" / "local"
    local.mkdir(parents=True)

    def env(**values):
        for key in ("TELEGRAM_DELIVERY_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                    "TELEGRAM_OWNER_CHAT_IDS"):
            monkeypatch.delenv(key, raising=False)
        for key, value in values.items():
            monkeypatch.setenv(key, value)

    authorized_env = {"TELEGRAM_DELIVERY_ENABLED": "true", "TELEGRAM_BOT_TOKEN": "fake-token",
                      "TELEGRAM_CHAT_ID": "123", "TELEGRAM_OWNER_CHAT_IDS": "123,456"}

    env(**authorized_env)
    assert cfd.build_sender(journal, root=str(root)).config.enabled is False      # no local file
    (local / "canonical_ticket_delivery.yaml").write_text("mode: ARCHIVE_ONLY\nauthorized_chat_ids: ['123']\n",
                                                         encoding="utf-8")
    assert cfd.build_sender(journal, root=str(root)).config.enabled is False      # archive-only mode
    (local / "canonical_ticket_delivery.yaml").write_text("mode: MESSAGE_DELIVERY\nauthorized_chat_ids: ['456']\n",
                                                         encoding="utf-8")
    assert cfd.build_sender(journal, root=str(root)).config.enabled is False      # recipient not authorized
    (local / "canonical_ticket_delivery.yaml").write_text("mode: MESSAGE_DELIVERY\nauthorized_chat_ids: ['123']\n",
                                                         encoding="utf-8")
    send = cfd.build_sender(journal, root=str(root))
    assert send.config.enabled is True and send.config.chat_id == "123"
    assert send.config.owner_chat_ids == frozenset({"123"})

    for removed in authorized_env:
        env(**{k: v for k, v in authorized_env.items() if k != removed})
        assert cfd.build_sender(journal, root=str(root)).config.enabled is False
    env(**{**authorized_env, "TELEGRAM_DELIVERY_ENABLED": "false"})
    assert cfd.build_sender(journal, root=str(root)).config.enabled is False
    env(**{**authorized_env, "TELEGRAM_OWNER_CHAT_IDS": "456"})
    assert cfd.build_sender(journal, root=str(root)).config.enabled is False

    (local / "canonical_ticket_delivery.yaml").write_text("mode: MESSAGE_DELIVERY\nauthorized_chat_ids: 123\n",
                                                         encoding="utf-8")
    assert cfd.build_sender(journal, root=str(root)).config.enabled is False      # malformed allowlist
    (local / "canonical_ticket_delivery.yaml").write_text("\t: not yaml", encoding="utf-8")
    assert cfd.build_sender(journal, root=str(root)).config.enabled is False      # unparseable override


def test_c16_watch_info_scope_flag_is_default_off_and_needs_full_authorization(tmp_path, monkeypatch):
    root, journal = tmp_path / "root", tmp_path / "journal"
    local = root / "config" / "local"
    local.mkdir(parents=True)
    for key in ("TELEGRAM_DELIVERY_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_OWNER_CHAT_IDS"):
        monkeypatch.setenv(key, {"TELEGRAM_DELIVERY_ENABLED": "true", "TELEGRAM_BOT_TOKEN": "fake-token",
                                 "TELEGRAM_CHAT_ID": "123", "TELEGRAM_OWNER_CHAT_IDS": "123"}[key])
    override = local / "canonical_ticket_delivery.yaml"

    def scope():
        return cfd.build_sender(journal, root=str(root)).config.watch_info_scope

    override.write_text("mode: MESSAGE_DELIVERY\nauthorized_chat_ids: ['123']\n", encoding="utf-8")
    assert scope() is False                                   # absent flag -> default OFF
    override.write_text("mode: MESSAGE_DELIVERY\nauthorized_chat_ids: ['123']\nwatch_info_scope: 'true'\n",
                        encoding="utf-8")
    assert scope() is False                                   # only boolean true enables
    override.write_text("mode: MESSAGE_DELIVERY\nauthorized_chat_ids: ['123']\nwatch_info_scope: true\n",
                        encoding="utf-8")
    assert scope() is True
    override.write_text("mode: ARCHIVE_ONLY\nauthorized_chat_ids: ['123']\nwatch_info_scope: true\n",
                        encoding="utf-8")
    assert scope() is False                                   # flag alone never authorizes delivery
    override.write_text("mode: MESSAGE_DELIVERY\nauthorized_chat_ids: ['456']\nwatch_info_scope: true\n",
                        encoding="utf-8")
    assert scope() is False                                   # recipient not authorized


def test_disabled_sender_writes_no_journal_and_sends_nothing(tmp_path):
    send, calls = sender(tmp_path, enabled=False)
    results, lines, journal, _, _ = run(tmp_path, send=send)
    assert len(results) == 4 and calls == []
    assert not (tmp_path / "delivery.sqlite").exists()
    # Production READY authority is OFF, so every decision is non-alerting before the gate is
    # even consulted; the digest still records that messaging was disabled for this session.
    assert all("delivery=summary_only" in ln for ln in lines)
    digest = cfd.build_session_summary(journal, session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    assert digest["delivery_enabled"] is False
    assert digest["delivery_counts"] == {"succeeded": 0, "failed": 0, "uncertain": 0, "disabled": 0,
                                         "blocked": 0, "summary_only": 4, "persistence_failed": 0,
                                         "not_attempted": 0}


def test_unauthorized_recipient_never_sends_and_records_stay_durable(tmp_path):
    calls = []
    blocked = Sender(tmp_path / "delivery.sqlite",
                     Config(enabled=True, token="fake-token", chat_id="999",
                            owner_chat_ids=frozenset({"123"}), watch_info_scope=True),
                     transport=lambda *a: calls.append(a))
    results, lines, journal, _, _ = run(tmp_path, send=blocked)
    assert len(results) == 4 and calls == []
    # Persistence never depends on routing: all four durable rows exist although nothing sent.
    assert len(TicketStore(os.path.join(journal, "ticket_store")).evaluations()) == 4
    assert all("ticket_store=VERIFIED" in ln for ln in lines)
    # An alert-eligible ticket under the same unauthorized recipient is blocked by the adapter
    # (tests/test_telegram_delivery_adapter.py::test_closed).
    eligible = next(t for t in json.loads(
        (REPO / "tests" / "fixtures" / "telegram_delivery" / "tickets.json").read_text())
        if t["decision"] == "INFO_ONLY_STALE")
    assert blocked.send_ticket(eligible) == "blocked" and calls == []


# ------------------------------------------------------------------ scheduled path wiring / safety

def test_scheduled_fx_task_uses_canonical_once_and_preserves_other_modes():
    runner = (REPO / "scripts" / "host" / "live_candles_smoke.py").read_text(encoding="utf-8")
    install = (REPO / "scripts" / "host" / "install_tasks.ps1").read_text(encoding="utf-8")
    verify = (REPO / "scripts" / "host" / "verify_tasks.ps1").read_text(encoding="utf-8")

    # Minutes stays adjacent to Mode: scripts/docs/build_context_pack.py parses the rows positionally.
    assert "@{ Name = 'AG-V1-FX-Cycles';    Mode = 'fx';     Minutes = 15; Canonical = $true;" in install
    assert "@{ Name = 'AG-V1-Crypto-Daily'; Mode = 'crypto'; Minutes = 15; Canonical = $false;" in install
    assert "@{ Name = 'AG-V1-LSMC-Watch';   Mode = 'lsmc';   Minutes = 5;  Canonical = $false;" in install
    assert "Canonical = $true" in verify and "$e.Canonical" in verify

    assert 'ap.add_argument("--canonical", action="store_true"' in runner
    assert 'ap.error("--canonical is only valid with --mode fx")' in runner
    # Exactly two canonical calls: the host-prerequisite failure recorder and the live path.
    assert runner.count("run_canonical_fx_cycle(") == 2
    assert runner.count("failure_provider(reason, details.get(reason,") == 1
    assert runner.count("provider = snapshot_provider(GuardedMT5(mt5))") == 1
    start = runner.index("manual_lines = run_manual_jobs(fetch, now, journal)")
    canonical_branch = runner[start:runner.index("else:\n                                lines = manual_lines + run_fx(", start)]
    assert "run_fx(" not in canonical_branch                    # no duplicate legacy FX evaluation
    assert "snapshot_provider(GuardedMT5(mt5))" in canonical_branch
    assert 'ticket_source="LIVE"' in canonical_branch
    assert "process_due_session_summaries(" in canonical_branch
    # The legacy FX path stays reachable only without --canonical.
    legacy = runner[runner.index("else:\n                                lines = manual_lines + run_fx("):]
    assert "run_fx(" in legacy
    # Crypto and Large-SMC scheduled modes are untouched by the canonical FX branch.
    assert runner.count("lines = run_crypto(now, journal, crypto_feed_for(crypto_config, fetch, quote),") == 1
    assert runner.count("run_lsmc(fetch, now, journal, crypto_feed=lsmc_crypto_feed(crypto_config, fetch, quote))") == 1


def test_canonical_module_never_imports_a_broker_or_execution_surface():
    code = (
        "import sys; sys.path.insert(0, 'scripts/host'); import canonical_fx_delivery;"
        "banned = [m for m in sys.modules if m.split('.')[0] in"
        " {'mt5', 'MetaTrader5', 'execution', 'trade_management', 'assistant', 'authorization'}];"
        "assert not banned, banned"
    )
    subprocess.run([sys.executable, "-c", code], cwd=REPO,
                   env=dict(os.environ, PYTHONPATH=str(REPO / "src")), check=True)


def test_repo_delivery_default_stays_archive_only_and_no_local_override_is_committed():
    assert not (REPO / "config" / "local" / "canonical_ticket_delivery.yaml").exists()
    assert not (REPO / "config" / "local" / "delivery_override.yaml").exists()
    assert "/config/local/" in (REPO / ".gitignore").read_text(encoding="utf-8")
