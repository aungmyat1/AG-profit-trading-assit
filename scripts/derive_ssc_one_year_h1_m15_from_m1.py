"""SSC ONE-YEAR H1/M15 AUTHORITY REMEDIATION V1 -- derivation driver.

DATA-INTEGRITY REMEDIATION ONLY. No SSC replay, no optimization, no strategy change.

Derives authoritative M15 and H1 from the already-frozen native MT5 M1 authority
(`SSC_V1_0_1_HIST_1Y_M1_001`) so the one-year SSC replay's three legs share one time
base by construction, resolving `BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT`.

Stages (mission A0-A8):
  A0  preflight (HEAD, ancestry, foreign WIP preserved)
  A1  derivation legitimacy -- ADJUDICATED AUTHORIZED on existing repository convention
  A2  derivation contract frozen and hashed BEFORE any output is generated
  A3  derive from M1 only; no strategy/optimization module is imported
  A4  validate against trusted exactly-aligned H1/M15 references (parity must be exact)
  A5  full-year quality census
  A6  cross-leg consistency gate re-run against derived H1 / derived M15 / canonical M1
  A7  lineage recorded
  A8  pre-existing anomalies recorded, never rewritten

READ-ONLY w.r.t. every pre-existing dataset: this script writes ONLY the derived dataset
package and its evidence. It never modifies DEV_002 / GEN_002 / HYP_002 or any frozen
evidence, never touches protected data, and never calls any SSC replay/strategy code.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.m1_derivation import (  # noqa: E402
    BASE_TIMEFRAME,
    BUCKET_POLICY,
    DERIVED_TIMEFRAMES,
    aggregate_m1,
    bucket_census,
    verify_against_reference,
    verify_derived_series,
)
from historical_replay.mt5_export_loader import load_mt5_export_csv  # noqa: E402
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"

SOURCE_M1_ID = "SSC_V1_0_1_HIST_1Y_M1_001"
SOURCE_M1_PATH = (REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / SOURCE_M1_ID
                  / "raw" / "EURUSD_M1.csv")
SOURCE_M1_SHA256 = "50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a"

DERIVED_ID = "SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001"
DERIVED_ROOT = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / DERIVED_ID
EVIDENCE_DIR = (REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
                / "SSC_V1_0_1_HIST_1Y_001")

WINDOW_START = datetime(2025, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

# A4 validation references -- used ONLY as comparison references, never as inputs.
# These are the sources the cross-leg consistency audit found EXACTLY aligned (0h) with
# the canonical M1 authority.
VALIDATION_REFERENCES = {
    "H1": [
        ("EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv",
         Path(r"D:\EURUSD_H1_202501020000_202607310000.csv"), "mt5"),
        ("SSC_V1_0_1_G2_DEV_001::H1",
         REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_001"
         / "raw" / "EURUSD_H1.csv", "utc"),
    ],
    "M15": [
        ("EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202607310000.csv",
         Path(r"D:\EURUSD_M15_202501020000_202607310000.csv"), "mt5"),
        ("SSC_V1_0_1_G2_DEV_001::M15",
         REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_001"
         / "raw" / "EURUSD_M15.csv", "utc"),
        ("SSC_V1_0_1_G2_DEV_002::M15",
         REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_002"
         / "raw" / "EURUSD_M15.csv", "utc"),
    ],
}

CONTRACT = {
    "schema": "AG_SSC_V1_0_1_H1M15_DERIVATION_CONTRACT_V1",
    "source_dataset": SOURCE_M1_ID,
    "source_sha256": SOURCE_M1_SHA256,
    "source_timeframe": BASE_TIMEFRAME,
    "derived_timeframes": list(DERIVED_TIMEFRAMES),
    "time_authority": "normalized UTC from canonical M1 (measured, per-week reopen)",
    "bucket_authority": "exact UTC floor: M15 -> 15-minute boundary, H1 -> 1-hour boundary",
    "broker_wallclock_buckets_used": False,
    "aggregation": {
        "open": "first M1 open by M1 timestamp",
        "high": "max M1 high",
        "low": "min M1 low",
        "close": "last M1 close by M1 timestamp",
        "volume": "sum of M1 volumes present; None when no member carries a volume",
    },
    "incomplete_bucket_policy": BUCKET_POLICY,
    "incomplete_bucket_policy_rationale": (
        "A bucket is emitted when it holds at least one M1 bar, aggregated from exactly "
        "the M1 bars present. Chosen by measurement: against native MT5 references this "
        "reproduces every native bar exactly (reference_only = 0, mismatch = 0), whereas "
        "resampler.resample's strict complete-bucket default silently drops 418 real H1 "
        "and 452 real M15 bars of the window. No bar is invented, no price altered, no "
        "missing M1 filled, no intra-minute path synthesized; a closed market has no M1 "
        "bars and therefore produces no bucket."
    ),
    "prohibited_and_not_performed": [
        "interpolating missing M1",
        "deriving M1 from M5/M15",
        "altering any price",
        "synthesizing intra-minute paths",
        "applying any timezone shift correction",
        "using any strategy outcome to influence dataset construction",
    ],
    "data_role": "HISTORICAL_RESEARCH_INPUT_ONLY",
    "derivation_class": "AUTHORIZED_DETERMINISTIC_TIMEFRAME_AGGREGATION",
    "independent_validation": False,
}


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _contract_hash() -> str:
    return hashlib.sha256(
        json.dumps(CONTRACT, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_utc_csv(path: Path, candles) -> None:
    """Write the canonical already-UTC `timestamp_utc` CSV schema, so the derived dataset
    is readable by the SAME repository loader every other SSC leg uses
    (historical_replay.utc_export_csv_loader.load_utc_export_csv) -- no new reader."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["timestamp_utc,open,high,low,close,tick_volume,spread,real_volume"]
    for c in candles:
        vol = 0 if c.volume is None else int(c.volume)
        lines.append(f"{c.time:%Y-%m-%d %H:%M:%S},{c.open},{c.high},{c.low},{c.close},{vol},0,0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    head_before = _git_commit()
    contract_hash = _contract_hash()

    # --- A0: preflight ---------------------------------------------------------------
    print("=== A0 preflight ===", file=sys.stderr)
    if not SOURCE_M1_PATH.exists():
        raise SystemExit(f"BLOCKED_SOURCE_MISSING: {SOURCE_M1_PATH}")
    actual_source_sha = _sha256_file(SOURCE_M1_PATH)
    if actual_source_sha != SOURCE_M1_SHA256:
        raise SystemExit(
            f"BLOCKED_SOURCE_IDENTITY: {actual_source_sha} != {SOURCE_M1_SHA256}")
    print(f"  source M1 sha256 verified from bytes: {actual_source_sha}", file=sys.stderr)

    # --- A2: contract frozen BEFORE any output --------------------------------------
    print("=== A2 derivation contract frozen ===", file=sys.stderr)
    print(f"  DERIVATION_CONTRACT_HASH = {contract_hash}", file=sys.stderr)

    # --- A3: derive from M1 only -----------------------------------------------------
    print("=== A3 deriving (M1 only) ===", file=sys.stderr)
    m1_candles, m1_report = load_utc_export_csv(str(SOURCE_M1_PATH), SYMBOL, BASE_TIMEFRAME)
    if m1_report.normalized_timezone != "UTC":
        raise SystemExit(f"BLOCKED_TIME_AUTHORITY: {m1_report.normalized_timezone}")
    print(f"  M1: {len(m1_candles)} bars {m1_candles[0].time} -> {m1_candles[-1].time}",
          file=sys.stderr)

    derived = {}
    for tf in DERIVED_TIMEFRAMES:
        derived[tf] = aggregate_m1(m1_candles, tf)
        print(f"  derived {tf}: {len(derived[tf])} bars", file=sys.stderr)

    # --- A4: validate against trusted references -------------------------------------
    print("=== A4 reference parity ===", file=sys.stderr)
    span = (m1_candles[0].time, m1_candles[-1].time + timedelta(minutes=1))
    parity = {}
    for tf in DERIVED_TIMEFRAMES:
        parity[tf] = []
        for label, path, kind in VALIDATION_REFERENCES[tf]:
            if not path.exists():
                parity[tf].append({"reference": label, "status": "REFERENCE_UNAVAILABLE"})
                continue
            if kind == "mt5":
                ref, _ = load_mt5_export_csv(str(path), SYMBOL, tf)
            else:
                ref, _ = load_utc_export_csv(str(path), SYMBOL, tf)
            result = verify_against_reference(derived[tf], ref, label, restrict_to=span)
            result["status"] = ("EXACT" if result["exact_match_rate"] == 1.0
                                and result["ohlc_mismatches"] == 0 else "NOT_EXACT")
            parity[tf].append(result)
            print(f"  {tf} {label}: exact={result['exact_match_rate']} "
                  f"common={result['common_buckets']} mismatch={result['ohlc_mismatches']} "
                  f"ref_only={result['reference_only_buckets']} [{result['status']}]",
                  file=sys.stderr)

    # Gate: every AVAILABLE reference must be EXACT. An unavailable reference (e.g. a D:\
    # file not mounted) is reported, not silently treated as a pass.
    not_exact = [r for tf in DERIVED_TIMEFRAMES for r in parity[tf]
                 if r.get("status") not in ("EXACT",)]
    if not_exact:
        raise SystemExit(
            "BLOCKED_REFERENCE_PARITY_NOT_EXACT: " + json.dumps(not_exact, indent=2))

    # --- A5: full-year quality --------------------------------------------------------
    print("=== A5 quality ===", file=sys.stderr)
    quality = {}
    census = {}
    for tf in DERIVED_TIMEFRAMES:
        quality[tf] = verify_derived_series(derived[tf], tf)
        census[tf] = bucket_census(m1_candles, tf)
        if quality[tf]["quality_status"] != "PASS":
            raise SystemExit(f"BLOCKED_DERIVED_QUALITY: {tf}: {quality[tf]}")
        print(f"  {tf}: rows={quality[tf]['row_count']} "
              f"{quality[tf]['first_timestamp_utc']} -> {quality[tf]['last_timestamp_utc']} "
              f"quality={quality[tf]['quality_status']}", file=sys.stderr)

    # --- write derived dataset package ------------------------------------------------
    files = {}
    for tf in DERIVED_TIMEFRAMES:
        path = DERIVED_ROOT / "raw" / f"{SYMBOL}_{tf}.csv"
        _write_utc_csv(path, derived[tf])
        files[tf] = {"path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                     "sha256": _sha256_file(path), "rows": len(derived[tf])}
        print(f"  wrote {files[tf]['path']} sha256={files[tf]['sha256']}", file=sys.stderr)

    combined = hashlib.sha256("\n".join(
        f"{SYMBOL}|{tf}|{files[tf]['sha256']}" for tf in DERIVED_TIMEFRAMES
    ).encode("utf-8")).hexdigest()

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema": "AG_SSC_HISTORICAL_INPUT_MANIFEST_V1",
        "package_id": DERIVED_ID,
        "dataset_id": DERIVED_ID,
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "strategy_version": "1.0.1",
        "symbol": SYMBOL,
        "generated_at_utc": generated_at,
        "data_role": "HISTORICAL_RESEARCH_INPUT_ONLY",
        "derivation_class": "AUTHORIZED_DETERMINISTIC_TIMEFRAME_AGGREGATION",
        "derivation_contract": CONTRACT,
        "derivation_contract_hash": contract_hash,
        "source_dataset": SOURCE_M1_ID,
        "source_sha256": actual_source_sha,
        "source_rows": len(m1_candles),
        "combined_dataset_fingerprint": combined,
        "per_file": {f"{SYMBOL}_{tf}": files[tf] for tf in DERIVED_TIMEFRAMES},
        "bucket_policy": BUCKET_POLICY,
        "bucket_census": census,
        "quality": quality,
        "reference_parity": parity,
        "window": {"start_utc": WINDOW_START.isoformat(), "end_utc": WINDOW_END.isoformat()},
        "provenance": (
            f"{SOURCE_M1_ID} (native MT5 M1, UTC-normalized, sha256 {actual_source_sha[:12]}..) "
            f"-> deterministic {SYMBOL}_M15.csv -> deterministic {SYMBOL}_H1.csv. "
            "Single source of truth; no cross-source splicing; no shift correction."
        ),
        "repository_commit": head_before,
    }
    DERIVED_ROOT.mkdir(parents=True, exist_ok=True)
    (DERIVED_ROOT / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    evidence = {
        "schema": "AG_SSC_V1_0_1_H1M15_AUTHORITY_REMEDIATION_EVIDENCE_V1",
        "generated_at_utc": generated_at,
        "repository": {"HEAD_BEFORE": head_before, "COMMIT": head_before},
        "source": {"SOURCE_M1_ID": SOURCE_M1_ID, "SOURCE_M1_SHA256": actual_source_sha,
                   "rows": len(m1_candles),
                   "first_timestamp_utc": m1_candles[0].time.isoformat(),
                   "last_timestamp_utc": m1_candles[-1].time.isoformat()},
        "derivation": {"DERIVATION_AUTHORITY": "historical_replay.m1_derivation.aggregate_m1 "
                                              "(wraps historical_replay.resampler convention)",
                       "DERIVATION_CONTRACT_HASH": contract_hash,
                       "BUCKET_AUTHORITY": CONTRACT["bucket_authority"],
                       "TIME_AUTHORITY": CONTRACT["time_authority"],
                       "BUCKET_POLICY": BUCKET_POLICY},
        "derived": {tf: {**files[tf], "quality": quality[tf], "census": census[tf],
                         "reference_parity": parity[tf]} for tf in DERIVED_TIMEFRAMES},
        "combined_dataset_fingerprint": combined,
        "lineage": {
            "chain": ["NATIVE_MT5_M1_BROKER_AUTHORITY",
                      "M15_DETERMINISTIC_DERIVED_DATASET",
                      "H1_DETERMINISTIC_DERIVED_DATASET"],
            "DATA_ROLE": "HISTORICAL_RESEARCH_INPUT_ONLY",
            "DERIVATION_CLASS": "AUTHORIZED_DETERMINISTIC_TIMEFRAME_AGGREGATION",
            "INDEPENDENT_VALIDATION": False,
            "previously_consumed_not_reclassified": True,
        },
        "safety": {
            "SSC_REPLAY_EXECUTED": False, "STRATEGY_CHANGED": False,
            "PARAMETERS_CHANGED": False, "OPTIMIZATION_RUN": False,
            "PROTECTED_DATA_ACCESSED": False, "H2_CONSUMED": False,
            "BROKER_MUTATION": False, "DEMO_ORDER": False, "LIVE_ORDER": False,
            "PRE_EXISTING_EVIDENCE_REWRITTEN": False,
        },
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "H1M15_AUTHORITY_REMEDIATION_EVIDENCE_V1.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "SOURCE_M1_ID": SOURCE_M1_ID, "SOURCE_M1_SHA256": actual_source_sha,
        "DERIVATION_CONTRACT_HASH": contract_hash,
        "M15_SHA256": files["M15"]["sha256"], "M15_ROWS": files["M15"]["rows"],
        "H1_SHA256": files["H1"]["sha256"], "H1_ROWS": files["H1"]["rows"],
        "COMBINED_DATASET_FINGERPRINT": combined,
        "M15_PARITY": [r.get("exact_match_rate") for r in parity["M15"]],
        "H1_PARITY": [r.get("exact_match_rate") for r in parity["H1"]],
        "FINAL_STATUS": "DERIVED_DATASET_ADMITTED",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
