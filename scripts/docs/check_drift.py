#!/usr/bin/env python3
"""Blocking structured documentation checks against canonical local sources."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from collect_facts import read_objective, tracked_paths

ROOT = Path(__file__).resolve().parents[2]
DATE = re.compile(r"20\d\d-\d\d-\d\d")
AFFIRMATIVE_DEMO = re.compile(r"demo_authorized\s*[:=]\s*(?:`?true`?|yes)\b", re.I)
AUTHORITY_FIELDS = ("demo_authorized", "live_authorized", "manager_dispatchable")


def _frontmatter_class(text: str) -> str | None:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return None
    metadata = yaml.safe_load(text[4:].split("\n---\n", 1)[0]) or {}
    value = metadata.get("class")
    return str(value).lower() if value is not None else None


def _sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines)) for heading, lines in sections]


def _advisory_policy(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get("schema") == "AG_ADVISORY_SCAN_ALLOWLIST_V1" else None


def _range_contains(entry: dict[str, Any], rel: str, line: int) -> bool:
    bounds = entry.get("lines")
    return (
        entry.get("file") == rel
        and isinstance(bounds, list)
        and len(bounds) == 2
        and all(isinstance(value, int) for value in bounds)
        and bounds[0] <= line <= bounds[1]
    )


def _policy_suppresses(policy: dict[str, Any] | None, rel: str, line: int, text: str) -> bool:
    if not policy:
        return False
    if any(_range_contains(entry, rel, line) for entry in policy.get("never_suppress", [])):
        return False
    allowlisted = False
    for entry in [*policy.get("allowlisted_ranges", []), *policy.get("verified_label_free", [])]:
        if not _range_contains(entry, rel, line):
            continue
        carve_outs = [
            {**carve_out, "file": entry.get("file")}
            for carve_out in entry.get("carve_outs", [])
        ]
        if any(_range_contains(carve_out, rel, line) for carve_out in carve_outs):
            return False
        allowlisted = True
    for carve_out in policy.get("carve_outs", []):
        if _range_contains(carve_out, rel, line):
            return False
    if allowlisted:
        return True
    for note in policy.get("disambiguation_notes", []):
        token = note.get("token")
        related = note.get("related_lines", [])
        location_matches = _range_contains(note, rel, line) or (
            note.get("file") == rel and isinstance(related, list) and line in related
        )
        if location_matches and isinstance(token, str) and token.lower() in text.lower():
            return True
    return False


def _paragraphs(text: str):
    heading = ""
    start = 1
    buffer: list[str] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            if buffer:
                yield heading, start, "\n".join(buffer)
                buffer = []
            heading = line[3:].strip()
            start = line_number + 1
            continue
        if not line.strip():
            if buffer:
                yield heading, start, "\n".join(buffer)
                buffer = []
            start = line_number + 1
            continue
        if not buffer:
            start = line_number
        buffer.append(line)
    if buffer:
        yield heading, start, "\n".join(buffer)


def _historical_policy(path: Path) -> tuple[set[str], set[str]]:
    classes: set[str] = {"evidence"}
    dated_files: set[str] = set()
    if not path.is_file():
        return classes, dated_files
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("|", 2)
        if len(fields) != 3:
            raise ValueError(f"{path}:{number}: expected kind|selector|reason")
        kind, selector, _ = (field.strip() for field in fields)
        if kind == "class":
            classes.add(selector.lower())
        elif kind == "section" and selector.endswith("#dated-heading"):
            dated_files.add(selector.removesuffix("#dated-heading"))
        else:
            raise ValueError(f"{path}:{number}: unsupported allowlist rule")
    return classes, dated_files


def current_truth_contradictions(
    root: Path, registry_rows: dict[str, Any], allowlist_path: Path | None = None
) -> list[str]:
    """Find current-truth prose assertions; evidence docs and dated sections are historical."""
    false_ids = {key for key, row in registry_rows.items() if row.get("demo_authorized") is False}
    classes, dated_files = _historical_policy(
        allowlist_path or root / "scripts" / "docs" / "docs_drift_allowlist.txt"
    )
    advisory = _advisory_policy(root / "scripts" / "docs" / "advisory_allowlist.json")
    documents = [root / "README.md", root / "PROJECT_STATUS.md"]
    documents.extend(sorted((root / "docs").rglob("*.md")))
    failures: list[str] = []
    for path in documents:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _frontmatter_class(text) in classes:
            continue
        rel = str(path.relative_to(root))
        for heading, paragraph_start, paragraph in _paragraphs(text):
            if rel in dated_files and DATE.search(heading):
                continue
            for match in AFFIRMATIVE_DEMO.finditer(paragraph):
                line = paragraph_start + paragraph[:match.start()].count("\n")
                prefix = paragraph[:match.start()]
                positions = [(prefix.rfind(strategy_id), strategy_id) for strategy_id in registry_rows]
                position, strategy_id = max(positions, default=(-1, ""))
                if position >= 0 and strategy_id in false_ids:
                    if _policy_suppresses(advisory, rel, line, paragraph):
                        continue
                    excerpt = " ".join(paragraph.split())[:240]
                    failures.append(f"{rel}:{line} [{strategy_id}]: {excerpt}")
    return failures


def _machine_line(path: Path, strategy_id: str, field: str) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        if strategy_id in line and field in line:
            return number
    for number, line in enumerate(lines, 1):
        if strategy_id in line:
            return number
    return 1


def _machine_assertions(node: Any, registry_ids: set[str], inherited: str | None = None):
    if isinstance(node, dict):
        local = inherited
        for identity_key in ("strategy_id", "id"):
            candidate = node.get(identity_key)
            if isinstance(candidate, str) and candidate in registry_ids:
                local = candidate
                break
        if local:
            for field in AUTHORITY_FIELDS:
                if field in node:
                    yield local, field, node[field], f"strategies.{local}.{field}"
        for key, value in node.items():
            child_identity = key if key in registry_ids and isinstance(value, dict) else local
            yield from _machine_assertions(value, registry_ids, child_identity)
    elif isinstance(node, list):
        for value in node:
            yield from _machine_assertions(value, registry_ids, inherited)


def _sidecar_supersessions(path: Path, tracked: set[str], root: Path) -> set[str]:
    sidecar = path.with_suffix(".supersession.yaml")
    if sidecar.relative_to(root).as_posix() not in tracked or not sidecar.is_file():
        return set()
    try:
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    raw_paths = data.get("json_path")
    paths = {raw_paths} if isinstance(raw_paths, str) else set(raw_paths or [])
    if (
        data.get("target") != path.name
        or data.get("authority_source") != "strategies/registry.yaml"
        or not data.get("superseded_by")
        or not re.fullmatch(r"20\d\d-\d\d-\d\d", str(data.get("date", "")))
        or not all(isinstance(item, str) for item in paths)
    ):
        return set()
    return paths


def machine_authority_contradictions(root: Path, registry_rows: dict[str, Any]) -> list[str]:
    """Compare strategy authority in docs/config JSON/YAML with the canonical registry."""
    failures: list[str] = []
    paths = []
    tracked = tracked_paths(root, "docs", "config")
    for base in (root / "docs", root / "config"):
        for pattern in ("*.json", "*.yaml", "*.yml"):
            paths.extend(path for path in base.rglob(pattern)
                         if path.relative_to(root).as_posix() in tracked)
    for path in sorted(set(paths)):
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content) if path.suffix == ".json" else yaml.safe_load(content)
        except (OSError, json.JSONDecodeError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("superseded_by") and data.get("date"):
            continue
        superseded_paths = _sidecar_supersessions(path, tracked, root)
        seen: set[tuple[str, str, str]] = set()
        for strategy_id, field, actual, logical_path in _machine_assertions(data, set(registry_rows)):
            expected_field = "demo_authorized" if field == "manager_dispatchable" else field
            expected = registry_rows[strategy_id].get(expected_field, "<missing>")
            identity = (strategy_id, field, repr(actual))
            if actual == expected or identity in seen or logical_path in superseded_paths:
                continue
            seen.add(identity)
            line = _machine_line(path, strategy_id, field)
            failures.append(
                f"{path.relative_to(root)}:{line} [{strategy_id}].{field}={actual!r}; registry={expected!r}"
            )
    return failures


def check(root: Path, facts_path: Path, registry_path: Path, objective_path: Path) -> list[str]:
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    fact_rows = {row.get("id"): row for row in facts.get("strategies", [])}
    registry_rows = registry.get("strategies") or {}
    if set(fact_rows) != set(registry_rows):
        errors.append("strategy IDs differ between facts.json and registry.yaml")
    for strategy_id, registry_row in sorted(registry_rows.items()):
        fact_row = fact_rows.get(strategy_id)
        if fact_row is None:
            continue
        expected_demo = registry_row.get("demo_authorized")
        demo = fact_row.get("demo_authorized") or {}
        if demo.get("value") != expected_demo or demo.get("evidence_source") != "strategies/registry.yaml":
            errors.append(f"{strategy_id}: demo_authorized differs from registry authority")
        for field in ("logic_verified", "edge_verified"):
            assertion = fact_row.get(field) or {}
            evidence = assertion.get("evidence_source")
            if assertion.get("value") is not None and not evidence:
                errors.append(f"{strategy_id}: {field} has a value without dated evidence_source")
            if evidence:
                evidence_path = root / evidence
                if (not evidence.startswith("docs/status/") or not evidence_path.is_file()
                        or not re.search(r"20\d\d-\d\d-\d\d", evidence)):
                    errors.append(f"{strategy_id}: {field} evidence_source is not a dated docs/status file")
    if facts.get("objective") != read_objective(objective_path):
        errors.append("objective differs between facts.json and docs/PROJECT_OBJECTIVE.md")
    errors.extend(f"current-truth contradiction: {item}" for item in current_truth_contradictions(root, registry_rows))
    errors.extend(f"machine contradiction: {item}" for item in machine_authority_contradictions(root, registry_rows))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--objective", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    errors = check(
        root,
        args.facts or root / "status" / "facts.json",
        args.registry or root / "strategies" / "registry.yaml",
        args.objective or root / "docs" / "PROJECT_OBJECTIVE.md",
    )
    for error in errors:
        print(f"BLOCKING: {error}")
    print(f"docs-drift blocking: {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
