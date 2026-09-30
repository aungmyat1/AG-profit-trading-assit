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
# Overnight/rollover cost fields required for CFD venue cost modelling (e.g. VT Markets MT5 BTCUSD/ETHUSD).
# Not required in every record; _mt5_symbol_meta in v1_tickets.crypto refuses if absent for the MT5 venue.
SWAP_FIELDS = ("swap_long", "swap_short", "swap_rollover3days")
HOST_CAPTURED = "HOST_CAPTURED"
# Absolute repo root. Evidence is resolved from here (or an absolute AG_EVIDENCE_ROOT), never the CWD.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Specific host data failure reasons (audit 2): logged and stamped on tickets instead of a generic DATA_ERROR.
METADATA_MISSING = "METADATA_MISSING"
SWAP_FIELDS_MISSING = "SWAP_FIELDS_MISSING"
SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
INCOMPLETE_CANDLES = "INCOMPLETE_CANDLES"
CWD_LOOKUP = "CWD_LOOKUP"
CONVERSION_ERROR = "CONVERSION_ERROR"
DATA_REASON_CODES = (METADATA_MISSING, SWAP_FIELDS_MISSING, SYMBOL_NOT_FOUND, INCOMPLETE_CANDLES, CWD_LOOKUP,
                     CONVERSION_ERROR)


class HostDataError(RuntimeError):
    """A host data/metadata failure carrying one of DATA_REASON_CODES."""

    def __init__(self, code: str, detail: str = ""):
        if code not in DATA_REASON_CODES:
            raise ValueError(f"unknown host data reason code {code!r}")
        super().__init__(f"{code} {detail}".strip())
        self.code = code


def evidence_root() -> str:
    """AG_EVIDENCE_ROOT when set, else the repo root. A relative root would resolve against the
    CWD, so it is refused with CWD_LOOKUP."""
    root = os.environ.get("AG_EVIDENCE_ROOT") or REPO_ROOT
    if not os.path.isabs(root):
        raise HostDataError(CWD_LOOKUP, f"evidence root {root!r} is relative to the CWD")
    return root


def server_utc_offset_hours(at_utc: dt.datetime) -> int:
    """Broker server UTC offset at `at_utc` under OFFSET_RULE: 3 during US DST, else 2."""
    ny = at_utc.astimezone(NY).utcoffset()
    return int(ny.total_seconds() // 3600) + SERVER_MINUS_NY_HOURS


def measured_server_offset_hours(tick_time: float, now_ts: float, tolerance_s: float = 300.0) -> Optional[int]:
    """Whole-hour broker offset measured from a live tick (MT5 tick.time is server wall clock
    encoded as epoch seconds) minus host time.time(). None when the difference is not within
    `tolerance_s` of a whole hour (stale tick, closed market, skewed host clock)."""
    delta = float(tick_time) - float(now_ts)
    hours = round(delta / 3600.0)
    return int(hours) if abs(delta - hours * 3600.0) <= tolerance_s else None


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
    all_fields: Dict[str, Any] = {f: info[f] for f in FIELDS}
    # Include swap/rollover fields when available; absent = field not in record (not None).
    all_fields.update({f: info[f] for f in SWAP_FIELDS if info.get(f) is not None})
    payload = {
        "schema": SCHEMA, "canonical_symbol": canonical_symbol, "broker_symbol": broker_symbol,
        "server": server, "server_utc_offset_hours": server_utc_offset_hours,
        "server_utc_offset_rule": OFFSET_RULE, "trade_mode": trade_mode, "captured_at_utc": captured_at_utc, "fields": all_fields,
        "source": "MetaTrader5.symbol_info (read-only)",
    }
    return {**payload, "sha256": hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()}


def evidence_path(canonical_symbol: str, root: Optional[str] = None) -> str:
    return os.path.join(root if root is not None else evidence_root(), EVIDENCE_DIR, f"{canonical_symbol}.json")


def write_record(record: Dict[str, Any], root: Optional[str] = None) -> str:
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
    path = evidence_path(canonical_symbol, root)
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    if record.get("canonical_symbol") != canonical_symbol or not verify(record):
        return None
    return record
