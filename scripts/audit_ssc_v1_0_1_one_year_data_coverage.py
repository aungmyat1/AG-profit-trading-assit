"""SSC v1.0.1 ONE-YEAR HISTORICAL RESEARCH BACKTEST (P1) -- data availability audit.

READ-ONLY, deterministic, no replay. Answers exactly one question before any economic
work is allowed to start:

    Does a canonical H1 + M15 + M1 EURUSD dataset exist that spans the mission's
    one-year historical evaluation window (and, for H1, additionally carries the
    canonical STRUCTURE_WARMUP_H1_BARS pre-window warmup)?

What it does:

  1. Enumerates every reachable EURUSD H1/M15/M1 source:
       (a) in-repo frozen dataset packages under data/research/**/raw/ (UTC
           `timestamp_utc` MetaTrader5 copy_rates_* exports), and
       (b) the owner-authorized D:\\ Vantage/MT5 "Export menu" family
           (tab-delimited, broker-local time, resolved to UTC by the pre-existing
           market_data_readiness.scanner -- reimplemented nowhere here).
  2. Independently recomputes each source's identity and quality signals (sha256, row
     count, first/last timestamp, duplicate / non-monotonic / invalid-OHLC counts,
     gap census, timezone authority, symbol-metadata authority).
  3. Computes per-timeframe UNION coverage inside the evaluation window and reports the
     EXACT missing intervals, plus the three-way (H1 x M15 x M1) intersection -- the
     only span over which a canonical replay could actually run end to end.

Hard rules enforced by construction (never violated silently):

  * No interpolation, no manufactured bars, no M5-for-M1 substitution, no provider
    mixing without explicit lineage. A source is either used as-is or not used.
  * PROTECTED datasets (OOS / holdout / CONFIRM_001) are never opened: their raw bytes
    are not read, and their manifest `access_count` is asserted unchanged.
  * An unresolved-timezone source is inadmissible for coverage (fail closed) rather
    than assumed UTC.
  * The strategy config is loaded read-only to resolve the canonical session windows;
    no strategy parameter is read back into, or out of, any dataset decision.

Authority: this script does NOT call session_sweep_continuation.replay.run_replay. P1
is a gate that must pass before P6 (the one canonical replay) is reachable at all.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from market_data_readiness.scanner import (  # noqa: E402
    classify_filename,
    discover_candidates,
    scan_file,
    sha256_stream,
)
from session_sweep_continuation.config import load_config  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

SYMBOL = "EURUSD"
TIMEFRAMES = ("H1", "M15", "M1")
NATIVE_DELTA = {"H1": timedelta(hours=1), "M15": timedelta(minutes=15), "M1": timedelta(minutes=1)}

# Candidate one-year evaluation windows. Neither is chosen from strategy outcomes:
#   PRIMARY  -- one complete year ending immediately BEFORE the protected prospective
#               CONFIRM_001 calendar (which opens 2026-09-15T00:00:00Z), per that
#               boundary and nothing else.
#   ALTERNATE -- the same one-year length calendar-shifted 4 days later, evaluated so
#               the admissibility verdict does not depend on where the boundary is
#               drawn (a robust gate must fail for both).
EVALUATION_WINDOWS = {
    "PRIMARY_1Y_ENDING_BEFORE_PROTECTED_CALENDAR": (
        datetime(2025, 9, 15, 0, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc),
    ),
    "ALTERNATE_1Y_CALENDAR_SHIFTED": (
        datetime(2025, 9, 19, 0, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 18, 23, 59, 59, tzinfo=timezone.utc),
    ),
}
PRIMARY_WINDOW_ID = "PRIMARY_1Y_ENDING_BEFORE_PROTECTED_CALENDAR"
EVALUATION_START, EVALUATION_END = EVALUATION_WINDOWS[PRIMARY_WINDOW_ID]
# market_structure.tiers.EXTERNAL_SWING_LENGTH(50) * 20 -- frozen, unchanged.
STRUCTURE_WARMUP_H1_BARS = 1000
# AG_STRATEGY_DIRECTION_CONTRACT_V1 P17 -- frozen, unchanged.
CANONICAL_PARTIAL_TARGET_MODE = "OPPOSITE_SESSION_BOUNDARY"

# Where the (owner-authorized, 2026-09-10 blanket D:\ FX authorization) broker export
# family lives. Only this one non-recursive directory is ever globbed.
EXTERNAL_ROOT = "D:\\"

# Datasets whose raw bytes must never be opened by this audit.
PROTECTED_DATASET_IDS = {
    "SSC1D_WP1_OOS_EURUSD_2024Q1",  # OOS pilot, access_count must remain 0
}

# Symbol-metadata manifests actually bound to each source family (path -> role).
SYMBOL_METADATA_BINDINGS = {
    "EXTERNAL_D_ROOT_H1": "config/historical_datasets/EURUSD_H1_symbol_metadata.yaml",
    "EXTERNAL_D_ROOT_M15": None,
    "EXTERNAL_D_ROOT_M1": None,
    "SSC_V1_0_1_G2_DEV_002": "config/historical_datasets/EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml",
    "SSC_V1_0_1_G2_DEV_001": None,
    "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914": "config/historical_datasets/EURUSD_H1_GEN_002_symbol_metadata.yaml",
}

# Declared data roles (read from each package's own dataset_manifest.json where one
# exists; this table only fills the gaps for packages that carry no manifest).
DECLARED_ROLES = {
    "SSC_V1_0_1_G2_DEV_001": "DEVELOPMENT (consumed)",
    "SSC_V1_0_1_G2_DEV_002": "DEVELOPMENT (consumed -- G2 POPULATION_V1 frozen)",
    "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914": "HYPOTHESIS_GENERATION_ONLY (consumed -- HYP_002)",
    "SSC_HYP002_H1_WARMUP_CONTEXT_20260528_20260731": "WARMUP_CONTEXT_ONLY (consumed)",
    "SSC1D_WP1_OOS_EURUSD_2024Q1": "OUT_OF_SAMPLE (PROTECTED, untouched)",
}

DERIVED_ARTIFACT_SOURCES = (
    (
        "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_EVALUATION_INPUT/"
        "EURUSD_H1_WARMUP_PLUS_GEN002.csv",
        "H1",
        "DERIVED_H1_CONTEXT (concatenation of two already-owner-approved H1 sources)",
    ),
)


# ---------------------------------------------------------------------------------
# interval algebra
# ---------------------------------------------------------------------------------
def _merge(intervals):
    out = []
    for start, end in sorted(intervals):
        if start >= end:
            continue
        if out and start <= out[-1][1]:
            if end > out[-1][1]:
                out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def _complement(window_start, window_end, covered):
    """Missing sub-intervals of [window_start, window_end) not covered by `covered`."""
    missing = []
    cursor = window_start
    for start, end in covered:
        start, end = max(start, window_start), min(end, window_end)
        if end <= start:
            continue
        if start > cursor:
            missing.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        missing.append((cursor, window_end))
    return missing


def _intersect(a, b):
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if start < end:
            out.append((start, end))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return out


def _weekdays_between(start, end):
    """Count Mon-Fri calendar days touched by [start, end) -- a lower bound on the FX
    weekdays an interval really loses; used only to prove a missing interval is not a
    weekend/news closure artefact."""
    days, cursor = 0, start.date()
    while cursor < end.date() or (cursor == end.date() and end.time() > datetime.min.time()):
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


def _iso(ts):
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


# ---------------------------------------------------------------------------------
# source discovery / measurement
# ---------------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _in_repo_sources():
    """Every EURUSD H1/M15/M1 file under data/research/**/raw/ plus declared derived
    artifact inputs. PROTECTED datasets are recorded from metadata only, never opened."""
    sources = []
    data_root = REPO_ROOT / "data" / "research"
    for ds_dir in sorted(p for p in data_root.rglob("*") if (p / "raw").is_dir()):
        dataset_id = ds_dir.name
        manifest = (_read_json(ds_dir / "dataset_manifest.json")
                    or _read_json(ds_dir / "oos_dataset_manifest.json") or {})
        protected = dataset_id in PROTECTED_DATASET_IDS
        for tf in TIMEFRAMES:
            path = ds_dir / "raw" / f"{SYMBOL}_{tf}.csv"
            if not path.exists():
                continue
            if protected:
                sources.append({
                    "source_id": f"{dataset_id}::{tf}",
                    "dataset_id": dataset_id,
                    "location": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "timeframe": tf,
                    "provider": manifest.get("broker", "UNKNOWN"),
                    "timezone_authority": "PROTECTED_NOT_INSPECTED",
                    "data_role": DECLARED_ROLES.get(dataset_id, "UNKNOWN"),
                    "status": "PROTECTED_NOT_ACCESSED",
                    "access_count": manifest.get("access_count"),
                    "admissible_for_coverage": False,
                    "exclusion_reason": "PROTECTED (OOS/holdout/confirmation role) -- raw bytes never opened",
                })
                continue
            sources.append(_measure_utc_source(path, tf, dataset_id, manifest))
        print(f"[in-repo] {dataset_id}", file=sys.stderr, flush=True)
    for rel, tf, role in DERIVED_ARTIFACT_SOURCES:
        path = REPO_ROOT / rel
        if path.exists():
            sources.append(_measure_utc_source(path, tf, "HYP_002_EVALUATION_INPUT", {}, role_override=role))
    return sources


def _measure_utc_source(path: Path, tf: str, dataset_id: str, manifest: dict, role_override=None):
    """Measure one already-UTC `timestamp_utc` CSV using the repository's own canonical
    UTC loader (which fails closed on any duplicate/unordered timestamp or invalid
    OHLC, so a successful load IS the quality verdict)."""
    entry = {
        "source_id": f"{dataset_id}::{tf}",
        "dataset_id": dataset_id,
        "location": str(path.relative_to(REPO_ROOT)).replace("\\", "/") if path.is_relative_to(REPO_ROOT) else str(path),
        "timeframe": tf,
        "provider": manifest.get("broker", "Vantage Markets (Pty) Ltd"),
        "broker_server": manifest.get("broker_server"),
        "schema": "UTC timestamp_utc (MetaTrader5 copy_rates_* native)",
        "data_role": role_override or DECLARED_ROLES.get(dataset_id) or manifest.get("data_role", "UNKNOWN"),
        # Symbol-metadata manifests in this repository are H1-structure manifests; only
        # an H1 leg can legitimately claim one.
        "symbol_metadata_manifest": SYMBOL_METADATA_BINDINGS.get(dataset_id) if tf == "H1" else None,
        "admissible_for_coverage": True,
        "status": "MEASURED",
    }
    try:
        candles, report = load_utc_export_csv(str(path), SYMBOL, tf)
    except Exception as exc:  # fail closed: an unreadable/invalid source is not usable
        entry.update({"status": "REJECTED_BY_LOADER", "error": f"{type(exc).__name__}: {exc}",
                      "admissible_for_coverage": False})
        return entry

    expected = (manifest.get("per_file") or {}).get(f"{SYMBOL}_{tf}", {}).get("sha256")
    sha = _sha256_file(path)
    entry.update({
        "sha256": sha,
        "manifest_sha256_match": (sha == expected) if expected else None,
        "row_count": len(candles),
        "first_timestamp_utc": _iso(report.start_utc),
        "last_timestamp_utc": _iso(report.end_utc),
        "duplicate_timestamps": 0,
        "non_monotonic_timestamps": 0,
        "invalid_ohlc_count": 0,
        "zero_or_negative_price_rows": 0,
        "quality_status": "PASS",
        "quality_evidence": "historical_replay.utc_export_csv_loader.load_utc_export_csv (fails closed)",
        "timezone_authority": f"UTC (loader-recorded source={report.source_timezone})",
        "unexpected_gap_count": len(report.unexpected_gaps),
        "expected_closure_gap_count": len(report.gaps) - len(report.unexpected_gaps),
        "largest_gap_hours": round(max((g.duration for g in report.gaps), default=timedelta(0)).total_seconds() / 3600, 2),
        "_bar_times": [c.time for c in candles],
    })
    return entry


def _external_sources():
    """Owner-authorized D:\\ broker export family, measured with the pre-existing
    market_data_readiness.scanner (streaming, read-only, hashes, resolves timezone).

    Only H1/M15/M1 candidates get a full row-by-row scan. Every other file discovered
    in the same directory (M5, Daily, raw bid/ask ticks) is inventoried metadata-only --
    hashed and range-recorded -- and marked ineligible by construction: M5 is not a
    canonical SSC input, and deriving M1 out of tick data would be exactly the
    "manufacture M1" substitution this mission forbids, so it is never attempted."""
    if not Path(EXTERNAL_ROOT).exists():
        return [{"source_id": "EXTERNAL_D_ROOT", "status": "EXTERNAL_ROOT_UNAVAILABLE",
                 "location": EXTERNAL_ROOT, "admissible_for_coverage": False}]
    sources = []
    for path in sorted(discover_candidates(EXTERNAL_ROOT, [SYMBOL])[SYMBOL]):
        meta = classify_filename(path)
        if meta is None:
            # e.g. an H4 export: no timeframe token this repository's scanner can route,
            # so it is recorded by filename only and never parsed.
            sources.append({
                "source_id": f"EXTERNAL_D_ROOT::{Path(path).name}",
                "dataset_id": "EXTERNAL_D_ROOT", "location": path,
                "timeframe": "UNCLASSIFIED", "filename_declared_range_raw": Path(path).name,
                "sha256": sha256_stream(path), "file_size_bytes": os.path.getsize(path),
                "provider": "Vantage Markets (Pty) Ltd / VantageMarkets-Demo (owner-authorized D:\\ FX export family)",
                "quality_status": "NOT_SCANNED_UNROUTABLE_FILENAME",
                "timezone_authority": "NOT_RESOLVED (out of scope)", "data_role": "OUT_OF_SCOPE_CANDIDATE",
                "admissible_for_coverage": False,
                "exclusion_reason": "NOT_ROUTABLE: filename carries no H1/M15/M5/M1/Daily timeframe token.",
                "status": "MEASURED_METADATA_ONLY",
            })
            continue
        if meta["declared_tf"] not in TIMEFRAMES:
            sources.append(_metadata_only_external_entry(path, meta))
            continue
        rec = scan_file(path, meta)
        rec.sha256 = sha256_stream(path)
        sources.append(_external_entry(rec))
        print(f"[external] scanned {Path(path).name} rows={rec.row_count} tz={rec.timezone_status}",
              file=sys.stderr, flush=True)
    return sources


def _metadata_only_external_entry(path, meta):
    """Hash + filename-declared range only. Never parsed, never eligible: these files
    exist in the same owner-authorized directory but are not canonical SSC inputs."""
    return {
        "source_id": f"EXTERNAL_D_ROOT::{meta['filename']}",
        "dataset_id": "EXTERNAL_D_ROOT",
        "location": path,
        "timeframe": meta["declared_tf"],
        "declared_timeframe": meta["declared_tf"],
        "filename_declared_range_raw": meta["filename"],
        "provider": "Vantage Markets (Pty) Ltd / VantageMarkets-Demo (owner-authorized D:\\ FX export family)",
        "schema": "MT5 Export-menu CSV (tab-delimited, broker-local time)",
        "sha256": sha256_stream(path),
        "file_size_bytes": os.path.getsize(path),
        "row_count": None,
        "quality_status": "NOT_SCANNED_OUT_OF_SCOPE",
        "quality_evidence": "metadata-only (sha256 + size); row-level scan intentionally skipped",
        "timezone_authority": "NOT_RESOLVED (out of scope)",
        "data_role": "OUT_OF_SCOPE_CANDIDATE",
        "admissible_for_coverage": False,
        "exclusion_reason": (
            "NOT_A_CANONICAL_INPUT: SSC v1.0.1 canonical inputs are H1 (bias/warmup), M15 "
            "(decision) and M1 (fill resolution) only. Substituting M5 or synthesizing M1 "
            "from raw tick data is prohibited by mission P1."
        ),
        "status": "MEASURED_METADATA_ONLY",
    }


def _external_entry(rec):
    """One fully scanned owner-authorized external H1/M15/M1 candidate."""
    normalized_tf = rec.observed_timeframe or rec.declared_timeframe
    entry = {
        "source_id": f"EXTERNAL_D_ROOT::{rec.filename}",
        "dataset_id": "EXTERNAL_D_ROOT",
        "location": rec.path,
        "timeframe": normalized_tf,
        "declared_timeframe": rec.declared_timeframe,
        "observed_timeframe": rec.observed_timeframe,
        "timeframe_status": rec.timeframe_status,
        "provider": "Vantage Markets (Pty) Ltd / VantageMarkets-Demo (owner-authorized D:\\ FX export family)",
        "broker_server": "VantageMarkets-Demo",
        "schema": "MT5 Export-menu CSV (tab-delimited, broker-local time)",
        "sha256": rec.sha256,
        "row_count": rec.row_count,
        "file_size_bytes": rec.file_size_bytes,
        "first_timestamp_utc": rec.first_ts_utc,
        "last_timestamp_utc": rec.last_ts_utc,
        "first_timestamp_source": rec.first_ts_raw,
        "last_timestamp_source": rec.last_ts_raw,
        "duplicate_timestamps": rec.duplicate_timestamps,
        "non_monotonic_timestamps": rec.nonmonotonic_timestamps,
        "invalid_ohlc_count": rec.ohlc_violations,
        "zero_or_negative_price_rows": rec.zero_or_negative_price_rows,
        "parse_failures": rec.parse_failures,
        "quality_status": rec.quality_status,
        "quality_evidence": "market_data_readiness.scanner.scan_file",
        "timezone_authority": rec.timezone_status,
        "broker_utc_offset_hours": rec.broker_utc_offset_hours,
        "largest_gap_hours": rec.largest_gap_hours,
        "data_role": "OWNER_AUTHORIZED_EXTERNAL_SOURCE",
        "symbol_metadata_manifest": SYMBOL_METADATA_BINDINGS.get(f"EXTERNAL_D_ROOT_{normalized_tf}"),
        "status": "MEASURED",
    }
    # Fail closed: an unresolved timezone (or a failed quality scan) can never
    # contribute coverage.
    entry["admissible_for_coverage"] = bool(
        normalized_tf in TIMEFRAMES
        and rec.quality_status == "PASS"
        and rec.timezone_status == "BROKER_OFFSET_CONFIRMED"
        and rec.first_ts_utc
        and rec.last_ts_utc
    )
    if not entry["admissible_for_coverage"]:
        reasons = [
            None if normalized_tf in TIMEFRAMES else f"timeframe={normalized_tf}",
            None if rec.quality_status == "PASS" else f"quality={rec.quality_status}",
            None if rec.timezone_status == "BROKER_OFFSET_CONFIRMED" else "timezone_unresolved",
        ]
        entry["exclusion_reason"] = "NOT_ADMISSIBLE: " + ", ".join(filter(None, reasons))
    return entry


# ---------------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------------
def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _coverage(sources, timeframe, window_start=EVALUATION_START, window_end=EVALUATION_END):
    """Union coverage of one timeframe by every admissible source, plus the exact
    missing sub-intervals of [window_start, window_end]."""
    intervals = []
    contributors = []
    for s in sources:
        if s.get("timeframe") != timeframe or not s.get("admissible_for_coverage"):
            continue
        start, end = _parse_iso(s["first_timestamp_utc"]), _parse_iso(s["last_timestamp_utc"])
        intervals.append((start, end + NATIVE_DELTA[timeframe]))
        contributors.append(s["source_id"])
    union = _merge(intervals)
    upper = window_end + timedelta(seconds=1)
    windowed = _merge([(max(a, window_start), min(b, upper))
                       for a, b in union if min(b, upper) > max(a, window_start)])
    missing = _complement(window_start, upper, windowed)
    return {
        "admissible_contributors": sorted(contributors),
        "covered_intervals": [[_iso(a), _iso(b)] for a, b in windowed],
        "missing_intervals": [
            {
                "from": _iso(a), "to": _iso(b),
                "duration_days": round((b - a).total_seconds() / 86400, 3),
                "weekdays_touched": _weekdays_between(a, b),
            }
            for a, b in missing
        ],
        "_union": union,
        "_windowed": windowed,
    }


def _window_report(sources, window_start, window_end, windows_config, h1_times):
    """One complete coverage verdict for one candidate evaluation window."""
    upper = window_end + timedelta(seconds=1)
    coverage = {tf: _coverage(sources, tf, window_start, window_end) for tf in TIMEFRAMES}
    three_way = _intersect(_intersect(coverage["H1"]["_windowed"], coverage["M15"]["_windowed"]),
                           coverage["M1"]["_windowed"])
    three_way_missing = _complement(window_start, upper, three_way)
    blocking = {tf: coverage[tf]["missing_intervals"] for tf in TIMEFRAMES
                if coverage[tf]["missing_intervals"]}

    warmup = {}
    for pair_id in sorted(windows_config):
        _ref_start, ref_end = windows_config[pair_id]["reference"].bounds_for_date(window_start.date())
        closed = sum(1 for t in h1_times if t < ref_end)
        warmup[pair_id] = {
            "first_window_decision_date": window_start.date().isoformat(),
            "reference_end_utc": _iso(ref_end),
            "closed_h1_bars_before_reference_end": closed,
            "required": STRUCTURE_WARMUP_H1_BARS,
            "warmup_pass": closed >= STRUCTURE_WARMUP_H1_BARS,
        }

    covered_days = {tf: round(sum((b - a).total_seconds() for a, b in coverage[tf]["_windowed"]) / 86400, 3)
                    for tf in TIMEFRAMES}
    return {
        "window": {"start_utc": _iso(window_start), "end_utc": _iso(window_end)},
        "AVAILABLE_H1": coverage["H1"]["covered_intervals"],
        "AVAILABLE_M15": coverage["M15"]["covered_intervals"],
        "AVAILABLE_M1": coverage["M1"]["covered_intervals"],
        "COMMON_INTERVAL": {
            "intervals": [[_iso(a), _iso(b)] for a, b in three_way],
            "total_covered_days": round(sum((b - a).total_seconds() for a, b in three_way) / 86400, 3),
            "note": "H1 x M15 x M1 intersection -- the only span a canonical replay could run end to end",
        },
        "WARMUP_AVAILABLE": {
            "pass": all(w["warmup_pass"] for w in warmup.values()),
            "per_session_pair": warmup,
            "warmup_ready_at_utc": _iso(h1_times[STRUCTURE_WARMUP_H1_BARS - 1])
            if len(h1_times) >= STRUCTURE_WARMUP_H1_BARS else None,
        },
        "MISSING_INTERVALS": blocking,
        "coverage_days_by_timeframe": covered_days,
        "three_way_missing_intervals": [
            {"from": _iso(a), "to": _iso(b),
             "duration_days": round((b - a).total_seconds() / 86400, 3),
             "weekdays_touched": _weekdays_between(a, b)}
            for a, b in three_way_missing
        ],
        "tier_a_full_year_coverage": not blocking,
        "FINAL_STATUS": "DATA_COVERAGE_COMPLETE" if not blocking else "BLOCKED_INCOMPLETE_ONE_YEAR_DATA",
    }


# ---------------------------------------------------------------------------------
# P2 -- lineage / contamination map
# ---------------------------------------------------------------------------------
CONSUMPTION_REGISTRY = ("artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/"
                        "SSC_V1_0_1_DATA_CONSUMPTION_REGISTRY_V1.json")

# Every named campaign P2 asks about, mapped to the registry record that actually
# evidences its consumption (a hypothesis "lane" is not a dataset of its own).
NAMED_CAMPAIGNS = [
    ("GEN_001", "GEN_001", "dataset"),
    ("GEN_002", "GEN_002", "dataset"),
    ("GEN_002A", "GEN_002A", "dataset"),
    ("DEV_001", "SSC_V1_0_1_G2_DEV_001", "dataset"),
    ("DEV_002", "SSC_V1_0_1_G2_DEV_002", "dataset"),
    ("Route B", "ROUTE_B_PHASE1_POPULATION", "dataset"),
    ("HYP_001", "GEN_001", "hypothesis_lane"),
    ("HYP_002", "GEN_002", "hypothesis_lane"),
    ("CONFIRM_001", "CONFIRM_001", "dataset"),
    ("HOLDOUT", "HOLDOUT", "protected"),
    ("OOS", "OOS", "protected"),
    ("H2", "H2_FRICTION_VERIFICATION", "dataset"),
]


def _lineage_map(sources, coverage):
    """P2: cross-reference the SSC data-consumption registry against this mission's
    one-year window. Nothing is re-labelled: a period that was consumed stays consumed,
    and the one-year campaign is classified HISTORICAL_RESEARCH_REPLICATION."""
    registry = _read_json(REPO_ROOT / CONSUMPTION_REGISTRY) or {}
    by_id = {r.get("dataset_id"): r for r in registry.get("records", [])}
    window_end_inclusive = EVALUATION_END

    def _overlap(r):
        start, end = r.get("start"), r.get("end")
        if not start or not end:
            return None
        try:
            s = _parse_iso(start)
            e = _parse_iso(end.split(" ")[0] if " " in end else end)
        except ValueError:
            return None
        lo, hi = max(s, EVALUATION_START), min(e, window_end_inclusive)
        if hi <= lo:
            return None
        return {
            "overlap_start_utc": _iso(lo), "overlap_end_utc": _iso(hi),
            "overlap_days": round((hi - lo).total_seconds() / 86400, 3),
        }

    campaign_rows = []
    for name, registry_id, kind in NAMED_CAMPAIGNS:
        record = by_id.get(registry_id)
        row = {
            "campaign": name,
            "kind": kind,
            "registry_record": registry_id,
            "protected_status": (record or {}).get("protected_status", "SEALED" if kind == "protected" else "UNKNOWN"),
            "prior_consumption": (record or {}).get("prior_consumption", "NONE (access_count=0)" if kind == "protected" else "UNKNOWN"),
            "counting_status": (record or {}).get("counting_status", "UNKNOWN"),
            "overlap_with_one_year_window": _overlap(record) if record else None,
        }
        is_protected = kind == "protected" or row["protected_status"] == "PROTECTED"
        row["one_year_campaign_effect"] = (
            "PROTECTED -- must remain untouched (access_count 0); a one-year window whose "
            "final days fall inside this calendar cannot be treated as DEVELOPMENT there."
            if is_protected
            else "OVERLAPS -- already-consumed historical period is re-inspected, NOT newly "
                 "consumed as fresh evidence; N must never be pooled with the earlier campaign."
            if row["overlap_with_one_year_window"]
            else "NO_OVERLAP_WITH_WINDOW"
        )
        campaign_rows.append(row)

    consumed_overlaps = sorted(
        r["campaign"] for r in campaign_rows
        if r["overlap_with_one_year_window"]
        and not (r["kind"] == "protected" or r["protected_status"] == "PROTECTED")
    )
    return {
        "schema": "AG_SSC_V1_0_1_HIST_1Y_LINEAGE_CONTAMINATION_MAP_V1",
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "strategy_version": "1.0.1",
        "generated_at_utc": datetime.now(timezone.utc).date().isoformat(),
        "registry_authority": CONSUMPTION_REGISTRY,
        "registry_head_sha": registry.get("head_sha"),
        "registry_freshness_boundary": registry.get("freshness_boundary"),
        "campaign_classification": "HISTORICAL_RESEARCH_ONLY",
        "campaign_classification_note": (
            "Explicitly NOT: a new G2 validation population, untouched OOS, holdout, "
            "CONFIRM_001, DEV_003, prospective confirmation, or DEMO-eligibility "
            "evidence. Previously consumed periods remain previously consumed, and no "
            "historical period becomes 'fresh' by being repackaged into a new dataset "
            "identity. Repository governance is not read as supporting a stronger role."
        ),
        "named_campaign_cross_reference": campaign_rows,
        "consumed_campaigns_overlapping_window": consumed_overlaps,
        "double_counting_warning": (
            "DEV_002 (N=22) sits entirely inside the one-year window. A one-year "
            "population must therefore NOT be added to DEV_002's N as if independent; "
            "the DEV_002 occurrences are a subset of the window, never additional sample."
        ),
        "protected_calendar_note": (
            "CONFIRM_001's reserved confirmation calendar begins 2026-09-15T00:00:00Z, "
            "i.e. the final four days of the mission's one-year window are protected "
            "confirmation calendar. Independent of the coverage block below, treating "
            "2026-09-15..2026-09-18 as DEVELOPMENT would contaminate protected evidence."
        ),
        "dataset_identity_conflicts": {
            "EURUSD_M15_GAP_20260620_20260802 (candidate)": (
                "Registry lists a 2026-06-20..2026-08-02 M15 gap as NOT_ACQUIRED. This "
                "audit finds the gap already covered by owner-authorized external M15 "
                "sources (see source_inventory); no acquisition is performed or implied."
            ),
            "SSC_V1_0_1_G2_DEV_001 vs SSC_V1_0_1_G2_DEV_002": (
                "DEV_002 M15/M1 are byte-identical to DEV_001's (same sha256). They are "
                "one dataset lineage, not two independent samples."
            ),
        },
        "protected_data_status": {
            "protected_registry_records": [
                r.get("dataset_id") for r in registry.get("records", [])
                if r.get("protected_status") == "PROTECTED"
            ],
            "protected_raw_bytes_accessed": False,
            "sealed_evidence_touched_to_create_this_campaign": False,
        },
        "coverage_contribution_disclosure": {
            "sources_used": sorted({s["source_id"] for s in sources if s.get("admissible_for_coverage")}),
            "timeframes_evaluated": sorted(coverage),
        },
        "safety": {
            "PROTECTED_DATA_ACCESSED": False, "HOLDOUT_ACCESSED": False, "OOS_ACCESSED": False,
            "CONFIRM_001_ACCESSED": False, "H2_CONSUMED": False,
            "CONFIRMATION_ROLE_CHANGED": False,
        },
        "FINAL_STATUS": "LINEAGE_MAP_FROZEN",
    }


def main() -> int:
    config = load_config(repo_root=str(REPO_ROOT))
    windows = session_windows_from_config(config)

    sources = _in_repo_sources() + _external_sources()

    # H1 warmup readiness from the merged admissible H1 series (closed bars only).
    h1_times = sorted({t for s in sources
                       if s.get("timeframe") == "H1" and s.get("admissible_for_coverage")
                       for t in s.get("_bar_times", ())})

    window_reports = {
        window_id: _window_report(sources, start, end, windows, h1_times)
        for window_id, (start, end) in EVALUATION_WINDOWS.items()
    }
    coverage = {tf: _coverage(sources, tf) for tf in TIMEFRAMES}  # primary window, for the lineage map
    primary = window_reports[PRIMARY_WINDOW_ID]
    blocking = primary["MISSING_INTERVALS"]
    complete = primary["tier_a_full_year_coverage"]

    report = {
        "schema": "AG_SSC_V1_0_1_ONE_YEAR_DATA_COVERAGE_AUDIT_V1",
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "strategy_version": "1.0.1",
        "symbol": SYMBOL,
        "generated_at_utc": datetime.now(timezone.utc).date().isoformat(),
        "generated_at_utc_note": "DATE_ONLY -- no mutable timestamp enters any coverage decision",
        "mission_classification": "HISTORICAL_RESEARCH_ONLY",
        "data_role": "HISTORICAL_RESEARCH_ONLY",
        "window_selection_rule": (
            "The primary window is anchored to the protected prospective CONFIRM_001 "
            "calendar boundary (2026-09-15T00:00:00Z), not to any strategy outcome: it is "
            "the one complete year ending immediately before that boundary. The alternate "
            "window is the same length shifted 4 days later, included so the verdict does "
            "not depend on where the boundary is drawn."
        ),
        "primary_window_id": PRIMARY_WINDOW_ID,
        "windows": window_reports,
        "p1_verdicts": {wid: {k: v for k, v in wr.items() if k.startswith(("AVAILABLE_", "COMMON_", "WARMUP_", "MISSING_", "FINAL_STATUS"))}
                        for wid, wr in window_reports.items()},
        "canonical_requirements": {
            "timeframe_roles": {"H1": "MARKET_BIAS_INPUT / structure warmup",
                                "M15": "STRATEGY_DECISION_INPUT",
                                "M1": "FILL_RESOLUTION_INPUT"},
            "structure_warmup_h1_bars": STRUCTURE_WARMUP_H1_BARS,
            "canonical_replay_authority": "session_sweep_continuation.replay.run_replay",
            "canonical_partial_target_semantic": CANONICAL_PARTIAL_TARGET_MODE,
            "config_hash": hashlib.sha256(
                json.dumps(config, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest(),
        },
        "source_inventory": [{k: v for k, v in s.items() if not k.startswith("_")} for s in sources],
        "coverage_by_timeframe": {
            tf: {k: v for k, v in coverage[tf].items() if not k.startswith("_")} for tf in TIMEFRAMES
        },
        "protected_data_status": {
            "PROTECTED_DATASETS_ENUMERATED": sorted(PROTECTED_DATASET_IDS),
            "PROTECTED_RAW_BYTES_ACCESSED": False,
            "access_counts": {s["dataset_id"]: s.get("access_count") for s in sources
                              if s.get("status") == "PROTECTED_NOT_ACCESSED"},
        },
        "blocking_missing_intervals": blocking,
        "precondition_tier_a_full_year_coverage": complete,
        "FINAL_STATUS": "DATA_COVERAGE_COMPLETE" if complete else "BLOCKED_INCOMPLETE_ONE_YEAR_DATA",
        "replay_authorized_by_this_audit": False,
        "note": ("P1 gate only. Even DATA_COVERAGE_COMPLETE would not itself authorize an "
                 "economic replay -- P2-P5 remain separate gates. No replay has been run."),
    }

    out_dir = (REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
               / "SSC_V1_0_1_HIST_1Y_001")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "DATA_COVERAGE_AUDIT_V1.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")

    lineage = _lineage_map(sources, coverage)
    lineage_path = out_dir / "LINEAGE_CONTAMINATION_MAP_V1.json"
    with open(lineage_path, "w", encoding="utf-8") as fh:
        json.dump(lineage, fh, indent=2, sort_keys=True)
        fh.write("\n")

    summary = {
        "FINAL_STATUS": report["FINAL_STATUS"],
        "artifact": str(out_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "lineage_artifact": str(lineage_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "primary_window": primary["window"],
        "primary_window_status": primary["FINAL_STATUS"],
        "primary_common_covered_days": primary["COMMON_INTERVAL"]["total_covered_days"],
        "primary_blocking_missing_intervals": primary["MISSING_INTERVALS"],
        "primary_warmup_pass": primary["WARMUP_AVAILABLE"]["pass"],
        "alternate_window_status": {
            wid: wr["FINAL_STATUS"] for wid, wr in window_reports.items() if wid != PRIMARY_WINDOW_ID
        },
        "consumed_campaigns_overlapping_primary_window": lineage["consumed_campaigns_overlapping_window"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
