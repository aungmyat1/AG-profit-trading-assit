#!/usr/bin/env python3
"""Collect deterministic documentation facts from repository-local authorities."""
from __future__ import annotations

import argparse
import json
import re
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


def parse_host_schedule(script_text: str) -> dict[str, Any]:
    """Keep installer intent, captured registration, and runtime observation distinct."""
    lines = script_text.splitlines()
    trigger_line = next((line.strip() for line in lines
                         if "New-ScheduledTaskTrigger" in line and "$trigger" in line), None)
    repeat_line = next((line.strip() for line in lines if "New-ScheduledTaskTrigger -Once" in line), None)
    at_line = next((line.strip() for line in lines if "$at =" in line and "Offset" in line), None)
    daily_supported = trigger_line is not None and re.search(
        r"New-ScheduledTaskTrigger\s+-Daily\s+-At\s+\$at\b", trigger_line
    ) is not None
    interval_match = re.search(r"-RepetitionInterval\s+\(New-TimeSpan\s+-Minutes\s+\$t\.Minutes\)", repeat_line or "")
    duration_match = re.search(r"-RepetitionDuration\s+\(New-TimeSpan\s+-Hours\s+(\d+)\)", repeat_line or "")
    offset_supported = at_line is not None and re.search(r"'00:\{0:D2\}'\s+-f\s+\$t\.Offset", at_line)

    plan_start = script_text.find("$Plan = @(")
    plan_body = script_text[plan_start:].split("$Plan = @(", 1)[-1].split("\n)", 1)[0] if plan_start >= 0 else ""
    plan_lines = [line.strip() for line in plan_body.splitlines() if "@{" in line]
    tasks = []
    for line in plan_lines:
        name = re.search(r"Name\s*=\s*'([^']+)'", line)
        if not name or not name.group(1).startswith("AG-"):
            continue
        minute = re.search(r"Minutes\s*=\s*(\d+)\b", line)
        offset = re.search(r"Offset\s*=\s*(\d+)\b", line)
        cadence = (f"every {minute.group(1)} minutes, daily"
                   if minute and daily_supported and interval_match and duration_match
                   else "UNPARSED")
        if cadence != "UNPARSED":
            cadence += f" for {duration_match.group(1)} hours"
        start = (f"00:{int(offset.group(1)):02d}" if offset and offset_supported else "UNPARSED")
        trigger = "Daily trigger with a repeated interval" if daily_supported and interval_match and duration_match else "UNPARSED"
        tasks.append({
            "name": name.group(1),
            "cadence": {"value": cadence, "raw_line": (repeat_line or line) if cadence == "UNPARSED" else repeat_line},
            "start": {"value": start, "raw_line": line if start == "UNPARSED" else at_line},
            "trigger": {"value": trigger, "raw_line": trigger_line or line},
            # The Task Scheduler trigger omits a time-zone argument; do not infer host zone.
            "time_zone": {"value": "UNPARSED", "raw_line": trigger_line or line},
        })
    declared_start = script_text.find("$Declared = @(")
    declared_body = (script_text[declared_start:].split("$Declared = @(", 1)[-1]
                     .split("\n)", 1)[0] if declared_start >= 0 else "")
    registered = []
    for row in re.findall(r"@\{(.*?)(?=\n  @\{|\Z)", declared_body, flags=re.DOTALL):
        name = re.search(r"Name\s*=\s*'([^']+)'", row)
        managed = re.search(r"Managed\s*=\s*'([^']+)'", row)
        if not name or not managed:
            continue
        registered.append({
            "name": name.group(1),
            "management": managed.group(1),
            "trigger": (re.search(r"Trigger\s*=\s*'([^']+)'", row) or [None, "NOT_RECORDED"])[1],
            "drift": (re.search(r"Drift\s*=\s*'([^']+)'", row) or [None, "NONE_RECORDED"])[1],
        })
    capture_date = re.search(r"exported via[^\n]*\n#\s*(\d{4}-\d{2}-\d{2})", script_text)
    return {
        "source": "scripts/host/install_tasks.ps1",
        "repo_declared": tasks,
        "registered_snapshot": {
            "captured_at": capture_date.group(1) if capture_date else "DATE_UNPARSED",
            "tasks": registered,
        },
        "runtime_observation": {
            "status": "NOT_PUBLISHED",
            "source": "scripts/host/heartbeat.py output",
        },
        "power_policy": {
            "captured_task_names": [row["name"] for row in registered
                                    if row["name"].startswith(("AG-Wake-", "AG-Sleep-"))],
            "state": "REGISTRATION_SNAPSHOT_ONLY",
        },
        "target_policy": "NO_SEPARATE_TARGET_CAPTURED",
    }


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

    schedule = parse_host_schedule(recorder.read_text(root / "scripts" / "host" / "install_tasks.ps1"))

    objective = read_objective(root / "docs" / "PROJECT_OBJECTIVE.md", recorder)
    delivery_config = yaml.safe_load(recorder.read_text(root / "config" / "ticket_delivery.yaml")) or {}
    tracked_scope = delivery_config.get("immediate_send_scope") or {}
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
        "telegram_scope": {
            "immediate_send_enabled": tracked_scope.get("enabled", []),
            "informational_disabled": tracked_scope.get("disabled", {}),
        },
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
    out.write_text(content, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
