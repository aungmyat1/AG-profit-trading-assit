#!/usr/bin/env python3
"""Collect deterministic documentation facts from repository-local authorities."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "status" / "facts.json"


def git(*args: str, cwd: Path = REPO_ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def version_for(root: Path, source: Any) -> str | None:
    if not isinstance(source, str) or not source.lower().endswith((".yaml", ".yml")):
        return None
    path = (root / source).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    value = content.get("version") if isinstance(content, dict) else None
    return None if value is None else str(value)


def collect(root: Path, head_ref: str = "HEAD") -> dict[str, Any]:
    registry_path = root / "strategies" / "registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    entries = (registry.get("strategies") or {})
    strategies = []
    for strategy_id, item in sorted(entries.items()):
        authorized = item.get("demo_authorized")
        verdict = ("DEMO_AUTHORIZED" if authorized is True else
                   "NOT_DEMO_AUTHORIZED" if authorized is False else "UNSPECIFIED")
        strategies.append({
            "id": strategy_id,
            "version": version_for(root, item.get("config_source")),
            "demo_authorized": authorized if isinstance(authorized, bool) else None,
            "verdict": verdict,
        })

    schedule_path = root / "config" / "ag_scheduler_v2.yaml"
    schedule_config = yaml.safe_load(schedule_path.read_text(encoding="utf-8")) or {}
    schedule = {
        "scheduler": schedule_config.get("version"),
        "timezone": schedule_config.get("timezone"),
        "tasks": [
            {"name": row.get("state"), "cadence": "daily", "start": row.get("start"), "end": row.get("end")}
            for row in schedule_config.get("schedule", [])
        ],
    }

    head_sha = git("rev-parse", "--verify", f"{head_ref}^{{commit}}", cwd=root)
    head_date = git("show", "-s", "--format=%cI", head_sha, cwd=root)
    # GitHub status APIs are intentionally not queried. A local result file is accepted
    # when an offline build has supplied one; otherwise the fact is explicitly absent.
    ci_result = None
    for rel in ("status/last_ci_result.json", ".github/last_ci_result.json"):
        try:
            ci_result = json.loads((root / rel).read_text(encoding="utf-8"))
            break
        except (OSError, json.JSONDecodeError):
            continue

    return {
        "schema": "AG_DOC_FACTS_V1",
        "git": {"head_sha": head_sha, "head_date": head_date},
        "strategies": strategies,
        "schedule": schedule,
        "last_ci_result": ci_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--head-ref", default="HEAD", help="commit/ref whose SHA and date identify this facts snapshot")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    out = args.output or (root / "status" / "facts.json")
    facts = collect(root, args.head_ref)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
