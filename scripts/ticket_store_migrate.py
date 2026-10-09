"""Migrate existing journal records into TICKET_STORE_V1 (source=LEGACY), then rebuild and check the index.

    python scripts/ticket_store_migrate.py --journal journal --store journal/ticket_store [--json]

Read-only on the journal. Idempotent: a second run writes nothing new.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ticket_store.index import check, rebuild  # noqa: E402
from ticket_store.legacy_migration import migrate  # noqa: E402
from ticket_store.store import TicketStore  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    counts = migrate(args.journal, TicketStore(args.store))
    rebuild(args.store)
    report = check(args.store)
    out = {"migration": counts, "integrity": "PASS" if report["ok"] else "FAIL",
           "index": {k: {"jsonl": v["jsonl"], "index": v["index"]} for k, v in report["tables"].items()}}
    print(json.dumps(out, indent=2) if args.json else out)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
