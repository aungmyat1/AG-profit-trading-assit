"""Config-level READY authority switch (owner decision D6, 2026-10-07). Pure apart from one YAML read.

A READY produced by the frozen engine is downgraded to SHADOW_INFO_ONLY unless
config/v1_tickets/ready_authority.yaml says `ready: ON` for that strategy. Levels are kept for
audit and the engine decision is recorded in `suppressed_decision`; nothing about strategy logic,
levels or thresholds changes. Fail closed: a missing or unreadable file, a missing entry, or any
value other than the literal ON means OFF.

Per-symbol verification (owner mission 2026-10-10): with D6 ON, a READY is still downgraded unless the
ticket's symbol is listed VERIFIED for the emitting strategy version. Authority:
strategies/registry.yaml -> strategies.<id>.candidate_versions."<version>".logic_verified_symbols (entries
`{symbol, evidence}`; logic verification only, not economic/edge evidence). Absent version, list, symbol or
evidence ref means not verified (fail closed). D6 OFF behaviour is unchanged.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(_ROOT, "config", "v1_tickets", "ready_authority.yaml")
REGISTRY_PATH = os.path.join(_ROOT, "strategies", "registry.yaml")
SHADOW_INFO_ONLY = "SHADOW_INFO_ONLY"
READY_AUTHORITY_OFF = "READY_AUTHORITY_OFF_D6"
READY_AUTHORITY_UNREADABLE = "READY_AUTHORITY_CONFIG_UNREADABLE"
READY_SYMBOL_NOT_VERIFIED = "READY_SYMBOL_NOT_VERIFIED"
SHADOW_LABEL = "SHADOW / INFO ONLY -- READY AUTHORITY OFF (D6) -- NOT ACTIONABLE -- NOT A BROKER ORDER"
SYMBOL_UNVERIFIED_LABEL = ("SHADOW / INFO ONLY -- SYMBOL NOT VERIFIED FOR THIS STRATEGY VERSION -- NOT ACTIONABLE "
                           "-- NOT A BROKER ORDER")


def ready_authority(strategy_id: str, path: Optional[str] = None) -> Tuple[bool, str]:
    """(READY allowed, reason). True only for an explicit `ready: ON`."""
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
    return (True, "READY_AUTHORITY_ON") if on else (False, str(entry.get("reason") or READY_AUTHORITY_OFF))


def symbol_verified(strategy_id: str, strategy_version: Any, symbol: Any,
                    registry_path: Optional[str] = None) -> bool:
    """True only if strategies/registry.yaml lists `symbol` with a non-empty `evidence` ref in
    candidate_versions."<strategy_version>".logic_verified_symbols for `strategy_id`. Anything else is False."""
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
               and e["evidence"].strip() for e in listed)


def apply_ready_authority(ticket: Dict[str, Any], path: Optional[str] = None,
                          registry_path: Optional[str] = None) -> Dict[str, Any]:
    """Keep decision READY only when D6 READY authority is ON AND the ticket's symbol is VERIFIED for the
    emitting strategy version; otherwise downgrade to SHADOW_INFO_ONLY. Non-READY tickets are unchanged."""
    if ticket.get("decision") != "READY":
        return ticket
    allowed, reason = ready_authority(str(ticket.get("strategy_id")), path)
    if not allowed:
        return {**ticket, "decision": SHADOW_INFO_ONLY, "suppressed_decision": "READY", "label": SHADOW_LABEL,
                "engine_reason_code": ticket.get("reason_code"), "reason_code": reason,
                "ready_authority": "OFF"}
    if symbol_verified(str(ticket.get("strategy_id")), ticket.get("strategy_version"), ticket.get("symbol"),
                       registry_path):
        return ticket
    return {**ticket, "decision": SHADOW_INFO_ONLY, "suppressed_decision": "READY", "label": SYMBOL_UNVERIFIED_LABEL,
            "engine_reason_code": ticket.get("reason_code"), "reason_code": READY_SYMBOL_NOT_VERIFIED,
            "ready_authority": "ON_SYMBOL_NOT_VERIFIED"}
