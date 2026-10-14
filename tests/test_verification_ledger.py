"""AGP-C20 T1: the verification ledger is read-only, byte-reproducible and agrees with the registry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verification_ledger as vl  # noqa: E402

from v1_tickets.authority import load_registry  # noqa: E402


def _registry_records():
    reg = load_registry()
    asw = reg["ST_ASIAN_SWEEP_5R_V1"]["candidate_versions"]
    ccfd = reg["ST_CRYPTO_CFD_SWEEP_RETEST_V1"]["candidate_versions"]["1.0.0"]
    verified = {v: [s for s in asw[v].get("logic_verified_scopes") or [] if s.get("status") == "LOGIC_VERIFIED"]
                for v in ("1.1.2", "1.1.3")}
    suspended = list(asw["1.1.2"].get("logic_suspended_scopes") or [])
    ccfd_scopes = [(s["symbol"], b) for s in ccfd["logic_verified_symbols"] for b in s["branches"]]
    return verified, suspended, ccfd_scopes, ccfd["logic_status"]


def test_committed_outputs_are_byte_reproducible():
    assert vl.main(["--check"]) == 0
    assert json.dumps(vl.build(), sort_keys=True) == json.dumps(vl.build(), sort_keys=True)


def test_ledger_counts_match_the_registry_records():
    verified, suspended, ccfd_scopes, ccfd_status = _registry_records()
    assert (len(verified["1.1.2"]), len(verified["1.1.3"]), len(suspended)) == (1, 4, 1)      # OD1014-FAST D9
    assert sorted(ccfd_scopes) == [("BTCUSD", "SHORT"), ("ETHUSD", "LONG"), ("ETHUSD", "SHORT")]
    assert ccfd_status == "LOGIC_VERIFIED"                                                       # OD1014-FAST D8
    ledger = vl.build()
    rows = ledger["rows"]
    lv = sorted((r["strategy"], r["symbol"], r["session"]) for r in rows if r["registry_status"] == "LOGIC_VERIFIED")
    # Rows carry the version each report lane runs: S1 on v1.1.2, EURUSD x ASIAN_LONDON on v1.1.3 (D3/D9).
    assert lv == [("ST_ASIAN_SWEEP_5R_V1@1.1.2", "GBPUSD", "ASIAN_LONDON"),
                  ("ST_ASIAN_SWEEP_5R_V1@1.1.3", "EURUSD", "ASIAN_LONDON")]
    # The v1.1.2 EURUSD x ASIAN_LONDON suspension is unchanged but that scope's lane now runs v1.1.3.
    assert not [r for r in rows if r["registry_status"] == "SUSPENDED"]
    # CCFD: identity re-recorded (D8) but the registry records no window, so tickets never claim verification.
    ccfd = {(r["symbol"], r["branch"]): r for r in rows if r["family"] == "crypto_cfd"}
    for key in ccfd_scopes:
        assert (ccfd[key]["registry_status"], ccfd[key]["blocking_finding_id"]) == ("UNVERIFIED", "WINDOW_NOT_IN_SCOPE")
    assert ledger["status_counts"] == {"LOGIC_VERIFIED": 2, "UNVERIFIED": 16}


def test_universe_is_od1012_without_audusd_and_nothing_is_inferred():
    rows = vl.build()["rows"]
    assert len(rows) == 18 and not any(r["symbol"] == "AUDUSD" for r in rows)
    lsmc = [r for r in rows if r["family"] == "large_smc"]
    assert all(set(r["gates"].values()) == {"UNKNOWN"} for r in lsmc)
    assert [r["symbol"] for r in lsmc if r["evidence_path"] != "UNKNOWN"] == ["EURUSD"]
    btc_long = next(r for r in rows if r["symbol"] == "BTCUSD" and r["branch"] == "LONG")
    assert btc_long["registry_status"] == "UNVERIFIED" and btc_long["next_action_owner"] == "DATA_INSUFFICIENT"
    ccfd = [r for r in rows if r["family"] == "crypto_cfd" and r["evidence_path"] != "UNKNOWN"]
    assert all(r["evidence_sha256"] == r["evidence_sha256_recorded"] for r in ccfd)
