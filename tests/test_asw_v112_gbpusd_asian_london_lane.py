"""AGP-4H-A: ST_ASIAN_SWEEP_5R_V1@1.1.2 lane GBPUSD x ASIAN_LONDON on the AGP-DATA-R3 60-weekday recorded file.

Pins the fixture sha256, the L2 half-point rounding regression (2026-08-25 TREND TP2), the
declared-fail-closed classification of every L2 failure, and prefix invariance. Logic only; no edge."""
from __future__ import annotations

import datetime as dt
import hashlib
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
    assert _eq(1.35850, 1.358505, 5)             # exact half-point tie: half-even neighbour (mode undeclared)
    assert _eq(1.34466, 1.34466 + 1e-16, 5)      # float noise on an on-grid expectation


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
    assert (rec["spread_points"], rec["point"], rec["source"]) == (1, 1e-05, "RECORDED_SPREAD_POINTS x HOST_CAPTURED_POINT")
    assert rec["spread_R"] == round(1e-05 / t["risk_distance"], 4)
    l5 = h.ticket_gates(h.load_strategy(h.CANDIDATE), CYCLE, day, session, post, now, w, t, h.TEST_SPREAD, 0.10,
                        SYMBOL, l5_spread=rec["spread_price"])["L5"]
    checks = {c["id"]: c for c in l5["checks"]}
    assert checks["L5.spread_R"]["verdict"] == PASS
    assert checks["L5.commission_R"]["value"] is None and checks["L5.commission_R"]["note"] == "COMMISSION NOT AVAILABLE"


def test_l5_spread_absent_without_a_signal_bar():
    assert h.recorded_spread(SYMBOL, {"signal_timestamp": None, "risk_distance": 0.001})["spread_price"] is None
