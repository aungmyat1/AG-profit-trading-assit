"""SSC v1.0.1 ONE-YEAR HISTORICAL REPLAY (R2/R3) -- CROSS-LEG TIMEZONE CONSISTENCY AUDIT.

READ-ONLY, deterministic, no replay, no writes to any mission artifact.

WHY THIS EXISTS
---------------
`scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` proves *timestamp-union coverage*:
that some admissible H1 source, some admissible M15 source and some admissible M1 source
between them span the window. That is necessary but NOT sufficient. A replay is only
meaningful if the H1 (bias), M15 (decision) and M1 (fill) legs are expressed in the SAME
time base. A source whose timestamps are broker wall-clock rather than UTC still "covers"
the window by timestamp union while describing a different wall-clock instant -- so the
coverage audit can pass while the replay would compare an M15 decision candle against M1
fill candles from a different time.

This script is the missing second half of the R2/R3 gate. It arbitrates every admissible
H1/M15 source against the FINEST-GRANULARITY canonical leg (the M1 fill-resolution
authority) by aggregating M1 into H1/M15 buckets and running a shift scan, then computes
the three-way intersection using ONLY timezone-consistent legs.

METHOD (no new data, no new timezone model)
-------------------------------------------
  * The M1 leg is the arbiter because it is the finest granularity and the leg whose own
    alignment is independently established (`SSC_V1_0_1_HIST_1Y_M1_001` is
    `PASS_EXACT` against the canonical DEV_002 M1 series on 43 292/43 292 bars).
  * Aggregation is exact OHLC bucketing (open = first bar's open, high = max, low = min,
    close = last bar's close). No interpolation, no synthesis.
  * The shift scan is -3..+3 hours (the broker's UTC+2/UTC+3 seasonal range plus zero).
  * Alignment is judged per DST season as well as globally: a file whose winter and summer
    alignments differ is internally DST-inconsistent and is reported as such rather than
    being assigned a single "best" shift that hides the defect.

HARD RULES
----------
  * Protected datasets are never opened (they are not in this script's source list).
  * No file is written; the report goes to stdout only. This script is a GATE, not an
    evidence generator -- the replay driver is responsible for persisting evidence.
  * A leg that is not exactly aligned (rate == 1.0) is never silently repaired, shifted,
    or substituted. It is reported and excluded from the consistent intersection.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.mt5_export_loader import load_mt5_export_csv  # noqa: E402
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data" / "research" / "ssc_fresh_dev"

SYMBOL = "EURUSD"
EXACT_ALIGNMENT_THRESHOLD = 0.999999

# The canonical one-year window this gate was written for (identical to the coverage
# audit's PRIMARY window; not outcome-derived).
WINDOW_START = datetime(2025, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

# DST seasons for the per-season arbitration (broker UTC+3 summer / UTC+2 winter).
SEASONS = {
    "WINTER_UTC_PLUS_2": (
        datetime(2025, 11, 1, tzinfo=timezone.utc), datetime(2026, 3, 1, tzinfo=timezone.utc)),
    "SUMMER_UTC_PLUS_3": (
        datetime(2026, 5, 1, tzinfo=timezone.utc), datetime(2026, 9, 1, tzinfo=timezone.utc)),
}

# (label, path, loader) -- loader is "utc" (already-UTC timestamp_utc CSV) or "mt5"
# (broker-local MT5 export-menu CSV, resolved by the per-week reopen authority).
H1_SOURCES = [
    ("EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv",
     Path(r"D:\EURUSD_H1_202501020000_202607310000.csv"), "mt5"),
    ("SSC_V1_0_1_G2_DEV_001::H1", DATA_ROOT / "SSC_V1_0_1_G2_DEV_001" / "raw" / "EURUSD_H1.csv", "utc"),
    ("SSC_V1_0_1_G2_DEV_002::H1", DATA_ROOT / "SSC_V1_0_1_G2_DEV_002" / "raw" / "EURUSD_H1.csv", "utc"),
    ("SSC_HYP002_H1_WARMUP_CONTEXT::H1",
     DATA_ROOT / "SSC_HYP002_H1_WARMUP_CONTEXT_20260528_20260731" / "raw" / "EURUSD_H1.csv", "utc"),
    ("SSC_FRESH_DEV_GEN_002::H1",
     DATA_ROOT / "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914" / "raw" / "EURUSD_H1.csv", "utc"),
    ("HYP_002_EVALUATION_INPUT::H1",
     REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
     / "HYP_002_EVALUATION_INPUT" / "EURUSD_H1_WARMUP_PLUS_GEN002.csv", "utc"),
]

M15_SOURCES = [
    ("EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202607310000.csv",
     Path(r"D:\EURUSD_M15_202501020000_202607310000.csv"), "mt5"),
    ("EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202606192345.csv",
     Path(r"D:\EURUSD_M15_202501020000_202606192345.csv"), "mt5"),
    ("EXTERNAL_D_ROOT::EURUSD_M15_202601020000_202606192345.csv",
     Path(r"D:\EURUSD_M15_202601020000_202606192345.csv"), "mt5"),
    ("EXTERNAL_D_ROOT::EURUSD_M15_202606220000_202607312345.csv",
     Path(r"D:\EURUSD_M15_202606220000_202607312345.csv"), "mt5"),
    ("SSC_V1_0_1_G2_DEV_001::M15", DATA_ROOT / "SSC_V1_0_1_G2_DEV_001" / "raw" / "EURUSD_M15.csv", "utc"),
    ("SSC_V1_0_1_G2_DEV_002::M15", DATA_ROOT / "SSC_V1_0_1_G2_DEV_002" / "raw" / "EURUSD_M15.csv", "utc"),
    ("SSC_FRESH_DEV_GEN_002::M15",
     DATA_ROOT / "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914" / "raw" / "EURUSD_M15.csv", "utc"),
]

M1_ARBITER = ("SSC_V1_0_1_HIST_1Y_M1_001::M1",
              DATA_ROOT / "SSC_V1_0_1_HIST_1Y_M1_001" / "raw" / "EURUSD_M1.csv", "utc")


def _load(path: Path, timeframe: str, loader: str):
    if loader == "mt5":
        return load_mt5_export_csv(str(path), SYMBOL, timeframe)
    return load_utc_export_csv(str(path), SYMBOL, timeframe)


def _aggregate(candles, minutes: int) -> dict:
    """Exact OHLC bucketing of a finer series into a coarser timeframe. An incomplete
    bucket is aggregated from the bars that exist (never padded or interpolated); the
    caller only ever compares buckets present in BOTH series."""
    buckets: dict = defaultdict(list)
    for c in candles:
        t = c.time.replace(second=0, microsecond=0)
        t -= timedelta(minutes=t.minute % minutes)
        buckets[t].append(c)
    out = {}
    for t, group in buckets.items():
        group.sort(key=lambda c: c.time)
        out[t] = (group[0].open, max(c.high for c in group),
                  min(c.low for c in group), group[-1].close)
    return out


def _shift_scan(by_time: dict, arbiter_agg: dict, season=None) -> list:
    """Exact-match rate for each candidate whole-hour shift."""
    results = []
    for shift in (-3, -2, -1, 0, 1, 2, 3):
        delta = timedelta(hours=shift)
        shared = [t for t in arbiter_agg
                  if (t + delta) in by_time
                  and (season is None or season[0] <= t < season[1])]
        if not shared:
            continue
        mismatches = sum(1 for t in shared if arbiter_agg[t] != by_time[t + delta])
        results.append({
            "shift_hours": shift, "shared_buckets": len(shared),
            "mismatches": mismatches, "exact_rate": 1.0 - mismatches / len(shared),
        })
    return results


def _audit_source(label, path, loader, timeframe, arbiter_agg, granularity_minutes):
    entry = {"source_id": label, "timeframe": timeframe, "loader": loader,
             "path": str(path), "opened": False}
    if not path.exists():
        entry.update({"status": "SOURCE_MISSING"})
        return entry, None
    try:
        candles, report = _load(path, timeframe, loader)
    except Exception as exc:  # fail closed -- an unreadable source is not usable
        entry.update({"status": "REJECTED_BY_LOADER",
                      "error": f"{type(exc).__name__}: {exc}"})
        return entry, None

    entry.update({
        "opened": True, "rows": len(candles),
        "first_timestamp_utc": candles[0].time.isoformat(),
        "last_timestamp_utc": candles[-1].time.isoformat(),
        "normalized_timezone": getattr(report, "normalized_timezone", None),
    })
    by_time = {c.time: (c.open, c.high, c.low, c.close) for c in candles}

    overall = _shift_scan(by_time, arbiter_agg)
    if not overall:
        entry.update({"status": "NO_OVERLAP_WITH_M1_ARBITER"})
        return entry, None
    overall.sort(key=lambda r: r["exact_rate"], reverse=True)
    best = overall[0]

    per_season = {}
    season_shifts = {}
    for name, window in SEASONS.items():
        scan = _shift_scan(by_time, arbiter_agg, season=window)
        if not scan:
            continue
        scan.sort(key=lambda r: r["exact_rate"], reverse=True)
        per_season[name] = scan[0]
        if scan[0]["exact_rate"] >= EXACT_ALIGNMENT_THRESHOLD:
            season_shifts[name] = scan[0]["shift_hours"]

    aligned = best["exact_rate"] >= EXACT_ALIGNMENT_THRESHOLD
    # A file that is exactly aligned in two seasons at DIFFERENT shifts is internally
    # DST-inconsistent: no single time base describes it.
    dst_inconsistent = len(set(season_shifts.values())) > 1

    entry.update({
        "best_shift_hours": best["shift_hours"],
        "best_exact_rate": round(best["exact_rate"], 6),
        "shared_buckets": best["shared_buckets"],
        "mismatches": best["mismatches"],
        "shift_scan": [{**r, "exact_rate": round(r["exact_rate"], 6)} for r in overall],
        "per_season_best": {k: {**v, "exact_rate": round(v["exact_rate"], 6)}
                            for k, v in per_season.items()},
        "dst_consistency": ("DST_INCONSISTENT" if dst_inconsistent
                            else "DST_CONSISTENT" if season_shifts else "NOT_EVALUABLE"),
        "timezone_consistent": bool(aligned and not dst_inconsistent),
        "status": ("ALIGNED" if aligned and not dst_inconsistent
                   else "MISALIGNED" if not aligned
                   else "DST_INCONSISTENT"),
    })
    if not aligned:
        entry["exclusion_reason"] = (
            f"NOT_ALIGNED: best whole-hour shift {best['shift_hours']:+d}h reaches only "
            f"{best['exact_rate']:.6f} exact agreement with the canonical M1 arbiter"
        )
    elif dst_inconsistent:
        entry["exclusion_reason"] = (
            "DST_INCONSISTENT: per-season exact shifts differ "
            f"({season_shifts}); no single time base describes this file"
        )

    if entry["timezone_consistent"]:
        return entry, candles
    return entry, None


def _consistent_intersection(series_by_tf) -> dict:
    """Three-way intersection using ONLY timezone-consistent legs."""
    if not all(series_by_tf.get(tf) for tf in ("H1", "M15", "M1")):
        return {"evaluable": False}
    spans = {}
    for tf, candles in series_by_tf.items():
        native = {"H1": timedelta(hours=1), "M15": timedelta(minutes=15),
                  "M1": timedelta(minutes=1)}[tf]
        spans[tf] = (candles[0].time, candles[-1].time + native)
    start = max(s[0] for s in spans.values())
    end = min(s[1] for s in spans.values())
    return {
        "evaluable": True,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "days": round((end - start).total_seconds() / 86400, 3) if end > start else 0.0,
        "per_timeframe_span": {k: {"start": v[0].isoformat(), "end": v[1].isoformat()}
                               for k, v in spans.items()},
        "limiting_timeframe": min(spans, key=lambda k: spans[k][1]),
    }


def main() -> int:
    arbiter_candles, _ = _load(M1_ARBITER[1], "M1", M1_ARBITER[2])
    print(f"M1 arbiter: {M1_ARBITER[0]} -- {len(arbiter_candles)} bars "
          f"{arbiter_candles[0].time.isoformat()} -> {arbiter_candles[-1].time.isoformat()}")
    arbiter_h1 = _aggregate(arbiter_candles, 60)
    arbiter_m15 = _aggregate(arbiter_candles, 15)

    report = {"schema": "AG_SSC_V1_0_1_ONE_YEAR_CROSS_LEG_TIMEZONE_CONSISTENCY_AUDIT_V1",
              "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1", "strategy_version": "1.0.1",
              "symbol": SYMBOL,
              "arbiter": {"source_id": M1_ARBITER[0], "timeframe": "M1",
                          "rows": len(arbiter_candles)},
              "window": {"start_utc": WINDOW_START.isoformat(),
                         "end_utc": WINDOW_END.isoformat()},
              "alignment_threshold": EXACT_ALIGNMENT_THRESHOLD,
              "h1_sources": [], "m15_sources": [],
              "timezone_consistent_h1": [], "timezone_consistent_m15": []}

    consistent_series = {}
    for tf, sources, agg, gran in (("H1", H1_SOURCES, arbiter_h1, 60),
                                   ("M15", M15_SOURCES, arbiter_m15, 15)):
        print(f"\n=== {tf} sources arbitrated against the M1 leg ===")
        for label, path, loader in sources:
            entry, candles = _audit_source(label, path, loader, tf, agg, gran)
            report[f"{tf.lower()}_sources"].append(entry)
            if entry.get("status") == "SOURCE_MISSING":
                print(f"  {label:60s} MISSING")
                continue
            if entry.get("status") == "REJECTED_BY_LOADER":
                print(f"  {label:60s} REJECTED: {entry['error']}")
                continue
            if entry.get("status") == "NO_OVERLAP_WITH_M1_ARBITER":
                print(f"  {label:60s} NO OVERLAP WITH M1 ARBITER")
                continue
            print(f"  {label:60s} rows={entry['rows']:6d} best={entry['best_shift_hours']:+d}h "
                  f"exact={entry['best_exact_rate']:.6f} {entry['dst_consistency']:15s} "
                  f"{entry['status']}")
            if entry["timezone_consistent"]:
                report[f"timezone_consistent_{tf.lower()}"].append(label)
                consistent_series.setdefault(tf, []).append(candles)

    # Union the timezone-consistent legs per timeframe (deduplicated by timestamp, with
    # every contributor individually proven exactly aligned to the same M1 arbiter, so
    # overlapping contributors agree by construction).
    for tf in ("H1", "M15"):
        groups = consistent_series.get(tf, [])
        if groups:
            merged = {}
            for candles in groups:
                for c in candles:
                    merged[c.time] = c
            consistent_series[tf] = [merged[t] for t in sorted(merged)]
    consistent_series["M1"] = arbiter_candles

    intersection = _consistent_intersection(consistent_series)
    report["timezone_consistent_intersection"] = intersection
    report["covers_requested_window"] = bool(
        intersection.get("evaluable")
        and datetime.fromisoformat(intersection["start_utc"]) <= WINDOW_START
        and datetime.fromisoformat(intersection["end_utc"]) >= WINDOW_END + timedelta(seconds=1)
    )
    report["FINAL_STATUS"] = (
        "CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW" if report["covers_requested_window"]
        else "BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT"
    )

    print("\n=== timezone-consistent three-way intersection ===")
    if intersection.get("evaluable"):
        print(f"  {intersection['start_utc']} -> {intersection['end_utc']} "
              f"({intersection['days']} days)")
        print(f"  limiting timeframe: {intersection['limiting_timeframe']}")
    else:
        print("  NOT EVALUABLE -- at least one timeframe has no timezone-consistent leg")
    print(f"\n  consistent H1 : {report['timezone_consistent_h1']}")
    print(f"  consistent M15: {report['timezone_consistent_m15']}")
    print(f"\nFINAL_STATUS = {report['FINAL_STATUS']}")
    if not report["covers_requested_window"]:
        print(f"requested window = {WINDOW_START.isoformat()} -> {WINDOW_END.isoformat()}")
    return 0 if report["covers_requested_window"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
