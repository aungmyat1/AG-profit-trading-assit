"""Deterministic drift check between the canonical universal skill root
(.agents/skills/) and its runtime-discovery mirror (.claude/skills/).

Canonical source: .agents/skills/ (see docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md
"Universal skill contract (vendor/model/runtime neutrality)"). .claude/skills/ is a
generated/manually-synced mirror for Claude-runtime discovery only and must never carry
independent skill semantics.

Read-only: reports drift, never writes. Marker files (whose name starts with
"_CANONICAL" or "_MIRROR") are expected to differ by design and are excluded from the
comparison. Exit code 0 = no drift, 1 = drift found.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_ROOT = REPO_ROOT / ".agents" / "skills"
MIRROR_ROOT = REPO_ROOT / ".claude" / "skills"
EXCLUDED_NAME_PREFIXES = ("_CANONICAL", "_MIRROR")


def _relevant_files(root: Path) -> dict:
    files = {}
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part == "worktrees" for part in path.parts):
            continue
        if path.name.startswith(EXCLUDED_NAME_PREFIXES):
            continue
        files[path.relative_to(root)] = path
    return files


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    canonical_files = _relevant_files(CANONICAL_ROOT)
    mirror_files = _relevant_files(MIRROR_ROOT)

    canonical_only = sorted(set(canonical_files) - set(mirror_files))
    mirror_only = sorted(set(mirror_files) - set(canonical_files))
    common = sorted(set(canonical_files) & set(mirror_files))

    content_drift = [
        rel for rel in common
        if _hash(canonical_files[rel]) != _hash(mirror_files[rel])
    ]

    if not canonical_only and not mirror_only and not content_drift:
        print(f"NO_DRIFT: {len(common)} files identical between {CANONICAL_ROOT} and {MIRROR_ROOT}")
        return 0

    if canonical_only:
        print("CANONICAL_ONLY (missing from mirror):")
        for rel in canonical_only:
            print(f"  {rel}")
    if mirror_only:
        print("MIRROR_ONLY (not in canonical -- must not carry independent semantics):")
        for rel in mirror_only:
            print(f"  {rel}")
    if content_drift:
        print("CONTENT_DRIFT (differs between canonical and mirror):")
        for rel in content_drift:
            print(f"  {rel}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
