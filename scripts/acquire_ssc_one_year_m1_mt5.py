"""SSC ONE-YEAR HISTORICAL M1 ACQUISITION -- owner-authorized Vantage/MT5 route.

Acquires the EURUSD M1 `FILL_RESOLUTION_INPUT` leg for the SSC v1.0.1 one-year
`HISTORICAL_RESEARCH_ONLY` window from the SAME broker/account/terminal every
owner-authorized SSC dataset came from (Vantage Markets (Pty) Ltd /
VantageMarkets-Demo / account 26088035), via the same acquisition mechanism the
repository's DEV_001/DEV_002 exports used (`MetaTrader5.copy_rates_range`).

READ-ONLY with respect to trading and research authority:
  * never calls session_sweep_continuation.replay.run_replay;
  * never places/checks an order, never mutates broker or account state;
  * never touches CONFIRM_001 / HOLDOUT / OOS / the SSC1D OOS pilot;
  * never changes a strategy YAML or parameter, and never substitutes M5/M15 for M1,
    interpolates, or synthesizes a bar.

Why this route is admissible (recorded 2026-09-19):
  The blocker was diagnosed as a TERMINAL setting, not broker retention:
  `config/common.ini` had `MaxBars=100000`, which caps the terminal's accessible M1
  base at the last ~100k bars. Before the change, every pre-2026-06-15 M1 request
  returned a degenerate single bar -- the oldest bar in that capped base
  (2026-06-15T09:57Z). The same terminal already held deep EURUSD M1 `.hcc` archives
  for 2010..2026 and served M5/M15/H1 back through the gap. After the owner raised the
  setting (terminal_info.maxbars 100000 -> 100000000) and restarted the terminal, real
  M1 history returns for every gap date.

Timezone authority: `copy_rates_range` returns true UTC epoch seconds (the same
convention `historical_replay.utc_export_csv_loader` documents for the owner-approved
DEV_001/DEV_002 exports). Naive datetimes are interpreted by the MT5 python bridge as
LOCAL time, so every request here passes timezone-aware UTC bounds.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.mt5_export_loader import _offset_segments, load_mt5_export_csv  # noqa: E402
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001

DATASET_ID = "SSC_V1_0_1_HIST_1Y_M1_001"
DATASET_DIR = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / DATASET_ID
# Raw acquisition (broker wall clock, MT5 Export format) and the UTC-normalized dataset
# CSV the repository's canonical UTC loader consumes.
RAW_BROKER_EXPORT = DATASET_DIR / "raw" / f"{SYMBOL}_M1_broker_export.csv"
RAW_CSV = DATASET_DIR / "raw" / f"{SYMBOL}_M1.csv"
PROVENANCE_PATH = DATASET_DIR / "acquisition_provenance.json"
MANIFEST_PATH = DATASET_DIR / "dataset_manifest.json"

# Mission target (the blocker) and the full one-year window the coverage gate needs.
TARGET_GAP = (datetime(2025, 9, 15, 0, 0, 0, tzinfo=timezone.utc),
              datetime(2026, 5, 18, 6, 46, 0, tzinfo=timezone.utc))
ONE_YEAR_WINDOW = (datetime(2025, 9, 15, 0, 0, 0, tzinfo=timezone.utc),
                   datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc))
# The bridge compares true-UTC request bounds against broker-wall-clock bar stamps, so a
# request made exactly on the window edges would come back shifted by the broker offset.
# One day of margin on each side removes that coupling entirely; nothing is fabricated by
# doing so -- the extra bars are real broker bars and are simply carried in the file.
ACQUIRE_MARGIN = timedelta(days=1)

# Already-consumed canonical UTC M1 used ONLY for source/derivation parity validation.
PARITY_CANONICAL = (REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_002"
                    / "raw" / "EURUSD_M1.csv")

EXPECTED_TERMINAL = {
    "server": "VantageMarkets-Demo",
    "login": 26088035,
    "symbol": SYMBOL,
}


def development_data_source_identity(info: dict, *, history_available: bool) -> bool:
    """Validate the research data source, not terminal vendor branding.

    ``terminal_info().company`` identifies the terminal vendor (MetaQuotes here),
    while broker/account identity is supplied by ``account_info``.  Execution
    authorization has separate guards and is intentionally not consulted here.
    """
    return bool(
        info.get("mt5_initialized")
        and info.get("server_matches_expected")
        and info.get("login_matches_expected")
        and info.get("environment") == "DEMO"
        and info.get("symbol_available")
        and info.get("symbol_visible")
        and history_available
    )

TICK_FIELDS = ["timestamp_utc", "open", "high", "low", "close",
               "tick_volume", "spread", "real_volume"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc(epoch: int) -> datetime:
    return datetime.fromtimestamp(int(epoch), timezone.utc)


# ---------------------------------------------------------------------------------
# stage 1 -- terminal identity
# ---------------------------------------------------------------------------------
def _bridge() -> Any:
    """The MetaTrader5 package ships as a compiled extension with no type stubs, so it is
    imported lazily and treated as opaque (typed Any) -- exactly as the sibling mission
    script does. Fails closed if the bridge is unavailable rather than degrading silently."""
    try:
        import MetaTrader5 as bridge
    except ImportError:
        raise SystemExit("MT5_PACKAGE_UNAVAILABLE")
    return bridge


def _bridge_version() -> str:
    try:
        import MetaTrader5 as bridge
        return str(getattr(bridge, "__version__", "UNKNOWN"))
    except ImportError:
        return "UNAVAILABLE"


def verify_terminal() -> dict:
    mt5 = _bridge()
    if not mt5.initialize():
        return {"status": "MT5_INITIALIZE_FAILED", "last_error": mt5.last_error()}
    ti, ai, si = mt5.terminal_info(), mt5.account_info(), mt5.symbol_info(SYMBOL)
    symbol_selected = mt5.symbol_select(SYMBOL, True)
    history = mt5.copy_rates_from(SYMBOL, mt5.TIMEFRAME_M1, datetime.now(timezone.utc), 1)
    info = {
        "status": "VERIFIED",
        "mt5_initialized": True,
        "terminal_build": getattr(ti, "build", None),
        "terminal_maxbars": getattr(ti, "maxbars", None),
        "terminal_path": getattr(ti, "path", None),
        "terminal_data_path": getattr(ti, "data_path", None),
        "terminal_company": getattr(ti, "company", None),
        "server": getattr(ai, "server", None),
        "login": getattr(ai, "login", None),
        "environment": "DEMO" if getattr(ai, "trade_mode", None) == 0 else "NON_DEMO",
        "symbol": SYMBOL,
        "symbol_available": si is not None,
        "symbol_selected": bool(symbol_selected),
        "history_available": history is not None and len(history) > 0,
        "symbol_digits": getattr(si, "digits", None),
        "symbol_point": getattr(si, "point", None),
        "symbol_tick_size": getattr(si, "trade_tick_size", None),
        "symbol_visible": getattr(si, "visible", None),
    }
    for key, expected in EXPECTED_TERMINAL.items():
        info[f"{key}_matches_expected"] = (info.get(key) == expected)
    info["identity_ok"] = development_data_source_identity(
        info, history_available=info["history_available"]
    )
    return info


# ---------------------------------------------------------------------------------
# stage 2 -- acquisition
# ---------------------------------------------------------------------------------
def acquire(start: datetime, end: datetime) -> dict:
    """Chunked read-only acquisition. Returns bars as (epoch, o, h, l, c, tick_volume,
    spread, real_volume). Chunking is by calendar month so no single call can be
    silently truncated."""
    mt5 = _bridge()
    if not mt5.initialize():
        raise SystemExit(f"MT5_INITIALIZE_FAILED {mt5.last_error()}")
    mt5.symbol_select(SYMBOL, True)

    bars: dict[int, tuple] = {}
    calls = []
    cursor = start
    while cursor < end:
        nxt = min((cursor.replace(day=1) + timedelta(days=32)).replace(day=1), end)
        rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M1, cursor, nxt)
        n = 0 if rates is None else len(rates)
        calls.append({"from_utc": _iso(cursor), "to_utc": _iso(nxt), "bars": n,
                      "error": None if rates is None else str(mt5.last_error())})
        if rates is not None:
            for r in rates:
                bars[int(r["time"])] = (int(r["time"]), float(r["open"]), float(r["high"]),
                                        float(r["low"]), float(r["close"]),
                                        int(r["tick_volume"]), int(r["spread"]), int(r["real_volume"]))
        cursor = nxt
    mt5.shutdown()
    return {"bars": bars, "calls": calls}


def write_broker_export(bars: dict[int, tuple], path: Path) -> dict:
    """Write the RAW acquisition in MT5 Export format, stamped in BROKER WALL CLOCK.

    This is required, not cosmetic: the MT5 python bridge returns epoch seconds that
    read correctly as the broker's own wall clock (see src/mt5/broker_time.py's module
    docstring), so `datetime.fromtimestamp(t, UTC)` on the raw values is broker time,
    NOT true UTC. Writing the raw file in the broker's own wall clock lets the
    repository's canonical loader resolve the offset from the data itself."""
    path.parent.mkdir(parents=True, exist_ok=True)
    times = sorted(bars)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<SPREAD>\n")
        for t in times:
            _, o, h, l, c, tv, sp, _rv = bars[t]
            stamp = datetime.fromtimestamp(t, timezone.utc)  # broker wall clock, deliberately
            fh.write(f"{stamp.strftime('%Y.%m.%d')}\t{stamp.strftime('%H:%M:%S')}\t"
                     f"{o:.5f}\t{h:.5f}\t{l:.5f}\t{c:.5f}\t{tv}\t{sp}\n")
    return {"row_count": len(times),
            "first_broker_wallclock": stamp_first(times), "last_broker_wallclock": stamp_last(times)}


def stamp_first(times):
    return datetime.fromtimestamp(times[0], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if times else None


def stamp_last(times):
    return datetime.fromtimestamp(times[-1], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if times else None


def write_utc_csv(candles, path: Path) -> dict:
    """Write the UTC-normalized dataset CSV in this repository's frozen in-repo dataset
    convention (`timestamp_utc,open,high,low,close,tick_volume,spread,real_volume`),
    identical in shape to the owner-approved DEV_001/DEV_002/GEN_002 M1 files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(TICK_FIELDS) + "\n")
        for c in candles:
            tv = int(c.volume) if c.volume is not None else 0
            fh.write(f"{c.time.strftime('%Y-%m-%d %H:%M:%S')},{c.open:.5f},{c.high:.5f},"
                     f"{c.low:.5f},{c.close:.5f},{tv},0,0\n")
    return {"row_count": len(candles),
            "first_timestamp_utc": _iso(candles[0].time), "last_timestamp_utc": _iso(candles[-1].time)}


# ---------------------------------------------------------------------------------
# stage 3 -- validation (P/A3 + A5)
# ---------------------------------------------------------------------------------
def _expected_fx_minutes(start: datetime, end: datetime) -> int:
    """Expected minute bars for a canonical FX week: open Sunday 21:00 UTC, close
    Friday 21:00 UTC (50 hours per week = 3000 minutes), daily 1-hour rollover break
    at 21:00-22:00 UTC Mon-Thu. Used as an adequacy measure, never to fill anything."""
    total = 0
    day = start
    while day < end:
        if day.weekday() <= 3 and day.hour == 21:  # daily maintenance hour
            day += timedelta(hours=1)
            continue
        if day.weekday() >= 5:  # Sat + Sun before 21:00
            day += timedelta(hours=1)
            continue
        if day.weekday() == 6 and day.hour < 21:  # Sunday before reopen
            day += timedelta(hours=1)
            continue
        total += 1
        day += timedelta(minutes=1)
    return total


def validate(start: datetime, end: datetime) -> dict:
    candles, report = load_utc_export_csv(str(RAW_CSV), SYMBOL, "M1")
    times = [c.time for c in candles]
    duplicates = sum(1 for a, b in zip(times, times[1:]) if b == a)
    non_monotonic = sum(1 for a, b in zip(times, times[1:]) if b < a)
    invalid_ohlc = sum(1 for c in candles
                       if not (c.high >= max(c.open, c.close) and c.low <= min(c.open, c.close)
                               and c.high >= c.low and min(c.open, c.high, c.low, c.close) > 0))

    largest = max((g.duration for g in report.gaps), default=timedelta(0))

    in_window = [c for c in candles if start <= c.time < end]

    # Exact per-minute missing count inside the window, evaluated against the canonical
    # FX minute calendar (never used to fill anything -- reporting only).
    have = set(times)
    cursor = start
    missing_minutes = 0
    while cursor < end:
        if cursor.weekday() <= 3 and cursor.hour == 21:
            cursor += timedelta(hours=1)
            continue
        if cursor.weekday() >= 5 or (cursor.weekday() == 6 and cursor.hour < 21):
            cursor += timedelta(minutes=1)
            continue
        if cursor not in have:
            missing_minutes += 1
        cursor += timedelta(minutes=1)

    # Gap structure from the RAW broker-time series (the import classification labels any
    # sub-40h break "UNEXPECTED_DATA_GAP", which would mislabel this broker's ordinary
    # intraday rollover/maintenance breaks as data defects).
    raw_times = list(report.broker_times)
    hist: collections.Counter = collections.Counter()
    for a, b in zip(raw_times, raw_times[1:]):
        hist[b - a] += 1
    native = timedelta(minutes=1)
    weekend_gaps = sum(n for d, n in hist.items() if d >= timedelta(hours=40))
    intraday_breaks = sum(n for d, n in hist.items()
                          if timedelta(0) < d < timedelta(hours=40) and d != native)

    monthly = {}
    for c in candles:
        key = c.time.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + 1

    return {
        "row_count": len(candles),
        "first_timestamp_utc": _iso(times[0]),
        "last_timestamp_utc": _iso(times[-1]),
        "duplicate_timestamps": duplicates,
        "non_monotonic_timestamps": non_monotonic,
        "invalid_ohlc_bars": invalid_ohlc,
        "gap_structure": {
            "native_one_minute_steps": hist[native],
            "weekend_closure_gaps": weekend_gaps,
            "intraday_break_gaps": intraday_breaks,
            "largest_gap_hours": round(largest.total_seconds() / 3600, 3),
            "top_non_native_durations": [
                {"duration": str(d), "count": n}
                for d, n in sorted(hist.items(), key=lambda kv: (-kv[1], str(kv[0])))
                if d != native
            ][:8],
            "note": ("Intraday break gaps are this broker's own rollover/maintenance behaviour "
                     "(observed as 2-7 minute steps and occasional ~1 hour breaks), not missing "
                     "trading data. No gap is ever filled, interpolated or synthesized."),
        },
        "minutes_absent_under_simple_utc_fx_calendar_model": missing_minutes,
        "expected_minutes_under_simple_utc_fx_calendar_model": _expected_fx_minutes(start, end),
        "calendar_model_caveat": (
            "The simple Sun 21:00 UTC -> Fri 21:00 UTC, Mon-Thu 21:00-22:00 UTC break model is an "
            "approximation of the FX calendar, not this broker's calendar (holidays, irregular "
            "rollover steps). It both over- and under-predicts and is therefore NOT the coverage "
            "gate. The authoritative verdict is the canonical audit in "
            "scripts/audit_ssc_v1_0_1_one_year_data_coverage.py."),
        "actual_minutes_in_window": len(in_window),
        "monthly_coverage": monthly,
        "schema": "UTC timestamp_utc, broker wall clock normalized per weekly reopen (src/mt5/broker_time.offset_from_reopen)",
        "quality_status": "PASS" if (duplicates == 0 and non_monotonic == 0 and invalid_ohlc == 0) else "FAIL",
    }


def parity(acquired_csv: Path, canonical_csv: Path) -> dict:
    """A3: compare against canonical owner-approved Vantage M1 on an ALREADY-CONSUMED
    overlap interval. Source validation only -- no strategy evidence."""
    got, _ = load_utc_export_csv(str(acquired_csv), SYMBOL, "M1")
    ref, _ = load_utc_export_csv(str(canonical_csv), SYMBOL, "M1")
    g = {c.time: c for c in got}
    r = {c.time: c for c in ref}
    overlap = sorted(set(g) & set(r))
    if not overlap:
        return {"PARITY_STATUS": "FAIL_NO_OVERLAP", "canonical_rows": len(ref)}
    exact = sum(1 for t in overlap
                if all(abs(a - b) < 1e-9 for a, b in (
                    (g[t].open, r[t].open), (g[t].high, r[t].high),
                    (g[t].low, r[t].low), (g[t].close, r[t].close))))
    return {
        "canonical_source": str(canonical_csv.relative_to(REPO_ROOT)).replace("\\", "/"),
        "canonical_rows": len(ref),
        "overlap_minutes": len(overlap),
        "overlap_first": _iso(overlap[0]),
        "overlap_last": _iso(overlap[-1]),
        "canonical_minutes_not_in_acquired": len(set(r) - set(g)),
        "exact_all_four_rate": round(exact / len(overlap), 6),
        "PARITY_STATUS": "PASS_EXACT" if exact / len(overlap) >= 0.999 else "FAIL",
    }


def _revalidate_only() -> int:
    """Recompute validation + parity from the already-acquired raw/dataset files and
    rewrite the manifest. Read-only with respect to the broker: no MT5 call at all."""
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    _, report = load_mt5_export_csv(str(RAW_BROKER_EXPORT), SYMBOL, "M1")
    candles, _ = load_utc_export_csv(str(RAW_CSV), SYMBOL, "M1")
    written = {"row_count": len(candles), "first_timestamp_utc": _iso(candles[0].time),
               "last_timestamp_utc": _iso(candles[-1].time)}
    segments = _offset_segments(list(report.broker_times))
    distinct_offsets = sorted({off for _, off in segments})
    validation = validate(*TARGET_GAP)
    parity_result = parity(RAW_CSV, PARITY_CANONICAL)
    _write_manifest(provenance, report, segments, distinct_offsets, written,
                    validation, parity_result)
    print(json.dumps({
        "MODE": "REVALIDATE_ONLY",
        "ROW_COUNT": written["row_count"],
        "RAW_SOURCE_SHA256": _sha256_file(RAW_BROKER_EXPORT),
        "M1_SHA256": _sha256_file(RAW_CSV),
        "TIMEZONE_AUTHORITY": report.source_timezone,
        "TIMEZONE_OFFSETS_DETECTED": distinct_offsets,
        "QUALITY_STATUS": validation["quality_status"],
        "GAP_STRUCTURE": validation["gap_structure"],
        "PARITY_STATUS": parity_result["PARITY_STATUS"],
        "PARITY_EXACT_RATE": parity_result["exact_all_four_rate"],
        "artifact": str(MANIFEST_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
    }, indent=2))
    return 0


def _write_manifest(provenance, report, segments, distinct_offsets, written,
                    validation, parity_result) -> None:
    manifest = {
        "schema": "AG_SSC_HISTORICAL_INPUT_MANIFEST_V1",
        "dataset_id": DATASET_ID,
        "package_id": DATASET_ID,
        "symbol": SYMBOL,
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "strategy_version": "1.0.1",
        "data_role": "HISTORICAL_RESEARCH_INPUT_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).date().isoformat(),
        "frozen_start": _iso(ONE_YEAR_WINDOW[0]),
        "frozen_end": _iso(ONE_YEAR_WINDOW[1]),
        "target_gap": {"start": _iso(TARGET_GAP[0]), "end": _iso(TARGET_GAP[1])},
        "per_file": {f"{SYMBOL}_M1": {
            "path": str(RAW_CSV.relative_to(REPO_ROOT)).replace("\\", "/"),
            "rows": written["row_count"],
            "sha256": _sha256_file(RAW_CSV),
            "first_timestamp": written["first_timestamp_utc"],
            "last_timestamp": written["last_timestamp_utc"],
        }},
        "raw_source": {
            "path": str(RAW_BROKER_EXPORT.relative_to(REPO_ROOT)).replace("\\", "/"),
            "rows": provenance.get("raw_source_rows"),
            "sha256": _sha256_file(RAW_BROKER_EXPORT),
            "interval_broker_wallclock": provenance.get("raw_source_interval_broker_wallclock"),
        },
        "timezone_authority": report.source_timezone,
        "timezone_offsets_detected_hours": distinct_offsets,
        "offset_changes_inside_period": len(distinct_offsets) > 1,
        "broker_offset_segment_count": len(segments),
        "acquisition_provenance": str(PROVENANCE_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "validation": validation,
        "parity_vs_canonical_dev002_m1": parity_result,
        "coverage_gate": ("scripts/audit_ssc_v1_0_1_one_year_data_coverage.py"
                          " -- must report DATA_COVERAGE_COMPLETE before any replay"),
        "warmup_role": {"may_initialize_h1_bias": False, "may_generate_decision_occurrence": False,
                        "may_contribute_economic_sample_N": False},
        "authorization": "Owner-authorized 2026-09-19 acquisition mission (Vantage/MT5 route 1); "
                         "owner raised the MT5 MaxBars setting to enable deep M1 history.",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--revalidate-only", action="store_true",
                    help="Recompute validation/parity and rewrite the manifest from the "
                         "already-acquired files. No broker call, no re-download -- used to "
                         "regenerate evidence deterministically.")
    args = ap.parse_args()

    if args.revalidate_only:
        return _revalidate_only()

    terminal = verify_terminal()
    print(json.dumps(terminal, indent=2))
    if terminal.get("status") != "VERIFIED" or not terminal.get("identity_ok"):
        print(json.dumps({"FINAL_STATUS": "BLOCKED_SOURCE_PROVENANCE",
                          "reason": "terminal/broker/account identity mismatch"}, indent=2))
        return 1
    if args.verify_only:
        return 0

    start, end = ONE_YEAR_WINDOW
    acq = acquire(start - ACQUIRE_MARGIN, end + ACQUIRE_MARGIN)
    raw_written = write_broker_export(acq["bars"], RAW_BROKER_EXPORT)

    # Canonical UTC normalization: the repository's own MT5-export loader resolves the
    # broker offset PER WEEKLY REOPEN from the data (src/mt5/broker_time.py), so any
    # seasonal DST change inside the year is detected rather than assumed.
    candles, report = load_mt5_export_csv(str(RAW_BROKER_EXPORT), SYMBOL, "M1")
    written = write_utc_csv(candles, RAW_CSV)

    segments = _offset_segments(list(report.broker_times))
    distinct_offsets = sorted({off for _, off in segments})

    provenance = {
        "schema": "AG_SSC_M1_ACQUISITION_PROVENANCE_V1",
        "dataset_id": DATASET_ID,
        "provider": "Vantage Markets (Pty) Ltd",
        "broker_server": terminal["server"],
        "account_login": terminal["login"],
        "environment": terminal["environment"],
        "symbol": SYMBOL,
        "symbol_metadata": {"digits": terminal["symbol_digits"], "point": terminal["symbol_point"],
                            "tick_size": terminal["symbol_tick_size"]},
        "data_type": "M1 OHLCV bars (MetaTrader5 TIMEFRAME_M1)",
        "acquisition_method": "MetaTrader5.copy_rates_range (python bridge), chunked by calendar month",
        "acquisition_timestamp_utc": _iso(datetime.now(timezone.utc)),
        "bridge_version": _bridge_version(),
        "terminal_build": terminal["terminal_build"],
        "terminal_maxbars_setting": terminal["terminal_maxbars"],
        "requested_interval_utc": {"from": _iso(start), "to": _iso(end)},
        "target_gap_utc": {"from": _iso(TARGET_GAP[0]), "to": _iso(TARGET_GAP[1])},
        "actual_interval_utc": {"from": written["first_timestamp_utc"],
                                "to": written["last_timestamp_utc"]},
        "loader_timezone_authority": report.source_timezone,
        "timezone": "BROKER_SERVER_TIME resolved to UTC per weekly reopen (src/mt5/broker_time.offset_from_reopen); "
                    "raw epochs read as broker wall clock, per that module's documented MT5 quirk",
        "timezone_offsets_detected_hours": distinct_offsets,
        "broker_offset_segments": [{"segment_start_broker": s.isoformat(), "offset_hours": o}
                                   for s, o in segments],
        "offset_changes_inside_period": len(distinct_offsets) > 1,
        "price_convention": "broker BID-based M1 OHLC (MT5 native bar convention)",
        "file_format": "raw: MT5 Export tab-delimited broker wall clock; dataset: CSV header "
                       + ",".join(TICK_FIELDS),
        "raw_source_file": str(RAW_BROKER_EXPORT.relative_to(REPO_ROOT)).replace("\\", "/"),
        "raw_source_sha256": _sha256_file(RAW_BROKER_EXPORT),
        "raw_source_rows": raw_written["row_count"],
        "raw_source_interval_broker_wallclock": {"from": raw_written["first_broker_wallclock"],
                                                 "to": raw_written["last_broker_wallclock"]},
        "row_count": written["row_count"],
        "sha256": _sha256_file(RAW_CSV),
        "api_calls": acq["calls"],
        "data_role": "HISTORICAL_RESEARCH_INPUT_ONLY",
        "notes": [
            "Not independent validation evidence: this interval is historical research input only.",
            "The one-year SSC replay is a separate one-shot mission and was NOT run here.",
        ],
    }
    PROVENANCE_PATH.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validation = validate(*TARGET_GAP)
    parity_result = parity(RAW_CSV, PARITY_CANONICAL)
    _write_manifest(provenance, report, segments, distinct_offsets, written,
                    validation, parity_result)

    summary = {
        "TARGET_GAP": {"from": _iso(TARGET_GAP[0]), "to": _iso(TARGET_GAP[1])},
        "ACTUAL_COVERAGE": {"from": written["first_timestamp_utc"], "to": written["last_timestamp_utc"]},
        "ROW_COUNT": written["row_count"],
        "RAW_SOURCE_SHA256": provenance["raw_source_sha256"],
        "M1_SHA256": provenance["sha256"],
        "TIMEZONE_AUTHORITY": report.source_timezone,
        "TIMEZONE_OFFSETS_DETECTED": distinct_offsets,
        "QUALITY_STATUS": validation["quality_status"],
        "GAP_STRUCTURE": validation["gap_structure"],
        "minutes_absent_under_simple_utc_fx_calendar_model":
            validation["minutes_absent_under_simple_utc_fx_calendar_model"],
        "PARITY_STATUS": parity_result["PARITY_STATUS"],
        "PARITY_EXACT_RATE": parity_result["exact_all_four_rate"],
        "PARITY_CANONICAL_MINUTES_MISSING": parity_result["canonical_minutes_not_in_acquired"],
        "artifact": str(MANIFEST_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "next_step": ("Run the canonical coverage audit "
                      "(scripts/audit_ssc_v1_0_1_one_year_data_coverage.py) and require "
                      "DATA_COVERAGE_COMPLETE before any replay. This script never replays."),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
