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
    assert s["gates"] == {"L1": "PASS", "L2": "PASS", "L3": "PASS", "L4": "PASS", "L5": "PASS", "L6": "PASS"}
    assert s["fetch_counts"] == {"D1": 50, "H1": 100, "M15": 96, "M5": 576}   # taken from the live cycle
    assert s["signal_events"]["source"].startswith("TEMP_INLINE")          # TEMP until AGP-ORACLE
    assert s["gate_evidence"]["l5_od1011"][0]["commission_source"] == "OD1011-COMMISSION"


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


def test_branch_scoped_logic_verified_record_is_bound_to_identity_and_evidence():
    """AGP-LANE-B3 (owner rulings 2026-10-11): LOGIC_VERIFIED per symbol x branch (OD1011-SCOPE) only where the
    60-day VT run verifies the branch (L1-L4/L6 PASS, L5 PASS per OD1011-L5, 0 event-log mismatches, every rule
    cell VT EXERCISED or SYNTHETIC_PROVEN); the 14-day run must pass too. Nothing else in the entry changes."""
    import hashlib

    import yaml

    from v1_tickets.authority import logic_identity
    from v1_tickets.ready_authority import symbol_verified

    rep14 = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    path60 = R.DATASETS["recorded_60d"][1] / "replay_report.json"
    rep60 = json.loads(path60.read_text(encoding="utf-8"))
    entry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))["strategies"][
        "ST_CRYPTO_CFD_SWEEP_RETEST_V1"]
    assert entry["active"] is False and entry["research"] is True
    assert entry["demo_authorized"] is False and entry["live_authorized"] is False and "logic_status" not in entry
    version = entry["candidate_versions"]["1.0.0"]
    digest = logic_identity("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0")["digest"]
    assert version["logic_status"] == "LOGIC_VERIFIED" and version["logic_verified_identity"] == digest
    assert version["edge_verified"] is False
    listed = {e["symbol"]: e for e in version["logic_verified_symbols"]}
    for sym in ("BTCUSD", "ETHUSD"):
        assert rep14["logic_verification"][sym]["all_checks_pass"] is True
        assert rep60["logic_verification"][sym]["all_checks_pass"] is True
        verified = [b for b in R.BRANCHES if rep60["logic_verification"][sym]["branches"][b]["verified"]]
        assert listed[sym]["branches"] == verified
        assert listed[sym]["logic_identity"] == digest == rep60["logic_verification"][sym]["logic_identity"]["digest"]
        assert listed[sym]["evidence"] == path60.relative_to(ROOT).as_posix()
        assert listed[sym]["evidence_sha256"] == hashlib.sha256(path60.read_bytes()).hexdigest()
        assert symbol_verified("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0", sym) is True
    assert listed["BTCUSD"]["branches"] == ["SHORT"] and listed["ETHUSD"]["branches"] == ["LONG", "SHORT"]
    assert rep60["logic_verification"]["BTCUSD"]["branches"]["LONG"]["entry_valid_scans"] == 0


def test_no_crypto_ticket_is_actionable_with_the_record():
    """The record grants no ticket authority: active:false keeps every ENTRY_VALID ticket BLOCKED with
    LOGIC_STATUS_NOT_VERIFIED (so the reader not yet enforcing `branches` cannot open BTCUSD LONG)."""
    for out in (R.OUT_DIR, R.DATASETS["recorded_60d"][1]):
        for line in (out / "tickets.jsonl").read_text(encoding="utf-8").splitlines():
            t = json.loads(line)["ticket"]
            assert t["decision"] != "READY" and t["owner_accept_allowed"] is False
            if (t.get("engine_result") or {}).get("result") == "ENTRY_VALID":
                assert "LOGIC_STATUS_NOT_VERIFIED" in t["reason_codes"]
