"""AGP-4H-A: ST_ASIAN_SWEEP_5R_V1@1.1.2 lane GBPUSD x ASIAN_LONDON on the AGP-DATA-R3 60-weekday recorded file.

Pins the fixture sha256, the L2 half-point rounding regression (2026-08-25 TREND TP2), the
declared-fail-closed classification of every L2 failure, and prefix invariance. Logic only; no edge."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib
from collections import defaultdict
from pathlib import Path

import pytest

import scripts.asw_v112_logic_verification as h
from v1_tickets.logic_gate import (
    EQ_EPS_POINTS,
    FAIL,
    NOT_EVALUABLE,
    PASS,
    _eq,
    l2_rule_conformance,
)

ROOT = Path(__file__).resolve().parents[1]
SYMBOL, CYCLE = "GBPUSD", "ASIAN_LONDON"
FIXTURE = h.D60_SYMBOLS[SYMBOL]["fixture"]
KEYS = ("setup", "signal_id", "signal_timestamp", "direction", "entry", "stop_loss", "targets")
FIXTURE_SHA256 = "aeaf0ba504569f1fa8b9867f2ac8992e8b33fc143a247644e48a34be16cf2a33"


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))
    monkeypatch.setattr(h, "SYMBOLS", {k: h.D60_SYMBOLS[k] for k in ("EURUSD", SYMBOL)})


def _days():
    by_day = defaultdict(list)
    for c in h.load_candles(SYMBOL):
        by_day[c.time.date().isoformat()].append(c)
    return by_day


def _l2(ds: str, by_day):
    day = dt.date.fromisoformat(ds)
    _, now, session, post = h.split(by_day[ds], CYCLE, day)
    t = h.ticket(CYCLE, day, session, post, now, symbol=SYMBOL)
    l2 = l2_rule_conformance(h.load_strategy(h.CANDIDATE), t, session, h.CYCLES[CYCLE][1], post, digits=5,
                             spread=h.TEST_SPREAD)
    return t, {c["id"]: c["verdict"] for c in l2["checks"]}


def test_fixture_sha256_pinned():
    assert hashlib.sha256((ROOT / FIXTURE).read_bytes()).hexdigest() == FIXTURE_SHA256


def test_eq_slack_is_float_noise_only():
    assert EQ_EPS_POINTS <= 1e-6                 # slack <= 1e-6 x point
    assert _eq(1.35851, 1.358505, 5)             # exact half-point tie: half-up neighbour
    assert _eq(1.34466, 1.34466 + 1e-16, 5)      # float noise on an on-grid expectation


def test_eq_rounds_ties_half_up_only():
    """OD1011-ROUNDING: ROUND_HALF_UP; the other tie neighbour (half-even/half-down) fails."""
    assert _eq(1.35851, 1.358505, 5)
    assert not _eq(1.35850, 1.358505, 5)
    assert _eq(1.35849, 1.358485, 5) and not _eq(1.35848, 1.358485, 5)   # odd/even base: still up
    assert _eq(1.3585, 1.3585049, 5) and not _eq(1.35851, 1.3585049, 5)  # below the tie rounds down


def test_eq_true_half_point_and_one_point_errors_fail():
    assert not _eq(1.358505, 1.35850, 5)         # half-point error against an on-grid expectation
    assert not _eq(1.35850, 1.358505 + 0.02e-5, 5)   # just past the tie: only 1.35851 conforms
    assert not _eq(1.35851, 1.35850, 5)          # one-point error
    assert not _eq(1.35852, 1.358505, 5)         # one point beyond the tie neighbour


def test_2026_08_25_trend_tp2_conforms_and_branch_still_fails_closed():
    t, v = _l2("2026-08-25", _days())
    assert (t["setup"], t["direction"]) == ("TREND", "SHORT")
    assert v["R.target_leg2"] == PASS
    assert v["R.regime_branch"] == FAIL      # TREND remains FAIL_CLOSED (ENTRY_LEVEL_NOT_MARKET_AT_SIGNAL)


def test_every_l2_failure_is_a_declared_fail_closed_rule():
    by_day = _days()
    for ds in h.fixture_days(h.load_candles(SYMBOL)):
        t, v = _l2(ds, by_day)
        if t.get("direction") is None:
            continue
        failed = {k for k, s in v.items() if s in (FAIL, NOT_EVALUABLE)}
        assert failed <= h.DECLARED_FAIL_CLOSED, (ds, failed - h.DECLARED_FAIL_CLOSED)


def test_prefix_invariance_every_bar():
    """The decision from bars[:t] equals the full-run decision truncated at t, for every t."""
    by_day = _days()
    for ds in h.fixture_days(h.load_candles(SYMBOL)):
        day = dt.date.fromisoformat(ds)
        _, now, session, post = h.split(by_day[ds], CYCLE, day)
        full = h.ticket(CYCLE, day, session, post, now, symbol=SYMBOL)
        sig_ts = full.get("signal_timestamp")
        for n in range(len(post) + 1):
            part = h.semantic(h.ticket(CYCLE, day, session, post[:n], now, symbol=SYMBOL))
            emitted = sig_ts is None or any(c.time == dt.datetime.fromisoformat(sig_ts) for c in post[:n])
            if emitted:   # session-decided (no signal bar) or signal bar already in the prefix
                assert {k: part[k] for k in KEYS} == {k: full.get(k) for k in KEYS}, (ds, n)
            else:         # no signal may appear before the full run's signal bar
                assert part["direction"] is None, (ds, n)


def test_l5_reads_recorded_spread_and_never_assumes_commission():
    by_day = _days()
    day = dt.date.fromisoformat("2026-08-31")
    w, now, session, post = h.split(by_day["2026-08-31"], CYCLE, day)
    t = h.ticket(CYCLE, day, session, post, now, symbol=SYMBOL)
    rec = h.recorded_spread(SYMBOL, t)
    # bar spread (1 pt) is a per-bar lower bound; the host snapshot (15 pt) is the conservative value
    assert (rec["bar_spread_points"], rec["host_spread_points"], rec["spread_points"], rec["source"]) == \
        (1, 15, 15, "HOST_SNAPSHOT")
    assert rec["spread_R"] == round(15 * 1e-05 / t["risk_distance"], 4)
    l5 = h.ticket_gates(h.load_strategy(h.CANDIDATE), CYCLE, day, session, post, now, w, t, h.TEST_SPREAD, 0.10,
                        SYMBOL, l5_spread=rec["spread_price"])["L5"]
    checks = {c["id"]: c for c in l5["checks"]}
    assert checks["L5.spread_R"]["verdict"] == PASS
    assert checks["L5.commission_R"]["value"] is None and checks["L5.commission_R"]["note"] == "COMMISSION NOT AVAILABLE"
    # OD1011-COMMISSION: 0 only when bound to the host-captured server; the cost gate applies it and the thresholds
    assert h.bound_commission(SYMBOL) == 0.0
    probe = h.cost_probe(CYCLE, day, session, post, now, SYMBOL, rec["spread_price"], 0.0)
    assert probe["gate_correct"] and probe["actionability"] == "COST_BLOCKED" and probe["cost_in_R"] == 0.6


def test_commission_is_never_zero_for_an_unbound_account(monkeypatch):
    real = h.symbol_metadata.load_record
    monkeypatch.setattr(h.symbol_metadata, "load_record",
                        lambda *a, **k: {**real(*a, **k), "server": "OtherBroker-Live"})
    assert h.bound_commission(SYMBOL) is None
    monkeypatch.setattr(h.symbol_metadata, "load_record", lambda *a, **k: None)
    assert h.bound_commission(SYMBOL) is None


def test_l5_spread_absent_without_a_signal_bar():
    assert h.recorded_spread(SYMBOL, {"signal_timestamp": None, "risk_distance": 0.001})["spread_price"] is None


def test_l5_bar_only_spread_is_insufficient_never_pass(monkeypatch):
    t = {"signal_timestamp": "2026-08-31T07:15:00+00:00", "risk_distance": 0.00025}
    monkeypatch.setattr(h.symbol_metadata, "load_record", lambda *a, **k: {"fields": {"point": 1e-05}})
    rec = h.recorded_spread(SYMBOL, t)
    assert (rec["bar_spread_points"], rec["spread_price"], rec["source"]) == (1, None, "BAR_ONLY_LOWER_BOUND")
    drv = importlib.import_module("scripts.asw_v112_60d_replay")
    kept = [{"l5_recorded_spread": rec}]
    owner = {"cost_warn_R": 0.10, "cost_block_R": 0.25}
    assert drv.lane_l5(kept, "WARN", owner)[0] == "INSUFFICIENT(spread)"


def test_session_row_with_kept_entries_and_no_owner_fails_closed():
    drv = importlib.import_module("scripts.asw_v112_60d_replay")
    kept = {"case_id": "recorded:X:ASIAN_LONDON:2026-08-31", "direction": "SHORT", "setup": "SWEEP",
            "day_type": "short-sweep",
            "ticket_gate_status": {g: "PASS" for g in ("L1", "L2", "L3", "L4", "L5", "L6")},
            "ticket_gate_blocking_failures": [], "l2_fail_ids": [], "l2_undeclared": [], "owner_ticket_L6": "PASS",
            "geometry": {"has_levels": True, "positive_stop": True, "target_order": True},
            "causality": {"prefix_mismatches": 0, "pre_emission_signals": 0, "streaming_hash_parity": True,
                          "future_mutations": 25, "future_mutation_mismatches": 0},
            "l5_recorded_spread": {"spread_R": 0.6, "source": "HOST_SNAPSHOT"}}
    row = drv.session_row("X", "ASIAN_LONDON", [kept], {"L1": "PASS", "L4": "PASS", "L5": "WARN"})
    assert row["valid_entries"] == 1
    assert row["gates"]["L5"] == "FAIL" and row["l5_detail"]["reason"].startswith("OWNER_BINDING_MISSING")
