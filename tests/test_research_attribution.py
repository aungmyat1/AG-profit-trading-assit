"""AG_RULE_ATTRIBUTION_V1 research pipeline (research/attribution/)."""
from __future__ import annotations

import importlib.util
import json
import os
import random
import subprocess
import sys

import pytest

from research.attribution import analysis, costs, frozen_engine, ledger, validation

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_metrics_basic():
    m = analysis.metrics([1.0, -1.0, 2.0, -0.5])
    assert m["n"] == 4 and m["expectancy_R"] == pytest.approx(0.375)
    assert m["profit_factor"] == pytest.approx(2.0)
    assert m["max_drawdown_R"] == pytest.approx(1.0)
    assert analysis.metrics([])["expectancy_R"] is None


def test_cells_below_30_are_insufficient_and_carry_no_metrics():
    rows = [{"symbol": "EURUSD", "session_pair": "ASIAN_LONDON", "direction": "LONG", "regime": "RANGE",
             "setup_model": "S1", "entry_number": 1, "outcome_class": "STOP_FIRST",
             "vt_net_R": -1.0, "in_frozen_baseline": True}] * 29
    table = analysis.category_table(rows)
    assert table and all(c["status"] == "INSUFFICIENT" and c["expectancy_R"] is None for c in table)
    assert analysis.failure_diagnosis(table) == []


def test_diagnosis_ranks_only_sufficient_negative_cells():
    cells = [{"category": "setup_type", "value": "S2", "status": "OK", "n": 40, "expectancy_R": -0.5},
             {"category": "setup_type", "value": "S1", "status": "OK", "n": 100, "expectancy_R": -0.3},
             {"category": "regime", "value": "RANGE", "status": "OK", "n": 50, "expectancy_R": 0.2},
             {"category": "symbol", "value": "GBPUSD", "status": "INSUFFICIENT", "n": 10, "expectancy_R": None}]
    diag = analysis.failure_diagnosis(cells)
    assert [d["value"] for d in diag] == ["S1", "S2"]


@pytest.mark.parametrize("events,expected", [
    ([{"event": "PARTIAL_TARGET_HIT"}, {"event": "RUNNER_BE_STOP"}], "TP1_FIRST"),
    ([{"event": "SL"}], "STOP_FIRST"),
    ([{"event": "SESSION_EXIT_FULL_POSITION"}], "EXPIRED"),
    ([{"event": "SL_AND_PARTIAL_TARGET_SAME_CANDLE"}], "NEITHER"),
    ([], "NEITHER"),
])
def test_outcome_class(events, expected):
    assert ledger.outcome_class({"event_sequence": events}) == expected


def test_vt_cost_model_is_flagged_placeholder():
    assert costs.COST_MODEL_STATUS == "PLACEHOLDER_NOT_BROKER_MEASURED"
    assert costs.cost_r("EURUSD", 0.0015, 0.0001) == pytest.approx(1.5 / 15)
    assert costs.cost_r("XAUUSD", 1.0, 0.1) is None and costs.cost_r("EURUSD", 0.0, 0.0001) is None


def test_pbo_noise_vs_dominant_trial():
    rng = random.Random(1)
    noise = [[rng.gauss(0, 1) for _ in range(10)] for _ in range(400)]
    assert 0.2 < validation.pbo_cscv(noise)["pbo"] < 0.8
    dominant = [[rng.gauss(1.0 if j == 0 else 0.0, 1) for j in range(10)] for _ in range(400)]
    assert validation.pbo_cscv(dominant)["pbo"] < 0.1
    assert validation.pbo_cscv([[0.0]] * 50)["status"] == "INSUFFICIENT"


def test_deflated_sharpe_penalises_more_trials():
    rng = random.Random(2)
    rets = [rng.gauss(0.1, 1) for _ in range(500)]
    sharpes = [rng.gauss(0, 0.05) for _ in range(50)]
    one = validation.deflated_sharpe(rets, 1, [0.0])["dsr"]
    many = validation.deflated_sharpe(rets, 50, sharpes)["dsr"]
    assert many < one


def test_verdict_rule():
    good = {"n": 40, "expectancy_R": 0.2, "profit_factor": 1.3}
    assert validation.verdict(good, {"dsr": 0.97}, {"pbo": 0.2}) == "DEMO_READY"
    assert validation.verdict(good, {"dsr": 0.90}, {"pbo": 0.2}) == "RETEST"
    assert validation.verdict(good, {"dsr": 0.99}, {"pbo": 0.6}) == "REJECT"
    assert validation.verdict({"n": 40, "expectancy_R": -0.1, "profit_factor": 0.8}, {"dsr": 0.99},
                              {"pbo": 0.1}) == "REJECT"
    assert validation.verdict({"n": 12, "expectancy_R": 0.5, "profit_factor": 2.0}, {"dsr": 0.99},
                              {"pbo": 0.1}) == "RETEST"


def test_walk_forward_and_cpcv_shapes():
    trades = [{"trading_date": f"2024-01-{d:02d}", "entry_time": f"2024-01-{d:02d}T08", "net_R": 1.0 if d % 2 else -1.0}
              for d in range(1, 31)]
    wf = validation.walk_forward(trades, n_folds=5)
    assert wf["status"] == "OK" and wf["oos"]["n"] == 25
    dates, names, mat = validation.daily_matrix({"A": trades, "B": trades[:10]})
    assert len(dates) == 30 and names == ["A", "B"]
    cp = validation.cpcv_oos(mat, names)
    assert cp["A"]["splits"] == 15


def test_gate_chain_stops_at_missing_public_data():
    spec = importlib.util.spec_from_file_location("run_attr", os.path.join(REPO_ROOT, "research", "attribution",
                                                                           "run_attribution.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    adm = {"strategies": {"X": {}}, "public_dev_data": {
        "manifest_path": "data/research/public_dev/__absent__.json", "allowed_sources": ["DUKASCOPY"],
        "end_exclusive_utc": "2025-09-14T00:00:00Z", "required_timeframes": ["M15"]}}
    assert mod.gate_data(adm, {"X": ["EURUSD"]})["X"]["status"] == "FAIL"
    assert mod.gate_admission({"strategies": {"ST_ASIAN_SWEEP_5R_V1": {
        "backtest_status": "NOT_EVALUABLE"}}})["ST_ASIAN_SWEEP_5R_V1"]["optimization_eligible"] is False


def _frozen_engine_runnable() -> bool:
    if frozen_engine.semantic_check()["status"] != "PASS":
        return False
    return all(importlib.util.find_spec(m) for m in ("pandas", "smartmoneyconcepts"))


@pytest.mark.skipif(not _frozen_engine_runnable(), reason="frozen commit or engine deps unavailable")
def test_frozen_engine_parity_subprocess():
    out = subprocess.run([sys.executable, "-m", "research.attribution.parity_check"], cwd=REPO_ROOT,
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    summary = json.loads(out.stdout.strip().splitlines()[-1])
    assert summary["status"] == "PASS" and summary["baseline_rows"] == summary["baseline_fills"]
