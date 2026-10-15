"""Derive a VT day from committed metadata; no snapshot or execution wiring.

The date/offset is rule-derived, never evidence of an observed host clock.
Callers must keep BLOCKED results out of reconciled C14 risk snapshots.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from host_evidence.symbol_metadata import (
    OFFSET_RULE,
    SCHEMA,
    load_record,
    server_utc_offset_hours,
    utc_to_server_time,
)

REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class VTServerDay:
    status: str
    reason_code: str
    server_day: Optional[date] = None
    utc_offset_hours: Optional[int] = None
    captured_at_utc: Optional[str] = None


def derive_vt_server_day(now_utc: datetime, *, canonical_symbol: str,
                         metadata_root: Optional[Path] = None) -> VTServerDay:
    """Use the evidenced rule, refusing absent/invalid evidence without defaults.

    metadata_root is a repository/evidence root, not the host_captured directory.
    The default is the committed repository, independent of CWD/environment.
    Numeric captured offsets corroborate the capture instant only; future offsets
    come from the committed rule. DERIVED_NOT_OBSERVED never grants risk admission.
    """
    if (not isinstance(now_utc, datetime) or now_utc.tzinfo is None
            or now_utc.utcoffset() is None):
        return VTServerDay("BLOCKED", "VT_SERVER_DAY_TIME_INVALID")
    if not isinstance(canonical_symbol, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", canonical_symbol):
        return VTServerDay("BLOCKED", "VT_SERVER_DAY_METADATA_NOT_EVIDENCED")
    root = REPO if metadata_root is None else Path(metadata_root)
    if not root.is_absolute():
        return VTServerDay("BLOCKED", "VT_SERVER_DAY_METADATA_NOT_EVIDENCED")
    try:
        record = load_record(canonical_symbol, root=str(root))
    except (AttributeError, TypeError, ValueError):
        record = None
    if (record is None or record.get("schema") != SCHEMA
            or record.get("server") != "VTMarkets-Demo"):
        return VTServerDay("BLOCKED", "VT_SERVER_DAY_METADATA_NOT_EVIDENCED")
    if record.get("server_utc_offset_rule") != OFFSET_RULE:
        return VTServerDay("BLOCKED", "VT_SERVER_DAY_RULE_NOT_EVIDENCED")
    try:
        captured = datetime.fromisoformat(record["captured_at_utc"])
        if captured.tzinfo is None or captured.utcoffset() is None:
            raise ValueError("capture timestamp must be aware")
        offset = record["server_utc_offset_hours"]
        if type(offset) is not int or offset != server_utc_offset_hours(captured):
            raise ValueError("captured offset contradicts the rule")
        instant = now_utc.astimezone(timezone.utc)
        return VTServerDay(
            "DERIVED_NOT_OBSERVED", "VT_SERVER_DAY_DERIVED",
            utc_to_server_time(instant).date(), server_utc_offset_hours(instant),
            record["captured_at_utc"],
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return VTServerDay("BLOCKED", "VT_SERVER_DAY_METADATA_NOT_EVIDENCED")
