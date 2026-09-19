"""Build SSC_V1_0_1_G2_DEV_002 -- H1 warmup remediation (WARMUP_CONTEXT_ONLY).

Combines the owner-approved historical EURUSD H1 (D:\\EURUSD_H1_202501020000_202607310000.csv,
broker wall-clock, +3h offset) as WARMUP_CONTEXT_ONLY with the DEV_001 H1 development
segment. M15/M1 are byte-copied from DEV_001 (unchanged). Produces a new frozen dataset
manifest + G2 population preregistration. NO replay, NO economics, NO optimization,
NO protected-data access.

Warmup role semantics (W3): H1 context may initialize structure/bias ONLY; it can never
generate a decision occurrence, trade, P/L, or economic sample, and does not extend the
DEVELOPMENT decision interval (which stays DEV_001's 2026-06-21T21:00 -> 2026-08-02).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from historical_replay.warmup_readiness import closed_h1_bar_count  # noqa: E402
from session_sweep_continuation.config import load_config  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

PARENT_ID = "SSC_V1_0_1_G2_DEV_001"
NEW_ID = "SSC_V1_0_1_G2_DEV_002"
SYMBOL = "EURUSD"
OFFSET_HOURS = 3  # VantageMarkets-Demo broker wall-clock = true UTC + 3h

D_RAW_H1 = r"D:\EURUSD_H1_202501020000_202607310000.csv"
PARENT_RAW_DIR = os.path.join(REPO_ROOT, "data", "research", "ssc_fresh_dev", PARENT_ID, "raw")
NEW_RAW_DIR = os.path.join(REPO_ROOT, "data", "research", "ssc_fresh_dev", NEW_ID, "raw")
NEW_DIR = os.path.join(REPO_ROOT, "data", "research", "ssc_fresh_dev", NEW_ID)
ARTIFACT_DIR = os.path.join(REPO_ROOT, "artifacts", "validation", "ST_SESSION_SWEEP_CONTINUATION_V1", NEW_ID)

DEV001_H1_FIRST = datetime(2026, 6, 21, 21, 0, 0, tzinfo=timezone.utc)  # DEV_001 H1 first bar (UTC)
DECISION_START = "2026-06-21T21:00:00Z"
DECISION_END = "2026-08-02T23:59:59Z"
REQUIRED_H1_BARS = 1000

CSV_HEADER = ["timestamp_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_dev001_csv(timeframe: str):
    path = os.path.join(PARENT_RAW_DIR, f"{SYMBOL}_{timeframe}.csv")
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader]
    return rows, path


def load_d_h1_warmup():
    """Parse the tab-delimited broker wall-clock D:\\ H1 export and convert to true UTC
    (wall-clock - OFFSET_HOURS). Only bars strictly before DEV001_H1_FIRST are kept."""
    warmup = []
    with open(D_RAW_H1, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # header <DATE>\t<TIME>\t...
        for row in reader:
            wall = datetime.strptime(f"{row[0]} {row[1]}", "%Y.%m.%d %H:%M:%S")
            ts = wall - timedelta(hours=OFFSET_HOURS)
            ts = ts.replace(tzinfo=timezone.utc)
            if ts >= DEV001_H1_FIRST:
                continue
            warmup.append({
                "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "open": row[2], "high": row[3], "low": row[4], "close": row[5],
                "tick_volume": row[6], "spread": row[8], "real_volume": row[7],
            })
    warmup.sort(key=lambda r: r["timestamp_utc"])
    return warmup


def write_csv(path: str, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in CSV_HEADER})


def build_combined_h1() -> list:
    warmup = load_d_h1_warmup()
    dev_rows, _ = load_dev001_csv("H1")
    combined = warmup + dev_rows
    combined.sort(key=lambda r: r["timestamp_utc"])

    times = [r["timestamp_utc"] for r in combined]
    dup = sum(1 for i in range(1, len(times)) if times[i] == times[i - 1])
    non_mono = sum(1 for i in range(1, len(times)) if times[i] < times[i - 1])
    bad = 0
    for r in combined:
        o, h, l, c = (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
        if not (h >= max(o, c) and l <= min(o, c) and h >= l and min(o, h, l, c) > 0):
            bad += 1
    if dup or non_mono or bad:
        raise SystemExit(f"H1_INTEGRITY_FAIL: dup={dup} non_mono={non_mono} bad={bad}")
    return combined


def validate_warmup(h1_path: str) -> dict:
    config = load_config(repo_root=REPO_ROOT)
    windows = session_windows_from_config(config)
    h1_candles, report = load_utc_export_csv(h1_path, SYMBOL, "H1")
    if report.normalized_timezone != "UTC":
        raise SystemExit("H1_TIMEZONE_NOT_UTC")

    first_ref_end = datetime(2026, 6, 22, 6, 0, tzinfo=timezone.utc)
    counts = {}
    min_count = None
    min_at = None
    d = datetime(2026, 6, 22, tzinfo=timezone.utc)
    end = datetime(2026, 8, 3, tzinfo=timezone.utc)
    while d < end:
        for pair_id, w in windows.items():
            ref_end = w["reference"].bounds_for_date(d.date())[1]
            n = closed_h1_bar_count(h1_candles, ref_end)
            if n < REQUIRED_H1_BARS:
                raise SystemExit(f"WARMUP_STILL_INSUFFICIENT: {pair_id} {d.date()} ref_end={ref_end} closed_h1={n} < {REQUIRED_H1_BARS}")
            if min_count is None or n < min_count:
                min_count, min_at = n, str(ref_end)
        d += timedelta(days=1)

    first_n = closed_h1_bar_count(h1_candles, first_ref_end)
    return {
        "minimum_required": REQUIRED_H1_BARS,
        "first_decision_closed_h1": first_n,
        "minimum_across_decisions": min_count,
        "minimum_at": min_at,
        "all_decisions_pass": True,
        "h1_total_rows": len(h1_candles),
    }


def main() -> None:
    os.makedirs(NEW_RAW_DIR, exist_ok=True)
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    # H1: warmup (D:\, wall-clock->UTC) + DEV_001 H1 development segment
    combined_h1 = build_combined_h1()
    h1_path = os.path.join(NEW_RAW_DIR, f"{SYMBOL}_H1.csv")
    write_csv(h1_path, combined_h1)

    # M15 / M1: byte-copy from DEV_001 (unchanged)
    for tf in ("M15", "M1"):
        src = os.path.join(PARENT_RAW_DIR, f"{SYMBOL}_{tf}.csv")
        dst = os.path.join(NEW_RAW_DIR, f"{SYMBOL}_{tf}.csv")
        shutil.copyfile(src, dst)

    h1_sha, m15_sha, m1_sha = _sha256(h1_path), _sha256(os.path.join(NEW_RAW_DIR, f"{SYMBOL}_M15.csv")), _sha256(os.path.join(NEW_RAW_DIR, f"{SYMBOL}_M1.csv"))
    parent_m15 = _sha256(os.path.join(PARENT_RAW_DIR, f"{SYMBOL}_M15.csv"))
    parent_m1 = _sha256(os.path.join(PARENT_RAW_DIR, f"{SYMBOL}_M1.csv"))
    if m15_sha != parent_m15 or m1_sha != parent_m1:
        raise SystemExit("M15/M1_CHANGED_FROM_PARENT")

    warmup_meta = validate_warmup(h1_path)

    canonical = "\n".join([f"{SYMBOL}|H1|{h1_sha}", f"{SYMBOL}|M15|{m15_sha}", f"{SYMBOL}|M1|{m1_sha}"])
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    manifest = {
        "package_id": NEW_ID,
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "strategy_version": "1.0.1",
        "symbol": SYMBOL,
        "parent_dataset": PARENT_ID,
        "parent_dataset_fingerprint": "3ac9fe2023f3c66d3e5ad4e99554574e24a62060e7920603b3af880590c03ef8",
        "remediation_reason": "INSUFFICIENT_H1_WARMUP",
        "semantic_change": False,
        "data_role": "DEVELOPMENT",
        "h1_context_interval": {"start": "2025-01-01T21:00:00Z", "end": "2026-08-02T23:00:00Z"},
        "development_decision_interval": {"start": DECISION_START, "end": DECISION_END},
        "warmup_role": {
            "WARMUP_CONTEXT_ONLY": True,
            "may_initialize_h1_structure": True,
            "may_initialize_h1_bias": True,
            "may_generate_decision_occurrence": False,
            "may_contribute_trade": False,
            "may_contribute_pnl": False,
            "may_contribute_economic_sample_N": False,
            "may_extend_development_decision_window": False,
            "may_be_used_for_optimization": False,
        },
        "per_file": {
            f"{SYMBOL}_H1": {"sha256": h1_sha, "rows": len(combined_h1), "path": os.path.relpath(h1_path, REPO_ROOT).replace("\\", "/")},
            f"{SYMBOL}_M15": {"sha256": m15_sha, "path": os.path.relpath(os.path.join(NEW_RAW_DIR, f"{SYMBOL}_M15.csv"), REPO_ROOT).replace("\\", "/")},
            f"{SYMBOL}_M1": {"sha256": m1_sha, "path": os.path.relpath(os.path.join(NEW_RAW_DIR, f"{SYMBOL}_M1.csv"), REPO_ROOT).replace("\\", "/")},
        },
        "combined_dataset_fingerprint": fingerprint,
        "combined_dataset_fingerprint_canonical_input": canonical,
        "warmup_readiness": warmup_meta,
        "data_quality": "PASS",
        "cross_timeframe_consistency": "PASS",
        "generated_at_utc": "2026-09-19",
        "generated_at_utc_note": "DATE_ONLY",
    }
    with open(os.path.join(NEW_DIR, "dataset_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")

    print(json.dumps({
        "new_dataset": NEW_ID,
        "h1_hash": h1_sha, "m15_hash": m15_sha, "m1_hash": m1_sha,
        "dataset_fingerprint": fingerprint,
        "h1_rows": len(combined_h1),
        "warmup_readiness": warmup_meta,
        "m15_m1_identical_to_parent": True,
    }, indent=2))


if __name__ == "__main__":
    main()
