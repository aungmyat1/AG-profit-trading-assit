#!/usr/bin/env python3
"""DRAFT — Mission 1 / P2: build and freeze ONE_YEAR_REPLAY_STACK_V1.

Read-only admission builder. Assembles the one-year replay stack from ALREADY-ADMITTED
assets, verifies every identity from bytes, runs the cross-leg timebase arbiter (P3),
proves warmup readiness (P4), asserts the protected-data firewall, and emits the
freeze manifest. It does NOT execute any replay and does NOT evaluate economics.

Design rules encoded (mirrors scripts/audit_ssc_v1_0_1_one_year_data_coverage.py):
  * no interpolation, no manufactured bars, no M5-for-M1 substitution
  * no provider mixing without declared lineage
  * protected datasets are metadata-only; content access asserted == 0
  * any failed gate -> non-zero exit and NO freeze manifest written (fail closed)

Run (repo root):
    python scripts/build_ssc_v1_0_1_one_year_replay_stack.py [--check]
    --check  : verify only, never write the freeze manifest

Outputs:
    artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/
        ONE_YEAR_REPLAY_STACK_V1.json

Integration notes for the executing agent:
  - Reuse historical_replay.utc_export_csv_loader.load_utc_export_csv for the
    timestamp_utc CSV family (M1, derived H1/M15). Reuse mt5_export_loader for any
    broker-local-time export -- do not re-implement loaders.
  - Timebase arbitration must call the P3 arbiter (single authority), not re-derive.
  - Fill the <FILL> fields in the emitted manifest from measured values only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from historical_replay.candle_store import TIMEFRAME_MINUTES  # noqa: E402
from historical_replay.timebase_arbiter import arbitrate  # noqa: E402  (P3 component)
from historical_replay.warmup_readiness import closed_h1_bar_count  # noqa: E402

SCHEMA = "AG_SSC_ONE_YEAR_REPLAY_STACK_V1"
STACK_ID = "ONE_YEAR_REPLAY_STACK_V1"
SYMBOL = "EURUSD"
STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION = "1.0.1"

WINDOW_START = datetime(2025, 9, 15, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

# Expected identities -- VERIFIED FROM BYTES AT RUNTIME, never trusted from this file.
# Values recorded here are the admission preimage for comparison.
M1_PATH = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_M1_001/raw/EURUSD_M1.csv"
M1_EXPECTED_SHA256 = "50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a"

H1_DERIVED = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_H1.csv"
M15_DERIVED = REPO / "data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_M15.csv"
H1_EXPECTED_SHA256 = "4eb522945697773ed34d1b8d47ab928b9e94e99828dade88db18fe186905e288"

MIN_H1_WARMUP_BARS = 1000  # SSC canonical minimum (warmup_readiness authority)


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
    report = {
        "schema": SCHEMA, "stack_id": STACK_ID, "symbol": SYMBOL,
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "window": {"start_utc": WINDOW_START.isoformat(), "end_utc": WINDOW_END.isoformat()},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PROPOSED",
    }

    # ---- Load and identity-verify the M1 authority from bytes -------------------
    m1_actual = sha256_file(M1_PATH)
    gate("M1_IDENTITY", m1_actual == M1_EXPECTED_SHA256,
         f"sha256 {m1_actual[:16]}.. expected {M1_EXPECTED_SHA256[:16]}..", errors)
    m1_candles, m1_report = load_utc_export_csv(str(M1_PATH), SYMBOL, "M1")
    gate("M1_QUALITY", m1_report.quality_status == "PASS", f"{m1_report.quality_status}", errors)

    # ---- Load derived H1/M15 and verify they are exact M1 aggregations ----------
    h1_actual = sha256_file(H1_DERIVED)
    gate("H1_IDENTITY", h1_actual == H1_EXPECTED_SHA256, f"sha256 {h1_actual[:16]}..", errors)
    h1_candles, _ = load_utc_export_csv(str(H1_DERIVED), SYMBOL, "H1")
    m15_candles, _ = load_utc_export_csv(str(M15_DERIVED), SYMBOL, "M15")

    v_h1 = arbitrate(m1_candles, h1_candles, TIMEFRAME_MINUTES["H1"])
    v_m15 = arbitrate(m1_candles, m15_candles, TIMEFRAME_MINUTES["M15"])
    gate("CROSS_LEG_TIMEBASE_H1", v_h1.admissible,
         f"{v_h1.status} shift={v_h1.best_shift_hours} rate={v_h1.exact_match_rate:.6f}", errors)
    gate("CROSS_LEG_TIMEBASE_M15", v_m15.admissible,
         f"{v_m15.status} shift={v_m15.best_shift_hours} rate={v_m15.exact_match_rate:.6f}", errors)

    # ---- Warmup readiness (actual closed-bar counting, not calendar hours) ------
    # The warmup source is a declared WARMUP_CONTEXT_ONLY leg. In the final wiring the
    # agent concatenates [warmup H1] + [derived decision-window H1] and evaluates the
    # SSC decision points. Here we assert the minimum is reachable at the FIRST decision
    # time using whatever H1 history precedes it.
    first_decision = WINDOW_START  # agent: replace with the true first SSC decision instant
    bars_before = closed_h1_bar_count(h1_candles, first_decision)
    gate("WARMUP_READINESS", bars_before >= MIN_H1_WARMUP_BARS,
         f"{bars_before} closed H1 bars before first decision (min {MIN_H1_WARMUP_BARS})", errors)

    # ---- Protected-data firewall: content access must remain zero ---------------
    # Metadata-only inspection of protected manifests is permitted; we assert their
    # recorded access counters are unchanged (0). Agent: enumerate the real protected
    # manifests (CONFIRM_001 / HOLDOUT / OOS) and read each access_count field.
    protected_access = {"CONFIRM_001": 0, "HOLDOUT": 0, "OOS": 0}  # <FILL from manifests>
    gate("PROTECTED_DATA_FIREWALL", all(v == 0 for v in protected_access.values()),
         f"access counts {protected_access}", errors)

    # ---- Coverage / quarantine cross-checks (delegate, don't re-implement) ------
    # Agent: import and call the existing coverage audit's window_report for the stack's
    # legs (DATA_COVERAGE_COMPLETE) and assert no quarantined package (GEN_002) appears
    # in any leg lineage (QUARANTINE_CHECK). Keep single-authority delegation.
    report["gates"] = {
        "CROSS_LEG_TIMEBASE": "CROSS_LEG_TIMEBASE_CONSISTENT" if (v_h1.admissible and v_m15.admissible) else "FAIL",
        "WARMUP": "WARMUP_STABLE" if bars_before >= MIN_H1_WARMUP_BARS else "FAIL",
        "PROTECTED_DATA_ACCESS_COUNT": sum(protected_access.values()),
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

    out_dir = REPO / "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{STACK_ID}.json"
    report["status"] = "FROZEN"
    # Freeze identity: hash the canonical serialization so R5 can bind to it exactly.
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    report["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nFROZE {out_path}\nmanifest_sha256 = {report['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
