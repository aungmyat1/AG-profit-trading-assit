"""Hermetic AGP-C4-CCFD-LOGIC replay. Manifest paths are relative to the manifest.

Recorded rerun: python scripts/ccfd_v100_logic_verification.py --fixtures PATH/manifest.json --out-dir work/ccfd-recorded
No network, broker acquisition, admission or generated-status writes.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
# Same strict import-only Linux portability shim as the existing ASW runner.
if "MetaTrader5" not in sys.modules:
    spec = importlib.util.spec_from_file_location("ccfd_portability", ROOT / "tests/conftest.py")
    spec.loader.exec_module(importlib.util.module_from_spec(spec))

from strategy_engine.session import Candle
from v1_tickets.ccfd_logic_gate import verify_case, STEPS
from v1_tickets.crypto_cfd_policy import load_ticket_policy
from v1_tickets.authority import logic_identity
from v1_tickets.code_identity import code_sha
from crypto_cfd_contract.contract import CONTRACT_ID, CONTRACT_VERSION

DEFAULT = ROOT / "tests/fixtures/ccfd_v100/synthetic/manifest.json"


def run(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    rows, hashes = [], {}
    recorded = manifest.get("source") == "MT5_VT_MARKETS_DEMO" and manifest.get("mission") == "AGP-DATA-R2"
    provenance_ok = recorded
    # Recorded admission requires a separate capture-side DATA-R2 provenance record.
    # Re-labelling the bundled synthetic corpus cannot produce recorded evidence.
    synthetic_hashes = {hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in DEFAULT.parent.glob("*.csv")}
    for case in manifest["cases"]:
        provenance = {}
        if recorded and case.get("provenance"):
            provenance = json.loads((manifest_path.parent / case["provenance"]).read_text())
        provenance_ok &= (provenance.get("source") == "MT5_VT_MARKETS_DEMO"
                          and provenance.get("mission") == "AGP-DATA-R2"
                          and provenance.get("symbol") == case["symbol"]
                          and provenance.get("recorded") is True
                          and bool(provenance.get("captured_at_utc")))
        candles = {}
        for timeframe in STEPS:
            path = manifest_path.parent / case["paths"][timeframe]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes[str(path.relative_to(manifest_path.parent))] = digest
            provenance_ok &= (provenance.get("sha256", {}).get(timeframe) == digest
                              and digest not in synthetic_hashes)
            with path.open() as f:
                candles[timeframe] = [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]),
                    *(float(r[k]) for k in ("open", "high", "low", "close"))) for r in csv.DictReader(f)]
        row = verify_case(case, candles, load_ticket_policy())
        rows.append({"id": case["id"], "symbol": case["symbol"], "window": case["window"], **row})
    required = {(s, d, w) for s in ("BTCUSD", "ETHUSD") for d in ("LONG", "SHORT")
                for w in ("WEEKDAY", "WEEKEND")}
    # Window labels are verified against the current ticket acquisition config.
    from v1_tickets.crypto_cfd import _config, _window
    _, windows = _config()
    covered = set()
    for case, row in zip(manifest["cases"], rows):
        good = all(g["status"] == "PASS" for g in row["gates"].values())
        window = _window(dt.datetime.fromisoformat(case["now"]), windows)
        row["window_matches_config"] = window == case["window"]
        if not row["window_matches_config"]:
            row["gates"]["L3"]["status"] = "FAIL"
        if good and row["window_matches_config"] and row["result"]["result"] == "ENTRY_VALID":
            covered.add((row["symbol"], row["result"]["evidence"]["target_plan"]["direction"], row["window"]))
    table = {}
    for name in ("L1", "L2", "L3", "L4", "L5", "L6"):
        statuses = {row["gates"][name]["status"] for row in rows}
        table[name] = ("FAIL" if "FAIL" in statuses else "NOT_EVIDENCED" if "NOT_EVIDENCED" in statuses
                       or not statuses else "WARN" if "WARN" in statuses else "PASS")
    uncovered = ["/".join(c) for c in sorted(required - covered)]
    eligible = provenance_ok and not uncovered and set(table.values()) == {"PASS"}
    verdict = "SYNTHETIC_ONLY" if not recorded else "LOGIC_VERIFIED" if eligible else "NOT_VERIFIED"
    return {"schema": "LOGIC_VERIFICATION_REPORT", "strategy_id": CONTRACT_ID,
            "strategy_version": CONTRACT_VERSION, "verdict": verdict, "head_sha": code_sha(),
            "logic_identity": logic_identity(CONTRACT_ID, CONTRACT_VERSION),
            "source": manifest.get("source"), "provenance_hashes_valid": bool(provenance_ok),
            "fixture_hashes": hashes, "gates": table, "uncovered_cases": uncovered,
            "recorded_uncovered_cases": ["/".join(c) for c in sorted(required)] if not provenance_ok else uncovered,
            "cases": rows, "NO_BROKER_MUTATION": True, "ORDER_API_CALLS": 0,
            "BROKER_MUTATION_COUNT": 0, "edge_verified": False, "execution_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "work/ccfd-v100")
    args = parser.parse_args()
    report = run(args.fixtures.resolve())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "LOGIC_VERIFICATION_REPORT.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: report[k] for k in ("verdict", "gates", "uncovered_cases", "NO_BROKER_MUTATION")}))
    return 0 if report["verdict"] == "LOGIC_VERIFIED" or (report["verdict"] == "SYNTHETIC_ONLY"
               and set(report["gates"].values()) == {"PASS"} and not report["uncovered_cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
