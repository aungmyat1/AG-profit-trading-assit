"""CCW-P1-REPLAY-01: replay ST_ASIAN_SWEEP_5R_V1@1.1.2 on the AGP-DATA-R3 60-weekday recorded files.

Drives the unchanged scripts/asw_v112_logic_verification.py harness with its D60_SYMBOLS routing,
one data scope per symbol (EURUSD alone, then EURUSD + each other symbol, as in AGP-C3-ASW-R2), and
takes each symbol's results from its own scope. Every case record carries the sha256 of the input
file it was replayed from. Per symbol x session, a gate with no positive example is INSUFFICIENT,
never PASS. Read-only and hermetic: no broker, network or MT5 call.

    python scripts/asw_v112_60d_replay.py --date 2026-10-10 --out docs/status/AGP_C3_ASW_V112_R2_60D_2026-10-10.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.asw_v112_logic_verification as h  # noqa: E402

SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
INSUFFICIENT = "INSUFFICIENT"
CASE_FIELDS = ("case_id", "cycle", "session_date", "fixture", "fixture_sha256", "setup", "direction", "entry",
               "stop_loss", "decision", "ticket_gate_status", "ticket_gate_blocking_failures", "l2_fail_ids",
               "l2_undeclared", "geometry", "causality", "owner_ticket_state",
               "owner_ticket_primary_block_reason", "owner_ticket_L6", "edge_verified", "day_type")


def file_sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def run_scope(symbol: str, date: str) -> dict:
    saved = h.SYMBOLS
    h.SYMBOLS = {k: h.D60_SYMBOLS[k] for k in dict.fromkeys(("EURUSD", symbol))}
    try:
        return h.build_report(f"{date}T00:00:00Z")
    finally:
        h.SYMBOLS = saved


def _revised(c: dict) -> bool:
    z = c["causality"]
    return bool(z["prefix_mismatches"] or z["pre_emission_signals"] or not z["streaming_hash_parity"]
                or z["future_mutation_mismatches"])


def rejection_reason(c: dict) -> str:
    if c["direction"] is None:
        return f"NO_SIGNAL:{c['day_type']}"
    fails = "+".join(c["ticket_gate_blocking_failures"]) or "NONE"
    rules = "+".join(c["l2_fail_ids"])
    return f"GATE:{fails}" + (f"({rules})" if rules else "")


def session_row(symbol: str, cycle: str, cases: list, symbol_gates: dict) -> dict:
    valid = [c for c in cases if c["ticket_gate_blocking_failures"] == []]
    rejected = [c for c in cases if c not in valid]
    l6 = [c["owner_ticket_L6"] for c in cases if c["owner_ticket_L6"]]
    mutations = sum(c["causality"]["future_mutations"] for c in cases)
    l4_bad = [c for c in cases if c["geometry"]["has_levels"]
              and not (c["geometry"]["positive_stop"] and c["geometry"]["target_order"])
              and c["ticket_gate_blocking_failures"] == []]
    gates = {
        "L1": "PASS" if symbol_gates["L1"] == "PASS" and all(
            c["ticket_gate_status"] is None or c["ticket_gate_status"]["L1"] == "PASS" for c in cases) else "FAIL",
        "L2": "FAIL" if any(c["l2_undeclared"] for c in cases) else (INSUFFICIENT if not valid else "PASS"),
        "L3": "FAIL" if any(_revised(c) for c in cases) else (INSUFFICIENT if not mutations else "PASS"),
        "L4": "FAIL" if l4_bad or symbol_gates["L4"] == "FAIL" else (INSUFFICIENT if not valid else "PASS"),
        # Harness L5: BLOCK (missing pip evidence) -> FAIL; WARN (cost not measurable) -> INSUFFICIENT.
        "L5": {"BLOCK": "FAIL", "WARN": INSUFFICIENT}.get(symbol_gates["L5"], symbol_gates["L5"]),
        "L6": INSUFFICIENT if not l6 else ("PASS" if set(l6) == {"PASS"} else "FAIL"),
    }
    return {"symbol": symbol, "session": cycle, "cases": len(cases), "valid_entries": len(valid),
            "valid_entry_case_ids": [c["case_id"] for c in valid],
            "rejections_by_reason": dict(sorted(Counter(rejection_reason(c) for c in rejected).items())),
            "gates": gates,
            "l3_revised_case_ids": [c["case_id"] for c in cases if _revised(c)]}


def build(date: str) -> dict:
    scopes, cases, matrix, symbol_gates, dataset = {}, [], [], {}, {}
    for sym in SYMBOLS:
        rep = run_scope(sym, date)
        scopes[sym] = {"verdicts": rep["verdicts"], "gates_by_symbol": rep["gates_by_symbol"],
                       "l5": rep["checks"]["L5_risk_and_friction"],
                       "l4_synthetic": rep["checks"]["L4_price_geometry"]["synthetic"],
                       "verification_code_sha": rep["verification_code_sha"]}
        spec = h.D60_SYMBOLS[sym]
        sha = file_sha256(spec["fixture"])
        dataset[sym] = {"path": spec["fixture"], "sha256": sha, "provenance": spec["provenance"],
                        "provenance_sha256_verified": rep["dataset_identity"][sym]["provenance_sha256_verified"]}
        day_type = rep["day_types"][sym]["by_case"]
        own = [c for c in rep["cases"] if c["case_id"].startswith(f"recorded:{sym}:")]
        for c in own:
            c["fixture_sha256"], c["day_type"] = sha, day_type[c["case_id"]]
        symbol_gates[sym] = rep["gates_by_symbol"][sym]
        cases += [{k: c.get(k) for k in CASE_FIELDS} for c in own]
        for cycle in h.CYCLES:
            matrix.append(session_row(sym, cycle, [c for c in own if c["cycle"] == cycle], symbol_gates[sym]))
        if sym == "EURUSD":
            ident = {k: rep[k] for k in ("strategy", "contract_path", "contract_hash", "engine_hash", "logic_identity")}
    return {
        "schema": "AG_ASW_V112_60D_REPLAY_V1", "mission": "CCW-P1-REPLAY-01", "date": date, **ident,
        "verification_basis": "AGP-DATA-R3 60-weekday recorded files (tests/fixtures/manual_ticket/*_spread_60d.csv)",
        "historical_only": ["tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv (5 days)",
                            "tests/fixtures/manual_ticket/GBPUSD_M15_recorded.csv (10 days)",
                            "tests/fixtures/manual_ticket/GBPUSD_M15_recorded_20d.csv (20 days)",
                            "tests/fixtures/manual_ticket/USDJPY_M15_recorded.csv (10 days)",
                            "tests/fixtures/manual_ticket/XAUUSD_M15_recorded.csv (10 days)",
                            "tests/fixtures/asian_sweep_v1_1_2/l4_recorded_failures.json (June-July dates)"],
        "spread_input": "harness TEST_SPREAD (0.2 pip); the 60d spread_points column is not consumed by the "
                        "unchanged harness, so cost-in-R stays unmeasured",
        "dataset_identity": dataset, "scopes": scopes, "symbol_gates": symbol_gates, "matrix": matrix,
        "cases": cases, "edge_verified": False, "registry_modified": False, "demo_authorized": False,
        "live_authorized": False, "broker_calls": 0, "ORDER_API_CALLS": 0, "BROKER_MUTATION_COUNT": 0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", help="write the evidence JSON here")
    args = ap.parse_args(argv)
    report = build(args.date)
    if args.out:
        cases = report.pop("cases")
        head = json.dumps(report, indent=1, sort_keys=True, default=str)[:-2]
        body = ",\n".join(json.dumps(c, sort_keys=True, default=str) for c in cases)
        (ROOT / args.out).write_text(f'{head},\n "cases": [\n{body}\n ]\n}}\n', encoding="utf-8")
        report["cases"] = cases
    for row in report["matrix"]:
        print(f"{row['symbol']} {row['session']:<15} cases={row['cases']} valid={row['valid_entries']} "
              + " ".join(f"{k}={v}" for k, v in row["gates"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
