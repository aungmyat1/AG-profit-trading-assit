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


def test_open_decisions_counted_from_the_register_never_a_bare_zero(tmp_path):
    out = pack.build(FACTS)
    count, sources = pack.open_decisions()
    assert sources == list(pack.REGISTERED_DECISION_SOURCES) and count == 11
    assert "Open decisions in registered tables: 11 (sources: `docs/governance/OWNER_DECISION_REGISTER.md`)." in out
    # No registered table -> UNKNOWN, not 0.
    assert pack.open_decisions(str(tmp_path)) == (None, [])
    assert "Open decisions in registered tables: UNKNOWN" in pack.build(FACTS, root=str(tmp_path))


def test_missing_or_incomplete_facts_fail_closed(tmp_path):
    with pytest.raises(SystemExit, match="FACTS_UNAVAILABLE"):
        pack.load_facts(str(tmp_path / "absent.json"))
    bad = tmp_path / "facts.json"
    bad.write_text(json.dumps({k: v for k, v in FACTS.items() if k != "inputs_sha256"}))
    with pytest.raises(SystemExit, match="FACTS_INCOMPLETE"):
        pack.load_facts(str(bad))
