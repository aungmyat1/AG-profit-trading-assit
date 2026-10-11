"""AG_TRADE_ASSISTANT_V1_0_3 -- FX combined daily decision report (scheduler-ready CLI;
this script is NOT itself a scheduler and installs nothing). Orchestration only: it
invokes the existing, unchanged pilot runtime/report code
(post_asian_pilot.report.render_pilot_end_report, via post_asian_pilot.daily_fx_report),
persists the canonical JSON to an append-only archive, and prints a human-readable
summary. Never calls execution.executor / mt5_gateway / order_check / order_send.

Manual invocation:
    python scripts/run_fx_daily_report.py --date 2026-09-03
    python scripts/run_fx_daily_report.py                # defaults to today (UTC)
    python scripts/run_fx_daily_report.py --json          # canonical JSON on stdout

Recommended future schedule (NOT installed by this script -- see
docs/status/AG_TRADE_ASSISTANT_V1_0_3_DAILY_REPORTING_HISTORY_AND_SCHEDULER_STATUS.md):
run once daily at/after 15:05 UTC, after both ASIAN_LONDON (closes 11:00 UTC) and
LONDON_NEWYORK (closes 15:00 UTC) have completed for the day, e.g.:

    schtasks /create /tn "AG_FX_Daily_Report" /sc daily /st 15:05 ^
      /tr "python \"D:\\ddev\\AG profit trading\\scripts\\run_fx_daily_report.py\""
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from post_asian_pilot.daily_fx_report import build_fx_daily_report, human_readable_fx_daily_report  # noqa: E402
from post_asian_pilot.report_archive import write_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AG_TRADE_ASSISTANT_V1_0_3 FX combined daily decision report "
                    "(read-only orchestration; PROPOSAL_ONLY, no execution)")
    parser.add_argument("--date", type=str, default=None, help="Trading date YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--json", action="store_true", help="Print canonical JSON instead of the human summary")
    args = parser.parse_args()

    trading_date = (dt.date.fromisoformat(args.date) if args.date
                    else dt.datetime.now(dt.timezone.utc).date())

    report = build_fx_daily_report(trading_date)
    archived_path = write_report("fx", trading_date, report)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(human_readable_fx_daily_report(report))
    print(f"\n(archived: {archived_path})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
