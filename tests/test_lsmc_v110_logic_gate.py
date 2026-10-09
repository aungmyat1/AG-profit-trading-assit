"""AGP-C1-LSMC: L1-L6 logic gate for ST_LARGE_SMC_V1@1.1.0 and the correlated-READY warning.
Synthetic fixtures only (tests/_lsmc_v110_fixtures.py); points from the committed VT host captures."""
from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import pytest
import yaml
from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars

from large_smc_watch import evaluate_snapshot
from v1_tickets import lsmc_logic_gate as G
from v1_tickets.correlation_guard import CORRELATED_READY, correlated_ready_warnings, legs

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _committed_captures(monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(ROOT))


def case(symbol="EURUSD", k=1.0, now=NOW):
    return {"case_id": f"t:{symbol}", "symbol": symbol, "now": now, "fixture": "t", "classification": "SYNTHETIC",
            "D1": d1_bars(k), "H1": h1_bars(k), "M5": m5_bars(k)}


def spec():
    return yaml.safe_load(G.CONTRACT_PATH.read_text(encoding="utf-8"))


def test_report_verified_with_contract_and_engine_hash():
    r = G.build_report([case(), case("BTCUSD", 60000.0)], code_sha="X", generated_at="T")
    assert r["schema"] == "LOGIC_VERIFICATION_REPORT" and r["strategy"] == "ST_LARGE_SMC_V1@1.1.0"
    assert r["verdict"] == "LOGIC_VERIFIED"
    assert len(r["contract_sha256"]) == 64 and len(r["engine_sha256"]) == 64
    assert all(r["engine_file_sha256"].values()) and all(r["dependency_sha256"].values())
    assert r["cases"][1]["metadata_source"] == "HOST_CAPTURED" and r["cases"][1]["point"] == 0.01


def test_contract_drift_fails_l2():
    s = spec()
    s["instruments"] = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSDT", "ETHUSDT"]
    s["rules"]["sweep_to_choch_window_m5_bars"] = 10
    c = case()
    bad = {x["id"] for x in G.l2(s, c, evaluate_snapshot("EURUSD", c["D1"], c["H1"], c["M5"], NOW))["checks"]
           if x["verdict"] == "FAIL"}
    assert {"L2.instruments_vt_only", "L2.sweep_choch_window"} <= bad


def test_wrong_side_stop_fails_l3():
    c = case()
    snap = evaluate_snapshot("EURUSD", c["D1"], c["H1"], c["M5"], NOW)
    o = dict(snap.opportunity, stop_c10=snap.opportunity["entry_reference"] + 0.001)
    assert G.l3(c, dataclasses.replace(snap, opportunity=o))["status"] == "FAIL"


def test_stale_data_fails_l4():
    c = case(now=NOW + dt.timedelta(minutes=30))
    snap = evaluate_snapshot("EURUSD", c["D1"], c["H1"], c["M5"], c["now"])
    assert snap.state == "STALE" and G.l4(c, snap)["status"] == "FAIL"


def test_missing_capture_is_not_verified(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path))
    r = G.build_report([case()], code_sha="X", generated_at="T")
    assert r["verdict"] == "LOGIC_NOT_VERIFIED"
    assert r["cases"][0]["state"] == "DATA_ERROR" and set(r["cases"][0]["blocking_failures"]) >= {"L2", "L4"}


# ------------------------------------------------------------------ correlated READY (warn-only)

def test_legs():
    assert legs("EURUSD-VIP") == ("EUR", "USD") and legs("BTCUSDT") == ("BTC", "USD") and legs("X") is None


def test_same_sign_leg_exposure_warns_without_changing_decisions():
    sigs = [{"strategy_id": "A", "symbol": "EURUSD", "direction": "LONG", "decision": "READY"},
            {"strategy_id": "B", "symbol": "GBPUSD", "direction": "LONG", "decision": "WATCH_READY"},
            {"strategy_id": "C", "symbol": "USDJPY", "direction": "LONG", "decision": "READY"},
            {"strategy_id": "D", "symbol": "XAUUSD", "direction": "LONG", "decision": "NO_TRADE"}]
    before = [dict(s) for s in sigs]
    w = correlated_ready_warnings(sigs)
    assert sigs == before
    assert [(x["code"], x["leg"], x["exposure"], x["blocking"]) for x in w] == [(CORRELATED_READY, "USD", "SHORT", False)]
    assert [m["symbol"] for m in w[0]["members"]] == ["EURUSD", "GBPUSD"]


def test_opposite_exposure_and_single_symbol_do_not_warn():
    assert correlated_ready_warnings([
        {"symbol": "EURUSD", "direction": "LONG", "decision": "READY"},
        {"symbol": "USDJPY", "direction": "SHORT", "decision": "READY"},   # also short USD -> warns
    ])[0]["leg"] == "USD"
    assert correlated_ready_warnings([
        {"symbol": "EURUSD", "direction": "LONG", "decision": "READY"},
        {"symbol": "USDJPY", "direction": "LONG", "decision": "READY"},
        {"symbol": "EURUSD", "direction": "LONG", "decision": "READY"},
    ]) == []
