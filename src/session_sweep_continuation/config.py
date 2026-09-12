"""Loads strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml and computes a deterministic
config_hash over its content. The hash is what canonical evidence records cite -- any
parameter change (EMA period, ATR multiplier, FVG thresholds, BOS sensitivity, TP R,
stop multiple, session times, ...) changes the hash, so evidence stays traceable to the
exact parameter set that produced it (spec requirement: FVG thresholds "included in
config hash").
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict

import yaml

DEFAULT_CONFIG_PATH = os.path.join("strategies", "ST_SESSION_SWEEP_CONTINUATION_V1.yaml")


class ConfigError(Exception):
    """Fail-closed config loading failure -- never silently defaulted."""


def load_config(repo_root: str = ".", path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    full_path = os.path.join(repo_root, path)
    if not os.path.isfile(full_path):
        raise ConfigError(f"strategy config not found at {path!r}")
    with open(full_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"malformed strategy config at {path!r}: expected a mapping")
    if data.get("strategy_id") != "ST_SESSION_SWEEP_CONTINUATION_V1":
        raise ConfigError("config strategy_id mismatch -- fail closed rather than silently proceed")
    return data


def compute_config_hash(config: Dict[str, Any]) -> str:
    """sha256 over a canonical (sorted-keys, no whitespace ambiguity) JSON
    serialization. Deterministic across runs and across platforms."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
