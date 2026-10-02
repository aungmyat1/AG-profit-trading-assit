"""C001/frozen-friction identity verification used before every offline replay.

The checks are intentionally content-addressed and local.  A mismatch is not repaired,
updated, or accepted with a flag: it blocks C001 and states that a changed rule belongs
to a new C002+ candidate/version.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .models import sha256_of_file, verify_freeze_record

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


def _read_json(path: Path) -> Mapping[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_c001_rule_identity(repository_root: Path) -> FrozenIdentityReport:
    root = Path(repository_root)
    manifest_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml"
    freeze_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json"
    record = _read_json(freeze_path)
    manifest = verify_freeze_record(manifest_path, freeze_path)
    checked = {"research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml": bool(manifest["frozen"])}
    for relative, expected in record.get("contract_file_sha256", {}).items():
        actual = sha256_of_file(root / relative)
        checked[relative] = actual == expected
    if not all(checked.values()):
        raise FrozenIdentityError(C001_MUTATION_REQUIRES_VERSION_BUMP,
                                  ",".join(sorted(path for path, good in checked.items() if not good)))
    return FrozenIdentityReport("PASS", record.get("candidate_id", "CRYPTO_CFD_C001"), checked)


def verify_friction_identity(repository_root: Path) -> FrozenIdentityReport:
    root = Path(repository_root)
    record_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.friction.freeze.json"
    record = _read_json(record_path)
    relative = record["friction_file"]
    expected = record["friction_file_sha256"]
    actual = sha256_of_file(root / relative)
    checked = {relative: actual == expected}
    if not checked[relative]:
        raise FrozenIdentityError(FRICTION_MUTATION_REQUIRES_VERSION_BUMP, relative)
    return FrozenIdentityReport("PASS", record.get("candidate_id", "CRYPTO_CFD_C001"), checked)


__all__ = [
    "C001_MUTATION_REQUIRES_VERSION_BUMP", "FRICTION_MUTATION_REQUIRES_VERSION_BUMP",
    "FrozenIdentityError", "FrozenIdentityReport", "verify_c001_rule_identity", "verify_friction_identity",
]
