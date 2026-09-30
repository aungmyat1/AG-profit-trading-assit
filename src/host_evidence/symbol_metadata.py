"""Host-captured MT5 symbol metadata evidence (AG V1 host go-live kit). Pure: no broker, no network.

scripts/host/capture_symbol_metadata.py writes one JSON file per canonical symbol to
`config/symbol_metadata/host_captured/<SYMBOL>.json`. The file holds the exact broker
symbol name, the owner-listed symbol_info() fields, the server UTC offset, the capture
time, and the sha256 of the canonical payload. large_smc_watch.contract and v1_tickets.fx
read it through load_record(). A missing, malformed or hash-mismatched file is ignored,
which fails closed back to FIXTURE_ONLY.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

EVIDENCE_DIR = os.path.join("config", "symbol_metadata", "host_captured")
SCHEMA = "AG_HOST_SYMBOL_METADATA_V1"
FIELDS = (
    "digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size", "volume_min",
    "volume_step", "volume_max", "trade_stops_level", "trade_freeze_level", "spread", "currency_profit",
)
HOST_CAPTURED = "HOST_CAPTURED"


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def build_record(canonical_symbol: str, broker_symbol: str, info: Dict[str, Any], server: str,
                 server_utc_offset_hours: Optional[int], captured_at_utc: str) -> Dict[str, Any]:
    missing = [f for f in FIELDS if info.get(f) is None]
    if missing:
        raise ValueError(f"symbol_info missing fields: {missing}")
    payload = {
        "schema": SCHEMA, "canonical_symbol": canonical_symbol, "broker_symbol": broker_symbol,
        "server": server, "server_utc_offset_hours": server_utc_offset_hours,
        "captured_at_utc": captured_at_utc, "fields": {f: info[f] for f in FIELDS},
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
        return (ok_hash and record.get("schema") == SCHEMA and all(fields.get(f) is not None for f in FIELDS)
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
