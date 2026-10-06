"""Manual Trade Ticket V1 daily report (Phase 8) -- read-only over journal/, prints and archives.

    python scripts/run_manual_ticket_report.py --date 2026-10-06 [--json]

The scheduled FX task also builds it once per day after the last session window. Never
touches MT5; EDGE_VERIFIED is always FALSE and orders sent by system is always 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "host"))

from post_asian_pilot.report_archive import write_report  # noqa: E402
from v1_tickets.manual_report import REPORT_TYPE, build_report, render_report  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=None)
    ap.add_argument("--journal", default=str(ROOT / "journal"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    day = dt.date.fromisoformat(args.date) if args.date else now.date()
    import live_candles_smoke as host   # expected symbol/session universe of the scheduled runner
    report = build_report(args.journal, day, now=now, expected=host.manual_expected())
    path = write_report(REPORT_TYPE, day, report, root=os.path.join(args.journal, "reports"))
    print(json.dumps(report, indent=2, default=str) if args.json else render_report(report))
    print(f"\n(archived: {path})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
