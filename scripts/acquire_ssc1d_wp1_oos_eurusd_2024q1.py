"""AG SSC1D-WP1 -- EURUSD OOS package acquisition (read-only).

Acquires a genuinely untouched historical EURUSD H1/M15/M1 package for use as the
SSC1D pilot's out-of-sample (OOS) evidence, per docs/validation/SSC_ONE_DAY_DEMO_PILOT_V2.md
and the SSC1D-WP1 mission.

Window chosen (2024-01-01 .. 2024-03-31 UTC) is strictly BEFORE the earliest date any
SSC research artifact in this repository has ever touched (GEN_001's earliest input,
EURUSD_H1_202501020000_202607310000.yaml, starts 2025-01-02). It therefore cannot
overlap SSC v1.0.0 development, GEN_001, GEN_002, HYP_001, or HYP_002 evidence by
construction (chosen on non-overlap grounds only, never on observed SSC performance).
It also strictly precedes 2026-09-14 (GEN_002's frozen_end), preserving all
post-2026-09-14 data for prospective/forward evidence rather than consuming it here.

Mirrors the acquisition discipline already used for GEN_002 (read-only MT5 export,
no trading function called, immutable raw files + per-file hash + combined fingerprint
+ integrity/gap report). No trading function is called (no order_send/order_check/
symbol_select/positions_*).

This script ACQUIRES DATA ONLY. It does not run SSC, does not compute occurrences,
does not evaluate economics, and must not be treated as consuming this package as OOS
until a later, separate work package explicitly runs the frozen candidate against it
exactly once (see SSC_ONE_DAY_DEMO_PILOT_V2.md section 10, P9).
"""
import csv
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5

PACKAGE_ID = "SSC1D_WP1_OOS_EURUSD_2024Q1"
PKG_ROOT = os.path.join("data", "research", "ssc1d_pilot", PACKAGE_ID)
RAW_DIR = os.path.join(PKG_ROOT, "raw")

SYMBOL = "EURUSD"
PULL_START = datetime(2024, 1, 1, 0, 0, 0)
PULL_END = datetime(2024, 3, 31, 23, 59, 59)

TIMEFRAMES = {
    "H1": mt5.TIMEFRAME_H1,
    "M15": mt5.TIMEFRAME_M15,
    "M1": mt5.TIMEFRAME_M1,
}
TF_SECONDS = {"H1": 3600, "M15": 900, "M1": 60}
# M1 is best-effort: this MT5 terminal's M1 history retention is empirically limited to
# roughly the trailing ~120 days from current server time, so a 2024Q1 M1 pull returns
# no data. That is recorded as a manifest gap, not treated as a fatal acquisition error.
OPTIONAL_TIMEFRAMES = {"M1"}

os.makedirs(RAW_DIR, exist_ok=True)

if not mt5.initialize():
    raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")

ai = mt5.account_info()
ti = mt5.terminal_info()
print("=" * 70)
print(f"MetaTrader5 package version : {mt5.__version__}")
print(f"broker/server               : {ai.server}")
print(f"terminal build               : {ti.build}")
print("=" * 70)

per_file = {}
fingerprint_lines = []
skipped_timeframes = {}

for tf_name, tf_const in TIMEFRAMES.items():
    rates = mt5.copy_rates_range(SYMBOL, tf_const, PULL_START, PULL_END)
    if rates is None or len(rates) == 0:
        if tf_name in OPTIONAL_TIMEFRAMES:
            skipped_timeframes[tf_name] = "NO_DATA -- broker M1 history retention exhausted for this window"
            print(f"{tf_name}: SKIPPED (no data available -- retention gap)")
            continue
        raise SystemExit(f"NO_DATA: {SYMBOL} {tf_name} {PULL_START} -> {PULL_END}")

    rows = []
    for r in rates:
        ts = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
        rows.append((ts, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                     int(r["tick_volume"]), int(r["spread"]), int(r["real_volume"])))
    rows.sort(key=lambda row: row[0])

    raw_path = os.path.join(RAW_DIR, f"{SYMBOL}_{tf_name}.csv")
    with open(raw_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
        for ts, o, h, l, c, tv, sp, rv in rows:
            w.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), o, h, l, c, tv, sp, rv])

    times = [r[0] for r in rows]
    dup = sum(1 for i in range(1, len(times)) if times[i] == times[i - 1])
    non_mono = sum(1 for i in range(1, len(times)) if times[i] < times[i - 1])
    bad_ohlc = sum(1 for _, o, h, l, c, *_ in rows if not (h >= max(o, c) and l <= min(o, c) and h >= l))

    step = TF_SECONDS[tf_name]
    expected_gaps, unexpected_gaps, gap_details = 0, 0, []
    for i in range(1, len(times)):
        delta = (times[i] - times[i - 1]).total_seconds()
        if delta <= step:
            continue
        probe = times[i - 1] + timedelta(seconds=step)
        weekend = False
        while probe <= times[i]:
            if probe.weekday() == 5:
                weekend = True
                break
            probe += timedelta(seconds=step)
        if weekend:
            expected_gaps += 1
        else:
            unexpected_gaps += 1
            gap_details.append({"from": str(times[i - 1]), "to": str(times[i]),
                                 "missing_seconds": int(delta - step)})

    if dup or non_mono or bad_ohlc or unexpected_gaps:
        raise SystemExit(f"INTEGRITY_FAIL[{tf_name}]: dup={dup} non_mono={non_mono} bad_ohlc={bad_ohlc} "
                          f"unexpected_gaps={unexpected_gaps} details={gap_details[:5]}")

    h = hashlib.sha256()
    with open(raw_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    raw_sha256 = h.hexdigest()
    fingerprint_lines.append(f"{SYMBOL}|{tf_name}|{raw_sha256}")

    per_file[f"{SYMBOL}_{tf_name}"] = {
        "raw_file": raw_path.replace("\\", "/"),
        "sha256": raw_sha256,
        "bars": len(rows),
        "first_timestamp": times[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_timestamp": times[-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duplicate_count": dup,
        "non_monotonic_count": non_mono,
        "invalid_ohlc_count": bad_ohlc,
        "expected_weekend_gaps": expected_gaps,
        "unexpected_gaps": unexpected_gaps,
    }
    print(f"{tf_name}: {len(rows)} bars, sha256={raw_sha256}")

combined_fp_input = "\n".join(fingerprint_lines)
combined_fp = hashlib.sha256(combined_fp_input.encode("utf-8")).hexdigest()

manifest = {
    "schema": "AG_SSC1D_OOS_DATASET_MANIFEST_V1",
    "package_id": PACKAGE_ID,
    "pilot_id": "SSC_ONE_DAY_OPTIMIZATION_PILOT_V1",
    "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
    "work_package": "SSC1D-WP1",
    "role": "OOS_UNTOUCHED (H1, M15 legs only -- M1 unavailable, see skipped_timeframes)",
    "role_note": "Acquired and hashed only. access_count starts at 0 and must be incremented "
                 "(to exactly 1, ever) only by the single frozen-candidate OOS run under P9 "
                 "of SSC_ONE_DAY_DEMO_PILOT_V2.md. No SSC code has been run against this data. "
                 "This package is INSUFFICIENT on its own for a canonical-parity SSC replay, "
                 "which requires M1 fill resolution -- see skipped_timeframes and the WP1 "
                 "dataset-role manifest's finding_wp1.m1_gap for detail.",
    "symbol": SYMBOL,
    "environment": "DEMO",
    "broker": ai.server,
    "metatrader5_package_version": mt5.__version__,
    "terminal_build": ti.build,
    "trading_function_called": False,
    "frozen_start": PULL_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "frozen_end": PULL_END.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "selection_rationale": "Chosen strictly by chronological non-overlap with every known SSC "
                            "research artifact (predates GEN_001's earliest input 2025-01-02 by "
                            "over 12 months); not chosen from or influenced by any SSC backtest "
                            "result -- no SSC code was run before or during this acquisition.",
    "per_file": per_file,
    "skipped_timeframes": skipped_timeframes,
    "combined_dataset_fingerprint_canonical_input": combined_fp_input,
    "combined_dataset_fingerprint": combined_fp,
    "access_count": 0,
}
manifest_path = os.path.join(PKG_ROOT, "oos_dataset_manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, sort_keys=True)

print(json.dumps(manifest, indent=2, sort_keys=True))
print(f"\nOOS_ACQUISITION_STATUS = PASS, combined_dataset_fingerprint={combined_fp}")
