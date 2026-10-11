"""Run one preregistered SSC H2 friction-campaign cell (read-only MT5 bid/ask spread).

Reuses the already-audited collector (fx_friction_research.spread_evidence) -- no second
collector. Read-only: connects via mt5.connection.connect() then calls
collect_fixed_grid(), which never calls order_send/order_check. Refuses to run if the
campaign manifest has not been frozen, refuses to overwrite a cell that already has a
raw file for the same UTC trading day, refuses weekend UTC days, and refuses to start
collection outside the cell's own preregistered UTC trade window (fail-closed: no
out-of-session sampling, no silent widening of a window).

Campaign identity: SSC_H2_FRICTION_CAMPAIGN_V1 (see campaign_manifest.json).
This is CONTEMPORANEOUS_BROKER_FRICTION_PROXY evidence only -- never historical spread
reconstruction, never strategy-edge evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mt5.connection import MT5ConnectionError, connect  # noqa: E402
from mt5.account import account  # noqa: E402
from fx_friction_research.spread_evidence import (  # noqa: E402
    collect_fixed_grid,
    raw_rows_hash,
    summarize_campaign_rows,
)

CAMPAIGN_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
    / "H2_FRICTION_VERIFICATION"
)
MANIFEST_PATH = CAMPAIGN_DIR / "campaign_manifest.json"
MANIFEST_HASH_PATH = CAMPAIGN_DIR / "campaign_manifest_hash.json"
SESSIONS_DIR = CAMPAIGN_DIR / "sessions"

EXPECTED_BROKER = "VantageMarkets-Demo"
VALID_SYMBOLS = ("EURUSD", "GBPUSD")
VALID_SESSION_IDS = ("ASIAN_LONDON", "LONDON_NEWYORK")
PIP_SIZE = 0.0001


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def _window_bounds(manifest: dict, session_id: str):
    for s in manifest["sessions"]:
        if s["session_id"] == session_id:
            return _parse_hhmm(s["trade_start_utc_hhmm"]), _parse_hhmm(s["trade_end_utc_hhmm"])
    raise SystemExit(f"SESSION_NOT_IN_MANIFEST: {session_id}")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=VALID_SYMBOLS)
    parser.add_argument("--session-id", required=True, choices=VALID_SESSION_IDS)
    parser.add_argument("--day", default=None, help="UTC trading day YYYY-MM-DD; default: today UTC")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print("REFUSING: campaign manifest not frozen yet", file=sys.stderr)
        return 1
    if not MANIFEST_HASH_PATH.exists():
        print("REFUSING: campaign manifest hash not frozen yet -- freeze the manifest first", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    campaign_id = manifest["campaign_id"]
    sample_count = manifest["samples_per_cell_minimum"]
    interval_seconds = manifest["sampling_interval_seconds"]
    start_hhmm, end_hhmm = _window_bounds(manifest, args.session_id)

    now = _now_utc()
    day = args.day or now.strftime("%Y-%m-%d")
    day_dt = datetime.strptime(day, "%Y-%m-%d")
    if day_dt.weekday() >= 5:
        print(f"REFUSING: {day} is a weekend UTC day -- not a valid FX trading day", file=sys.stderr)
        return 1

    # Fail-closed window guard: collection must fit entirely within the cell's trade window.
    window_start = datetime.combine(day_dt.date(), start_hhmm, tzinfo=timezone.utc)
    window_end = datetime.combine(day_dt.date(), end_hhmm, tzinfo=timezone.utc)
    collection_seconds = sample_count * interval_seconds
    if now < window_start:
        print(f"REFUSING: window not yet open -- {args.session_id} opens {window_start.isoformat()} (now {now.isoformat()})", file=sys.stderr)
        return 1
    if now + timedelta(seconds=collection_seconds) > window_end:
        print(f"REFUSING: insufficient time remaining in {args.session_id} window ({window_end.isoformat()}) to complete {sample_count} samples", file=sys.stderr)
        return 1

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = SESSIONS_DIR / f"{day}_{args.symbol}_{args.session_id}_raw.jsonl"
    summary_path = SESSIONS_DIR / f"{day}_{args.symbol}_{args.session_id}_summary.json"
    if raw_path.exists():
        print(f"REFUSING: {raw_path} already exists -- a completed/in-progress cell is never restarted", file=sys.stderr)
        return 1

    try:
        connect()
    except MT5ConnectionError as exc:
        print(f"MT5_CONNECTION_FAILED: {exc}", file=sys.stderr)
        return 1

    # Broker identity preflight (read-only).
    acct = account()
    if acct.server != EXPECTED_BROKER:
        print(f"BROKER_IDENTITY_MISMATCH: expected {EXPECTED_BROKER}, got {acct.server}", file=sys.stderr)
        return 1
    if not acct.is_demo:
        print(f"ACCOUNT_NOT_DEMO: {acct.server} reported a non-demo account -- refusing for a research campaign", file=sys.stderr)
        return 1

    rows = collect_fixed_grid(
        symbol=args.symbol,
        pip_size=PIP_SIZE,
        campaign_id=campaign_id,
        window_id=f"{args.session_id}:{args.symbol}",
        sample_count=sample_count,
        interval_seconds=interval_seconds,
    )

    with raw_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    summary = summarize_campaign_rows(rows)
    summary.update({
        "campaign_id": campaign_id,
        "symbol": args.symbol,
        "session_id": args.session_id,
        "day": day,
        "broker_server": acct.server,
        "account_environment": "DEMO",
        "raw_rows_hash": raw_rows_hash(rows),
    })
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
