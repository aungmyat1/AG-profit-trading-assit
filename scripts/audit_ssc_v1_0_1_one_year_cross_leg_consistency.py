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
MIN_COMMON_BUCKETS_FOR_CENSUS = 100  # below this, a shift's "explanation" is noise, not evidence

# The canonical one-year window this gate was written for (identical to the coverage
# audit's PRIMARY window; not outcome-derived).
WINDOW_START = datetime(2025, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

# EU DST transition instants that actually fall inside the mission window (broker
# server time is UTC+2 winter / UTC+3 summer, EU convention: last Sunday of March
# spring-forward, last Sunday of October fall-back). These two dates split the window
# into three season segments with NO gap and NO overlap, so every timestamp in the
# window is classified into exactly one segment -- unlike the previous fixed
# `SEASONS` calendar windows (Nov1-Mar1 / May1-Sep1), which left the ~4.5 months
# around each transition (2025-09-15..2025-11-01, 2026-03-01..2026-05-01) unclassified
# and therefore untested by the per-season census (fixed 2026-09-21, cross-leg gate
# hardening: the prior windows never straddled an actual transition instant).
DST_FALL_BACK_2025 = datetime(2025, 10, 26, 1, 0, tzinfo=timezone.utc)
DST_SPRING_FORWARD_2026 = datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)

# Season segments, restricted to the mission window (so no timestamp far outside the
# window -- e.g. EXTERNAL_D_ROOT's own 2025-01-02 history, which predates a DIFFERENT
# DST transition -- is ever miscounted into one of these labels).
SEASON_SEGMENTS = (
    ("SUMMER_PRE_FALLBACK", WINDOW_START, DST_FALL_BACK_2025),
    ("WINTER", DST_FALL_BACK_2025, DST_SPRING_FORWARD_2026),
    ("SUMMER_POST_SPRINGFORWARD", DST_SPRING_FORWARD_2026, WINDOW_END + timedelta(seconds=1)),
)

# (label, path, loader) -- loader is "utc" (already-UTC timestamp_utc CSV) or "mt5"
# (broker-local MT5 export-menu CSV, resolved by the per-week reopen authority).
#
# DERIVED legs (mission SSC ONE-YEAR H1/M15 AUTHORITY REMEDIATION V1) are produced by
# `scripts/derive_ssc_one_year_h1_m15_from_m1.py` FROM the M1 arbiter itself, so their
# alignment with it is guaranteed BY CONSTRUCTION rather than being an independent
# finding. They are tracked separately for exactly that reason: the gate must never
# present a self-derived leg as independent corroboration of the arbiter's own alignment.
DERIVED_H1 = ("DERIVED::SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::H1",
              DATA_ROOT / "SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001" / "raw" / "EURUSD_H1.csv", "utc")
DERIVED_M15 = ("DERIVED::SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::M15",
               DATA_ROOT / "SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001" / "raw" / "EURUSD_M15.csv", "utc")
DERIVED_SOURCE_IDS = {DERIVED_H1[0], DERIVED_M15[0]}

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
    DERIVED_H1,
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
    DERIVED_M15,
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


# ---------------------------------------------------------------------------
# Ported predicate logic (cross_leg_timebase_arbiter.py draft, Mission 1 P3 hardening,
# 2026-09-21): per-BUCKET bimodal shift census, independent of any calendar-season
# heuristic. Kept in this one script (no second arbiter module) per instruction --
# `scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` remains the single P3
# authority; this augments its own `_audit_source`, it does not compete with it.
# ---------------------------------------------------------------------------

def _bimodal_shift_census(by_time: dict, arbiter_agg: dict, min_common_buckets: int) -> dict:
    """For EACH arbiter bucket, find the whole-hour shift (if any) at which the
    candidate's bucket matches it exactly, then count how many buckets each shift
    explains. A leg is internally DST-fractured iff >= 2 distinct shifts each explain
    at least `min_common_buckets` -- this is the generalization of the DEV_002 finding
    (winter at -1h, summer at 0h) and needs no calendar-season assumption at all."""
    explaining_counts: dict = {}
    for t, agg_ohlc in arbiter_agg.items():
        for shift in (-3, -2, -1, 0, 1, 2, 3):
            candidate_ohlc = by_time.get(t + timedelta(hours=shift))
            if candidate_ohlc is not None and candidate_ohlc == agg_ohlc:
                explaining_counts[shift] = explaining_counts.get(shift, 0) + 1
                break  # this bucket is explained by its first (smallest-|shift|-first) match
    return {h: n for h, n in explaining_counts.items() if n >= min_common_buckets}


def _segments_with_coverage(by_time: dict, arbiter_agg: dict, min_common_buckets: int) -> dict:
    """Season-segment coverage (see SEASON_SEGMENTS): {segment_name: shared_bucket_count}
    for every segment where the candidate shares >= min_common_buckets with the arbiter,
    restricted to the mission window. Pure function -- no file I/O -- so P3's
    single-season-exclusion rule is directly unit-testable."""
    per_segment_common = {}
    for name, seg_start, seg_end in SEASON_SEGMENTS:
        seg_common = sum(1 for t in arbiter_agg if seg_start <= t < seg_end and (t in by_time))
        if seg_common >= min_common_buckets:
            per_segment_common[name] = seg_common
    return per_segment_common


def _classify_alignment(best: dict, census: dict, segments_evaluated: int) -> tuple:
    """Pure admission-status predicate (P3 hardening, 2026-09-21): returns
    (status, dst_consistency, timezone_consistent). Admission ('ALIGNED') requires ALL
    of: no internal DST fracture (bimodal census), best whole-hour shift == +0h at
    exact_rate == 1.0, AND coverage in >= 2 season segments (never a single-season
    source, however cleanly aligned within its own one segment)."""
    if len(census) >= 2:
        return "DST_INCONSISTENT", "DST_INCONSISTENT", False
    aligned_at_zero = best["shift_hours"] == 0 and best["exact_rate"] >= EXACT_ALIGNMENT_THRESHOLD
    if not aligned_at_zero:
        return "MISALIGNED", "NOT_EVALUABLE", False
    if segments_evaluated < 2:
        return "NOT_EVALUABLE_SINGLE_SEASON", "NOT_EVALUABLE", False
    return "ALIGNED", "DST_CONSISTENT", True


def _merge_with_conflict_detection(groups: list) -> tuple:
    """Union candle groups by timestamp, verifying OHLC agreement on any shared
    timestamp instead of last-writer-wins overwrite (P3 hardening, 2026-09-21: a prior
    version silently let a later-listed source's bar replace an earlier one even when
    they disagreed -- verified reproducible: a uniformly-shifted +3h leg admitted as
    ALIGNED at 0h-only-in-one-season could overwrite 1437/1440 genuinely-UTC bars from
    an earlier source for one day). Returns (merged_candles_ascending, conflict_isoformat_timestamps).
    A conflicting timestamp is dropped from the merge entirely (fail closed), never
    resolved by source-list order."""
    merged: dict = {}
    conflicts: list = []
    for candles in groups:
        for c in candles:
            existing = merged.get(c.time)
            if existing is None:
                merged[c.time] = c
            elif (existing.open, existing.high, existing.low, existing.close) != (c.open, c.high, c.low, c.close):
                conflicts.append(c.time.isoformat())
                merged.pop(c.time, None)
    return [merged[t] for t in sorted(merged)], sorted(set(conflicts))


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

    # Internal DST fracture: per-bucket bimodal census, calendar-independent (catches
    # the DEV_002 shape and any other internally-mixed-offset file, not just one that
    # happens to fracture at a SEASON_SEGMENTS boundary).
    census = _bimodal_shift_census(by_time, arbiter_agg, MIN_COMMON_BUCKETS_FOR_CENSUS)

    # Season-segment coverage: restricted to the mission window, split at the two real
    # DST transition instants inside it (2025-10-26, 2026-03-29). A source whose data
    # only ever falls in ONE segment has never been tested across a DST boundary --
    # its own shift==0/rate==1.0 result, however clean, is NOT_EVALUABLE evidence that
    # it stays UTC-consistent across a transition (this is the gap a two-season
    # Nov1-Mar1 / May1-Sep1 calendar heuristic silently papered over for any source
    # confined to one of those un-modelled shoulder months).
    per_segment_common = _segments_with_coverage(by_time, arbiter_agg, MIN_COMMON_BUCKETS_FOR_CENSUS)
    status, dst_consistency, timezone_consistent = _classify_alignment(best, census, len(per_segment_common))

    entry.update({
        "best_shift_hours": best["shift_hours"],
        "best_exact_rate": round(best["exact_rate"], 6),
        "shared_buckets": best["shared_buckets"],
        "mismatches": best["mismatches"],
        # A leg derived FROM the arbiter is aligned by construction -- it can never be
        # independent corroboration of the arbiter's own alignment.
        "derived_from_arbiter": label in DERIVED_SOURCE_IDS,
        "shift_scan": [{**r, "exact_rate": round(r["exact_rate"], 6)} for r in overall],
        "bimodal_shift_census": census,
        "season_segments_evaluated": sorted(per_segment_common),
        "dst_consistency": dst_consistency,
        "timezone_consistent": timezone_consistent,
        "status": status,
    })
    if status == "MISALIGNED":
        entry["exclusion_reason"] = (
            f"NOT_ALIGNED_AT_ZERO_SHIFT: best whole-hour shift {best['shift_hours']:+d}h "
            f"reaches {best['exact_rate']:.6f} exact agreement; admission requires "
            f"best_shift == +0h at exact_rate == 1.0"
        )
    elif status == "DST_INCONSISTENT":
        entry["exclusion_reason"] = (
            f"INTERNALLY_DST_INCONSISTENT: per-bucket census explains distinct shifts "
            f"{census} at >= {MIN_COMMON_BUCKETS_FOR_CENSUS} buckets each; no single time "
            f"base describes this file"
        )
    elif status == "NOT_EVALUABLE_SINGLE_SEASON":
        entry["exclusion_reason"] = (
            f"NOT_EVALUABLE_SINGLE_SEASON: aligned at +0h/1.0 but data only falls in "
            f"{sorted(per_segment_common)} -- never tested across a DST transition, so "
            f"UTC-consistency across the boundary is unproven, not assumed"
        )

    if timezone_consistent:
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

    # Union the timezone-consistent legs per timeframe. Every contributor was
    # individually proven ALIGNED (best_shift==0, exact_rate==1.0) against the SAME M1
    # arbiter, so overlapping contributors are expected to agree by construction -- but
    # this is now VERIFIED per shared timestamp, not assumed: a disagreement is a real
    # defect (e.g. a source that passed its own global/segment checks by coincidence)
    # and is reported as a CONFLICT, with the conflicting timestamp dropped from the
    # merged series (fail closed) rather than silently resolved by source-list order
    # (previously: `merged[c.time] = c`, last writer wins).
    conflicts = {"H1": [], "M15": []}
    for tf in ("H1", "M15"):
        groups = consistent_series.get(tf, [])
        if groups:
            consistent_series[tf], conflicts[tf] = _merge_with_conflict_detection(groups)
    consistent_series["M1"] = arbiter_candles
    report["cross_leg_conflicts"] = conflicts
    any_conflicts = bool(conflicts["H1"] or conflicts["M15"])

    intersection = _consistent_intersection(consistent_series)
    report["timezone_consistent_intersection"] = intersection
    report["covers_requested_window"] = bool(
        not any_conflicts
        and intersection.get("evaluable")
        and datetime.fromisoformat(intersection["start_utc"]) <= WINDOW_START
        and datetime.fromisoformat(intersection["end_utc"]) >= WINDOW_END + timedelta(seconds=1)
    )
    report["decision_window_timebase"] = "UTC_SINGLE_TIMEBASE" if report["covers_requested_window"] else "NOT_ESTABLISHED"
    report["FINAL_STATUS"] = (
        "CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW" if report["covers_requested_window"]
        else "BLOCKED_CROSS_LEG_CONFLICTS_DETECTED" if any_conflicts
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
    independent_h1 = [s for s in report["timezone_consistent_h1"] if s not in DERIVED_SOURCE_IDS]
    independent_m15 = [s for s in report["timezone_consistent_m15"] if s not in DERIVED_SOURCE_IDS]
    report["independent_corroboration"] = {
        "H1": independent_h1, "M15": independent_m15,
        "note": ("DERIVED::* legs are produced FROM the M1 arbiter and are aligned by "
                 "construction -- they are excluded from this list and are never presented "
                 "as independent corroboration of the arbiter's own alignment."),
    }
    print(f"\n  independent (non-derived) corroboration H1 : {independent_h1}")
    print(f"  independent (non-derived) corroboration M15: {independent_m15}")
    if any_conflicts:
        print(f"\n  CROSS_LEG_CONFLICTS (dropped from merge, fail closed): {report['cross_leg_conflicts']}")
    print(f"\ndecision_window_timebase = {report['decision_window_timebase']}")
    print(f"FINAL_STATUS = {report['FINAL_STATUS']}")
    if not report["covers_requested_window"]:
        print(f"requested window = {WINDOW_START.isoformat()} -> {WINDOW_END.isoformat()}")
    return 0 if report["covers_requested_window"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
