"""SSC 1Y M1 GAP SOURCE ADMISSION -- source search, adjudication and parity probe.

Mission: resolve the ONLY remaining blocker for the SSC v1.0.1 one-year
HISTORICAL_RESEARCH_ONLY backtest -- missing EURUSD M1 fill-resolution coverage over
2025-09-15T00:00:00Z -> 2026-05-18T06:46:00Z.

Read-only with respect to strategy and protected evidence. It does NOT call
session_sweep_continuation.replay.run_replay (`--derive` writes bars, but never runs a
replay), never places or checks an order, never touches demo/live authorization, and
never reads HOLDOUT/OOS/CONFIRM_001 or the SSC1D OOS pilot.

Stages (all optional, all record into one artifact):

  --probe-mt5       P1: ask the already-connected MT5 terminal (same broker/account as
                    every owner-authorized SSC dataset) how far back each timeframe's
                    history actually reaches inside the gap. This is a live probe of
                    broker history depth, not a download of a new provider.
  --tick            P2: adjudicate the local raw bid/ask tick export (provenance,
                    timestamp convention, ordering, duplicates, gaps, weekend behaviour,
                    invalid prices) and classify it.
  --parity          P4: derive candidate M1 bars from the tick export using each price
                    stream (bid / ask / mid) over an ALREADY-CONSUMED overlap interval
                    and measure the match against canonical MT5 M1. Source/derivation
                    validation only -- creates no strategy evidence.

Why the live MT5 probe matters: every owner-authorized SSC EURUSD dataset in this
repository came from THIS account/server via `MetaTrader5.copy_rates_range`
(account 26088035, VantageMarkets-Demo). Whether a one-year M1 leg is obtainable is
therefore a question about this broker's served history, not about a new provider.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from session_sweep_continuation.config import load_config  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
TICK_EXPORT = Path("D:/EURUSD_202606182200_202608241902.csv")
CANONICAL_M1 = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_002" / "raw" / "EURUSD_M1.csv"
ARTIFACT_DIR = (REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
                / "SSC_V1_0_1_HIST_1Y_001")

GAP_START = datetime(2025, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
GAP_END = datetime(2026, 5, 18, 6, 46, 0, tzinfo=timezone.utc)

# Probe dates spanning the gap (each: local broker calendar day, 1 day wide).
PROBE_DATES = [
    "2025-09-16", "2025-10-15", "2025-11-17", "2025-12-15",
    "2026-01-15", "2026-02-16", "2026-03-16", "2026-04-15", "2026-05-04",
]
# First-of-month probes used to bound where M1 availability actually begins. M15/H1 are
# probed on the same dates so a "no M1" result can be distinguished from "the request
# itself is broken".
BOUNDARY_PROBE_DATES = ["2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01",
                        "2026-07-01", "2026-08-01", "2026-09-01"]
BOUNDARY_PROBE_TIMEFRAMES = ("M1", "M15")
# Control dates that MUST return data (documented-good canonical M1 coverage).
CONTROL_DATES = ["2026-06-01", "2026-07-01"]
TIMEFRAMES = [("M1", 1), ("M5", 5), ("M15", 15), ("H1", 60), ("D1", 1440)]


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


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------
# P1 -- broker-served history depth probe (same broker/account as owner-authorized data)
# ---------------------------------------------------------------------------------
def probe_mt5(paths_only: bool = False) -> dict:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"status": "MT5_PACKAGE_UNAVAILABLE"}

    if not mt5.initialize():
        return {"status": "MT5_INITIALIZE_FAILED", "last_error": mt5.last_error()}

    tf_map = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
              "H1": mt5.TIMEFRAME_H1, "D1": mt5.TIMEFRAME_D1}
    term = mt5.terminal_info()
    acct = mt5.account_info()
    result = {
        "status": "PROBED",
        "bridge": "MetaTrader5 python package via already-running terminal (read-only rates calls)",
        "terminal_build": getattr(term, "build", None),
        "terminal_max_bars_setting": getattr(term, "maxbars", None),
        "terminal_data_path": getattr(term, "data_path", None),
        "broker_company": getattr(acct, "company", None),
        "broker_server": getattr(acct, "server", None),
        "account_login": getattr(acct, "login", None),
        "symbol": SYMBOL,
        "queries": [],
    }

    def query(label: str, day: str, tf_name: str):
        start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        # copy_rates_range takes naive datetimes and returns broker-wall-clock stamps
        # as epoch seconds, the same convention the repository's owner-authorized
        # acquisitions used.
        rates = mt5.copy_rates_range(SYMBOL, tf_map[tf_name], start.replace(tzinfo=None),
                                     end.replace(tzinfo=None))
        row = {"label": label, "date": day, "timeframe": tf_name, "bars": None}
        if rates is None:
            row["error"] = str(mt5.last_error())
        else:
            row["bars"] = len(rates)
            if len(rates) == 0:
                row["error"] = "EMPTY"
            else:
                row["first_broker_stamp"] = datetime.fromtimestamp(
                    int(rates["time"][0]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                row["last_broker_stamp"] = datetime.fromtimestamp(
                    int(rates["time"][-1]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                row["first_close"] = float(rates["close"][0])
        return row

    if not paths_only:
        for day in PROBE_DATES:
            result["queries"].append(query("GAP", day, "M1"))
        for day in CONTROL_DATES:
            for tf_name, _ in TIMEFRAMES:
                result["queries"].append(query("CONTROL", day, tf_name))
        # timeframe depth comparison on two gap dates
        for day in ("2025-12-15", "2026-04-15"):
            for tf_name, _ in TIMEFRAMES:
                result["queries"].append(query("GAP_DEPTH", day, tf_name))
        # where does M1 availability actually begin? (M1 and M15 on identical dates)
        for day in BOUNDARY_PROBE_DATES:
            for tf_name in BOUNDARY_PROBE_TIMEFRAMES:
                result["queries"].append(query("BOUNDARY", day, tf_name))

    m1_gap = [q for q in result["queries"] if q["timeframe"] == "M1" and q["label"] == "GAP"]
    if m1_gap:
        result["gap_m1_verdict"] = (
            "BROKER_M1_HISTORY_ABSENT_IN_GAP"
            if all((q.get("bars") or 0) <= 1 for q in m1_gap)
            else "BROKER_M1_HISTORY_PRESENT_IN_GAP"
        )
    # Same-date M5/M15/H1/D1 controls distinguish "broker has no history" from "M1
    # specifically is unavailable": these are all weekday dates inside the gap.
    m15_same_dates = [q for q in result["queries"]
                      if q["timeframe"] == "M15" and q["label"] == "GAP_DEPTH"]
    if m15_same_dates:
        result["m15_history_depth_verdict"] = (
            "BROKER_M15_HISTORY_PRESENT_BACK_THROUGH_GAP"
            if all((q.get("bars") or 0) > 1 for q in m15_same_dates)
            else "BROKER_M15_HISTORY_ALSO_ABSENT_OR_PARTIAL"
        )
    # A zero-bar answer on a non-trading calendar day (e.g. a Sunday first-of-month)
    # means "market closed", not "history missing" -- recorded, not judged.
    result["same_date_other_timeframe_evidence"] = [
        {"date": q["date"], "timeframe": q["timeframe"], "bars": q["bars"]}
        for q in result["queries"] if q["label"] == "GAP_DEPTH"
    ]
    boundary_m1 = [q for q in result["queries"]
                   if q["label"] == "BOUNDARY" and q["timeframe"] == "M1"]
    if boundary_m1:
        real = sorted(q["date"] for q in boundary_m1 if (q.get("bars") or 0) > 1)
        result["m1_availability_boundary"] = {
            "probe_dates": [q["date"] for q in boundary_m1],
            "dates_returning_real_m1": real,
            "earliest_probed_date_with_real_m1": real[0] if real else None,
            "dates_returning_degenerate_single_bar": [
                q["date"] for q in boundary_m1 if (q.get("bars") or 0) == 1
            ],
            "interpretation": (
                "A one-bar answer to a full-day M1 range is this bridge's degenerate "
                "'history not available' response, not real coverage."
            ),
        }
    controls = [q for q in result["queries"] if q["label"] == "CONTROL"]
    result["control_verdict"] = (
        "CONTROLS_HAVE_DATA" if all((q.get("bars") or 0) > 0 for q in controls)
        else "CONTROLS_EMPTY -- probe itself is unreliable"
    )
    mt5.shutdown()
    return result


# ---------------------------------------------------------------------------------
# P2 -- raw tick export adjudication
# ---------------------------------------------------------------------------------
def _parse_tick_stamp(date_s: str, time_s: str) -> datetime:
    """Fixed-position parse of `YYYY.MM.DD` + `HH:MM:SS[.fff]`. Deliberately not
    strptime: this runs once per tick over a multi-million-row export."""
    return datetime(
        int(date_s[0:4]), int(date_s[5:7]), int(date_s[8:10]),
        int(time_s[0:2]), int(time_s[3:5]), int(time_s[6:8]),
        int(time_s[9:12]) * 1000 if len(time_s) > 9 else 0,
    )


def _minute_of(ts: datetime) -> datetime:
    return datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute)


def adjudicate_tick(path: Path) -> dict:
    if not path.exists():
        return {"status": "TICK_EXPORT_MISSING", "path": str(path)}
    out = {
        "status": "ADJUDICATED", "path": str(path), "file_size_bytes": os.path.getsize(path),
        "sha256": _sha256_file(path),
    }
    rows = 0
    parse_failures = 0
    dup = 0
    non_monotonic = 0
    invalid = 0
    crossed = 0
    bid_only = 0
    ask_only = 0
    both_sides = 0
    row_lengths = {}
    per_minute_bid = {}
    per_minute_ask = {}
    per_minute_mid = {}
    prev = None
    first = last = None
    header = []
    flags = {}
    last_key = [None, None]
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, [])
        for row in reader:
            if not row or len(row) < 3:
                continue
            row_lengths[len(row)] = row_lengths.get(len(row), 0) + 1
            try:
                ts = _parse_tick_stamp(row[0], row[1])
            except (ValueError, IndexError):
                parse_failures += 1
                continue
            # MT5's tick export writes ONE side per record: a bid change leaves the ask
            # column blank and vice-versa. A blank side is therefore NOT an invalid
            # price -- it is the defining shape of this export format.
            bid_s = row[2].strip() if len(row) > 2 else ""
            ask_s = row[3].strip() if len(row) > 3 else ""
            bid = float(bid_s) if bid_s else None
            ask = float(ask_s) if ask_s else None
            flag = row[6].strip() if len(row) > 6 else (row[5].strip() if len(row) > 5 else "")
            rows += 1
            if rows % 1_000_000 == 0:
                print(f"[tick] parsed {rows:,} rows...", file=sys.stderr, flush=True)
            first = first or ts
            last = ts
            flags[flag] = flags.get(flag, 0) + 1
            have_bid = bid is not None and math.isfinite(bid) and bid > 0
            have_ask = ask is not None and math.isfinite(ask) and ask > 0
            if have_bid and have_ask:
                both_sides += 1
            elif have_bid:
                bid_only += 1
            elif have_ask:
                ask_only += 1
            else:
                invalid += 1
            if have_bid and have_ask and ask < bid:
                crossed += 1
            if prev is not None:
                if ts == prev:
                    dup += 1
                elif ts < prev:
                    non_monotonic += 1
            prev = ts
            if have_bid or have_ask:
                # Cache the minute object: consecutive ticks overwhelmingly share a
                # minute, so this avoids one datetime construction per row.
                key = (ts.year, ts.month, ts.day, ts.hour, ts.minute)
                if key != last_key[0]:
                    last_key[0] = key
                    # timezone-aware: canonical Candle.time is UTC-aware, so naive keys
                    # would silently never intersect with it.
                    last_key[1] = datetime(*key, tzinfo=timezone.utc)
                minute = last_key[1]
                if have_bid:
                    b = round(bid, 5)
                    agg = per_minute_bid.get(minute)
                    if agg is None:
                        per_minute_bid[minute] = [b, b, b, b]
                    else:
                        agg[1] = max(agg[1], b)
                        agg[2] = min(agg[2], b)
                        agg[3] = b
                if have_ask:
                    a = round(ask, 5)
                    agg = per_minute_ask.get(minute)
                    if agg is None:
                        per_minute_ask[minute] = [a, a, a, a]
                    else:
                        agg[1] = max(agg[1], a)
                        agg[2] = min(agg[2], a)
                        agg[3] = a
                if have_bid and have_ask:
                    mid = round((bid + ask) / 2, 5)
                    agg = per_minute_mid.get(minute)
                    if agg is None:
                        per_minute_mid[minute] = [mid, mid, mid, mid]
                    else:
                        agg[1] = max(agg[1], mid)
                        agg[2] = min(agg[2], mid)
                        agg[3] = mid
    out.update({
        "header": header,
        "row_count": rows,
        "rest_row_length_histogram": row_lengths,
        "parse_failures": parse_failures,
        "duplicate_timestamps": dup,
        "non_monotonic_timestamps": non_monotonic,
        "invalid_price_rows": invalid,
        "crossed_price_rows": crossed,
        "bid_only_rows": bid_only,
        "ask_only_rows": ask_only,
        "both_sides_present_rows": both_sides,
        "flag_value_counts": flags,
        "first_tick_broker_wallclock": first.isoformat() if first else None,
        "last_tick_broker_wallclock": last.isoformat() if last else None,
        "distinct_minutes_bid": len(per_minute_bid),
        "distinct_minutes_ask": len(per_minute_ask),
        "distinct_minutes_mid": len(per_minute_mid),
        "format_note": ("MT5 tick export writes one side per record -- a blank bid or ask "
                        "column is the format's normal shape, not a bad price."),
        "authority_note": ("Provenance is NOT established by the filename. This file is a "
                           "manual MT5 'Ticks' export with no broker/account/venue metadata "
                           "sidecar anywhere in the repository; it is admissible only if an "
                           "owner-authorized acquisition record binds it to a named "
                           "broker/account/interval."),
        "quality_status": "PASS" if (parse_failures == 0 and non_monotonic == 0 and invalid == 0) else "PARTIAL",
    })
    out["_minutes"] = {"bid": per_minute_bid, "ask": per_minute_ask, "mid": per_minute_mid}
    return out


# ---------------------------------------------------------------------------------
# P4 -- overlap parity: tick-derived M1 vs canonical MT5 M1
# ---------------------------------------------------------------------------------
def parity(tick: dict, canonical_csv: Path) -> dict:
    """Determines the tick export's UTC offset and price stream FROM the data: every
    candidate offset is scored, and the best-scoring one is reported as the observed
    convention (never assumed)."""
    candles, report = load_utc_export_csv(str(canonical_csv), SYMBOL, "M1")
    canonical = {c.time: c for c in candles}

    def score(offset_hours: float, stream: str):
        minutes = {ts - timedelta(hours=offset_hours): v for ts, v in tick["_minutes"][stream].items()}
        overlap = sorted(set(canonical) & set(minutes))
        if not overlap:
            return None
        exact = 0
        devs = []
        max_dev = 0.0
        for ts in overlap:
            c, (o, h, l, cl) = canonical[ts], minutes[ts]
            if (abs(o - c.open) < 1e-9 and abs(h - c.high) < 1e-9
                    and abs(l - c.low) < 1e-9 and abs(cl - c.close) < 1e-9):
                exact += 1
            for a, b in ((o, c.open), (h, c.high), (l, c.low), (cl, c.close)):
                devs.append(abs(a - b))
                max_dev = max(max_dev, abs(a - b))
        n = len(overlap)
        return {
            "utc_offset_hours_assumed": offset_hours, "stream": stream, "bars_compared": n,
            "exact_all_four_rate": round(exact / n, 6),
            "max_abs_deviation": round(max_dev, 8),
            "mean_abs_deviation": round(sum(devs) / len(devs), 10),
            "__minutes": minutes,
        }

    grid = [s for off in (-3, -2, 0, 2, 3) for s in (score(off, stream) for stream in ("bid", "ask", "mid"))
            if s is not None]
    grid.sort(key=lambda r: (-r["exact_all_four_rate"], r["mean_abs_deviation"]))
    best = grid[0] if grid else None

    result = {
        "canonical_source": str(canonical_csv.relative_to(REPO_ROOT)).replace("\\", "/"),
        "canonical_timezone_authority": "UTC (timestamp_utc, MetaTrader5 copy_rates_range native)",
        "canonical_first": _iso(candles[0].time),
        "canonical_last": _iso(candles[-1].time),
        "canonical_rows": len(candles),
        "canonical_expected_closure_gaps": len(report.gaps) - len(report.unexpected_gaps),
        "candidate_conventions_scored": len(grid),
        "grid": [{k: v for k, v in row.items() if not k.startswith("__")} for row in grid],
    }
    if best is None:
        result["PARITY_STATUS"] = "FAIL_NO_OVERLAP"
        return result

    minutes = best["__minutes"]
    tick_minutes = set(minutes)
    overlap = sorted(set(canonical) & tick_minutes)
    result.update({
        "observed_utc_offset_hours": best["utc_offset_hours_assumed"],
        "observed_price_stream": best["stream"],
        "overlap_minutes": len(overlap),
        "overlap_first": _iso(overlap[0]) if overlap else None,
        "overlap_last": _iso(overlap[-1]) if overlap else None,
        "canonical_minutes_not_in_tick": len(set(canonical) - tick_minutes),
        "tick_minutes_not_in_canonical": len(tick_minutes - set(canonical)),
        "exact_open_rate": round(sum(1 for ts in overlap if abs(minutes[ts][0] - canonical[ts].open) < 1e-9) / len(overlap), 6),
        "exact_high_rate": round(sum(1 for ts in overlap if abs(minutes[ts][1] - canonical[ts].high) < 1e-9) / len(overlap), 6),
        "exact_low_rate": round(sum(1 for ts in overlap if abs(minutes[ts][2] - canonical[ts].low) < 1e-9) / len(overlap), 6),
        "exact_close_rate": round(sum(1 for ts in overlap if abs(minutes[ts][3] - canonical[ts].close) < 1e-9) / len(overlap), 6),
        "exact_all_four_rate": best["exact_all_four_rate"],
        "max_abs_deviation": best["max_abs_deviation"],
        "mean_abs_deviation": best["mean_abs_deviation"],
    })
    result["PARITY_STATUS"] = (
        "PASS_EXACT" if best["exact_all_four_rate"] >= 0.999
        else "PARTIAL" if best["exact_all_four_rate"] > 0.0
        else "FAIL"
    )

    # Session-boundary differences: are the deviations concentrated at session edges?
    # Windows come from the strategy config's own UTC session clock (read-only).
    try:
        config = load_config(repo_root=str(REPO_ROOT))
        windows = session_windows_from_config(config)
    except Exception as exc:  # pragma: no cover - config failure is reported, not hidden
        result["session_boundary_check"] = {"status": "NOT_EVALUATED", "error": f"{type(exc).__name__}: {exc}"}
        return result

    def _in_window(ts, pair_id, kind):
        ref_start, ref_end = windows[pair_id][kind].bounds_for_date(ts.date())
        return ref_start <= ts < ref_end

    breakdown = {}
    for pair_id in sorted(windows):
        inside = [ts for ts in overlap if _in_window(ts, pair_id, "trade")]
        breakdown[pair_id] = _rate(minutes, canonical, inside)
    outside = [ts for ts in overlap
               if not any(_in_window(ts, p, "trade") for p in windows)]
    breakdown["OUTSIDE_ALL_TRADE_WINDOWS"] = _rate(minutes, canonical, outside)
    result["session_boundary_check"] = {
        "definition": "exact all-four OHLC match rate restricted to each session pair's trade window (UTC clock from the strategy config)",
        "by_segment": breakdown,
    }
    return result


def _rate(minutes, canonical, times) -> dict:
    if not times:
        return {"bars": 0, "exact_all_four_rate": None}
    exact = sum(
        1 for ts in times
        if abs(minutes[ts][0] - canonical[ts].open) < 1e-9
        and abs(minutes[ts][1] - canonical[ts].high) < 1e-9
        and abs(minutes[ts][2] - canonical[ts].low) < 1e-9
        and abs(minutes[ts][3] - canonical[ts].close) < 1e-9
    )
    return {"bars": len(times), "exact_all_four_rate": round(exact / len(times), 6)}


def tick_data(cache_path: Path, tick_path: Path = TICK_EXPORT) -> dict:
    """Parse the tick export once and cache the per-minute aggregation, keyed by the
    file's SHA-256, so repeated analysis of a 240 MB / 5.9 M-row export never re-parses."""
    if not tick_path.exists():
        return {"status": "TICK_EXPORT_MISSING", "path": str(tick_path)}
    sha = _sha256_file(tick_path)
    cached = _read_json(cache_path) if cache_path.exists() else None
    if cached and cached.get("tick_sha256") == sha:
        minutes = {stream: {datetime.fromisoformat(k): v for k, v in store.items()}
                   for stream, store in cached["minutes"].items()}
        out = {k: v for k, v in cached.items() if k != "minutes"}
        out["_minutes"] = minutes
        out["parse_cache"] = "HIT"
        return out
    tick = adjudicate_tick(tick_path)
    if tick.get("status") == "ADJUDICATED":
        payload = {k: v for k, v in tick.items() if not k.startswith("_")}
        payload["tick_sha256"] = sha
        payload["minutes"] = {stream: {k.isoformat(): v for k, v in store.items()}
                              for stream, store in tick["_minutes"].items()}
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        tick["parse_cache"] = "MISS (written)"
    return tick


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-mt5", action="store_true")
    ap.add_argument("--tick", action="store_true")
    ap.add_argument("--parity", action="store_true")
    # Smoke-test only: point at a truncated copy to validate logic without paying the
    # full 240 MB / ~13-minute parse. Never used for the recorded evidence run.
    ap.add_argument("--tick-path", default=str(TICK_EXPORT))
    ap.add_argument("--cache-path", default=None)
    args = ap.parse_args()
    if not (args.probe_mt5 or args.tick or args.parity):
        args.probe_mt5 = args.tick = args.parity = True

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / "M1_SOURCE_ADMISSION_V1.json"
    report = {"schema": "AG_SSC_V1_0_1_ONE_YEAR_M1_SOURCE_ADMISSION_V1",
              "generated_at_utc": datetime.now(timezone.utc).date().isoformat(),
              "generated_at_utc_note": "DATE_ONLY",
              "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1", "strategy_version": "1.0.1",
              "symbol": SYMBOL, "target_missing_interval": {"from": _iso(GAP_START), "to": _iso(GAP_END)}}

    if args.probe_mt5:
        report["P1_mt5_depth_probe"] = probe_mt5()
    tick = None
    if args.tick or args.parity:
        # Cache lives in the OS temp dir on purpose: it is a derived parse accelerator,
        # not evidence, and must never be committed.
        cache = Path(args.cache_path) if args.cache_path else \
            Path(os.environ.get("TEMP", ".")) / "ssc_tick_minute_cache.json"
        tick = tick_data(cache, Path(args.tick_path))
    if args.tick and tick is not None:
        report["P2_tick_adjudication"] = {k: v for k, v in tick.items() if not k.startswith("_")}
    if args.parity and tick is not None and tick.get("status") == "ADJUDICATED":
        report["P4_overlap_parity"] = parity(tick, CANONICAL_M1)
        report["P2_tick_adjudication"] = {k: v for k, v in tick.items() if not k.startswith("_")}

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({k: v for k, v in report.items() if not k.startswith("P2")}, indent=2, default=str))
    print(f"\nartifact: {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
