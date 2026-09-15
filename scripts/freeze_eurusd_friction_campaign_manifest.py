"""Freeze the WP3A.1 multi-session friction-evidence campaign manifest -- must run and
be committed BEFORE any campaign observation is collected (WP1). Writes
campaign_manifest.json and its own deterministic sha256 (over canonical sorted JSON,
same technique as fx_friction_research.spread_evidence.raw_rows_hash) into
campaign_manifest_hash.json alongside it. Refuses to overwrite an existing manifest --
a campaign, once frozen, is immutable; a genuinely new campaign needs a new campaign_id
and its own directory, never a silent edit of this one.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_LARGE_SMC_V1" / "EURUSD_ADMISSION_CONTRACTS"
    / "friction_campaign_wp3a1"
)
MANIFEST_PATH = OUT_DIR / "campaign_manifest.json"
HASH_PATH = OUT_DIR / "campaign_manifest_hash.json"

CAMPAIGN_ID = "LSMC_EURUSD_FRICTION_WP3A1_V1"


def build_manifest(created_utc: str) -> dict:
    return {
        "schema": "AG_LARGE_SMC_EURUSD_FRICTION_CAMPAIGN_MANIFEST_V1",
        "campaign_id": CAMPAIGN_ID,
        "created_utc": created_utc,
        "broker": "VantageMarkets-Demo",
        "symbol": "EURUSD",
        "minimum_trading_days": 5,
        "sampling_interval_seconds": 5,
        "samples_per_window_minimum": 120,
        "windows": [
            {"window_id": "WINDOW_A_ASIAN_REFERENCE", "start_utc_hhmm": "05:30", "end_utc_hhmm": "05:40"},
            {"window_id": "WINDOW_B_PRE_LONDON", "start_utc_hhmm": "06:50", "end_utc_hhmm": "07:00"},
            {"window_id": "WINDOW_C_LONDON", "start_utc_hhmm": "09:00", "end_utc_hhmm": "09:10"},
            {"window_id": "WINDOW_D_LONDON_NEWYORK", "start_utc_hhmm": "12:30", "end_utc_hhmm": "12:40"},
        ],
        "required_minimum_population": {
            "windows_per_day": 4,
            "samples_per_window": 120,
            "minimum_days": 5,
            "total_minimum_observations": 2400,
        },
        "trading_day_definition": (
            "UTC calendar day; a trading day counts toward minimum_trading_days only if "
            "the FX market is open (Mon-Fri UTC, no recognized holiday closure) -- a "
            "weekend or closed day is skipped, never substituted with another day's data."
        ),
        "collection_rules": {
            "adaptive_sampling": False,
            "deletion_of_high_spread_samples": False,
            "restart_of_unfavorable_windows": False,
            "connection_gap_handling": (
                "recorded as MISSING_GAP rows (fx_friction_research.spread_evidence."
                "MISSING_SOURCE), never silently backfilled, interpolated, or omitted"
            ),
            "fixed_grid": (
                "each window samples on a fixed sampling_interval_seconds grid anchored "
                "to that window run's own start time; a missed/failed tick is recorded "
                "as MISSING_GAP, not skipped without a trace"
            ),
        },
        "frozen_before_collection": True,
        "amendments_after_freeze": (
            "NONE -- any change to this manifest after campaign_manifest_hash is computed "
            "voids the campaign; a genuinely new campaign requires a new campaign_id"
        ),
    }


def canonical_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    if MANIFEST_PATH.exists():
        print(f"REFUSING: campaign manifest already frozen at {MANIFEST_PATH}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    created_utc = datetime.now(timezone.utc).isoformat()
    manifest = build_manifest(created_utc)
    manifest_hash = canonical_hash(manifest)

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    HASH_PATH.write_text(
        json.dumps({"campaign_manifest_hash": manifest_hash, "hashed_utc": created_utc}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"campaign_manifest_hash": manifest_hash, "manifest_path": str(MANIFEST_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
