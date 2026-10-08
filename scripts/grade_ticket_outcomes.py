#!/usr/bin/env python3
"""Replay M1 outcomes from TICKET_STORE_V1 and print a grouped report.

No MT5 terminal or network is used. M1 history is read from <m1-dir>/<SYMBOL>.csv.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ticket_store.grader import load_m1_csv, make_report, replay
from ticket_store.store import TicketStore

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--from", dest="date_from", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--to", dest="date_to", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--m1-dir", required=True)
    ap.add_argument("--expiry-minutes", type=int, default=15)
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.expiry_minutes <= 0:
        ap.error("--expiry-minutes must be positive")
    store = TicketStore(args.store)
    if not args.report_only:
        symbols = {r.get("symbol") for r in store.evaluations()
                   if args.date_from.isoformat() <= str(r.get("evaluated_at_utc", ""))[:10] <= args.date_to.isoformat()}
        bars = {s: load_m1_csv(Path(args.m1_dir) / f"{s}.csv") for s in symbols
                if s and (Path(args.m1_dir) / f"{s}.csv").exists()}
        counts = replay(store, bars, args.date_from, args.date_to, expiry_minutes=args.expiry_minutes)
    else:
        counts = None
    report = make_report(store)
    output = {"replay": counts, "report": report}
    print(json.dumps(output if args.json else report, indent=2, sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
