import datetime as dt
import json
from pathlib import Path

from ticket_store.grader import Bar, grade_record, load_m1_csv, make_report, replay
from ticket_store.store import LIVE, REPLAY, TicketStore, build_evaluation

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def record(symbol="EURUSD", *, state="READY", source=REPLAY, reason=None, hashes=None, spread_time=0):
    return build_evaluation(
        ticket_id=f"{symbol}-ticket", strategy="ST_ASIAN_SWEEP_5R_V1@1.1.1", source=source,
        symbol=symbol, session="ASIAN_LONDON", evaluated_at_utc=T0.isoformat(), signal_close_utc=T0.isoformat(),
        state=state, block_reasons=[reason] if reason else [], direction="LONG", entry=1.1000, sl=1.0990,
        tp1=1.1020, tp2=1.1050, spread_at_signal=0.0001,
        spread_measured_at_utc=(T0 + dt.timedelta(minutes=spread_time)).isoformat(), input_bar_hashes=hashes,
    )


def bar(minute, o=1.1000, h=1.1001, lo=1.0999, c=1.1000):
    return Bar(T0 + dt.timedelta(minutes=minute), o, h, lo, c)


def test_first_touch_fill_tp1_cost_metrics_and_spread_gap():
    r = grade_record(record(spread_time=20), [bar(0), bar(1, h=1.1022, c=1.102)])
    assert (r["result"], r["grade"], r["gross_R"], r["net_R"]) == ("TP1", "TP1", 2.0, 1.9)
    assert r["fill_time_utc"] == T0.isoformat() and r["minutes_to_outcome"] == 2
    assert r["mfe_R"] == 2.2 and r["mae_R"] == 0.1
    assert r["flags"] == ["SPREAD_TIMING_GAP"]


def test_tp2_first_touch_is_recorded_when_its_level_is_first():
    rec = record()
    rec["tp1"] = 1.105
    rec["tp2"] = 1.102
    r = grade_record(rec, [bar(0), bar(1, h=1.1022, c=1.102)])
    assert r["result"] == "TP2" and r["net_R"] == 1.9


def test_sl_and_same_bar_ambiguous_are_sl_first():
    sl = grade_record(record(), [bar(0), bar(1, h=1.1002, lo=1.0988)])
    amb = grade_record(record(), [bar(0, h=1.1022, lo=1.0988)])
    assert (sl["result"], sl["net_R"]) == ("SL", -1.1)
    assert (amb["result"], amb["grade"], amb["net_R"]) == ("AMBIGUOUS", "SL", -1.1)


def test_m1_gaps_fail_closed_after_entry():
    r = grade_record(record(), [bar(0), bar(1), bar(3, h=1.1022, c=1.102)], expiry_minutes=2)
    assert r["result"] == "DATA_INSUFFICIENT" and r["reason"] == "M1_GAP_AFTER_FILL"


def test_unfilled_entry_expires_and_history_must_cover_expiry():
    rec = record()
    bars = [bar(i, o=1.2, h=1.2001, lo=1.1999, c=1.2) for i in range(5)]
    expired = grade_record(rec, bars, expiry_minutes=5)
    assert expired["result"] == "EXPIRED" and expired["minutes_to_outcome"] == 5
    assert grade_record(rec, bars[:2], expiry_minutes=5)["result"] == "DATA_INSUFFICIENT"


def test_counterfactual_cohort_replay_store_idempotence_and_report(tmp_path):
    store = TicketStore(str(tmp_path))
    live = record("EURUSD", source=LIVE, hashes={"reference": "a", "trade": "b"})
    ready = record("EURUSD", source=REPLAY, hashes={"reference": "a", "trade": "b"})
    blocked = record("GBPUSD", state="BLOCKED", reason="SPREAD_TOO_WIDE")
    for r in (live, ready, blocked):
        store.append_evaluation(r)
    bars = {"EURUSD": [bar(0), bar(1, h=1.1022, c=1.102)],
            "GBPUSD": [bar(0), bar(1, h=1.1022, c=1.102)]}
    counts = replay(store, bars, T0.date(), T0.date(), expiry_minutes=5)
    assert counts == {"evaluations_seen": 2, "graded": 1, "counterfactual": 1, "skipped": 0}
    assert replay(store, bars, T0.date(), T0.date(), expiry_minutes=5) == {
        "evaluations_seen": 2, "graded": 0, "counterfactual": 0, "skipped": 0}
    outcomes = store.outcomes()
    assert {o["outcome_kind"] for o in outcomes} == {"FIRST_TOUCH_M1_V1", "COUNTERFACTUAL_M1_V1"}
    report = make_report(store)
    assert report["replay_parity"][0]["status"] == "BAR_HASH_MATCH"
    group = next(g for g in report["groups"] if g["symbol"] == "GBPUSD")
    assert group["counterfactual_R_by_block_reason"]["SPREAD_TOO_WIDE"]["expectancy_R"] == 1.9
    assert group["flag"] == "DIRECTIONAL_ONLY"


def test_replay_can_backfill_live_evaluations_as_replay_outcomes(tmp_path):
    store = TicketStore(str(tmp_path))
    store.append_evaluation(record("EURUSD", source=LIVE))
    bars = {"EURUSD": [bar(0), bar(1, h=1.1022, c=1.102)]}
    assert replay(store, bars, T0.date(), T0.date(), expiry_minutes=5)["graded"] == 1
    assert len(store.outcomes()) == 1 and store.outcomes()[0]["source"] == REPLAY


def test_replay_bar_hash_mismatch_is_reported(tmp_path):
    store = TicketStore(str(tmp_path))
    store.append_evaluation(record(source=LIVE, hashes={"trade": "old"}))
    store.append_evaluation(record(source=REPLAY, hashes={"trade": "new"}))
    assert make_report(store)["replay_parity"][0]["status"] == "BAR_HASH_MISMATCH"


def test_offline_fixture_csv_is_timezone_pinned():
    path = Path(__file__).parent / "fixtures" / "ticket_outcome_m1" / "EURUSD.csv"
    bars = load_m1_csv(path)
    assert bars and all(b.time.tzinfo == UTC for b in bars)


def test_sample_report_is_built_from_pinned_m1_fixtures(tmp_path, capsys):
    fixture_dir = Path(__file__).parent / "fixtures" / "ticket_outcome_m1"
    store_root = tmp_path / "store"
    store = TicketStore(str(store_root))
    for symbol, state, reason, spread_time in (
        ("BTCUSD", "READY", None, 16), ("GBPUSD", "BLOCKED", "SPREAD_TOO_WIDE", 0),
        ("USDJPY", "READY", None, 0), ("XAUUSD", "READY", None, 0),
    ):
        store.append_evaluation(record(symbol, state=state, reason=reason, spread_time=spread_time))
    from scripts.grade_ticket_outcomes import main as cli_main
    cli_main(["--store", str(store_root), "--from", T0.date().isoformat(), "--to", T0.date().isoformat(),
              "--m1-dir", str(fixture_dir), "--expiry-minutes", "5", "--json"])
    output = json.loads(capsys.readouterr().out)
    assert output["replay"] == {"evaluations_seen": 4, "graded": 3, "counterfactual": 1, "skipped": 0}
    report = output["report"]
    assert len(report["groups"]) == 4
    assert next(g for g in report["groups"] if g["symbol"] == "BTCUSD")["outcome_flags"]["SPREAD_TIMING_GAP"] == 1
    assert next(g for g in report["groups"] if g["symbol"] == "XAUUSD")["counts_by_state"] == {"READY": 1}
    expected = fixture_dir / "sample_report.json"
    assert json.loads(expected.read_text(encoding="utf-8")) == report
