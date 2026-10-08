"""Rebuild (default) or only check the TICKET_STORE_V1 SQLite index from its JSONL files.

    python scripts/ticket_store_reindex.py --store artifacts/ticket_store [--check-only] [--json]

Exit 0 when the integrity check passes (JSONL count == index count, identical ids), else 1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ticket_store.index import check, rebuild  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True, help="store root (the directory holding evaluations/ and outcomes/)")
    ap.add_argument("--check-only", action="store_true", help="do not rebuild; only compare JSONL with the index")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.check_only:
        rebuild(args.store)
    report = check(args.store)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name, t in report["tables"].items():
            print(f"{name:12s} jsonl={t['jsonl']} index={t['index']} missing={len(t['missing'])} extra={len(t['extra'])}")
        print("INTEGRITY", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
