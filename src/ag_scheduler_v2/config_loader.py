"""Loads and validates config/ag_scheduler_v2.yaml. Fails closed (SchedulerConfigConflict)
on anything malformed or reinterpreted, matching session_clock.py's SessionContractConflict
convention -- a corrupted config must never silently fall back to a plausible-looking
guess.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

CONTRACT_VERSION = "AG_DAILY_OPPORTUNITY_SCHEDULER_V2"
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "ag_scheduler_v2.yaml"


class SchedulerConfigConflict(ValueError):
    """Raised when config/ag_scheduler_v2.yaml is missing, malformed, or reinterpreted."""


@lru_cache(maxsize=1)
def _raw_config(path: Optional[str] = None) -> dict:
    p = Path(path) if path else _CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except OSError as exc:
        raise SchedulerConfigConflict(f"SCHEDULER_CONFIG_CONFLICT: cannot read {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SchedulerConfigConflict("SCHEDULER_CONFIG_CONFLICT: ag_scheduler_v2.yaml did not parse to a mapping")
    if raw.get("version") != CONTRACT_VERSION:
        raise SchedulerConfigConflict(
            f"SCHEDULER_CONFIG_CONFLICT: expected version {CONTRACT_VERSION!r}, got {raw.get('version')!r}"
        )
    if raw.get("timezone") != "UTC":
        raise SchedulerConfigConflict("SCHEDULER_CONFIG_CONFLICT: scheduler authority timezone must be UTC")
    return raw


def load_config(path: Optional[str] = None) -> dict:
    return _raw_config(path)


def config_hash(path: Optional[str] = None) -> str:
    """Deterministic hash of the raw config file bytes, for evidence attribution
    (spec section 37: config_hash on every scheduler-generated evidence record)."""
    p = Path(path) if path else _CONFIG_PATH
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return f"sha256:{digest[:16]}"


@dataclass(frozen=True)
class StandbyPolicy:
    allow_p1_research: bool


def load_standby_policy(path: Optional[str] = None) -> StandbyPolicy:
    raw = load_config(path)
    standby = raw.get("standby") or {}
    if "allow_p1_research" not in standby:
        raise SchedulerConfigConflict("SCHEDULER_CONFIG_CONFLICT: standby.allow_p1_research is required")
    return StandbyPolicy(allow_p1_research=bool(standby["allow_p1_research"]))
