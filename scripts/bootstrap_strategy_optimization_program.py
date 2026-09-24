#!/usr/bin/env python3
"""Create the first frozen four-track inventory and blocked Task C registry entry.

Read-only inputs are canonical strategy/governance YAML and existing status files. This
bootstrap does not load trade datasets, run replay, compare candidates, or search params.
All outputs are create-once; an existing inventory/experiment ID is never overwritten.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from strategy_optimization.inventory import build_initial_inventory, write_inventory_once  # noqa: E402
from strategy_optimization.task_c import (  # noqa: E402
    TASK_C_BASELINE_SEARCH_REF,
    register_task_c_experiment,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--inventory-output",
        type=Path,
        default=Path("artifacts/optimization/inventory/AG_STRATEGY_OPTIMIZATION_FRAMEWORK_V1_INITIAL_FREEZE.json"),
    )
    parser.add_argument("--registry-root", type=Path, default=Path("artifacts/optimization"))
    parser.add_argument("--created-at-utc", default=None)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    inventory_path = args.inventory_output
    if not inventory_path.is_absolute():
        inventory_path = repo_root / inventory_path
    registry_root = args.registry_root
    if not registry_root.is_absolute():
        registry_root = repo_root / registry_root

    search_path = repo_root / TASK_C_BASELINE_SEARCH_REF
    if not search_path.is_file():
        parser.error(f"Task C provenance search report is missing: {search_path}")
    try:
        search_report = json.loads(search_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Task C provenance search report is invalid: {exc}")
    if search_report.get("conclusion", {}).get("exact_baseline_reproduced") is not False:
        parser.error("bootstrap requires an explicit NOT_REPRODUCED baseline-search conclusion")

    timestamp = args.created_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    inventory = build_initial_inventory(repo_root, generated_at_utc=timestamp)
    inventory_sha = write_inventory_once(inventory_path, inventory)
    manifest = register_task_c_experiment(
        repo_root,
        registry_root,
        actor="strategy-optimization-bootstrap",
        created_at_utc=timestamp,
    )
    print(f"inventory={inventory_path}")
    print(f"inventory_sha256={inventory_sha}")
    print(f"task_c_experiment={manifest.experiment_id}")
    print("task_c_state=BLOCKED_REPRODUCIBILITY")
    print("economic_claim=NOT_AVAILABLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
