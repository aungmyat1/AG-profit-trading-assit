"""AG-EGSVF single canonical machine-readable lifecycle-stage authority
(AG_PROJECT_READINESS_POST_LARGE_SMC_PROMOTION_IMPLEMENTATION_V2, P0).

Before this module, each adapter (fx_adapter.py/btc_adapter.py/large_smc_adapter.py)
hardcoded its own `lifecycle_stage` Python literal -- functional, but an adapter
"owning" lifecycle state (rather than reading it) risks silent drift between adapters
and any future governance action, and gives lifecycle promotion no single, auditable
mutation point. `config/governance/strategy_lifecycle.yaml` is now that single source;
this module is its sole reader. Adapters call get_lifecycle_stage(strategy_id,
semantic_version, repo_root) and fail closed -- never silently default -- on any of:

- the registry file is missing or malformed
- the strategy has no entry at all
- the entry has no lifecycle_stage
- the recorded lifecycle_stage is not a valid LifecycleStage member
- the registry's recorded semantic_version does not exactly match the caller's own
  SEMANTIC_VERSION constant (a stale registry entry must never be silently used to
  evaluate a different strategy version's eligibility)

get_next_stage() derives the next adjacent lifecycle stage from the canonical
LIFECYCLE_ORDER tuple (models.py) -- adapters no longer separately hardcode
`next_transition` either, removing a second, redundant source of the same fact.

This module deliberately does NOT own or read proposal_generation_authorized/
demo_authorized/live_authorized -- those already have a canonical home
(strategies/registry.yaml, strategies/<ID>.yaml) and remain read from there unchanged.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

import yaml

from .models import LIFECYCLE_ORDER, LifecycleStage

DEFAULT_REGISTRY_PATH = os.path.join("config", "governance", "strategy_lifecycle.yaml")


class LifecycleRegistryError(Exception):
    """Fail-closed lifecycle-registry failure. Raised for a missing/malformed registry
    file, a missing strategy entry, an unknown/missing lifecycle_stage, or a
    semantic-version mismatch -- never silently resolved to a default stage."""


def _load_raw(repo_root: str, path: str) -> Dict:
    full_path = os.path.join(repo_root, path)
    if not os.path.isfile(full_path):
        raise LifecycleRegistryError(f"lifecycle registry not found at {path!r}")
    with open(full_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "strategies" not in data:
        raise LifecycleRegistryError(
            f"malformed lifecycle registry at {path!r}: missing top-level 'strategies' key"
        )
    return data


def get_lifecycle_stage(
    strategy_id: str,
    semantic_version: str,
    repo_root: str = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> LifecycleStage:
    """Returns the canonical current LifecycleStage for (strategy_id, semantic_version).
    Fail-closed: raises LifecycleRegistryError rather than ever returning a guessed or
    default stage."""
    data = _load_raw(repo_root, registry_path)
    strategies = data.get("strategies") or {}
    entry = strategies.get(strategy_id)
    if entry is None:
        raise LifecycleRegistryError(f"no lifecycle registry entry for {strategy_id!r}")

    recorded_version = entry.get("semantic_version")
    if recorded_version != semantic_version:
        raise LifecycleRegistryError(
            f"{strategy_id}: lifecycle registry semantic_version {recorded_version!r} does not "
            f"match caller's semantic_version {semantic_version!r} -- refusing to evaluate "
            "eligibility under a mismatched strategy version."
        )

    stage_name = entry.get("lifecycle_stage")
    if not stage_name:
        raise LifecycleRegistryError(f"{strategy_id}: lifecycle registry entry has no lifecycle_stage")
    try:
        return LifecycleStage(stage_name)
    except ValueError:
        raise LifecycleRegistryError(f"{strategy_id}: unknown lifecycle_stage {stage_name!r}")


def get_next_stage(current_stage: LifecycleStage) -> Optional[LifecycleStage]:
    """The next adjacent stage in the canonical LIFECYCLE_ORDER, or None if
    current_stage is already the terminal stage (LIVE_AUTHORIZED). Derived, not a
    second stored fact -- there is exactly one place (this function) that knows what
    "next" means for a given stage."""
    idx = LIFECYCLE_ORDER.index(current_stage)
    if idx + 1 >= len(LIFECYCLE_ORDER):
        return None
    return LIFECYCLE_ORDER[idx + 1]
