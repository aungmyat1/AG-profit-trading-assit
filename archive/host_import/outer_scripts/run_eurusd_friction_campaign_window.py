"""Run one predeclared WP3A.1 campaign window's fixed-grid collection (WP2). Reuses the
already-audited collector (fx_friction_research.spread_evidence) -- no second collector.
Read-only: connects via mt5.connection.connect() then calls collect_fixed_grid(), which
never calls order_send/order_check. Refuses to run if the campaign manifest has not been
frozen first, and refuses to overwrite a window that already has a raw file for the same
UTC trading day -- a completed or in-progress window is never silently restarted or
appended-over because its results looked unfavorable.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mt5.connection import MT5ConnectionError, connect  # noqa: E402
from fx_friction_research.spread_evidence import (  # noqa: E402
    collect_fixed_grid,
    raw_rows_hash,
    summarize_campaign_rows,
)

CAMPAIGN_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_LARGE_SMC_V1" / "EURUSD_ADMISSION_CONTRACTS"
    / "friction_campaign_wp3a1"
)
MANIFEST_PATH = CAMPAIGN_DIR / "campaign_manifest.json"
SESSIONS_DIR = CAMPAIGN_DIR / "sessions"

VALID_WINDOW_IDS = (
    "WINDOW_A_ASIAN_REFERENCE", "WINDOW_B_PRE_LONDON", "WINDOW_C_LONDON", "WINDOW_D_LONDON_NEWYORK",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-id", required=True, choices=VALID_WINDOW_IDS)
    parser.add_argument("--day", default=None, help="UTC trading day label YYYY-MM-DD; default: today UTC")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print("REFUSING: campaign manifest not frozen yet -- run "
              "freeze_eurusd_friction_campaign_manifest.py first", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    campaign_id = manifest["campaign_id"]
    sample_count = manifest["samples_per_window_minimum"]
    interval_seconds = manifest["sampling_interval_seconds"]

    day = args.day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if datetime.strptime(day, "%Y-%m-%d").weekday() >= 5:
        print(f"REFUSING: {day} is a weekend UTC day -- not a valid FX trading day for this campaign", file=sys.stderr)
        return 1

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = SESSIONS_DIR / f"{day}_{args.window_id}_raw.jsonl"
    summary_path = SESSIONS_DIR / f"{day}_{args.window_id}_summary.json"
    if raw_path.exists():
        print(f"REFUSING: {raw_path} already exists -- a completed/in-progress window is never restarted", file=sys.stderr)
        return 1

    try:
        connect()
    except MT5ConnectionError as exc:
        print(f"MT5_CONNECTION_FAILED: {exc}", file=sys.stderr)
        return 1

    rows = collect_fixed_grid(
        symbol="EURUSD",
        pip_size=0.0001,
        campaign_id=campaign_id,
        window_id=args.window_id,
        sample_count=sample_count,
        interval_seconds=interval_seconds,
    )

    with raw_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    summary = summarize_campaign_rows(rows)
    summary.update({
        "campaign_id": campaign_id,
        "window_id": args.window_id,
        "day": day,
        "raw_rows_hash": raw_rows_hash(rows),
    })
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
