"""Aggregate all completed WP3A.1 campaign window sessions into daily, per-window-group,
and campaign-level spread statistics (WP3/WP4/WP5), plus C10 descriptive ratios (WP8).
Read-only: only reads the *_raw.jsonl / *_summary.json files already written by
run_eurusd_friction_campaign_window.py -- never connects to MT5, never places an order.
Writes campaign_evidence_manifest.json (every session's raw_rows_hash + a deterministic
combined_campaign_hash) alongside the per-day/per-window/aggregate statistics report.
Does NOT decide FRICTION_POLICY_SIGNABILITY or touch friction_policy_contract.json --
that judgment call is made in the status write-up, not auto-derived from sample count.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from fx_friction_research.c10_friction_ratios import friction_to_stop_ratios  # noqa: E402
from fx_friction_research.spread_evidence import combine_hashes, summarize_campaign_rows  # noqa: E402

CAMPAIGN_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_LARGE_SMC_V1" / "EURUSD_ADMISSION_CONTRACTS"
    / "friction_campaign_wp3a1"
)
SESSIONS_DIR = CAMPAIGN_DIR / "sessions"
EVIDENCE_MANIFEST_PATH = CAMPAIGN_DIR / "campaign_evidence_manifest.json"
REPORT_PATH = CAMPAIGN_DIR / "campaign_aggregate_report.json"


def load_sessions():
    sessions = []
    for summary_path in sorted(SESSIONS_DIR.glob("*_summary.json")):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        raw_path = summary_path.with_name(summary_path.name.replace("_summary.json", "_raw.jsonl"))
        rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        sessions.append({"summary": summary, "rows": rows, "raw_path": str(raw_path)})
    return sessions


def main() -> int:
    sessions = load_sessions()
    if not sessions:
        print(json.dumps({"error": "NO_SESSIONS_COLLECTED", "sessions_dir": str(SESSIONS_DIR)}, indent=2))
        return 1

    by_day = defaultdict(list)
    by_window = defaultdict(list)
    all_rows = []
    for session in sessions:
        day = session["summary"]["day"]
        window_id = session["summary"]["window_id"]
        by_day[day].append(session)
        by_window[window_id].extend(session["rows"])
        all_rows.extend(session["rows"])

    daily_stats = {}
    for day, day_sessions in sorted(by_day.items()):
        day_rows = [row for s in day_sessions for row in s["rows"]]
        windows_present = sorted({s["summary"]["window_id"] for s in day_sessions})
        daily_stats[day] = {
            "windows_completed": windows_present,
            "window_completion_count": len(windows_present),
            "spread_statistics": summarize_campaign_rows(day_rows),
        }

    session_grouped_stats = {
        window_id: summarize_campaign_rows(rows) for window_id, rows in sorted(by_window.items())
    }

    aggregate_summary = summarize_campaign_rows(all_rows)

    evidence_hashes = {
        f"{s['summary']['day']}_{s['summary']['window_id']}": s["summary"]["raw_rows_hash"] for s in sessions
    }
    combined_campaign_hash = combine_hashes(list(evidence_hashes.values()))

    complete_days = sorted(day for day, stats in daily_stats.items() if stats["window_completion_count"] == 4)

    report = {
        "collection_days_attempted": sorted(by_day.keys()),
        "collection_days_complete": complete_days,
        "collection_days_complete_count": len(complete_days),
        "total_sample_count": aggregate_summary["sample_count"],
        "total_missing_sample_count": aggregate_summary["missing_sample_count"],
        "daily_spread_statistics": daily_stats,
        "session_grouped_spread_statistics": session_grouped_stats,
        "aggregate_spread_statistics": aggregate_summary,
        "c10_friction_ratios": {
            "aggregate": friction_to_stop_ratios(aggregate_summary),
            "by_window_group": {
                window_id: friction_to_stop_ratios(stats) for window_id, stats in session_grouped_stats.items()
            },
        },
        "combined_campaign_hash": combined_campaign_hash,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    EVIDENCE_MANIFEST_PATH.write_text(
        json.dumps({"evidence_hashes": evidence_hashes, "combined_campaign_hash": combined_campaign_hash}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps({
        "collection_days_complete_count": len(complete_days),
        "total_sample_count": aggregate_summary["sample_count"],
        "combined_campaign_hash": combined_campaign_hash,
        "report_path": str(REPORT_PATH),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
