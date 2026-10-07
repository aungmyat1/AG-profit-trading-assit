#!/usr/bin/env python3
"""Deterministic daily evaluation for all required FX and crypto instrument/session pairs.

Produces one canonical decision record per pair, guaranteeing NO SILENT SESSION.
Defaults to ARCHIVE_ONLY with no broker mutation and no network: without a connected
MT5 feed every pair produces a deterministic BLOCKED/INSUFFICIENT_DATA record.

Examples:
    python scripts/run_daily_evaluation.py --dry-run        # fixture-free, offline determinism
    python scripts/run_daily_evaluation.py --json            # machine-readable summary
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import List

# Ensure src/ and repo root are importable when running directly.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
if os.path.join(_REPO, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO, "src"))

# Portability shim (same as tests/conftest.py): install the bundled MetaTrader5.py
# stub when the Windows-only MetaTrader5 wheel is not installed, so CLI invocations
# on Linux/macOS can at least import the portability-tested modules.  Any real
# broker call raises MT5StubOperationAttempted.
try:
    import MetaTrader5  # noqa: F401
except ModuleNotFoundError:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("MetaTrader5", os.path.join(_REPO, "MetaTrader5.py"))
    _mod = importlib.util.module_from_spec(_spec)
    assert _spec and _spec.loader
    sys.modules["MetaTrader5"] = _mod
    _spec.loader.exec_module(_mod)

from v1_tickets.daily_evaluator import run_daily_evaluation  # noqa: E402

UTC = dt.timezone.utc


def _parse_now(s: str | None) -> dt.datetime:
    if not s:
        return dt.datetime.now(UTC)
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--now", default=None, help="ISO override for wall clock (UTC)")
    p.add_argument("--day", default=None, help="ISO trading date override (defaults to now.date())")
    p.add_argument("--archive-root", default="artifacts", help="archive root directory")
    p.add_argument("--json", action="store_true", help="emit JSON summary")
    p.add_argument("--no-crypto", action="store_true", help="skip crypto pairs (FX only)")
    p.add_argument("--dry-run", action="store_true", help="offline, no data source, BLOCKED expected")
    args = p.parse_args(argv)

    now = _parse_now(args.now)
    day = dt.date.fromisoformat(args.day) if args.day else now.date()
    results = run_daily_evaluation(
        now=now, day=day, archive_root=args.archive_root,
        include_crypto=not args.no_crypto,
        policy_root=_REPO,
    )
    summary = [{
        "instrument": r.instrument, "session": r.session, "venue": r.venue,
        "decision": r.decision, "ticket_id": r.ticket_id, "archive_path": r.archive_path,
    } for r in results]
    if args.json:
        print(json.dumps({"evaluated_at": now.isoformat(), "results": summary}, indent=2))
    else:
        for r in results:
            print(f"{r.instrument:8s} {r.session:20s} {r.decision:32s} {r.ticket_id}")
            if not args.dry_run:
                # Print rendered text for WATCH_READY/INFO_ONLY, otherwise just a summary line.
                if r.canonical.get("presentation") in ("WATCH_READY", "INFO_ONLY"):
                    print("-" * 60)
                    print(r.rendered_text)
                    print("-" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
