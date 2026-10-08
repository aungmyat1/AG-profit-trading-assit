#!/usr/bin/env python3
"""Collect deterministic documentation facts from repository-local authorities."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

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


SCHEDULE_LAYER_MEANINGS = {
    # Four deliberately distinct layers. None of them may be collapsed into another: a declared
    # plan is not a registration, a registration is not an observed run, and a target is not a fact.
    "REPO_DECLARED": "what `install_tasks.ps1 -Apply` registers from $Plan (repository declaration)",
    "REGISTERED": "what Windows Task Scheduler actually held on the declaration capture date",
    "TARGET": "the proposed always-on end state, declared only; -Apply is not run by this collector",
    "OBSERVED": "runtime execution evidence; heartbeat.py output is not published, so this layer "
                "stays NOT_PUBLISHED rather than being inferred from the declaration",
}
OBSERVED_NOT_PUBLISHED = "NOT_PUBLISHED"


def _kv_comment(text: str, tag: str) -> dict[str, str]:
    """`# <tag>: K=V; K=V` -> {K: V}; empty when the tagged line is absent."""
    line = re.search(rf"^# {re.escape(tag)}: (.+)$", text, re.M)
    if not line:
        return {}
    out: dict[str, str] = {}
    for item in line.group(1).split(";"):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            out[key.strip()] = value.strip()
    return out


def _first(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _block(script_text: str, header: str) -> str:
    """Body of a `$Header = @( ... )` array literal (the text up to the closing `\n)`)."""
    start = script_text.find(header)
    if start < 0:
        return ""
    body = script_text[start:].split(header, 1)[-1]
    return body.split("\n)", 1)[0]


def _plan_tasks(script_text: str) -> list[dict[str, Any]]:
    """$Plan rows: the repository-declared install plan (never a registration fact)."""
    lines = script_text.splitlines()
    trigger_line = next((line.strip() for line in lines
                         if "New-ScheduledTaskTrigger" in line and "$trigger" in line), None)
    repeat_line = next((line.strip() for line in lines if "New-ScheduledTaskTrigger -Once" in line), None)
    at_line = next((line.strip() for line in lines if "$at = " in line), None)
    daily_supported = trigger_line is not None and re.search(
        r"New-ScheduledTaskTrigger\s+-Daily\s+-At\s+\$at\b", trigger_line) is not None
    interval_match = re.search(r"-RepetitionInterval\s+\(New-TimeSpan\s+-Minutes\s+\$t\.Minutes\)",
                               repeat_line or "")
    duration_match = re.search(r"-RepetitionDuration\s+\(New-TimeSpan\s+-Hours\s+(\d+)\)",
                               repeat_line or "")
    # The start time is a literal HH:MM:SS (SCHED-R1-B) or, historically, a minute Offset.
    literal_start = re.search(r"\$at\s*=\s*\$t\.StartAt\b", at_line or "")
    offset_start = re.search(r"'00:\{0:D2\}'\s*-f\s*\$t\.Offset", at_line or "")
    start_supported = literal_start is not None or offset_start is not None

    tasks: list[dict[str, Any]] = []
    for line in (line.strip() for line in _block(script_text, "$Plan = @(").splitlines()):
        if "@{" not in line:
            continue
        name = _first(r"Name\s*=\s*'([^']+)'", line)
        if not name or not name.startswith("AG-"):
            continue
        minute = _first(r"Minutes\s*=\s*(\d+)\b", line)
        literal = _first(r"StartAt\s*=\s*'(\d\d:\d\d:\d\d)'", line)
        offset = _first(r"Offset\s*=\s*(\d+)\b", line)
        cadence = (f"every {minute} minutes, daily"
                   if minute and daily_supported and interval_match and duration_match else "UNPARSED")
        if cadence != "UNPARSED":
            cadence += f" for {duration_match.group(1)} hours"      # type: ignore[union-attr]
        if literal and start_supported:
            start: Optional[str] = literal
        elif offset and offset_start:
            start = f"00:{int(offset):02d}"
        else:
            start = "UNPARSED"
        trigger = ("Daily trigger with a repeated interval"
                   if daily_supported and interval_match and duration_match else "UNPARSED")
        tasks.append({
            "name": name,
            "mode": _first(r"Mode\s*=\s*'(\w+)'", line),
            "minutes": int(minute) if minute else None,
            "canonical": _first(r"Canonical\s*=\s*\$(\w+)", line),
            "cadence": {"value": cadence, "raw_line": (repeat_line or line) if cadence == "UNPARSED" else repeat_line},
            "start": {"value": start, "raw_line": line if start == "UNPARSED" else at_line},
            "trigger": {"value": trigger, "raw_line": trigger_line or line},
            # The Task Scheduler trigger omits a time-zone argument; do not infer the host zone.
            "time_zone": {"value": "UNPARSED", "raw_line": trigger_line or line},
        })
    return tasks


def _declared_tasks(script_text: str) -> list[dict[str, Any]]:
    """$Declared rows: the sanitized host capture plus its declared always-on target."""
    rows: list[dict[str, Any]] = []
    for chunk in _block(script_text, "$Declared = @(").split("\n  @{")[1:]:
        # The Target literal spans lines and contains `{PLACEHOLDER}` braces, so its boundary is
        # found from the `Note = ` that always follows it rather than by brace matching.
        target_at = chunk.find("Target = @{")
        region = chunk[target_at:] if target_at >= 0 else ""
        note_at = region.find("Note = ")
        if note_at >= 0:
            region = region[:note_at]
        target: dict[str, str] = {}
        for key in ("State", "Exe", "Args", "Days", "Start", "EveryMin"):
            # EveryMin is an unquoted integer; the rest are single-quoted strings that may
            # themselves contain `{PLACEHOLDER}` braces, so they are matched as quoted values.
            value = (_first(r"\b" + key + r"\s*=\s*'([^']*)'", region)
                     if key != "EveryMin" else _first(r"\b" + key + r"\s*=\s*(\d+)", region))
            if value is not None and value != "":
                target[key] = value
        rows.append({
            "name": _first(r"\bName\s*=\s*'([^']+)'", chunk),
            "path": _first(r"\bPath\s*=\s*'([^']*)'", chunk),
            "managed": _first(r"\bManaged\s*=\s*'(\w+)'", chunk),
            "status": _first(r"\bStatus\s*=\s*'(\w+)'", chunk),
            "registered": _first(r"\bRegistered\s*=\s*'([^']*)'", chunk),
            "delete_after": _first(r"\bDeleteAfter\s*=\s*'([\d-]+)'", chunk),
            "note": _first(r"\bNote\s*=\s*'([^']*)'", chunk),
            "target": target,
        })
    return rows


def _registered_state(registered: Optional[str]) -> str:
    """ENABLED / DISABLED / ABSENT from the captured registration summary; UNPARSED when unclear."""
    if not registered:
        return "UNPARSED"
    if registered == "ABSENT":
        return "ABSENT"
    if registered.startswith("DISABLED"):
        return "DISABLED"
    return "ENABLED" if registered.startswith("ENABLED") else "UNPARSED"


def _declared_drift(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Registered-vs-target differences that the declaration itself makes comparable.

    Only fields the declaration states in machine-comparable form are compared; anything else is
    left as the verbatim `registered` string instead of being guessed at.
    """
    drift: list[dict[str, Any]] = []
    for row in rows:
        target = row.get("target") or {}
        registered = row.get("registered")
        registered_state = _registered_state(registered)
        if target.get("State") and target["State"] != registered_state:
            drift.append({"task": row["name"], "field": "state",
                          "registered": registered_state, "target": target["State"]})
        if registered_state in ("ABSENT", "UNPARSED") or not target.get("Days"):
            continue
        days = "DAILY" if "daily" in registered else ("Mon-Fri" if "Mon-Fri" in registered else "UNPARSED")
        if days != "UNPARSED" and days != target.get("Days"):
            drift.append({"task": row["name"], "field": "days", "registered": days,
                          "target": target.get("Days")})
        start = _first(r"(\d\d:\d\d)", registered)
        if start and target.get("Start") and start != target["Start"][:5]:
            drift.append({"task": row["name"], "field": "start", "registered": start,
                          "target": target["Start"]})
        every = _first(r"every (\d+) min", registered)
        if every and target.get("EveryMin") and int(every) != int(target["EveryMin"]):
            drift.append({"task": row["name"], "field": "every_min", "registered": int(every),
                          "target": int(target["EveryMin"])})
    return drift


def parse_host_schedule(script_text: str) -> dict[str, Any]:
    """Parse the installer's schedule declaration into four explicitly distinct layers.

    Nothing here reads the live host: the collector is offline and deterministic. The OBSERVED
    layer therefore stays NOT_PUBLISHED instead of being inferred from the declaration.
    """
    declared = _declared_tasks(script_text)
    plan = _plan_tasks(script_text)
    time_zone = _kv_comment(script_text, "AG-HOST-TIMEZONE")
    power = _kv_comment(script_text, "AG-HOST-POWER-POLICY")
    return {
        "source": "scripts/host/install_tasks.ps1",
        "captured": _first(r"on (\d{4}-\d{2}-\d{2})", script_text) or "UNPARSED",
        "host_time_zone": time_zone or {"value": "UNPARSED"},
        "host_power_policy": power or {"value": "UNPARSED"},
        "layers": {
            "REPO_DECLARED": {"meaning": SCHEDULE_LAYER_MEANINGS["REPO_DECLARED"], "tasks": plan},
            "REGISTERED": {"meaning": SCHEDULE_LAYER_MEANINGS["REGISTERED"],
                           "tasks": [{"name": r["name"], "path": r["path"], "managed": r["managed"],
                                      "status": r["status"], "registered": r["registered"],
                                      "delete_after": r["delete_after"]} for r in declared]},
            "TARGET": {"meaning": SCHEDULE_LAYER_MEANINGS["TARGET"],
                       "tasks": [{"name": r["name"], "target": r["target"], "note": r["note"]}
                                 for r in declared]},
            "OBSERVED": {"meaning": SCHEDULE_LAYER_MEANINGS["OBSERVED"], "value": OBSERVED_NOT_PUBLISHED,
                         "source": "scripts/host/heartbeat.py output (not yet published)"},
        },
        "drift": _declared_drift(declared),
        # Backward-compatible flat view of the repository-declared plan.
        "tasks": plan,
        "live_host_state": "scripts/host/heartbeat.py output (not yet published)",
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
