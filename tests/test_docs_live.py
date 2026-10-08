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
        "scripts/docs/advisory_allowlist.json",
        "scripts/generate_live_status.py",
        "strategies/registry.yaml",
        "docs/PROJECT_OBJECTIVE.md",
        "status/facts.json",
        "config/ag_scheduler_v2.yaml",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    run("git", "init", "-q", cwd=tmp_path)
    run("git", "add", ".", cwd=tmp_path)
    return tmp_path


def test_untracked_supersession_sidecar_does_not_change_digest_or_suppress(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    # Track a machine-readable contradiction; add a valid-looking but untracked sidecar.
    manifest_rel = "docs/v2/AG_V2_BASELINE_MANIFEST_V1.json"
    target = root / manifest_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"strategies": {"SESSION_TRADE_V1": {
        "demo_authorized": True, "manager_dispatchable": True
    }}}), encoding="utf-8")
    run("git", "add", manifest_rel, cwd=root)
    before = run(sys.executable, "scripts/docs/collect_facts.py", "--repo-root", str(root), "--output", str(root / "facts.json"), cwd=root)
    digest_before = json.loads((root / "facts.json").read_text())["inputs_sha256"]
    sidecar = target.with_suffix(".supersession.yaml")
    sidecar.write_text(
        "target: AG_V2_BASELINE_MANIFEST_V1.json\n"
        "json_path: [strategies.SESSION_TRADE_V1.demo_authorized, strategies.SESSION_TRADE_V1.manager_dispatchable]\n"
        "superseded_by: current\ndate: 2026-10-08\nauthority_source: strategies/registry.yaml\n",
        encoding="utf-8",
    )
    run(sys.executable, "scripts/docs/collect_facts.py", "--repo-root", str(root), "--output", str(root / "facts.json"), cwd=root)
    digest_after = json.loads((root / "facts.json").read_text())["inputs_sha256"]
    assert digest_after == digest_before
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1
    assert result.stdout.count("machine contradiction") == 2


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


def test_machine_authority_mismatch_is_blocking_unless_superseded(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    facts = json.loads((root / "status/facts.json").read_text(encoding="utf-8"))
    strategy_id = facts["strategies"][0]["id"]
    current = facts["strategies"][0]["demo_authorized"]["value"]
    manifest = root / "docs/fixture.json"
    manifest.write_text(json.dumps({
        "class": "evidence",
        "strategies": {strategy_id: {"demo_authorized": not current}},
    }), encoding="utf-8")
    run("git", "add", "docs/fixture.json", cwd=root)

    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1
    assert "machine contradiction" in result.stdout

    manifest.write_text(json.dumps({
        "superseded_by": "docs/current.json",
        "date": "2026-10-08",
        "strategies": {strategy_id: {"demo_authorized": not current}},
    }), encoding="utf-8")
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 0


def test_never_suppress_overrides_allowlisted_range(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        "---\nclass: authority\n---\n"
        "`SESSION_TRADE_V1` is `demo_authorized: true`.\n",
        encoding="utf-8",
    )
    policy_path = root / "scripts/docs/advisory_allowlist.json"
    policy = {
        "schema": "AG_ADVISORY_SCAN_ALLOWLIST_V1",
        "allowlisted_ranges": [{"id": "all", "file": "README.md", "lines": [1, 10]}],
        "verified_label_free": [],
        "disambiguation_notes": [],
        "never_suppress": [],
    }
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 0

    policy["allowlisted_ranges"][0]["carve_outs"] = [{"lines": [4, 4]}]
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1

    policy["allowlisted_ranges"] = []
    policy["disambiguation_notes"] = [{
        "file": "README.md", "lines": [4, 4], "token": "demo_authorized"
    }]
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 0

    policy["allowlisted_ranges"] = [{"id": "all", "file": "README.md", "lines": [1, 10]}]
    policy["disambiguation_notes"] = []
    policy["never_suppress"] = [{"file": "README.md", "lines": [4, 4], "ref": "test"}]
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1
    assert "current-truth contradiction" in result.stdout


def test_baseline_sidecar_is_exact_and_removal_restores_blocking(tmp_path: Path) -> None:
    root = drift_fixture(tmp_path)
    manifest_rel = "docs/v2/AG_V2_BASELINE_MANIFEST_V1.json"
    sidecar_rel = "docs/v2/AG_V2_BASELINE_MANIFEST_V1.supersession.yaml"
    for relative in (manifest_rel, sidecar_rel):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    run("git", "add", manifest_rel, sidecar_rel, cwd=root)

    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 0

    sidecar = root / sidecar_rel
    sidecar.unlink()
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1
    assert result.stdout.count("machine contradiction") == 2

    shutil.copy2(ROOT / sidecar_rel, sidecar)
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(
            "authority_source: strategies/registry.yaml", "authority_source: docs/obsolete.json"
        ),
        encoding="utf-8",
    )
    result = run(sys.executable, "scripts/docs/check_drift.py", "--repo-root", str(root), cwd=root, check=False)
    assert result.returncode == 1


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
    # Missing index fails closed; once initialized and staged, collection is stable.
    unavailable = run(sys.executable, "scripts/docs/collect_facts.py", cwd=root, check=False)
    assert unavailable.returncode == 1
    assert "cannot enumerate tracked collector inputs" in unavailable.stderr
    run("git", "init", "-q", cwd=root)
    run("git", "config", "user.name", "Docs Test", cwd=root)
    run("git", "config", "user.email", "docs-test@example.invalid", cwd=root)
    run("git", "add", ".", cwd=root)
    run(sys.executable, "scripts/docs/collect_facts.py", cwd=root)
    run("cog", "-r", "PROJECT_STATUS.md", cwd=root)
    before = (root / "status/facts.json").read_bytes()
    run("cog", "--check", "PROJECT_STATUS.md", cwd=root)
    run("git", "add", "PROJECT_STATUS.md", "status/facts.json", cwd=root)
    run("git", "commit", "-qm", "generated docs", cwd=root)
    first_sha = run("git", "rev-parse", "HEAD", cwd=root).stdout.strip()
    for _ in range(2):
        run(sys.executable, "scripts/docs/collect_facts.py", cwd=root)
        assert (root / "status/facts.json").read_bytes() == before
        run("cog", "--check", "PROJECT_STATUS.md", cwd=root)
        run("git", "commit", "--allow-empty", "-qm", "SHA independence", cwd=root)
    assert run("git", "rev-parse", "HEAD", cwd=root).stdout.strip() != first_sha

    # Even an input-only registry edit must fail Cog before collection repairs JSON.
    registry = root / "strategies/registry.yaml"
    registry.write_bytes(registry.read_bytes() + b"\n# input freshness test\n")
    stale = run("cog", "--check", "PROJECT_STATUS.md", cwd=root, check=False)
    assert stale.returncode != 0
    run(sys.executable, "scripts/docs/collect_facts.py", cwd=root)
    run("cog", "-r", "PROJECT_STATUS.md", cwd=root)
    run("cog", "--check", "PROJECT_STATUS.md", cwd=root)
    assert (root / "status/facts.json").read_bytes() != before
