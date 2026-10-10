"""Config-level READY authority switch (owner decision D6, 2026-10-07). Pure apart from one YAML read.

A READY produced by the frozen engine is downgraded to SHADOW_INFO_ONLY unless
config/v1_tickets/ready_authority.yaml says `ready: ON` for that strategy. Levels are kept for
audit and the engine decision is recorded in `suppressed_decision`; nothing about strategy logic,
levels or thresholds changes. Fail closed: a missing or unreadable file, a missing entry, or any
value other than the literal ON means OFF.

Owner-record binding: with D6 ON, a READY is still downgraded unless the owner decision register
contains an approved, exact-version, exact-contract-hash record whose symbol and session scopes
include the ticket. The YAML record block is delimited by READY_AUTHORITY_RECORDS markers.

Per-symbol verification (owner mission 2026-10-10): with D6 ON and the owner record matched, a READY
is still downgraded unless the ticket's symbol is listed VERIFIED for the emitting strategy version. Authority:
strategies/registry.yaml -> strategies.<id>.candidate_versions."<version>".logic_verified_symbols (entries
`{symbol, evidence}`, optionally scoped by `sessions` / `engine_setups` per OD1011-SCOPE; logic verification
only, not economic/edge evidence). Absent version, list, symbol, evidence ref, or a ticket outside the entry's
scope means not verified (fail closed). D6 OFF behaviour is unchanged.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(_ROOT, "config", "v1_tickets", "ready_authority.yaml")
REGISTRY_PATH = os.path.join(_ROOT, "strategies", "registry.yaml")
OWNER_DECISION_REGISTER_PATH = os.path.join(_ROOT, "docs", "governance", "OWNER_DECISION_REGISTER.md")
SHADOW_INFO_ONLY = "SHADOW_INFO_ONLY"
READY_AUTHORITY_OFF = "READY_AUTHORITY_OFF_D6"
READY_AUTHORITY_UNREADABLE = "READY_AUTHORITY_CONFIG_UNREADABLE"
READY_SYMBOL_NOT_VERIFIED = "READY_SYMBOL_NOT_VERIFIED"
SHADOW_LABEL = "SHADOW / INFO ONLY -- READY AUTHORITY OFF (D6) -- NOT ACTIONABLE -- NOT A BROKER ORDER"
SYMBOL_UNVERIFIED_LABEL = ("SHADOW / INFO ONLY -- SYMBOL NOT VERIFIED FOR THIS STRATEGY VERSION -- NOT ACTIONABLE "
                           "-- NOT A BROKER ORDER")
OWNER_DECISION_RECORD_MISSING = "OWNER_DECISION_RECORD_MISSING"
OWNER_DECISION_RECORD_INVALID = "OWNER_DECISION_RECORD_INVALID"
OWNER_DECISION_VERSION_MISMATCH = "OWNER_DECISION_VERSION_MISMATCH"
OWNER_DECISION_CONTRACT_MISMATCH = "OWNER_DECISION_CONTRACT_HASH_MISMATCH"
OWNER_DECISION_SYMBOL_OUT_OF_SCOPE = "OWNER_DECISION_SYMBOL_OUT_OF_SCOPE"
OWNER_DECISION_SESSION_OUT_OF_SCOPE = "OWNER_DECISION_SESSION_OUT_OF_SCOPE"

_RECORD_START = "<!-- READY_AUTHORITY_RECORDS_START -->"
_RECORD_END = "<!-- READY_AUTHORITY_RECORDS_END -->"


def _owner_records(register_path: str) -> list[dict]:
    """Read structured authorization records embedded in the owner decision register.

    Owners can add a YAML block between the READY_AUTHORITY_RECORDS markers. It must have a
    `ready_authority_records` list; each approved row binds decision_id, strategy_id, version,
    contract_sha256, symbol_scope, session_scope, and ISO date. No record is added here.
    """
    with open(register_path, encoding="utf-8") as f:
        source = f.read()
    if _RECORD_START not in source or _RECORD_END not in source:
        return []
    block = source.split(_RECORD_START, 1)[1].split(_RECORD_END, 1)[0]
    block = re.sub(r"\A\s*```(?:yaml)?\s*|\s*```\s*\Z", "", block, flags=re.IGNORECASE)
    parsed = yaml.safe_load(block) or {}
    rows = parsed.get("ready_authority_records", []) if isinstance(parsed, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("ready_authority_records must be a list of mappings")
    return rows


def _validate_record(record: dict) -> bool:
    required = ("decision_id", "strategy_id", "version", "contract_sha256")
    if any(not isinstance(record.get(key), str) or not record[key].strip() for key in required):
        return False
    if record.get("status") not in {"APPROVED", "CONFIRMED", "AUTHORIZED", "RATIFIED", "RESOLVED"}:
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", record["contract_sha256"]):
        return False
    if not isinstance(record.get("symbol_scope"), list) or not record["symbol_scope"]:
        return False
    if not isinstance(record.get("session_scope"), list) or not record["session_scope"]:
        return False
    record_date = record.get("date")
    try:
        if isinstance(record_date, str):
            date.fromisoformat(record_date)
        elif not isinstance(record_date, date):
            return False
    except ValueError:
        return False
    return all(isinstance(value, str) and value for value in (*record["symbol_scope"], *record["session_scope"]))


def ready_authority(strategy_id: str, path: Optional[str] = None, *, strategy_version: Any = None,
                    contract_sha256: Optional[str] = None, symbol: Any = None, session: Any = None,
                    owner_register_path: Optional[str] = None) -> Tuple[bool, str]:
    """READY is allowed only by config ON plus a matching, scoped owner-register record."""
    try:
        with open(path or CONFIG_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        entry = (raw.get("strategies") or {}).get(strategy_id)
    except (OSError, ValueError, AttributeError, yaml.YAMLError):
        return False, READY_AUTHORITY_UNREADABLE
    if not isinstance(entry, dict):
        return False, READY_AUTHORITY_OFF
    # YAML 1.1 parses bare ON/OFF as booleans; accept True or the string "ON" only.
    on = entry.get("ready") is True or str(entry.get("ready")).upper() == "ON"
    if not on:
        return False, str(entry.get("reason") or READY_AUTHORITY_OFF)
    if strategy_version is None or not contract_sha256 or not isinstance(symbol, str) or not isinstance(session, str):
        return False, OWNER_DECISION_RECORD_MISSING
    try:
        records = _owner_records(owner_register_path or OWNER_DECISION_REGISTER_PATH)
    except OSError:
        return False, OWNER_DECISION_RECORD_MISSING
    except (ValueError, yaml.YAMLError):
        return False, OWNER_DECISION_RECORD_INVALID
    scoped = [row for row in records if row.get("strategy_id") == strategy_id]
    if not scoped:
        return False, OWNER_DECISION_RECORD_MISSING
    for record in scoped:
        if not _validate_record(record):
            continue
        if record["version"] != str(strategy_version):
            continue
        if record["contract_sha256"] != contract_sha256:
            continue
        if symbol not in record["symbol_scope"]:
            continue
        if session not in record["session_scope"]:
            continue
        return True, "READY_AUTHORITY_ON_OWNER_RECORD"
    if any(_validate_record(row) and row["version"] == str(strategy_version) for row in scoped):
        if any(_validate_record(row) and row["version"] == str(strategy_version)
               and row["contract_sha256"] != contract_sha256 for row in scoped):
            return False, OWNER_DECISION_CONTRACT_MISMATCH
        if any(_validate_record(row) and row["version"] == str(strategy_version)
               and row["contract_sha256"] == contract_sha256 and symbol not in row["symbol_scope"]
               for row in scoped):
            return False, OWNER_DECISION_SYMBOL_OUT_OF_SCOPE
        if any(_validate_record(row) and row["version"] == str(strategy_version)
               and row["contract_sha256"] == contract_sha256 and symbol in row["symbol_scope"]
               and session not in row["session_scope"] for row in scoped):
            return False, OWNER_DECISION_SESSION_OUT_OF_SCOPE
    if any(not _validate_record(row) for row in scoped):
        return False, OWNER_DECISION_RECORD_INVALID
    return False, OWNER_DECISION_VERSION_MISMATCH


def _in_scope(entry: Dict[str, Any], key: str, value: Any) -> bool:
    """An unscoped entry (no `key`) covers every value; a scoped one must list `value` (malformed -> False)."""
    if key not in entry:
        return True
    scope = entry[key]
    return isinstance(scope, list) and isinstance(value, str) and value in scope


def symbol_verified(strategy_id: str, strategy_version: Any, symbol: Any,
                    registry_path: Optional[str] = None, *, cycle: Any = None, setup: Any = None) -> bool:
    """True only if strategies/registry.yaml lists `symbol` with a non-empty `evidence` ref in
    candidate_versions."<strategy_version>".logic_verified_symbols for `strategy_id`, and the entry's optional
    branch scope (`sessions`, `engine_setups`; OD1011-SCOPE) includes the ticket's cycle and setup.
    Anything else is False."""
    try:
        with open(registry_path or REGISTRY_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        entry = (raw.get("strategies") or {}).get(strategy_id) or {}
        version = (entry.get("candidate_versions") or {}).get(str(strategy_version)) or {}
        listed = version.get("logic_verified_symbols")
    except (OSError, ValueError, AttributeError, yaml.YAMLError):
        return False
    if not isinstance(listed, list) or not isinstance(symbol, str):
        return False
    return any(isinstance(e, dict) and e.get("symbol") == symbol and isinstance(e.get("evidence"), str)
               and e["evidence"].strip() and _in_scope(e, "sessions", cycle) and _in_scope(e, "engine_setups", setup)
               for e in listed)


def apply_ready_authority(ticket: Dict[str, Any], path: Optional[str] = None,
                          registry_path: Optional[str] = None, *, contract_path: Optional[str] = None,
                          owner_register_path: Optional[str] = None) -> Dict[str, Any]:
    """Keep READY only with D6 ON, an owner record bound to the loaded contract, and symbol evidence."""
    if ticket.get("decision") != "READY":
        return ticket
    try:
        contract_sha = hashlib.sha256(Path(contract_path).read_bytes()).hexdigest() if contract_path else None
    except OSError:
        contract_sha = None
    allowed, reason = ready_authority(str(ticket.get("strategy_id")), path,
                                     strategy_version=ticket.get("strategy_version"),
                                     contract_sha256=contract_sha, symbol=ticket.get("symbol"),
                                     session=ticket.get("cycle"), owner_register_path=owner_register_path)
    if not allowed:
        return {**ticket, "decision": SHADOW_INFO_ONLY, "suppressed_decision": "READY", "label": SHADOW_LABEL,
                "engine_reason_code": ticket.get("reason_code"), "reason_code": reason,
                "ready_authority": "OFF"}
    if symbol_verified(str(ticket.get("strategy_id")), ticket.get("strategy_version"), ticket.get("symbol"),
                       registry_path, cycle=ticket.get("cycle"), setup=ticket.get("setup")):
        return ticket
    return {**ticket, "decision": SHADOW_INFO_ONLY, "suppressed_decision": "READY", "label": SYMBOL_UNVERIFIED_LABEL,
            "engine_reason_code": ticket.get("reason_code"), "reason_code": READY_SYMBOL_NOT_VERIFIED,
            "ready_authority": "ON_SYMBOL_NOT_VERIFIED"}
