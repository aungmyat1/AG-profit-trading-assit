"""Build write-once inventory snapshots for the four independent strategy tracks."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

from post_asian_pilot.fingerprint import fingerprint
from .admission import evaluate_repository_admission
from .track_adapters import STRATEGY_TRACK_ADAPTERS, build_track_snapshot


class InventoryError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_initial_inventory(
    repo_root: str | Path,
    *,
    generated_at_utc: Optional[str] = None,
) -> Mapping[str, Any]:
    """Snapshot governance identity/status only; never scans or loads trade datasets."""
    root = Path(repo_root)
    snapshots = [build_track_snapshot(root, adapter) for adapter in STRATEGY_TRACK_ADAPTERS]
    contract_path = root / "config/governance/optimization_admission_contract.yaml"
    try:
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InventoryError("canonical optimization admission contract is unavailable") from exc
    if not isinstance(contract, Mapping):
        raise InventoryError("canonical optimization admission contract is invalid")
    contract_identity = contract.get("identity", {})
    if not isinstance(contract_identity, Mapping):
        contract_identity = {}
    admission = evaluate_repository_admission(root, {})

    payload = {
        "schema_version": "AG_STRATEGY_OPTIMIZATION_FRAMEWORK_V1_INITIAL_INVENTORY",
        "generated_at_utc": generated_at_utc or _utc_now(),
        "authority_reuse": {
            "strategy_contracts": "strategies/<ID>.yaml (per-track; not mutated)",
            "execution_and_demo_authority": "strategies/registry.yaml (owner-only; not mutated)",
            "strategy_lifecycle": "config/governance/strategy_lifecycle.yaml plus validation_framework.lifecycle_registry (sole canonical lifecycle; not mutated)",
            "hypothesis_preregistration": "src/svos/hypothesis.py",
            "candidate_freeze": "src/svos/candidate.py",
            "bounded_optimization": "src/svos/optimization.py and src/svos/optimization_admission.py",
            "performance_metrics": "src/performance/calculator.py and src/performance/models.py",
            "content_fingerprints": "src/post_asian_pilot/fingerprint.py",
        },
        "optimization_admission": {
            "contract_ref": "config/governance/optimization_admission_contract.yaml",
            "contract_id": contract_identity.get("contract_id"),
            "contract_status": contract_identity.get("status", "NOT_DECLARED"),
            "current_evaluation_status": admission.status,
            "current_blockers": list(admission.blockers),
            "policy": "No search/replay/optimization is admitted by this inventory; unsigned contract fails closed.",
        },
        "dataset_roles": [
            "DEVELOPMENT", "DEVELOPMENT_REUSED", "REPLICATION", "OOS",
            "FINAL_HOLDOUT", "FORWARD_SHADOW",
        ],
        "dataset_role_invariants": {
            "only_optimizer_roles": ["DEVELOPMENT", "DEVELOPMENT_REUSED"],
            "protected_roles_cannot_be_downgraded": ["REPLICATION", "OOS", "FINAL_HOLDOUT", "FORWARD_SHADOW"],
            "roles_are_pinned_in_write_once_dataset_manifests": True,
            "access_is_journaled_before_reader_callback": True,
        },
        "candidate_state_machine": {
            "authority": "research experiment only; subordinate to canonical strategy lifecycle",
            "terminal_states_are_irreversible": True,
            "failure_returns_to_search": False,
            "failed_experiment_requires_new_experiment_id": True,
        },
        "strategy_tracks": snapshots,
        "inventory_builder_scope": {
            "strategy_configs_mutated_by_builder": False,
            "strategy_lifecycle_mutated_by_builder": False,
            "strategy_execution_authority_mutated_by_builder": False,
            "market_data_rows_consumed_by_builder": False,
            "market_data_replay_run_by_builder": False,
            "candidate_comparison_run_by_builder": False,
            "parameter_search_run_by_builder": False,
            "economic_claims_created_by_builder": False,
        },
    }
    return {**payload, "inventory_sha256": fingerprint(payload)}


def write_inventory_once(path: str | Path, inventory: Mapping[str, Any]) -> str:
    """Persist an inventory snapshot without replacing a prior freeze."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(inventory, sort_keys=True, indent=2, default=str) + "\n"
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise InventoryError(f"inventory snapshot is immutable: {destination}") from exc
    return str(inventory["inventory_sha256"])


__all__ = ["InventoryError", "build_initial_inventory", "write_inventory_once"]
