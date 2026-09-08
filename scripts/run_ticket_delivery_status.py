#!/usr/bin/env python
"""WP4.5 scheduler-facing status CLI for src/ticket_delivery/ (AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1).

Read-only. Exposes archive/ticket/claim/delivery state for a given logical ticket, or
lists all delivery records currently on disk. This script does NOT run a strategy
cycle, does NOT archive or deliver anything itself, and has no execution/approval/
broker flag of any kind -- it is a diagnostic surface over the existing durable
delivery journal (src/ticket_delivery/delivery_store.py), the same convention as
scripts/test_dev_connection.py's read-only pattern.

Required environment variables for a real (not yet wired) delivery run would be
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (names only -- see
src/ticket_delivery/telegram_adapter.py; this script never reads or prints their
values, and does not itself construct a TelegramClient).

Usage:
    python scripts/run_ticket_delivery_status.py --state-dir journal/ticket_delivery [--ticket-id ID]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default="journal/ticket_delivery")
    parser.add_argument("--ticket-id", default=None, help="show one logical_ticket_id's record only")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from ticket_delivery.delivery_store import TicketDeliveryStore

    store = TicketDeliveryStore(state_dir=args.state_dir)

    if args.ticket_id:
        record = store.get(args.ticket_id)
        if record is None:
            _report(args, {"status": "NOT_FOUND", "logical_ticket_id": args.ticket_id})
            return 1
        _report(args, _redacted(record))
        return 0

    all_records = store._records.all()  # noqa: SLF001 -- read-only diagnostic, no public list-all method yet
    rows = [_redacted(_deserialize(v)) for v in all_records.values()]
    actionable_failures = [r for r in rows if r["state"] in ("DELIVERY_FAILED_TERMINAL", "DELIVERY_AMBIGUOUS")]
    _report(args, {"status": "OK", "count": len(rows), "records": rows})
    return 1 if actionable_failures else 0


def _deserialize(raw: dict):
    from ticket_delivery.delivery_store import _deserialize as _d
    return _d(raw)


def _redacted(record) -> dict:
    """No secret ever lives on a DeliveryRecord (bot token/chat id are never persisted
    there -- see telegram_adapter.py's redaction), so this is a plain field projection,
    not a real redaction step; named defensively in case a future field ever changes
    that."""
    return {
        "logical_ticket_id": record.logical_ticket_id,
        "delivery_attempt_id": record.delivery_attempt_id,
        "state": record.state,
        "attempt_number": record.attempt_number,
        "strategy_id": record.strategy_id,
        "strategy_version": record.strategy_version,
        "application_release": record.application_release,
        "symbol": record.symbol,
        "cycle": record.cycle,
        "trading_date": record.trading_date,
        "provider_response_id": record.provider_response_id,
        "retry_classification": record.retry_classification,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result))
        return
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main())
