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
    asw = reg["ST_ASIAN_SWEEP_5R_V1"]["candidate_versions"]["1.1.2"]
    ccfd = reg["ST_CRYPTO_CFD_SWEEP_RETEST_V1"]["candidate_versions"]["1.0.0"]
    verified = [s for s in asw.get("logic_verified_scopes") or [] if s.get("status") == "LOGIC_VERIFIED"]
    suspended = list(asw.get("logic_suspended_scopes") or [])
    stale = ([(s["symbol"], b) for s in ccfd["logic_verified_symbols"] for b in s["branches"]]
             if ccfd.get("logic_status") == "STALE_IDENTITY" else [])
    return verified, suspended, stale


def test_committed_outputs_are_byte_reproducible():
    assert vl.main(["--check"]) == 0
    assert json.dumps(vl.build(), sort_keys=True) == json.dumps(vl.build(), sort_keys=True)


def test_ledger_counts_match_the_registry_records():
    verified, suspended, stale = _registry_records()
    assert (len(verified), len(suspended), len(stale)) == (1, 1, 3)
    rows = vl.build()["rows"]
    lv = [r for r in rows if r["registry_status"] == "LOGIC_VERIFIED"]
    assert [(r["symbol"], r["session"], r["branch"]) for r in lv] == [("GBPUSD", "ASIAN_LONDON", "RANGE_SWEEP")]
    # OD1014-FAST D5: the one suspended record is scoped to EURUSD x ASIAN_LONDON
    assert [(r["symbol"], r["session"]) for r in rows if r["registry_status"] == "SUSPENDED"] == [
        ("EURUSD", "ASIAN_LONDON")]
    assert vl.build()["status_counts"] == {"LOGIC_VERIFIED": 1, "STALE_IDENTITY": 3, "SUSPENDED": 1, "UNVERIFIED": 13}
    assert sorted((r["symbol"], r["branch"]) for r in rows if r["registry_status"] == "STALE_IDENTITY") == sorted(stale)


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
