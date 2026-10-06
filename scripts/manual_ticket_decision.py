"""Record the owner's decision on one manual ticket (Manual Trade Ticket V1 Phase 6).

Append-only; never touches MT5. TAKEN records a trade the owner placed BY HAND.

    python scripts/manual_ticket_decision.py --date 2026-10-06 --ticket-id <id> --decision SKIPPED --reason NEWS
    python scripts/manual_ticket_decision.py --date 2026-10-06 --ticket-id <id> --decision TAKEN \\
        --fill-time 2026-10-06T07:22:00+00:00 --fill 1.16080 --sl 1.16061 --tp 1.16200 --note "1 pip slippage"
    python scripts/manual_ticket_decision.py --date 2026-10-06 --expire     # auto EXPIRED past valid_until
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from v1_tickets.manual_ticket import ticket_path  # noqa: E402
from v1_tickets.owner_decision import (  # noqa: E402
    DECISIONS, SKIP_REASONS, DecisionError, ManualTicketDecision, decision_ticket, expire_undecided, record_decision,
)
from v1_tickets.scan_record import read_jsonl  # noqa: E402

DEFAULT_JOURNAL = str(Path(__file__).resolve().parent.parent / "journal")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True, help="ticket session date YYYY-MM-DD")
    ap.add_argument("--journal", default=DEFAULT_JOURNAL)
    ap.add_argument("--ticket-id")
    ap.add_argument("--decision", choices=DECISIONS)
    ap.add_argument("--reason", choices=SKIP_REASONS)
    ap.add_argument("--fill-time")
    ap.add_argument("--fill", type=float)
    ap.add_argument("--sl", type=float)
    ap.add_argument("--tp", type=float)
    ap.add_argument("--note")
    ap.add_argument("--expire", action="store_true", help="auto-record EXPIRED for undecided past-valid tickets")
    args = ap.parse_args(argv)
    day = dt.date.fromisoformat(args.date)
    now = dt.datetime.now(dt.timezone.utc)
    try:
        if args.expire:
            out = expire_undecided(args.journal, read_jsonl(ticket_path(args.journal, day)), now)
            print(json.dumps(out, indent=2, default=str))
            return 0
        if not args.ticket_id or not args.decision:
            ap.error("--ticket-id and --decision are required unless --expire")
        ticket = decision_ticket(args.journal, args.ticket_id, day)
        if ticket is None:
            print(f"TICKET_NOT_FOUND {args.ticket_id} in {ticket_path(args.journal, day)}", file=sys.stderr)
            return 2
        taken = args.decision == "TAKEN"
        decision = ManualTicketDecision(
            ticket_id=args.ticket_id, decision=args.decision, recorded_at=now.isoformat(),
            fill_time=args.fill_time if taken else None, actual_fill=args.fill if taken else None,
            actual_sl=args.sl if taken else None, actual_tp=args.tp if taken else None,
            deviation_note=args.note if taken else None, skip_reason=args.reason,
            note=None if taken else args.note)
        print(json.dumps(record_decision(args.journal, ticket, decision), indent=2, default=str))
        return 0
    except DecisionError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
