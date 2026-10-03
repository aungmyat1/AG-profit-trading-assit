"""C001/frozen-friction identity verification used before every offline replay.

The checks are intentionally content-addressed and local.  A mismatch is not repaired,
updated, or accepted with a flag: it blocks C001 and states that a changed rule belongs
to a new C002+ candidate/version.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .models import verify_freeze_record

C001_MUTATION_REQUIRES_VERSION_BUMP = "C001_RULE_MUTATION_REQUIRES_C002_PLUS"
FRICTION_MUTATION_REQUIRES_VERSION_BUMP = "FRICTION_SCENARIO_MUTATION_REQUIRES_NEW_CANDIDATE"


class FrozenIdentityError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}{': ' + detail if detail else ''}")


@dataclass(frozen=True)
class FrozenIdentityReport:
    status: str
    candidate_id: str
    checked_files: Mapping[str, bool]
    reason_code: str | None = None


def _identity_bytes(root: Path, relative: str) -> tuple[bytes, bool]:
    """Return committed bytes and whether the tracked path is clean against HEAD.

    Non-Git fixture directories use their on-disk bytes, preserving the small unit-test
    seam while production verification remains anchored to committed Git objects.
    """
    try:
        repo = Path(subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip())
    except subprocess.SubprocessError:
        return (root / relative).read_bytes(), True
    try:
        subprocess.run(
            ["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", relative],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
        )
        clean = subprocess.run(
            ["git", "-C", str(repo), "diff", "--quiet", "--ignore-cr-at-eol",
             "HEAD", "--", relative],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        ).returncode == 0
        data = subprocess.check_output(
            ["git", "-C", str(repo), "cat-file", "blob", f"HEAD:{relative}"],
            stderr=subprocess.DEVNULL,
        )
        return data, clean
    except subprocess.SubprocessError:
        return b"", False


def verify_c001_rule_identity(repository_root: Path) -> FrozenIdentityReport:
    root = Path(repository_root)
    manifest_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml"
    freeze_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json"
    freeze_bytes, freeze_clean = _identity_bytes(
        root, "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json",
    )
    record = json.loads(freeze_bytes.decode("utf-8"))
    manifest = verify_freeze_record(manifest_path, freeze_path)
    checked = {
        "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml": bool(manifest["frozen"]),
        "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json": freeze_clean,
    }
    for relative, expected in record.get("contract_file_sha256", {}).items():
        committed, clean = _identity_bytes(root, relative)
        actual = hashlib.sha256(committed).hexdigest()
        checked[relative] = clean and actual == expected
    if not all(checked.values()):
        raise FrozenIdentityError(C001_MUTATION_REQUIRES_VERSION_BUMP,
                                  ",".join(sorted(path for path, good in checked.items() if not good)))
    return FrozenIdentityReport("PASS", record.get("candidate_id", "CRYPTO_CFD_C001"), checked)


def verify_friction_identity(repository_root: Path) -> FrozenIdentityReport:
    root = Path(repository_root)
    record_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.friction.freeze.json"
    freeze_relative = "research/edge_discovery/candidates/CRYPTO_CFD_C001.friction.freeze.json"
    freeze_bytes, freeze_clean = _identity_bytes(root, freeze_relative)
    record = json.loads(freeze_bytes.decode("utf-8"))
    relative = record["friction_file"]
    expected = record["friction_file_sha256"]
    committed, clean = _identity_bytes(root, relative)
    actual = hashlib.sha256(committed).hexdigest()
    checked = {freeze_relative: freeze_clean, relative: clean and actual == expected}
    if not checked[relative]:
        raise FrozenIdentityError(FRICTION_MUTATION_REQUIRES_VERSION_BUMP, relative)
    return FrozenIdentityReport("PASS", record.get("candidate_id", "CRYPTO_CFD_C001"), checked)


__all__ = [
    "C001_MUTATION_REQUIRES_VERSION_BUMP", "FRICTION_MUTATION_REQUIRES_VERSION_BUMP",
    "FrozenIdentityError", "FrozenIdentityReport", "verify_c001_rule_identity", "verify_friction_identity",
]
