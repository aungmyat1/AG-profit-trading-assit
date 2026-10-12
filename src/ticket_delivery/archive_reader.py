"""Read-only access to the latest archived cycle decision (ticket_delivery.archive layout).

archive_cycle_decision() writes `fx_ticket_archive/{strategy}/{symbol}/{cycle}/{year}/{date}.json`
and, for changed content on the same day, append-only `{date}.correction-NNN.json` records whose
`new_record` holds the replacement. The latest record is the highest-numbered correction, else
the base file. A missing record is None -- never a guessed outcome.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Any, Dict, Optional

_CORRECTION = re.compile(r"^(\d{4}-\d{2}-\d{2})\.correction-(\d{3})\.json$")


def latest_cycle_decision(root: str, strategy_id: str, symbol: str, cycle: str,
                          trading_date: dt.date) -> Optional[Dict[str, Any]]:
    """The newest archived CycleDecisionRecord dict for one (strategy, symbol, cycle, date), or None.
    A corrupt or unreadable file raises (the caller's summary engine records that fail-closed)."""
    directory = os.path.join(root, "fx_ticket_archive", strategy_id, symbol, cycle, str(trading_date.year))
    day = trading_date.isoformat()
    corrections = []
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            match = _CORRECTION.match(name)
            if match and match.group(1) == day:
                corrections.append((int(match.group(2)), name))
    if corrections:
        with open(os.path.join(directory, max(corrections)[1]), encoding="utf-8") as stream:
            record = json.load(stream).get("new_record")
        if not isinstance(record, dict):
            raise ValueError("correction record without new_record")
        return record
    base = os.path.join(directory, f"{day}.json")
    if not os.path.exists(base):
        return None
    with open(base, encoding="utf-8") as stream:
        record = json.load(stream)
    if not isinstance(record, dict):
        raise ValueError("archived cycle decision is not an object")
    return record
