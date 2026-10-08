#!/usr/bin/env python3
"""Generate the deterministic project live-status authority summary."""
from __future__ import annotations

import argparse
import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "status" / "PROJECT_LIVE_STATUS.md"


def tracked_paths(root: Path, *patterns: str) -> set[str]:
    """Return tracked paths only; an unavailable Git index is an explicit error."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "-z", "--", *patterns],
            cwd=root, check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"cannot enumerate tracked collector inputs: {exc}") from exc
    try:
        return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}
    except UnicodeDecodeError as exc:
        raise RuntimeError("tracked collector input path is not valid UTF-8") from exc


def collector_input_paths(root: Path) -> list[str]:
    """Sorted tracked authorities, including sidecars and strategy config sources."""
    tracked = tracked_paths(root, "docs", "config", "strategies", "scripts/docs/advisory_allowlist.json")
    paths = {"strategies/registry.yaml", "docs/PROJECT_OBJECTIVE.md",
             "config/ag_scheduler_v2.yaml", "scripts/docs/advisory_allowlist.json"}
    for required in paths:
        if required not in tracked:
            raise RuntimeError(f"required collector input is not tracked: {required}")
    registry = yaml.safe_load((root / "strategies/registry.yaml").read_text(encoding="utf-8")) or {}
    for row in (registry.get("strategies") or {}).values():
        source = row.get("config_source")
        if isinstance(source, str) and source.lower().endswith((".yaml", ".yml")):
            path = (root / source).resolve()
            path.relative_to(root.resolve())
            relative = path.relative_to(root.resolve()).as_posix()
            if relative not in tracked:
                raise RuntimeError(f"collector input is not tracked: {relative}")
            paths.add(relative)
    paths.update(path for path in tracked
                 if path.startswith(("docs/", "config/"))
                 and path.endswith(".supersession.yaml"))
    return sorted(paths)


def inputs_sha256(root: Path) -> str:
    """Hash sorted UTF-8 paths + NUL + byte length + NUL + exact file bytes.

    Length framing prevents ambiguous boundaries; paths are repository-relative.
    """
    digest = hashlib.sha256()
    for relative in collector_input_paths(root):
        data = (root / relative).read_bytes()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(str(len(data)).encode("ascii") + b"\0" + data)
    return digest.hexdigest()


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


def collect_live_status_facts(root: Path) -> dict[str, Any]:
    """Return fields shared by PROJECT_LIVE_STATUS and status/facts.json."""
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
        "schema": "AG_PROJECT_LIVE_STATUS_V4",
        "inputs_sha256": inputs_sha256(root),
        "strategies": strategies,
    }


def render_markdown(facts: dict[str, Any]) -> str:
    lines = [
        "<!-- GENERATED FILE — DO NOT MANUALLY EDIT. Regenerate with scripts/generate_live_status.py -->",
        "# Project Live Status",
        "",
        f"Schema: `{facts['schema']}`",
        f"inputs_sha256: `{facts['inputs_sha256']}`",
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
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    facts = collect_live_status_facts(REPO_ROOT)
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
