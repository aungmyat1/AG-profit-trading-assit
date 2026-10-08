"""DOCS-LIVE-2-NEXT: CONTEXT_PACK.md is built from status/facts.json only and is reproducible."""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_context_pack", REPO / "scripts" / "docs" / "build_context_pack.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)
FACTS = json.loads((REPO / "status" / "facts.json").read_text(encoding="utf-8"))


def test_same_inputs_give_a_byte_identical_pack():
    assert pack.build(FACTS) == pack.build(json.loads(json.dumps(FACTS)))


def test_header_carries_inputs_sha256_and_no_stub_or_git_sha():
    out = pack.build(FACTS)
    assert f"inputs_sha256: `{FACTS['inputs_sha256']}`" in out
    assert "STUB_READER" not in out and "head_sha" not in out


def test_committed_pack_matches_a_fresh_build():
    assert (REPO / pack.OUT).read_text(encoding="utf-8") == pack.build(FACTS)


def test_pack_schedule_lists_host_tasks_and_excludes_v2_phase_names():
    from scripts.docs.collect_facts import collect, parse_host_schedule

    host_script = (REPO / "scripts/host/install_tasks.ps1").read_text(encoding="utf-8")
    expected = [task["name"] for task in parse_host_schedule(host_script)["tasks"]]
    assert "scripts/host/install_tasks.ps1" in collect(REPO)["input_paths"]
    schedule = pack.build(FACTS).split("## Schedule\n", 1)[1]
    # The four layers must stay distinguishable: a declaration, a registration, an observed run and
    # a target are different facts and must never be collapsed into one table.
    for layer in ("REPO_DECLARED", "REGISTERED", "TARGET", "OBSERVED"):
        assert f"### {layer}" in schedule, layer
    assert "Value: **NOT_PUBLISHED**" in schedule
    assert all(f"`{name}`" in schedule for name in expected)
    assert "5-minute cadence deferred until the crypto runner checks its active window before MT5 attach" in schedule
    import yaml
    config = yaml.safe_load((REPO / "config/ag_scheduler_v2.yaml").read_text(encoding="utf-8"))
    phase_names = [row.get("state") for row in config.get("schedule", [])]
    assert not any(name and f"`{name}`" in schedule for name in phase_names)


def test_unparsed_host_trigger_keeps_the_source_line():
    from scripts.docs.collect_facts import parse_host_schedule

    source = (REPO / "scripts/host/install_tasks.ps1").read_text(encoding="utf-8")
    malformed = source.replace(
        "$trigger = New-ScheduledTaskTrigger -Daily -At $at",
        "$trigger = New-ScheduledTaskTrigger -CalendarKind Weekly",
    )
    schedule = parse_host_schedule(malformed)
    assert len(schedule["tasks"]) == 3
    assert all(task["trigger"]["value"] == "UNPARSED" for task in schedule["tasks"])
    assert all(task["trigger"]["raw_line"] == "$trigger = New-ScheduledTaskTrigger -CalendarKind Weekly"
               for task in schedule["tasks"])
    assert schedule["layers"]["REPO_DECLARED"]["tasks"] == schedule["tasks"]


def test_open_decisions_counted_from_the_register_never_a_bare_zero(tmp_path):
    out = pack.build(FACTS)
    count, sources = pack.open_decisions()
    assert sources == list(pack.REGISTERED_DECISION_SOURCES) and count == 11
    assert "Open decisions in registered tables: 11 (sources: `docs/governance/OWNER_DECISION_REGISTER.md`)." in out
    # No registered table -> UNKNOWN, not 0.
    assert pack.open_decisions(str(tmp_path)) == (None, [])
    no_sources = {**FACTS, "pack_context": {"pending_decisions": None, "decision_sources": [],
                                          "invariants_present": False}}
    assert "Open decisions in registered tables: UNKNOWN" in pack.build(no_sources, root=str(tmp_path))


def test_missing_or_incomplete_facts_fail_closed(tmp_path):
    with pytest.raises(SystemExit, match="FACTS_UNAVAILABLE"):
        pack.load_facts(str(tmp_path / "absent.json"))
    bad = tmp_path / "facts.json"
    bad.write_text(json.dumps({k: v for k, v in FACTS.items() if k != "inputs_sha256"}))
    with pytest.raises(SystemExit, match="FACTS_INCOMPLETE"):
        pack.load_facts(str(bad))


def test_pack_render_reads_no_sources_outside_collected_facts(monkeypatch):
    import builtins

    def unexpected_read(*args, **kwargs):
        raise AssertionError("pack rendering opened a source outside the digest")

    monkeypatch.setattr(builtins, "open", unexpected_read)
    monkeypatch.setattr(Path, "read_text", unexpected_read)
    monkeypatch.setattr(Path, "read_bytes", unexpected_read)
    monkeypatch.setattr(pack.os.path, "exists", unexpected_read)
    assert f"inputs_sha256: `{FACTS['inputs_sha256']}`" in pack.build(FACTS)
