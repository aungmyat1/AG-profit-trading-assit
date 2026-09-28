"""AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2: resolves the governance/lifecycle
fields new to CanonicalProposal (economic_edge_established, demo_eligible,
demo_authorized, live_authorized, lifecycle_stage) from the repository's existing,
already-authoritative sources -- never a second, competing authority.

- lifecycle_stage: read via validation_framework.lifecycle_registry.get_lifecycle_stage(),
  the sole reader of config/governance/strategy_lifecycle.yaml (fail-closed on a missing/
  mismatched entry -- this module does not catch that error, callers decide how to
  degrade).
- demo_authorized/live_authorized: read from strategies/registry.yaml (this repo's own
  canonical home for those two facts -- lifecycle_registry.py explicitly does not own
  them, see its own module docstring).
- demo_eligible: read from the strategy's own YAML (strategies/<ID>.yaml), defaulting to
  False if the field is absent.
- economic_edge_established: always False. No field/authority for this exists anywhere
  in the repository (checked: strategies/registry.yaml, every strategies/<ID>.yaml,
  config/governance/strategy_lifecycle.yaml) -- inventing promotion criteria here would
  be a registry-authorization promotion, which is explicitly out of scope.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import yaml

from validation_framework.lifecycle_registry import LifecycleRegistryError, get_lifecycle_stage

DEFAULT_REGISTRY_PATH = os.path.join("strategies", "registry.yaml")


@dataclass(frozen=True)
class StrategyAuthority:
    strategy_id: str
    semantic_version: str
    lifecycle_stage: Optional[str]
    demo_eligible: bool
    demo_authorized: bool
    live_authorized: bool
    economic_edge_established: bool = False
    proposal_only: bool = True
    execution_eligible: bool = False
    broker_mutation_blocked: bool = True


def _load_yaml(repo_root: str, path: str) -> dict:
    full_path = os.path.join(repo_root, path)
    if not os.path.isfile(full_path):
        return {}
    with open(full_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def resolve_strategy_authority(
    strategy_id: str,
    semantic_version: str,
    repo_root: str = ".",
    strategy_config_path: Optional[str] = None,
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> StrategyAuthority:
    """Read-only, additive resolution -- never mutates any authority file, never
    promotes a lifecycle stage or authorization. `strategy_config_path` defaults to
    strategies/<strategy_id>.yaml when omitted."""
    try:
        lifecycle_stage = get_lifecycle_stage(strategy_id, semantic_version, repo_root).value
    except LifecycleRegistryError:
        lifecycle_stage = None

    registry = _load_yaml(repo_root, registry_path)
    registry_entry = (registry.get("strategies") or {}).get(strategy_id) or {}
    demo_authorized = bool(registry_entry.get("demo_authorized", False))
    live_authorized = bool(registry_entry.get("live_authorized", False))

    if strategy_config_path is None:
        strategy_config_path = os.path.join("strategies", f"{strategy_id}.yaml")
    strategy_config = _load_yaml(repo_root, strategy_config_path)
    demo_eligible = bool(strategy_config.get("demo_eligible", False))
    authority_block = strategy_config.get("authority")
    if isinstance(authority_block, dict) and "demo_eligible" in authority_block:
        demo_eligible = bool(authority_block.get("demo_eligible", False))
    if isinstance(authority_block, dict):
        # Strategy's own authority block, when present (e.g. ST_LARGE_SMC_V1), narrows
        # (never widens) demo/live authorization -- both sources must agree to grant it.
        demo_authorized = demo_authorized and bool(authority_block.get("demo_authorized", False))
        live_authorized = live_authorized and bool(authority_block.get("live_authorized", False))

    return StrategyAuthority(
        strategy_id=strategy_id,
        semantic_version=semantic_version,
        lifecycle_stage=lifecycle_stage,
        demo_eligible=demo_eligible,
        demo_authorized=demo_authorized,
        live_authorized=live_authorized,
    )
