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
OUTCOME_MODEL_NOT_PINNED = "C001_OUTCOME_MODEL_NOT_PINNED"
UNDECLARED_PRE_RESULT_CORRECTION = "C001_UNDECLARED_PRE_RESULT_CORRECTION"
CORRECTION_AFTER_RESULTS = "C001_CORRECTION_RECORDED_AFTER_RESULTS"
APPLICATION_IDENTITY_INCOMPLETE = "C001_APPLICATION_IDENTITY_INCOMPLETE"

# Files that decide fills, exits and gross R are part of the frozen identity, not just the
# strategy contract files. The replay model declares REPLAY_FILL_MODEL_V1 frozen and directly
# determines C001 outcomes, so an edit to it must be rejected exactly like a contract edit --
# otherwise a later change to the fill model silently moves results under the same identity.
OUTCOME_DEFINING_FILES = (
    "src/edge_discovery/replay_c001.py",
)


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


def _check_pinned(root: Path, relative: str, expected: str, checked: dict) -> None:
    committed, clean = _identity_bytes(root, relative)
    actual = hashlib.sha256(committed).hexdigest()
    checked[relative] = bool(clean and actual == expected)


def verify_c001_rule_identity(repository_root: Path) -> FrozenIdentityReport:
    """Verify the whole frozen identity, including the model that produces the outcomes.

    Two sections of the freeze record are checked: `contract_file_sha256` (the strategy
    contract) and `outcome_defining_file_sha256` (the replay/fill model). A gap in the
    latter is a hard failure, not a warning -- an unpinned outcome model means a later
    edit could move results without changing the identity.

    A pinned hash may only differ from the file when the freeze record carries a matching
    `pre_result_corrections` entry, and only while no economic result exists
    (`edge_verified: false`). An undeclared difference still fails closed.
    """
    root = Path(repository_root)
    manifest_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml"
    freeze_path = root / "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json"
    freeze_relative = "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json"
    freeze_bytes, freeze_clean = _identity_bytes(root, freeze_relative)
    record = json.loads(freeze_bytes.decode("utf-8"))
    manifest = verify_freeze_record(manifest_path, freeze_path)
    checked = {
        "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml": bool(manifest["frozen"]),
        freeze_relative: freeze_clean,
    }

    pinned: dict[str, str] = {}
    pinned.update(record.get("contract_file_sha256", {}))
    outcome_pinned = record.get("outcome_defining_file_sha256", {})
    pinned.update(outcome_pinned)
    for relative in OUTCOME_DEFINING_FILES:
        if relative not in outcome_pinned:
            raise FrozenIdentityError(OUTCOME_MODEL_NOT_PINNED, relative)

    # A correction is only ever a pre-result instrument: once an economic result exists, the mere
    # presence of one is a governance violation even if the bytes currently match.
    corrections = {entry.get("path"): entry for entry in record.get("pre_result_corrections", [])}
    if corrections and record.get("edge_verified") is not False:
        raise FrozenIdentityError(CORRECTION_AFTER_RESULTS,
                                  ",".join(sorted(corrections)))
    for relative, expected in pinned.items():
        _check_pinned(root, relative, expected, checked)
        if checked[relative]:
            continue
        entry = corrections.get(relative)
        if entry is None:
            continue
        if record.get("edge_verified") is not False:
            raise FrozenIdentityError(CORRECTION_AFTER_RESULTS, relative)
        if entry.get("corrected_sha256") != expected:
            raise FrozenIdentityError(UNDECLARED_PRE_RESULT_CORRECTION, relative)
        # The declared correction must describe the bytes that are actually committed.
        committed, clean = _identity_bytes(root, relative)
        if clean and hashlib.sha256(committed).hexdigest() == expected:
            checked[relative] = True

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
    "OUTCOME_MODEL_NOT_PINNED", "UNDECLARED_PRE_RESULT_CORRECTION", "CORRECTION_AFTER_RESULTS",
    "APPLICATION_IDENTITY_INCOMPLETE",
    "OUTCOME_DEFINING_FILES",
    "FrozenIdentityError", "FrozenIdentityReport", "verify_c001_rule_identity", "verify_friction_identity",
]
