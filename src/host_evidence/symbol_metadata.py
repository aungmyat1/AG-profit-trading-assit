"""Host-captured MT5 symbol metadata evidence (AG V1 host go-live kit). Pure: no broker, no network.

scripts/host/capture_symbol_metadata.py writes one JSON file per canonical symbol to
`config/symbol_metadata/host_captured/<SYMBOL>.json`. The file holds the exact broker
symbol name, the owner-listed symbol_info() fields, the server UTC offset rule and its
value at capture time, the capture time, and the sha256 of the canonical payload.
large_smc_watch.contract and v1_tickets.fx read it through load_record(). A missing,
malformed or hash-mismatched file is ignored, which fails closed back to FIXTURE_ONLY.

Server time (owner-stated VT Markets convention, 2026-09-30): server midnight = New York
17:00, i.e. server wall clock = America/New_York wall clock + 7h. That is UTC+3 during US
DST and UTC+2 otherwise. The offset is derived from this rule, never detected from a
symbol's weekly reopen bar (which misreads XAUUSD's later reopen as +4 and a late first
USDJPY bar as ambiguous).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

EVIDENCE_DIR = os.path.join("config", "symbol_metadata", "host_captured")
SCHEMA = "AG_HOST_SYMBOL_METADATA_V2"
_ACCEPTED_SCHEMAS = ("AG_HOST_SYMBOL_METADATA_V1", SCHEMA)
NY = ZoneInfo("America/New_York")
SERVER_MINUS_NY_HOURS = 7
OFFSET_RULE = "SERVER_MIDNIGHT_EQUALS_NEW_YORK_1700: server_utc_offset_hours = America/New_York UTC offset + 7"
FIELDS = (
    "digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size", "volume_min",
    "volume_step", "volume_max", "trade_stops_level", "trade_freeze_level", "spread", "currency_profit",
)
HOST_CAPTURED = "HOST_CAPTURED"


def server_utc_offset_hours(at_utc: dt.datetime) -> int:
    """Broker server UTC offset at `at_utc` under OFFSET_RULE: 3 during US DST, else 2."""
    ny = at_utc.astimezone(NY).utcoffset()
    return int(ny.total_seconds() // 3600) + SERVER_MINUS_NY_HOURS


def server_time_to_utc(server_wall_clock: dt.datetime) -> dt.datetime:
    """Naive broker-server wall-clock reading -> aware UTC, under OFFSET_RULE."""
    ny_wall = server_wall_clock.replace(tzinfo=None) - dt.timedelta(hours=SERVER_MINUS_NY_HOURS)
    return ny_wall.replace(tzinfo=NY).astimezone(dt.timezone.utc)


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def build_record(canonical_symbol: str, broker_symbol: str, info: Dict[str, Any], server: str,
                 server_utc_offset_hours: Optional[int], captured_at_utc: str,
                 trade_mode: Optional[str] = None) -> Dict[str, Any]:
    missing = [f for f in FIELDS if info.get(f) is None]
    if missing:
        raise ValueError(f"symbol_info missing fields: {missing}")
    payload = {
        "schema": SCHEMA, "canonical_symbol": canonical_symbol, "broker_symbol": broker_symbol,
        "server": server, "server_utc_offset_hours": server_utc_offset_hours,
        "server_utc_offset_rule": OFFSET_RULE, "trade_mode": trade_mode, "captured_at_utc": captured_at_utc, "fields": {f: info[f] for f in FIELDS},
        "source": "MetaTrader5.symbol_info (read-only)",
    }
    return {**payload, "sha256": hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()}


def evidence_path(canonical_symbol: str, root: str = ".") -> str:
    return os.path.join(root, EVIDENCE_DIR, f"{canonical_symbol}.json")


def write_record(record: Dict[str, Any], root: str = ".") -> str:
    path = evidence_path(record["canonical_symbol"], root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True, default=str)
    os.replace(tmp, path)
    return path


def verify(record: Dict[str, Any]) -> bool:
    try:
        payload = {k: v for k, v in record.items() if k != "sha256"}
        ok_hash = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest() == record.get("sha256")
        fields = record.get("fields") or {}
        return (ok_hash and record.get("schema") in _ACCEPTED_SCHEMAS and all(fields.get(f) is not None for f in FIELDS)
                and float(fields["point"]) > 0 and int(fields["digits"]) >= 0)
    except (TypeError, ValueError, KeyError):
        return False


def load_record(canonical_symbol: str, root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    root = root if root is not None else os.environ.get("AG_EVIDENCE_ROOT", ".")
    path = evidence_path(canonical_symbol, root)
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    if record.get("canonical_symbol") != canonical_symbol or not verify(record):
        return None
    return record
