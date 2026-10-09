"""Emit LOGIC_VERIFICATION_REPORT for ST_LARGE_SMC_V1@1.1.0 (AGP-C1-LSMC).

Read-only. Cases: the 1.1.0 synthetic watch fixtures (tests/_lsmc_v110_fixtures.py, scaled per
VT symbol) and the per-symbol 1.1.1 audit fixtures (tests/fixtures/large_smc_v111/, the
BTCUSDT/ETHUSDT price series evaluated under the VT symbols BTCUSD/ETHUSD). Points come from
the committed VT host captures (config/symbol_metadata/host_captured). No broker, no network.

    python scripts/lsmc_v110_logic_verification.py [--out PATH.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
os.environ["AG_EVIDENCE_ROOT"] = str(ROOT)   # committed VT host captures only

# Reuse the import-only Linux MetaTrader5 portability shim (as audit_lsmc_v111_candidate.py). No MT5 call.
if "MetaTrader5" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("lsmc_gate_test_conftest", ROOT / "tests/conftest.py")
    if _spec is not None and _spec.loader is not None:
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))

from _lsmc_v110_fixtures import NOW, UTC, d1_bars, h1_bars, m5_bars  # noqa: E402
from _lsmc_v111_fixtures import fixture_manifest, load_fixture  # noqa: E402
from v1_tickets.code_identity import code_sha  # noqa: E402
from v1_tickets.lsmc_logic_gate import build_report  # noqa: E402

V110_SCALE = {"EURUSD": 1.0, "GBPUSD": 1.2, "USDJPY": 140.0, "XAUUSD": 2400.0, "BTCUSD": 60000.0, "ETHUSD": 3000.0}
NEAR = dt.datetime(2026, 1, 6, 8, 35, tzinfo=UTC)
VT_NAME = {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"}


def cases():
    out = []
    for sym, k in V110_SCALE.items():
        for label, now in (("OPPORTUNITY", NOW), ("NEAR_POI", NEAR)):
            out.append({"case_id": f"v110_synthetic:{sym}:{label}", "symbol": sym, "now": now,
                        "fixture": "tests/_lsmc_v110_fixtures.py", "classification": "SYNTHETIC",
                        "D1": d1_bars(k), "H1": h1_bars(k), "M5": m5_bars(k)})
    classes = {s["symbol"]: s["classification"] for s in fixture_manifest()["sources"]}
    for src in classes:
        bars = load_fixture(src)
        sym = VT_NAME.get(src, src)
        out.append({"case_id": f"v111_fixture:{src}->{sym}", "symbol": sym, "now": bars["evaluated_at"],
                    "fixture": bars["fixture_file"], "classification": classes[src],
                    "D1": bars["D1"], "H1": bars["H1"], "M5": bars["M5"]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args(argv)
    report = build_report(cases(), code_sha=code_sha(),
                          generated_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat())
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(f"{report['schema']} {report['strategy']} verdict={report['verdict']}")
    print(f"contract_sha256={report['contract_sha256']} engine_sha256={report['engine_sha256']}")
    for c in report["cases"]:
        print(f"  {c['case_id']:<42} state={c['state']:<12} gates={c['gate_status']} fail={c['blocking_failures']}")
    return 0 if report["verdict"] == "LOGIC_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
