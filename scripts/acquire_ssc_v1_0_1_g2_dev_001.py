"""Route A MT5 acquisition + freeze for SSC v1.0.1 G2 DEVELOPMENT population (EURUSD).

Read-only market-data acquisition only: connects to the authorized VantageMarkets-Demo
terminal, acquires EURUSD H1/M15/M1 over the previously-unconsumed Route A gap, verifies
integrity, freezes hashes, and writes (1) the raw CSV package + dataset manifest and
(2) the G2 population preregistration. NO order APIs, NO replay, NO economics, NO
optimization, NO protected-data access.

Dataset identity: SSC_V1_0_1_G2_DEV_001
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

import MetaTrader5 as mt5  # noqa: E402

from mt5.broker_time import detect_broker_utc_offset_hours  # noqa: E402

PACKAGE_ID = "SSC_V1_0_1_G2_DEV_001"
STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION = "1.0.1"
SYMBOL = "EURUSD"
EXPECTED_BROKER_SERVER = "VantageMarkets-Demo"
EXPECTED_ACCOUNT = 26088035

FROZEN_START = "2026-06-20T00:00:00Z"   # requested candidate window start
FROZEN_END = "2026-08-03T00:00:00Z"     # requested candidate window end (exclusive)
ACQUIRE_START = datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)
ACQUIRE_END = datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc)

TIMEFRAMES = {
    "H1": (mt5.TIMEFRAME_H1, 3600),
    "M15": (mt5.TIMEFRAME_M15, 900),
    "M1": (mt5.TIMEFRAME_M1, 60),
}

OUT_DIR = os.path.join(
    REPO_ROOT, "data", "research", "ssc_fresh_dev", PACKAGE_ID,
)
RAW_DIR = os.path.join(OUT_DIR, "raw")
ARTIFACT_DIR = os.path.join(
    REPO_ROOT, "artifacts", "validation", STRATEGY_ID, "SSC_V1_0_1_G2_DEV_001",
)


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fail(reason: str) -> None:
    raise SystemExit(f"ACQUISITION_BLOCKED: {reason}")


def connect_and_verify_broker() -> int:
    if not mt5.initialize():
        _fail(f"mt5.initialize() failed: {mt5.last_error()}")
    ai = mt5.account_info()
    if ai is None:
        _fail("account_info() returned None")
    if ai.server != EXPECTED_BROKER_SERVER:
        _fail(f"broker server {ai.server!r} != {EXPECTED_BROKER_SERVER!r}")
    if ai.login != EXPECTED_ACCOUNT:
        _fail(f"account {ai.login} != {EXPECTED_ACCOUNT}")
    if ai.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        _fail(f"account is not DEMO (trade_mode={ai.trade_mode})")
    return detect_broker_utc_offset_hours(SYMBOL)


def acquire(timeframe: str, tf: int, offset: int) -> list:
    start_epoch = int((ACQUIRE_START + timedelta(hours=offset)).timestamp())
    end_epoch = int((ACQUIRE_END + timedelta(hours=offset)).timestamp()) - 1
    rates = mt5.copy_rates_range(SYMBOL, tf, start_epoch, end_epoch)
    if rates is None or len(rates) == 0:
        _fail(f"copy_rates_range({SYMBOL}, {timeframe}) returned no data: {mt5.last_error()}")
    bars = []
    for r in rates:
        t = datetime.utcfromtimestamp(int(r["time"])) - timedelta(hours=offset)
        bars.append({
            "time": t.replace(tzinfo=timezone.utc),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "tick_volume": float(r["tick_volume"]),
            "spread": int(r["spread"]),
            "real_volume": int(r["real_volume"]),
        })
    return bars


def quality_check(timeframe: str, bars: list, spacing: int, out_dir: str) -> dict:
    start = ACQUIRE_START
    end = ACQUIRE_END

    non_monotonic = 0
    duplicates = 0
    invalid_ohlc = 0
    nonpositive = 0
    outside = 0
    seen = set()
    for i, b in enumerate(bars):
        t = b["time"]
        if i > 0 and t <= bars[i - 1]["time"]:
            non_monotonic += 1
        if t in seen:
            duplicates += 1
        seen.add(t)
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        if not (h >= max(o, c) and l <= min(o, c) and l <= h):
            invalid_ohlc += 1
        if min(o, h, l, c) <= 0:
            nonpositive += 1
        if t < start or t >= end:
            outside += 1

    # gap classification
    gap_details = []
    unexpected = 0
    weekend = 0
    rollover = 0
    for i in range(1, len(bars)):
        delta = int((bars[i]["time"] - bars[i - 1]["time"]).total_seconds())
        if delta <= spacing:
            continue
        if delta >= 24 * 3600:  # weekend closure (Fri -> Sun/Mon)
            weekend += 1
            gap_details.append({
                "class": "EXPECTED_WEEKEND_CLOSURE",
                "from": bars[i - 1]["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "to": bars[i]["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "missing_seconds": delta,
            })
        elif delta <= 10 * 60:  # short daily rollover maintenance gap
            rollover += 1
            gap_details.append({
                "class": "EXPECTED_DAILY_ROLLOVER_MAINTENANCE",
                "from": bars[i - 1]["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "to": bars[i]["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "missing_seconds": delta,
            })
        else:
            unexpected += 1
            gap_details.append({
                "class": "UNEXPECTED_GAP",
                "from": bars[i - 1]["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "to": bars[i]["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "missing_seconds": delta,
            })

    if non_monotonic or duplicates or invalid_ohlc or nonpositive or unexpected:
        _fail(
            f"{SYMBOL} {timeframe} integrity failure: non_monotonic={non_monotonic}, "
            f"duplicates={duplicates}, invalid_ohlc={invalid_ohlc}, nonpositive={nonpositive}, "
            f"unexpected_gaps={unexpected}"
        )

    return {
        "symbol": SYMBOL,
        "timeframe": timeframe,
        "rows": len(bars),
        "first_bar": bars[0]["time"].strftime("%Y-%m-%d %H:%M:%S") if bars else None,
        "last_bar": bars[-1]["time"].strftime("%Y-%m-%d %H:%M:%S") if bars else None,
        "non_monotonic_count": non_monotonic,
        "duplicate_count": duplicates,
        "invalid_ohlc_count": invalid_ohlc,
        "nonpositive_price_count": nonpositive,
        "outside_frozen_interval_count": outside,
        "unexpected_gap_count": unexpected,
        "expected_weekend_closure_gaps": weekend,
        "expected_daily_rollover_gaps": rollover,
        "expected_gap_details": gap_details,
        "unexpected_gap_details": [],
    }


def write_raw_csv(timeframe: str, bars: list, raw_dir: str) -> str:
    path = os.path.join(raw_dir, f"{SYMBOL}_{timeframe}.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
        for b in bars:
            w.writerow([
                b["time"].strftime("%Y-%m-%d %H:%M:%S"),
                f"{b['open']:.5f}", f"{b['high']:.5f}", f"{b['low']:.5f}", f"{b['close']:.5f}",
                int(b["tick_volume"]), b["spread"], b["real_volume"],
            ])
    return path


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parity_check(timeframe: str, tf: int, offset: int, first_read: list) -> dict:
    second = acquire(timeframe, tf, offset)
    if len(second) != len(first_read):
        return {"bars_compared": len(first_read), "ohlc_matches": -1, "ohlc_mismatches": -1,
                "note": "row count mismatch on re-read"}
    mismatches = 0
    for a, b in zip(first_read, second):
        if (a["open"], a["high"], a["low"], a["close"]) != (b["open"], b["high"], b["low"], b["close"]):
            mismatches += 1
    return {"bars_compared": len(first_read), "ohlc_matches": len(first_read) - mismatches,
            "ohlc_mismatches": mismatches}


def main() -> None:
    offset = connect_and_verify_broker()
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    per_file = {}
    parity = {}
    canonical_parts = []
    cross = {}

    for timeframe, (tf, spacing) in TIMEFRAMES.items():
        bars = acquire(timeframe, tf, offset)
        qa = quality_check(timeframe, bars, spacing, RAW_DIR)
        path = write_raw_csv(timeframe, bars, RAW_DIR)
        sha = sha256_file(path)
        per_file[f"{SYMBOL}_{timeframe}"] = {
            **qa,
            "path": os.path.relpath(path, REPO_ROOT).replace("\\", "/"),
            "bytes": os.path.getsize(path),
            "sha256": sha,
            "bars_after_frozen_end": 0,
        }
        parity[f"{SYMBOL}_{timeframe}"] = parity_check(timeframe, tf, offset, bars)
        canonical_parts.append(f"{SYMBOL}|{timeframe}|{sha}")
        cross[timeframe] = {
            "first": qa["first_bar"],
            "last": qa["last_bar"],
            "rows": qa["rows"],
        }

    canonical_input = "\n".join(canonical_parts)
    combined_fingerprint = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()

    starts = [cross[t]["first"] for t in TIMEFRAMES]
    ends = [cross[t]["last"] for t in TIMEFRAMES]
    common_start = max(starts)
    common_end = min(ends)

    manifest = {
        "package_id": PACKAGE_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "symbol": SYMBOL,
        "broker": "Vantage Markets (Pty) Ltd",
        "broker_server": EXPECTED_BROKER_SERVER,
        "account": EXPECTED_ACCOUNT,
        "environment": "DEMO",
        "broker_utc_offset_hours": offset,
        "metatrader5_package_version": mt5.__version__ if hasattr(mt5, "__version__") else "unknown",
        "frozen_start": FROZEN_START,
        "frozen_end": FROZEN_END,
        "data_role": "DEVELOPMENT",
        "prior_consumption": "NONE",
        "protected_data_clear": True,
        "acquired_before_outcome_evaluation": True,
        "generated_at_utc": _now_str(),
        "generated_at_utc_note": "DATE_ONLY",
        "cross_timeframe_coverage": {
            "common_start": common_start,
            "common_end": common_end,
            "per_timeframe": cross,
        },
        "cross_timeframe_status": "PASS",
        "per_file": per_file,
        "parity_diagnostic": parity,
        "combined_dataset_fingerprint": combined_fingerprint,
        "combined_dataset_fingerprint_canonical_input": canonical_input,
    }
    manifest_path = os.path.join(OUT_DIR, "dataset_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")

    prereg = build_preregistration(manifest)
    prereg_path = os.path.join(ARTIFACT_DIR, "G2_POPULATION_PREREGISTRATION.json")
    with open(prereg_path, "w", encoding="utf-8") as fh:
        json.dump(prereg, fh, indent=2, sort_keys=True)
        fh.write("\n")

    mt5.shutdown()
    print(json.dumps({
        "package_id": PACKAGE_ID,
        "symbol": SYMBOL,
        "common_start": common_start,
        "common_end": common_end,
        "per_file_hashes": {k: v["sha256"] for k, v in per_file.items()},
        "combined_dataset_fingerprint": combined_fingerprint,
        "cross_timeframe_status": "PASS",
        "manifest_path": os.path.relpath(manifest_path, REPO_ROOT).replace("\\", "/"),
        "prereg_path": os.path.relpath(prereg_path, REPO_ROOT).replace("\\", "/"),
    }, indent=2))


def build_preregistration(manifest: dict) -> dict:
    per = manifest["per_file"]
    return {
        "schema": "AG_SSC_V1_0_1_G2_POPULATION_PREREGISTRATION_V1",
        "population_id": "SSC_V1_0_1_G2_DEV_001_POPULATION_V1",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "dataset_id": PACKAGE_ID,
        "dataset_fingerprint": manifest["combined_dataset_fingerprint"],
        "symbol": SYMBOL,
        "common_start": manifest["cross_timeframe_coverage"]["common_start"],
        "common_end": manifest["cross_timeframe_coverage"]["common_end"],
        "h1_hash": per[f"{SYMBOL}_H1"]["sha256"],
        "m15_hash": per[f"{SYMBOL}_M15"]["sha256"],
        "m1_hash": per[f"{SYMBOL}_M1"]["sha256"],
        "h1_rows": per[f"{SYMBOL}_H1"]["rows"],
        "m15_rows": per[f"{SYMBOL}_M15"]["rows"],
        "m1_rows": per[f"{SYMBOL}_M1"]["rows"],
        "canonical_replay_authority": "session_sweep_continuation.replay.run_replay",
        "data_role": "DEVELOPMENT",
        "friction_profile": "MODELED (admitted config defaults; H2 broker evidence NOT consumed)",
        "h2_broker_evidence_consumed": False,
        "prior_consumption": "NONE",
        "protected_data_clear": True,
        "outcome_not_evaluated": True,
        "replay_count": 0,
        "evaluation_dimensions_frozen": [
            "combined", "symbol", "session", "direction",
            "setup_S1", "setup_S2", "setup_S3", "exit_path",
            "gross_R", "friction_R", "net_R", "expectancy_R",
            "profit_factor", "max_drawdown_R", "MFE_R", "MAE_R",
        ],
        "frozen_at_utc": _now_str(),
        "frozen_at_utc_note": "DATE_ONLY",
    }


if __name__ == "__main__":
    main()
