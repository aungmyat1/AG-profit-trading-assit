from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=check, text=True, capture_output=True)


def drift_fixture(tmp_path: Path) -> Path:
    for relative in (
        "scripts/docs/check_drift.py",
        "scripts/docs/collect_facts.py",
        "scripts/docs/docs_drift_allowlist.txt",
        "scripts/generate_live_status.py",
        "strategies/registry.yaml",
        "docs/PROJECT_OBJECTIVE.md",
        "status/facts.json",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def test_registry_demo_authorized_flip_is_blocking(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    registry_path = root / "strategies/registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    first = sorted(registry["strategies"])[0]
    registry["strategies"][first]["demo_authorized"] = not registry["strategies"][first]["demo_authorized"]
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1
    assert f"{first}: demo_authorized differs" in result.stdout


def test_objective_edit_without_regeneration_is_blocking(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    objective = root / "docs/PROJECT_OBJECTIVE.md"
    text = objective.read_text(encoding="utf-8")
    objective.write_text(text.replace("Every trading day", "Every calendar day", 1), encoding="utf-8")

    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1
    assert "objective differs" in result.stdout


def test_six_current_truth_session_trade_claims_are_blocking(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    (root / "README.md").write_text(
        "---\nclass: authority\n---\n"
        "`SESSION_TRADE_V1` is independently `demo_authorized: true` for ASIAN_LONDON.\n",
        encoding="utf-8",
    )
    capability = root / "docs/PROJECT_CAPABILITY_COMPLETENESS.md"
    capability.write_text(
        "---\nclass: status\n---\n# Capability\n\n"
        "| `SESSION_TRADE_V1` | `demo_authorized: true` |\n\n"
        "`SESSION_TRADE_V1` being `demo_authorized: true` grants no other authority.\n\n"
        "`SESSION_TRADE_V1` is independently `demo_authorized: true` for ASIAN_LONDON.\n\n"
        "`SESSION_TRADE_V1` is separately `demo_authorized: true` for its own cycle.\n\n"
        "`SESSION_TRADE_V1: demo_authorized=true, authorized_cycle=ASIAN_LONDON`.\n",
        encoding="utf-8",
    )

    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1
    assert result.stdout.count("current-truth contradiction") == 6


def test_evidence_class_and_dated_status_section_are_historical(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    evidence = root / "docs/status/HISTORICAL.md"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        "---\nclass: evidence\n---\n# Snapshot\n\n"
        "`SESSION_TRADE_V1` was `demo_authorized: true`.\n",
        encoding="utf-8",
    )
    (root / "PROJECT_STATUS.md").write_text(
        "# Project Status\n\n## Prior state (2026-09-05)\n\n"
        "`SESSION_TRADE_V1` was `demo_authorized: true`.\n",
        encoding="utf-8",
    )

    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 0


def test_committing_generated_file_does_not_change_cog_check(tmp_path: Path) -> None:
    pytest.importorskip("cogapp")
    root = tmp_path / "repo"
    root.mkdir()
    for relative in ("PROJECT_STATUS.md", "docs/PROJECT_OBJECTIVE.md"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    for directory in ("scripts/docs", "strategies", "config"):
        shutil.copytree(ROOT / directory, root / directory)
    shutil.copy2(ROOT / "scripts/generate_live_status.py", root / "scripts/generate_live_status.py")
    run("git", "init", "-q", cwd=root)
    run("git", "config", "user.name", "Docs Test", cwd=root)
    run("git", "config", "user.email", "docs-test@example.invalid", cwd=root)
    run("git", "add", ".", cwd=root)
    run("git", "commit", "-qm", "source snapshot", cwd=root)
    source_sha = run("git", "rev-parse", "HEAD", cwd=root).stdout.strip()

    run(sys.executable, "scripts/docs/collect_facts.py", "--source-sha", source_sha, cwd=root)
    run("cog", "-r", "PROJECT_STATUS.md", cwd=root)
    before = (root / "PROJECT_STATUS.md").read_bytes()
    run("git", "add", "PROJECT_STATUS.md", "status/facts.json", cwd=root)
    run("git", "commit", "-qm", "commit generated docs", cwd=root)

    run("cog", "--check", "PROJECT_STATUS.md", cwd=root)
    assert (root / "PROJECT_STATUS.md").read_bytes() == before
    facts = json.loads((root / "status/facts.json").read_text(encoding="utf-8"))
    assert facts["source_snapshot"]["sha"] == source_sha
