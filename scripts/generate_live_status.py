#!/usr/bin/env python3
"""Generate the deterministic project live-status authority summary."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "status" / "PROJECT_LIVE_STATUS.md"


def _git_date(root: Path, source_sha: str) -> str:
    return subprocess.check_output(
        ["git", "show", "-s", "--format=%cI", f"{source_sha}^{{commit}}"], cwd=root, text=True
    ).strip()


def _version_for(root: Path, source: Any) -> str | None:
    if not isinstance(source, str) or not source.lower().endswith((".yaml", ".yml")):
        return None
    path = (root / source).resolve()
    try:
        path.relative_to(root.resolve())
        content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (ValueError, OSError, yaml.YAMLError):
        return None
    value = content.get("version") if isinstance(content, dict) else None
    return None if value is None else str(value)


def collect_live_status_facts(root: Path, source_sha: str) -> dict[str, Any]:
    """Return fields shared by PROJECT_LIVE_STATUS and status/facts.json."""
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_sha):
        raise ValueError("--source-sha must be an explicit 40-character commit SHA")
    registry = yaml.safe_load((root / "strategies" / "registry.yaml").read_text(encoding="utf-8")) or {}
    strategies = []
    for strategy_id, item in sorted((registry.get("strategies") or {}).items()):
        demo = item.get("demo_authorized")
        live = item.get("live_authorized")
        strategies.append({
            "id": strategy_id,
            "version": _version_for(root, item.get("config_source")),
            "demo_authorized": demo if isinstance(demo, bool) else None,
            "live_authorized": live if isinstance(live, bool) else None,
        })
    return {
        "schema": "AG_PROJECT_LIVE_STATUS_V3",
        "source_snapshot": {"sha": source_sha, "date": _git_date(root, source_sha)},
        "strategies": strategies,
    }


def render_markdown(facts: dict[str, Any]) -> str:
    source = facts["source_snapshot"]
    lines = [
        "<!-- GENERATED FILE — DO NOT MANUALLY EDIT. Regenerate with scripts/generate_live_status.py -->",
        "# Project Live Status",
        "",
        f"Schema: `{facts['schema']}`",
        f"source_snapshot: `{source['sha']}` ({source['date']})",
        "",
        "## Strategy authority",
        "",
        "| strategy_id | version | demo_authorized | live_authorized |",
        "|---|---|---:|---:|",
    ]
    for row in facts["strategies"]:
        version = row["version"] or "unspecified"
        demo = "unknown" if row["demo_authorized"] is None else str(row["demo_authorized"]).lower()
        live = "unknown" if row["live_authorized"] is None else str(row["live_authorized"]).lower()
        lines.append(f"| `{row['id']}` | `{version}` | {demo} | {live} |")
    lines += [
        "",
        "Authority source: [`strategies/registry.yaml`](../../strategies/registry.yaml).",
        "Logic and economic-edge verification are intentionally outside this generated authority table.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    facts = collect_live_status_facts(REPO_ROOT, args.source_sha)
    if args.json:
        print(json.dumps(facts, indent=2, sort_keys=True))
        return 0
    rendered = render_markdown(facts)
    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != rendered:
            print(f"LIVE_STATUS_STALE: {OUTPUT_PATH}")
            return 1
        print(f"LIVE_STATUS_FRESH: {OUTPUT_PATH}")
        return 0
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"LIVE_STATUS_WRITTEN: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
