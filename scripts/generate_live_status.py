#!/usr/bin/env python3
"""Generate the deterministic project live-status authority summary."""
from __future__ import annotations

import argparse
import json
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
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


class InputRecorder:
    """Verify on read and retain the exact bytes used, independently of path prefixes."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.tracked = tracked_paths(self.root)
        self.inputs: dict[str, bytes] = {}

    def read_text(self, path: Path) -> str:
        try:
            relative = path.resolve().relative_to(self.root).as_posix()
        except ValueError as exc:
            raise RuntimeError(f"collector input escapes repository: {path}") from exc
        if relative not in self.tracked:
            raise RuntimeError(f"collector input is not tracked: {relative}")
        if relative not in self.inputs:
            self.inputs[relative] = path.read_bytes()
        return self.inputs[relative].decode("utf-8")

    def digest(self) -> str:
        digest = hashlib.sha256()
        for relative, data in sorted(self.inputs.items()):
            digest.update(relative.encode("utf-8") + b"\0")
            digest.update(str(len(data)).encode("ascii") + b"\0" + data)
        return digest.hexdigest()


def collector_input_paths(root: Path) -> list[str]:
    from scripts.docs.collect_facts import collect
    return collect(root)["input_paths"]


def inputs_sha256(root: Path) -> str:
    """Hash sorted UTF-8 paths + NUL + byte length + NUL + exact file bytes.

    Length framing prevents ambiguous boundaries; paths are repository-relative.
    """
    from scripts.docs.collect_facts import collect
    return collect(root)["inputs_sha256"]


def _version_for(root: Path, source: Any, recorder: InputRecorder) -> str | None:
    if not isinstance(source, str) or not source.lower().endswith((".yaml", ".yml")):
        return None
    path = (root / source).resolve()
    content = yaml.safe_load(recorder.read_text(path)) or {}
    value = content.get("version") if isinstance(content, dict) else None
    return None if value is None else str(value)


def collect_live_status_facts(root: Path, recorder: InputRecorder | None = None) -> dict[str, Any]:
    """Return fields shared by PROJECT_LIVE_STATUS and status/facts.json."""
    standalone = recorder is None
    recorder = recorder or InputRecorder(root)
    registry = yaml.safe_load(recorder.read_text(root / "strategies" / "registry.yaml")) or {}
    strategies = []
    for strategy_id, item in sorted((registry.get("strategies") or {}).items()):
        demo = item.get("demo_authorized")
        live = item.get("live_authorized")
        strategies.append({
            "id": strategy_id,
            "version": _version_for(root, item.get("config_source"), recorder),
            "demo_authorized": demo if isinstance(demo, bool) else None,
            "live_authorized": live if isinstance(live, bool) else None,
        })
    return {
        "schema": "AG_PROJECT_LIVE_STATUS_V4",
        "inputs_sha256": inputs_sha256(root) if standalone else recorder.digest(),
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
