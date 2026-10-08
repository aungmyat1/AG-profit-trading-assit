#!/usr/bin/env python3
"""Collect deterministic documentation facts from repository-local authorities."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_live_status import collect_live_status_facts  # noqa: E402


def read_objective(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    marker = "## Objective\n"
    if marker not in text:
        raise ValueError(f"{path}: missing ## Objective section")
    body = text.split(marker, 1)[1].split("\n## ", 1)[0].strip()
    return {"source": "docs/PROJECT_OBJECTIVE.md#objective", "text": body}


def collect(root: Path, source_sha: str) -> dict[str, Any]:
    shared = collect_live_status_facts(root, source_sha)
    strategies: list[dict[str, Any]] = []
    for item in shared["strategies"]:
        strategies.append({
            "id": item["id"],
            "version": item["version"],
            "logic_verified": {"value": None, "evidence_source": None},
            "edge_verified": {"value": None, "evidence_source": None},
            "demo_authorized": {
                "value": item["demo_authorized"],
                "evidence_source": "strategies/registry.yaml",
            },
        })

    schedule_config = yaml.safe_load((root / "config" / "ag_scheduler_v2.yaml").read_text(encoding="utf-8")) or {}
    schedule = {
        "scheduler": schedule_config.get("version"),
        "timezone": schedule_config.get("timezone"),
        "tasks": [
            {"name": row.get("state"), "cadence": "daily", "start": row.get("start"), "end": row.get("end")}
            for row in schedule_config.get("schedule", [])
        ],
    }

    return {
        "schema": "AG_DOC_FACTS_V2",
        "source_snapshot": shared["source_snapshot"],
        "objective": read_objective(root / "docs" / "PROJECT_OBJECTIVE.md"),
        "strategies": strategies,
        "schedule": schedule,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--source-sha", required=True, help="explicit commit SHA represented by this snapshot")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    out = args.output or (root / "status" / "facts.json")
    facts = collect(root, args.source_sha)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
