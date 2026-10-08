"""Config-level READY authority switch (owner decision D6, 2026-10-07). Pure apart from one YAML read.

A READY produced by the frozen engine is downgraded to SHADOW_INFO_ONLY unless
config/v1_tickets/ready_authority.yaml says `ready: ON` for that strategy. Levels are kept for
audit and the engine decision is recorded in `suppressed_decision`; nothing about strategy logic,
levels or thresholds changes. Fail closed: a missing or unreadable file, a missing entry, or any
value other than the literal ON means OFF.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "v1_tickets", "ready_authority.yaml")
SHADOW_INFO_ONLY = "SHADOW_INFO_ONLY"
READY_AUTHORITY_OFF = "READY_AUTHORITY_OFF_D6"
READY_AUTHORITY_UNREADABLE = "READY_AUTHORITY_CONFIG_UNREADABLE"
SHADOW_LABEL = "SHADOW / INFO ONLY -- READY AUTHORITY OFF (D6) -- NOT ACTIONABLE -- NOT A BROKER ORDER"


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


def apply_ready_authority(ticket: Dict[str, Any], path: Optional[str] = None) -> Dict[str, Any]:
    """Downgrade decision READY to SHADOW_INFO_ONLY when READY authority is OFF; else unchanged."""
    if ticket.get("decision") != "READY":
        return ticket
    allowed, reason = ready_authority(str(ticket.get("strategy_id")), path)
    if allowed:
        return ticket
    return {**ticket, "decision": SHADOW_INFO_ONLY, "suppressed_decision": "READY", "label": SHADOW_LABEL,
            "engine_reason_code": ticket.get("reason_code"), "reason_code": reason,
            "ready_authority": "OFF"}
