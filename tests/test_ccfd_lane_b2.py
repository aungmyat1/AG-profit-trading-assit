"""AGP-LANE-B2: emission-ticket provenance, rule-coverage matrix, recorded_60d manifest, and the
missing-bar rule (a gap reaches the contract's data-incomplete path, never interpolation)."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ccfd_sweep_retest_replay as R  # noqa: E402
from scripts.ccfd_recorded_cases import (  # noqa: E402
    RECORDED_60D,
    partial_days,
    read_rows,
    verify,
)

UTC = dt.timezone.utc
REPORT = json.loads((R.OUT_DIR / "replay_report.json").read_text(encoding="utf-8"))
COMMITTED = [json.loads(line) for line in (R.OUT_DIR / "tickets.jsonl").read_text(encoding="utf-8").splitlines()]


# ------------------------------------------------------------- 4) the 2 extra tickets come from code

@pytest.mark.parametrize("symbol,day", [("BTCUSD", dt.date(2026, 10, 9)), ("ETHUSD", dt.date(2026, 10, 5))])
def test_emission_research_tickets_are_reproduced_by_run_symbol(symbol, day):
    """The two non-CYCLE tickets are built by run_symbol -> manual_ticket.build_crypto_cfd_manual_ticket
    at the first ENTRY_VALID scan of the day; re-running the code reproduces them byte-for-byte."""
    committed = [t for t in COMMITTED if t["stream"] == "EMISSION_RESEARCH" and t["symbol"] == symbol]
    assert len(committed) == 1
    rebuilt = [t for t in R.build("2026-10-10", symbols=(symbol,), days=[day])["_tickets"]
               if t["stream"] == "EMISSION_RESEARCH"]
    assert len(rebuilt) == 1
    a, b = (json.dumps(t, sort_keys=True, default=str) for t in (rebuilt[0], committed[0]))
    assert a == b


def test_only_cycle_and_code_emitted_streams_exist():
    streams = {t["stream"] for t in COMMITTED}
    assert streams == {"CYCLE", "EMISSION_RESEARCH"}
    assert sum(t["stream"] == "EMISSION_RESEARCH" for t in COMMITTED) == 2


# ------------------------------------------------------------- 5) rule coverage matrix

def test_coverage_matrix_covers_every_rule_direction_and_window():
    cov = REPORT["rule_coverage"]
    for sym, matrix in cov["vt"].items():
        assert set(matrix) == {rule for rule, _ in R.RULES}
        for rule, scope in R.RULES:
            cells = matrix[rule]["cells"]
            assert set(cells) == {f"{d}|{w}" for d in ("LONG", "SHORT") for w in R.WINDOWS}
            for cell, v in cells.items():
                expected = {"NOT_APPLICABLE"} if scope in ("LONG", "SHORT") and not cell.startswith(scope) \
                    else {"EXERCISED", "NOT_EXERCISED"}
                assert v["status"] in expected and (v["status"] == "EXERCISED") == (v["scans"] > 0)
        assert sorted(cov["vt_not_exercised"][sym]) == sorted(R.coverage_gaps(matrix))


def test_vt_coverage_agrees_with_scan_results():
    for sym, matrix in REPORT["rule_coverage"]["vt"].items():
        res = REPORT["symbols"][sym]["scan_results"]
        incomplete = sum(v["scans"] for k, v in matrix["liquidity_contract.completeness_rule"]["cells"].items()
                         if k.startswith("LONG"))
        assert incomplete == res["REFERENCE_INCOMPLETE"]
        entry = sum(v["scans"] for v in matrix["entry_timing_contract.actionable_event"]["cells"].values())
        assert entry == res.get("ENTRY_VALID", 0)


def test_coverage_only_fills_vt_gaps_only_and_is_labelled():
    cov = REPORT["rule_coverage"]
    co = cov["coverage_only_binance"]
    assert co["label"] == "COVERAGE_ONLY" and co["authoritative"] is False
    for sym, gaps in cov["vt_not_exercised"].items():
        assert set(co["vt_gap_cells"][sym]) == set(gaps)            # never consulted for a VT-exercised cell
        assert cov["not_exercised_anywhere"][sym] == sorted(c for c, s in co["vt_gap_cells"][sym].items()
                                                             if s == "NOT_EXERCISED")
    raw = json.loads(R.COVERAGE_ONLY.read_text(encoding="utf-8"))
    assert raw["feeds_logic_verdict"] is raw["feeds_registry"] is raw["feeds_tickets"] is False
    assert raw["raw_data_committed"] is False and raw["ORDER_API_CALLS"] == 0


def test_rule_events_direction_and_ids():
    ids = {rule for rule, _ in R.RULES}
    inc = {"result": "REFERENCE_INCOMPLETE", "evidence": {}}
    assert R.rule_events(inc, {"M5": []}, dt.datetime(2026, 10, 9, tzinfo=UTC)) == {
        ("liquidity_contract.completeness_rule", "ANY")}
    for sym, matrix in REPORT["rule_coverage"]["vt"].items():
        assert set(matrix) == ids


# ------------------------------------------------------------- recorded_60d manifest (PR #143)

def test_recorded_60d_manifest_verifies_and_lists_partial_days_without_filling():
    manifest = verify(RECORDED_60D / "manifest.json")
    assert manifest["mission"] == "AGP-HOST-CRYPTO60"
    assert manifest["gaps"]["policy"].startswith("missing bars are listed, never filled")
    for sym in ("BTCUSD", "ETHUSD"):
        prov = json.loads((RECORDED_60D / f"{sym}_provenance.json").read_text(encoding="utf-8"))
        assert prov["server_utc_offset_hours"] == ["3/3"] and prov["days_kept"] == 60 == len(prov["days"])
        assert prov["partial_days_m5_bars"] == manifest["gaps"]["partial_days_m5_bars"][sym] == partial_days(
            RECORDED_60D, sym)
        assert prov["partial_days_m5_bars"]["2026-08-15"] == 120
        rows = read_rows(RECORDED_60D / f"{sym}_m5.csv")
        days = {r["timestamp_utc"][:10] for r in rows}
        assert len(rows) == 288 * len(days) - sum(288 - n for n in prov["partial_days_m5_bars"].values())
    assert all(c["quote_time"] for c in manifest["cases"])


# ------------------------------------------------------------- missing bar -> data-incomplete path

def test_loader_keeps_recorded_gaps_and_a_missing_bar_reaches_reference_incomplete():
    data = R.load_symbol("BTCUSD", RECORDED_60D)
    assert len(data["bars"]["M5"]) == len(read_rows(RECORDED_60D / "BTCUSD_m5.csv"))      # nothing filled
    gap_day = [c for c in data["bars"]["M5"] if c.time.date() == dt.date(2026, 8, 28)]
    assert len(gap_day) == 286                                                            # 2 bars missing
    counts = {"D1": 50, "H1": 100, "M15": 96, "M5": 576}
    cfg = R.load_market_structure_config()
    now = dt.datetime(2026, 8, 29, 12, tzinfo=UTC)
    r = R.engine("BTCUSD", now, R.closed_inputs(data, now, counts), cfg)
    assert r["result"] == "REFERENCE_INCOMPLETE" and r["evidence"]["reference"]["status"] == "INCOMPLETE"

    # A complete day with one bar removed: same data-incomplete path, no interpolation.
    full_now = dt.datetime(2026, 10, 10, 0, tzinfo=UTC)
    x = R.closed_inputs(data, full_now, counts)
    assert R.engine("BTCUSD", full_now, x, cfg)["result"] != "REFERENCE_INCOMPLETE"
    drop = dt.datetime(2026, 10, 9, 12, tzinfo=UTC)
    holed = {**x, "M5": [c for c in x["M5"] if c.time != drop]}
    out = R.engine("BTCUSD", full_now, holed, cfg)
    assert out["result"] == "REFERENCE_INCOMPLETE" and out["reason_codes"] == ["REFERENCE_INCOMPLETE"]


def test_live_cycle_with_a_missing_bar_is_a_data_error_not_a_filled_ticket():
    from v1_tickets import crypto_cfd

    data = R.load_symbol("BTCUSD", RECORDED_60D)
    drop = dt.datetime(2026, 10, 8, 3, tzinfo=UTC)
    holed = {**data, "bars": {**data["bars"], "M5": [c for c in data["bars"]["M5"] if c.time != drop]}}
    holed["times"] = {tf: [c.time for c in rows] for tf, rows in holed["bars"].items()}
    now = dt.datetime(2026, 10, 9, 14, tzinfo=UTC)
    t = crypto_cfd.build_crypto_cfd_cycle("BTCUSD", now, feed=R.ReplayFeed(holed, now), balance=None)
    assert t["decision"] == "DATA_ERROR" and "REFERENCE_INCOMPLETE" in t["reason_codes"]


# ------------------------------------------------------------- 60-day VT replay (PR #143), after the guard

REPORT_60D = json.loads((R.DATASETS["recorded_60d"][1] / "replay_report.json").read_text(encoding="utf-8"))


def test_60d_replay_scans_every_day_through_the_guard():
    assert REPORT_60D["dataset"]["id"] == "recorded_60d" and len(REPORT_60D["days_run"]) == 60
    assert REPORT_60D["engine_entry_point"].startswith("crypto_cfd_contract.evaluate")
    assert REPORT_60D["weekend_days"] == [d for d in REPORT_60D["days_run"]
                                          if dt.date.fromisoformat(d).isoweekday() in (6, 7)]
    assert len(REPORT_60D["weekend_days"]) == 16
    partial = verify(RECORDED_60D / "manifest.json")["gaps"]["partial_days_m5_bars"]
    for sym, s in REPORT_60D["symbols"].items():
        assert s["scans"] == 60 * 288
        # owner ruling 2026-10-11 (A): L3 compares the signal event log -> 0 mismatches of any kind
        assert not any(s["mismatches"].values()) and s["signal_events"]["event_log_mismatches"] == 0
        assert s["gates"] == {g: "PASS" for g in ("L1", "L2", "L3", "L4", "L5", "L6")}
        for day in partial[sym]:                       # the day after a partial day: data-incomplete path
            nxt = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
            if nxt in s["per_day"]:
                assert s["per_day"][nxt]["results"] == {"REFERENCE_INCOMPLETE": 288}


def test_60d_reissues_older_than_the_expiry_window_are_expired_and_never_actionable():
    """Item 1b: every REISSUE whose retest bar is older than the signal-expiry window (manual_ticket
    valid_until = retest open + 20 min) is EXPIRED, its ticket carries SIGNAL_STALE and is never actionable."""
    totals = {"total": 0, "fresh": 0, "expired": 0}
    tickets = {json.loads(line)["case_id"]: json.loads(line) for line in
               (R.DATASETS["recorded_60d"][1] / "tickets.jsonl").read_text(encoding="utf-8").splitlines()}
    for sym, s in REPORT_60D["symbols"].items():
        reissues = [e for e in s["signal_events"]["log"] if e["type"] == "REISSUE"]
        assert len(reissues) == len(s["reissues"]) == s["signal_events"]["reissues"]["total"]
        for e, row in zip(reissues, s["reissues"]):
            now, retest = (dt.datetime.fromisoformat(e[k]) for k in ("bar_close_utc", "retest_candle_time_utc"))
            old = now > retest + R.SIGNAL_TTL
            assert (e["freshness"] == "EXPIRED") == old == row["expiry_rule_fired"]
            if old:
                assert row["actionable"] is False and row["ticket_decision"] != "READY"
            t = tickets[f"{sym}_REISSUE_{now:%Y%m%dT%H%MZ}"]
            assert t["stream"] == "REISSUE_RESEARCH" and t["signal_event"] == e
            assert ("SIGNAL_STALE" in t["ticket"]["reason_codes"]) == old
        for k in totals:
            totals[k] += s["signal_events"]["reissues"][k]
    assert totals == {"total": 1, "fresh": 0, "expired": 1}          # ETHUSD 2026-09-09 20:00 (10:55 retest)


def test_60d_every_emit_expires_and_no_day_fails():
    for sym, s in REPORT_60D["symbols"].items():
        by = s["signal_events"]["events_by_type"]
        assert by["EMIT"] == by["EXPIRE"] == len(s["emissions"]) and by.get("WITHDRAW", 0) == 0
        assert all(e["reason"] == "SIGNAL_STALE" for e in s["signal_events"]["log"] if e["type"] == "EXPIRE")
        assert not any(d["failure_class"] for d in s["per_day"].values())
        assert REPORT_60D["logic_verification"][sym]["all_checks_pass"] is True


def test_60d_coverage_proof_marks_only_rejection_rules_synthetic_and_never_counts_binance():
    """Item 3: SYNTHETIC_PROVEN only for rejection-only rules with a synthetic unit case; entry-branch cells
    count only when VT EXERCISED; COVERAGE_ONLY (Binance) cells never verify a branch."""
    cov = REPORT_60D["rule_coverage"]
    for sym, proof in cov["proof"].items():
        for rule, row in proof.items():
            for cell, st in row.items():
                vt = cov["vt"][sym][rule]["cells"][cell]["status"]
                assert st == vt or (vt == "NOT_EXERCISED" and st in ("SYNTHETIC_PROVEN", "COVERAGE_ONLY_EXERCISED"))
                assert st != "SYNTHETIC_PROVEN" or rule in R.SYNTHETIC_PROOFS
        for b, v in REPORT_60D["logic_verification"][sym]["branches"].items():
            open_cells = [g for g in cov["open_gaps"][sym] if g.split("|")[1] == b]
            assert v["verified"] == (not open_cells and not [x for x in v["blocking"] if not x.startswith("COVERAGE:")])
    assert cov["open_gaps"]["ETHUSD"] == []
    assert {g.split("|")[1] for g in cov["open_gaps"]["BTCUSD"]} == {"LONG"}
