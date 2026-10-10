"""AGP-LANE-B replay runner for ST_CRYPTO_CFD_SWEEP_RETEST_V1 on the VT recorded fixtures (#128/#131).

Runs one weekend day plus the ETHUSD ENTRY_VALID weekday (2026-10-04/05) to stay fast; the full
14-day run is the committed artifact.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ccfd_sweep_retest_replay as R  # noqa: E402

DAYS = [dt.date(2026, 10, 4), dt.date(2026, 10, 5)]
ARTIFACT = R.OUT_DIR / "replay_report.json"


@pytest.fixture(scope="module")
def eth():
    return R.build("2026-10-10", symbols=("ETHUSD",), days=DAYS)


def test_replay_runs_weekend_and_weekday_with_zero_mismatches(eth):
    s = eth["symbols"]["ETHUSD"]
    assert eth["weekend_days"] == ["2026-10-04"] and s["scans"] == 2 * 288
    assert sum(s["mismatches"].values()) == 0
    assert s["gates"] == {"L1": "PASS", "L2": "PASS", "L3": "PASS", "L4": "PASS", "L5": "WARN", "L6": "PASS"}
    assert s["fetch_counts"] == {"D1": 50, "H1": 100, "M15": 96, "M5": 576}   # taken from the live cycle
    assert s["prefix_invariance"]["source"].startswith("TEMP_INLINE")


def test_emission_ticket_uses_existing_schema_and_owner_band(eth):
    em = eth["symbols"]["ETHUSD"]["emissions"]
    assert [(e["now"], e["direction"]) for e in em] == [("2026-10-05T18:10:00+00:00", "LONG")]
    e = em[0]
    assert 10 < e["spread_pct_of_stop"] <= 20 and e["spread_band"] == "WARN"
    assert e["ticket_decision"] == "BLOCKED" and "SPREAD_WARN" in e["ticket_warnings"]
    assert "LOGIC_STATUS_NOT_VERIFIED" in e["ticket_reason_codes"]      # registry active:false holds
    assert e["live_cycle_reason_codes"] == ["OUTSIDE_CONFIG_WINDOW"]
    t = next(x for x in eth["_tickets"] if x["stream"] == "EMISSION_RESEARCH")["ticket"]
    assert t["strategy_id"] == "ST_CRYPTO_CFD_SWEEP_RETEST_V1" and t["execution_authorized"] is False
    assert {"decision", "reason_codes", "warnings", "engine_result", "spread_pct_of_stop", "valid_until"} <= set(t)


def test_spread_band_changes_ticket_state_not_logic_verdict(eth, monkeypatch):
    tight = {**R.load_ticket_policy(), "spread_ok_pct": 5.0, "spread_block_pct": 10.0}
    monkeypatch.setattr(R, "load_ticket_policy", lambda: tight)
    again = R.build("2026-10-10", symbols=("ETHUSD",), days=[dt.date(2026, 10, 5)])
    s = again["symbols"]["ETHUSD"]
    assert s["emissions"][0]["spread_band"] == "BLOCK"
    assert "SPREAD_TOO_WIDE" in s["emissions"][0]["ticket_reason_codes"]
    assert s["gates"] == eth["symbols"]["ETHUSD"]["gates"]


def test_prefix_check_flags_a_revised_emission():
    t0 = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc)
    entry = {"result": "ENTRY_VALID", "sweep": 1, "mss": 2, "retest": 3, "target_plan": 4}
    stream = [(t0, {"result": "WAITING_SWEEP"}), (t0 + R.M5, entry), (t0 + 2 * R.M5, {**entry, "target_plan": 5})]
    out = R.prefix_invariance_temp(stream)
    assert out["prefix_mismatches"] == 1 and out["verdict"] == "FAIL"


def test_registry_untouched_and_no_broker_imports(eth):
    assert eth["registry"] == {"active": False, "research": True, "modified": False}
    tree = ast.parse((ROOT / "scripts/ccfd_sweep_retest_replay.py").read_text(encoding="utf-8"))
    names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {"order_send", "order_check"} & names
    assert not any(m and (m.startswith("execution") or m.startswith("mt5")) for m in mods)


def test_committed_artifact_is_consistent():
    rep = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert len(rep["days_run"]) == 14 and len(rep["weekend_days"]) == 4
    assert rep["registry"] == {"active": False, "research": True, "modified": False}
    lines = (R.OUT_DIR / "tickets.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == rep["tickets_total"]
    for sym in ("BTCUSD", "ETHUSD"):
        assert sum(rep["symbols"][sym]["mismatches"].values()) == 0


def test_btcusd_logic_verified_record_is_bound_to_identity_and_evidence():
    import yaml

    from v1_tickets.authority import logic_identity
    from v1_tickets.ready_authority import symbol_verified

    rep = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert rep["logic_verification"]["BTCUSD"]["all_checks_pass"] is True
    assert all(d["failure_class"] is None for d in rep["symbols"]["BTCUSD"]["per_day"].values())
    entry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))["strategies"][
        "ST_CRYPTO_CFD_SWEEP_RETEST_V1"]
    assert entry["active"] is False and entry["research"] is True
    rec = entry["candidate_versions"]["1.0.0"]
    digest = logic_identity("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0")["digest"]
    assert rec["logic_verified_identity"] == digest == rep["logic_verification"]["BTCUSD"]["logic_identity"]["digest"]
    assert [s["symbol"] for s in rec["logic_verified_symbols"]] == ["BTCUSD"]
    assert (ROOT / rec["logic_verified_symbols"][0]["evidence"]).is_file()
    assert symbol_verified("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0", "BTCUSD") is True
    assert symbol_verified("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0", "ETHUSD") is False
