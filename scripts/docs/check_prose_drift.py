#!/usr/bin/env python3
"""Advisory prose report using the blocking check's truth classification."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from check_drift import ROOT, current_truth_contradictions


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
    print(f"docs-drift advisory: {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
