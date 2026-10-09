"""Ticket-only D2/D4 owner policy. Never changes the frozen CFD strategy contract.

Fail closed: missing, malformed, conflicting or wrongly-bound keys have no defaults.
The parser reports the existing missing-authority reason codes for ticket decisions.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from crypto_cfd_contract.contract import CONTRACT_ID, CONTRACT_VERSION
from v1_tickets.authority import REPO_ROOT

POLICY_PATH = "config/v1_tickets/crypto_cfd_ticket_policy.yaml"
SPREAD_UNDEFINED = "SPREAD_POLICY_UNDEFINED"
RISK_AMBIGUOUS = "RISK_POLICY_AMBIGUOUS"


def load_ticket_policy(path: Path | None = None) -> dict[str, Any]:
    path = path if path is not None else REPO_ROOT / POLICY_PATH
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raw = None
    raw = raw if isinstance(raw, dict) else {}

    def number(key: str) -> float | None:
        value = raw.get(key)
        if type(value) not in (int, float):
            return None
        try:
            value = float(value)
        except (ValueError, OverflowError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    ok, limit = number("spread_ok_pct"), number("spread_block_pct")
    risk, warn, block = number("risk_pct"), number("cost_warn_R"), number("cost_block_R")
    bound = raw.get("strategy_id") == CONTRACT_ID and str(raw.get("strategy_version")) == CONTRACT_VERSION
    if not bound or ok is None or limit is None or ok >= limit:
        ok = limit = None
    if not bound or risk is None or warn is None or block is None or risk > 100 or warn >= block:
        risk = warn = block = None
    reasons = []
    if ok is None:
        reasons.append(SPREAD_UNDEFINED)
    if risk is None:
        reasons.append(RISK_AMBIGUOUS)
    return {
        "spread_ok_pct": ok, "spread_block_pct": limit,
        "risk_pct": risk, "cost_warn_R": warn, "cost_block_R": block,
        "open_authorities": reasons,
    }
