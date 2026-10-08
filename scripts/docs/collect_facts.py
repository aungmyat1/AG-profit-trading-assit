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

from scripts.generate_live_status import InputRecorder, collect_live_status_facts, tracked_paths  # noqa: E402


def read_objective(path: Path, recorder: InputRecorder | None = None) -> dict[str, str]:
    text = recorder.read_text(path) if recorder else path.read_text(encoding="utf-8")
    marker = "## Objective\n"
    if marker not in text:
        raise ValueError(f"{path}: missing ## Objective section")
    body = text.split(marker, 1)[1].split("\n## ", 1)[0].strip()
    return {"source": "docs/PROJECT_OBJECTIVE.md#objective", "text": body}


def collect(root: Path) -> dict[str, Any]:
    recorder = InputRecorder(root)
    shared = collect_live_status_facts(root, recorder)
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

    schedule_config = yaml.safe_load(recorder.read_text(root / "config" / "ag_scheduler_v2.yaml")) or {}
    schedule = {
        "scheduler": schedule_config.get("version"),
        "timezone": schedule_config.get("timezone"),
        "tasks": [
            {"name": row.get("state"), "cadence": "daily", "start": row.get("start"), "end": row.get("end")}
            for row in schedule_config.get("schedule", [])
        ],
    }

    objective = read_objective(root / "docs" / "PROJECT_OBJECTIVE.md", recorder)
    # These policy authorities are read by the docs gate; keep their freshness covered too.
    json.loads(recorder.read_text(root / "scripts/docs/advisory_allowlist.json"))
    for relative in sorted(recorder.tracked):
        if relative.startswith(("docs/", "config/")) and relative.endswith(".supersession.yaml"):
            yaml.safe_load(recorder.read_text(root / relative))
    decisions_source = "docs/governance/OWNER_DECISION_REGISTER.md"
    sources, pending = [], None
    if (root / decisions_source).exists():
        text = recorder.read_text(root / decisions_source)
        sources.append(decisions_source)
        pending = sum(1 for line in text.splitlines() if line.lstrip().startswith("|")
                      and "PENDING_OWNER" in [cell.strip() for cell in line.strip().strip("|").split("|")])
    invariants = root / "docs/agents/INVARIANTS.md"
    if invariants.exists():
        recorder.read_text(invariants)
    return {
        "schema": "AG_DOC_FACTS_V3",
        "inputs_sha256": recorder.digest(),
        "input_paths": sorted(recorder.inputs),
        "pack_context": {"pending_decisions": pending, "decision_sources": sources,
                         "invariants_present": invariants.exists()},
        "objective": objective,
        "strategies": strategies,
        "schedule": schedule,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    out = args.output or (root / "status" / "facts.json")
    facts = collect(root)
    content = json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        fresh = out.is_file() and out.read_text(encoding="utf-8") == content
        print("FACTS_FRESH" if fresh else "FACTS_STALE")
        return 0 if fresh else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
