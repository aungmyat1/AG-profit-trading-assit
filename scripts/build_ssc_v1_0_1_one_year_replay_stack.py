"""Mission 1 / P2 + P8 -- build and freeze ONE_YEAR_REPLAY_STACK_V1.

Read-only admission builder. Assembles the one-year SSC v1.0.1 replay stack from
ALREADY-ADMITTED assets, verifies every identity from bytes, delegates cross-leg
timebase arbitration to the existing P3 gate
(`scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` -- not reimplemented
here), proves warmup readiness (P4, `historical_replay.warmup_readiness` +
`historical_replay.warmup_merge`), asserts the protected-data firewall from the frozen
lineage map, rejects any quarantined dataset (P5, GEN_002), and emits the freeze
manifest. It does NOT execute any replay and does NOT evaluate economics.

Fail-closed: any failed gate -> non-zero exit and NO freeze manifest written.

Run (repo root):
    python scripts/build_ssc_v1_0_1_one_year_replay_stack.py [--check]
    --check  : verify only, never write the freeze manifest

Output:
    artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/
        ONE_YEAR_REPLAY_STACK_V1.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from historical_replay.mt5_export_loader import load_mt5_export_csv  # noqa: E402
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from historical_replay.warmup_merge import merge_warmup_and_decision_window  # noqa: E402
from historical_replay.warmup_readiness import closed_h1_bar_count  # noqa: E402

SCHEMA = "AG_SSC_ONE_YEAR_REPLAY_STACK_V1"
STACK_ID = "ONE_YEAR_REPLAY_STACK_V1"
SYMBOL = "EURUSD"
STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION = "1.0.1"

WINDOW_START = datetime(2025, 9, 15, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)
REQUIRED_H1_WARMUP_BARS = 1000  # market_structure.tiers.analyze_structure_tiers warmup requirement

M1_PATH = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_M1_001/raw/EURUSD_M1.csv"
M1_EXPECTED_SHA256 = "50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a"

DERIVED_H1_PATH = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_H1.csv"
DERIVED_M15_PATH = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_M15.csv"
H1_EXPECTED_SHA256 = "4eb522945697773ed34d1b8d47ab928b9e94e99828dade88db18fe186905e288"
M15_EXPECTED_SHA256 = "c9833427404d8634d8cf57b000017ecea7ad865ab22db4eadedacb80de9b6956"

WARMUP_H1_PATH = Path(r"D:\EURUSD_H1_202501020000_202607310000.csv")
WARMUP_H1_EXPECTED_SHA256 = None  # EXTERNAL_D_ROOT source; identity is the cross-leg gate's own +0h/1.0 admission, not a frozen repo hash

GEN_002_PACKAGE_DIR = REPO / "data/research/ssc_fresh_dev/SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914"
GEN_002_QUARANTINE_RECORD = GEN_002_PACKAGE_DIR / "GEN_002_QUARANTINE_RECORD_V1.json"

LINEAGE_MAP_PATH = REPO / "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/LINEAGE_CONTAMINATION_MAP_V1.json"

OUT_DIR = REPO / "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gate(name: str, ok: bool, detail: str, errors: list) -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    if not ok:
        errors.append(f"{name}: {detail}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify only; never write freeze manifest")
    args = ap.parse_args()

    errors: list = []

    # ---- P5: GEN_002 quarantine must exist and be cited; no GEN_002 leg is ever an input here ----
    quarantined = json.loads(GEN_002_QUARANTINE_RECORD.read_text(encoding="utf-8")) if GEN_002_QUARANTINE_RECORD.exists() else None
    gate("GEN_002_QUARANTINE_RECORD_PRESENT", quarantined is not None,
         str(GEN_002_QUARANTINE_RECORD.relative_to(REPO)), errors)
    stack_input_paths = {M1_PATH, DERIVED_H1_PATH, DERIVED_M15_PATH, WARMUP_H1_PATH}
    gate("GEN_002_NOT_A_STACK_INPUT", not any(str(GEN_002_PACKAGE_DIR) in str(p) for p in stack_input_paths),
         "no stack leg resolves inside the quarantined GEN_002 package directory", errors)

    # ---- P2: identity-verify every leg from bytes ----
    m1_actual = sha256_file(M1_PATH)
    gate("M1_IDENTITY", m1_actual == M1_EXPECTED_SHA256, f"sha256 {m1_actual[:16]}..", errors)
    h1_actual = sha256_file(DERIVED_H1_PATH)
    gate("H1_IDENTITY", h1_actual == H1_EXPECTED_SHA256, f"sha256 {h1_actual[:16]}..", errors)
    m15_actual = sha256_file(DERIVED_M15_PATH)
    gate("M15_IDENTITY", m15_actual == M15_EXPECTED_SHA256, f"sha256 {m15_actual[:16]}..", errors)
    warmup_present = WARMUP_H1_PATH.exists()
    gate("WARMUP_SOURCE_PRESENT", warmup_present, str(WARMUP_H1_PATH), errors)

    if errors:
        print("\nADMISSION FAILED at identity gates -- no freeze manifest written (fail closed):")
        for e in errors:
            print("  -", e)
        return 1

    m1_candles, m1_report = load_utc_export_csv(str(M1_PATH), SYMBOL, "M1")
    h1_candles, _ = load_utc_export_csv(str(DERIVED_H1_PATH), SYMBOL, "H1")
    m15_candles, _ = load_utc_export_csv(str(DERIVED_M15_PATH), SYMBOL, "M15")
    warmup_candles, _ = load_mt5_export_csv(str(WARMUP_H1_PATH), SYMBOL, "H1")

    # ---- P3: delegate to the existing cross-leg timebase gate (single authority; not reimplemented) ----
    audit_script = REPO / "scripts" / "audit_ssc_v1_0_1_one_year_cross_leg_consistency.py"
    proc = subprocess.run([sys.executable, str(audit_script)], capture_output=True, text=True, cwd=str(REPO))
    cross_leg_pass = proc.returncode == 0 and "CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW" in proc.stdout
    gate("CROSS_LEG_TIMEBASE_CONSISTENT", cross_leg_pass,
         f"audit exit={proc.returncode}", errors)

    coverage_script = REPO / "scripts" / "audit_ssc_v1_0_1_one_year_data_coverage.py"
    proc2 = subprocess.run([sys.executable, str(coverage_script)], capture_output=True, text=True, cwd=str(REPO))
    coverage_pass = proc2.returncode == 0 and "DATA_COVERAGE_COMPLETE" in proc2.stdout
    gate("DATA_COVERAGE_COMPLETE", coverage_pass, f"audit exit={proc2.returncode}", errors)

    # ---- P4: warmup readiness + convergence (merge WARMUP_CONTEXT_ONLY H1 in front of the decision window) ----
    merged_h1 = merge_warmup_and_decision_window(warmup_candles, h1_candles)
    first_decision = WINDOW_START
    bars_before = closed_h1_bar_count(merged_h1, first_decision)
    warmup_sufficient = bars_before >= REQUIRED_H1_WARMUP_BARS
    gate("WARMUP_SUFFICIENT_AT_FIRST_DECISION", warmup_sufficient,
         f"{bars_before} closed H1 bars before {first_decision.isoformat()} (min {REQUIRED_H1_WARMUP_BARS})", errors)
    warmup_status = "WARMUP_STABLE" if warmup_sufficient else "WARMUP_INSUFFICIENT"
    gate("WARMUP_STATUS", warmup_sufficient, warmup_status, errors)

    # ---- P6: protected-data firewall -- reuse the frozen lineage map's safety block ----
    lineage_map = json.loads(LINEAGE_MAP_PATH.read_text(encoding="utf-8"))
    safety = lineage_map.get("safety", {})
    protected_clear = not any(safety.get(k) for k in ("CONFIRM_001_ACCESSED", "HOLDOUT_ACCESSED", "OOS_ACCESSED", "PROTECTED_DATA_ACCESSED"))
    gate("PROTECTED_DATA_FIREWALL", protected_clear, f"safety={safety}", errors)
    protected_access_count = sum(1 for k in ("CONFIRM_001_ACCESSED", "HOLDOUT_ACCESSED", "OOS_ACCESSED") if safety.get(k))

    report = {
        "schema": SCHEMA, "stack_id": STACK_ID, "symbol": SYMBOL,
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "window": {"start_utc": WINDOW_START.isoformat(), "end_utc": WINDOW_END.isoformat()},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "M1": {
                "dataset_id": "SSC_V1_0_1_HIST_1Y_M1_001", "role": "FILL_RESOLUTION_INPUT",
                "sha256": m1_actual, "rows": len(m1_candles),
                "range_utc": [m1_candles[0].time.isoformat(), m1_candles[-1].time.isoformat()],
                "source_lineage": "native MT5 broker export (VantageMarkets-Demo), UTC-normalized per-week reopen",
                "timezone_authority": "BROKER_SERVER_TIME(UTC+2/UTC+3 seasonal, per-week reopen) -> normalized UTC",
            },
            "M15": {
                "dataset_id": "SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::M15", "role": "STRATEGY_DECISION_INPUT",
                "sha256": m15_actual, "rows": len(m15_candles),
                "range_utc": [m15_candles[0].time.isoformat(), m15_candles[-1].time.isoformat()],
                "source_lineage": "deterministic exact-UTC-bucket derivation from SSC_V1_0_1_HIST_1Y_M1_001 (historical_replay.m1_derivation, NATIVE_FAITHFUL_INCLUSIVE policy)",
                "timezone_authority": "normalized UTC from canonical M1 (derived, zero shift by construction)",
            },
            "H1": {
                "dataset_id": "SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::H1", "role": "MARKET_BIAS_INPUT",
                "sha256": h1_actual, "rows": len(h1_candles),
                "range_utc": [h1_candles[0].time.isoformat(), h1_candles[-1].time.isoformat()],
                "source_lineage": "deterministic exact-UTC-bucket derivation from SSC_V1_0_1_HIST_1Y_M1_001 (historical_replay.m1_derivation, NATIVE_FAITHFUL_INCLUSIVE policy)",
                "timezone_authority": "normalized UTC from canonical M1 (derived, zero shift by construction)",
            },
            "WARMUP_H1": {
                "dataset_id": "EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv", "role": "WARMUP_CONTEXT_ONLY",
                "sha256": sha256_file(WARMUP_H1_PATH), "rows": len(warmup_candles),
                "range_utc": [warmup_candles[0].time.isoformat(), warmup_candles[-1].time.isoformat()],
                "source_lineage": "owner-approved external MT5 export (config/historical_datasets/EURUSD_H1_symbol_metadata.yaml, dataset_fingerprint sha256:f1b456e4...); independently proven +0h/exact=1.000000/DST_CONSISTENT against the M1 arbiter",
                "timezone_authority": "BROKER_SERVER_TIME(UTC+2/UTC+3 seasonal) -> normalized UTC, +0h shift verified",
                "declared_scope": "WARMUP_CONTEXT_ONLY -- supplies pre-window H1 history only; the decision-window H1 leg above remains the sole MARKET_BIAS_INPUT authority",
            },
        },
        "gates": {
            "DATA_COVERAGE": "DATA_COVERAGE_COMPLETE" if coverage_pass else "FAIL",
            "CROSS_LEG_TIMEBASE": "CROSS_LEG_TIMEBASE_CONSISTENT" if cross_leg_pass else "FAIL",
            "WARMUP": warmup_status,
            "WARMUP_BARS_BEFORE_FIRST_DECISION": bars_before,
            "GEN_002_QUARANTINE_ENFORCED": True,
            "PROTECTED_DATA_ACCESS_COUNT": protected_access_count,
        },
        "status": "PROPOSED",
    }

    if errors:
        print("\nADMISSION FAILED -- no freeze manifest written (fail closed):")
        for e in errors:
            print("  -", e)
        report["status"] = "ADMISSION_FAILED"
        return 1

    if args.check:
        print("\n--check: all gates PASS; freeze manifest NOT written.")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{STACK_ID}.json"
    report["status"] = "FROZEN"
    canonical = json.dumps({k: v for k, v in report.items() if k != "manifest_sha256"}, sort_keys=True, separators=(",", ":"), default=str)
    report["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nFROZE {out_path}\nmanifest_sha256 = {report['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
