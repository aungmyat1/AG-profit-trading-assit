#!/usr/bin/env python3
"""Advisory prose report using the blocking check's truth classification."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import yaml

from check_drift import ROOT, current_truth_contradictions


def _route_paths(context: dict) -> list[str]:
    paths: set[str] = set()
    for value in (context.get("authorities") or {}).values():
        if isinstance(value, str):
            paths.add(value)
    for route in (context.get("workstreams") or {}).values():
        if not isinstance(route, dict):
            continue
        for key in ("authority", "status"):
            if isinstance(route.get(key), str):
                paths.add(route[key])
        for key in ("read_first", "skills"):
            paths.update(value for value in route.get(key, []) if isinstance(value, str))
    return sorted(paths)


def missing_routes_at_snapshot(root: Path) -> list[str]:
    facts = json.loads((root / "status" / "facts.json").read_text(encoding="utf-8"))
    source_sha = facts["source_snapshot"]["sha"]
    context = json.loads((root / "config" / "agent_context.json").read_text(encoding="utf-8"))
    missing = []
    for route in _route_paths(context):
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{source_sha}:{route}"], cwd=root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode:
            missing.append(route)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    registry_path = args.registry or root / "strategies" / "registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    warnings = current_truth_contradictions(root, registry.get("strategies") or {})
    for warning in warnings:
        print(f"ADVISORY: {warning}")
    missing_routes = missing_routes_at_snapshot(root)
    for route in missing_routes:
        print(f"ADVISORY: config/agent_context.json route missing at source_snapshot: {route}")
    print(f"docs-drift advisory: {len(warnings)} prose warning(s), {len(missing_routes)} missing route(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
