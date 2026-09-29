"""Tests for scripts/governance/main_protection_tripwire.py using throwaway git repos."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "main_protection_tripwire", ROOT / "scripts" / "governance" / "main_protection_tripwire.py"
)
tripwire = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tripwire)

POLICY = {
    "schema": "AG_MAIN_PROTECTION_TRIPWIRE_V1",
    "max_deleted_files": 5,
    "max_deleted_fraction": 0.5,
    "protected_paths": [
        "strategies/registry.yaml",
        "src/trade_ticket/",
        "config/governance/",
    ],
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "config/governance").mkdir(parents=True)
    (tmp_path / tripwire.POLICY_PATH).write_text(json.dumps(POLICY), encoding="utf-8")
    (tmp_path / "src/trade_ticket").mkdir(parents=True)
    (tmp_path / "src/trade_ticket/ticket.py").write_text("x\n")
    for i in range(20):
        (tmp_path / f"f{i}.txt").write_text(f"{i}\n")
    base = _commit(tmp_path, "base")
    return tmp_path, base


def test_benign_change_passes(repo):
    path, base = repo
    (path / "f0.txt").unlink()
    (path / "new.txt").write_text("n\n")
    head = _commit(path, "benign")
    r = tripwire.evaluate(base, head, str(path))
    assert r["verdict"] == "PASS" and r["deleted_count"] == 1


def test_mass_deletion_trips(repo):
    path, base = repo
    for i in range(6):
        (path / f"f{i}.txt").unlink()
    head = _commit(path, "mass")
    r = tripwire.evaluate(base, head, str(path))
    assert r["verdict"] == "TRIPPED"
    assert any(x.startswith("MASS_DELETION_COUNT") for x in r["reasons"])


def test_protected_directory_file_removal_trips(repo):
    path, base = repo
    (path / "src/trade_ticket/ticket.py").unlink()
    head = _commit(path, "rm ticket")
    r = tripwire.evaluate(base, head, str(path))
    assert r["verdict"] == "TRIPPED"
    assert r["protected_removed"] == ["src/trade_ticket/ticket.py"]


def test_rename_away_from_protected_path_trips(repo):
    path, base = repo
    _git(path, "mv", "src/trade_ticket/ticket.py", "src/other.py")
    head = _commit(path, "rename")
    assert tripwire.evaluate(base, head, str(path))["verdict"] == "TRIPPED"


def test_protected_path_absent_at_base_is_not_required(repo):
    # strategies/registry.yaml is protected but not present at base: adding nothing is fine.
    path, base = repo
    head = _commit(path, "empty")
    assert tripwire.evaluate(base, head, str(path))["verdict"] == "PASS"


def test_policy_is_read_from_base_so_loosening_in_same_change_does_not_help(repo):
    path, base = repo
    loosened = dict(POLICY, protected_paths=[])
    (path / tripwire.POLICY_PATH).write_text(json.dumps(loosened), encoding="utf-8")
    (path / "src/trade_ticket/ticket.py").unlink()
    head = _commit(path, "loosen + delete")
    assert tripwire.evaluate(base, head, str(path))["verdict"] == "TRIPPED"


def test_policy_file_removal_trips(repo):
    path, base = repo
    (path / tripwire.POLICY_PATH).unlink()
    head = _commit(path, "rm policy")
    r = tripwire.evaluate(base, head, str(path))
    assert r["verdict"] == "TRIPPED"
    assert tripwire.POLICY_PATH in r["protected_removed"]


def test_null_base_fails_closed():
    assert tripwire.main(["--base", tripwire.NULL_SHA, "--head", "HEAD"]) == 2


def test_unknown_revision_fails_closed(repo):
    path, _ = repo
    assert tripwire.main(["--base", "deadbeef" * 5, "--head", "HEAD", "--repo", str(path)]) == 2
