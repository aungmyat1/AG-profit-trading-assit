#!/usr/bin/env python3
"""AG main-protection tripwire (bounded, stdlib only).

Compares two git revisions and FAILS (exit 1) when the change:
  * deletes more than ``max_deleted_files`` files, or more than
    ``max_deleted_fraction`` of the files tracked at the base revision; or
  * deletes (or renames away) any protected authority path that exists at base.

The policy is read from the BASE revision, so a change cannot loosen the policy and
exploit the looser policy in the same diff. If the policy does not exist at base yet
(the change that introduces it), the working-tree copy is used.

Exit codes: 0 = PASS, 1 = TRIPPED, 2 = cannot evaluate (fails closed).

Usage:
    python scripts/governance/main_protection_tripwire.py --base <rev> --head <rev>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

POLICY_PATH = "config/governance/main_protection_tripwire.json"
NULL_SHA = "0" * 40


def _git(args: List[str], cwd: Optional[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def load_policy(base: str, cwd: Optional[str]) -> Dict:
    try:
        raw = _git(["show", f"{base}:{POLICY_PATH}"], cwd)
    except subprocess.CalledProcessError:
        raw = (Path(cwd or ".") / POLICY_PATH).read_text(encoding="utf-8")
    return json.loads(raw)


def is_protected(path: str, protected: List[str]) -> bool:
    for entry in protected:
        if entry.endswith("/"):
            if path.startswith(entry):
                return True
        elif path == entry:
            return True
    return False


def evaluate(base: str, head: str, cwd: Optional[str] = None) -> Dict:
    policy = load_policy(base, cwd)
    base_files = [p for p in _git(["ls-tree", "-r", "-z", "--name-only", base], cwd).split("\0") if p]
    diff = _git(["diff", "--name-status", "--no-renames", "-z", base, head], cwd).split("\0")
    deleted = [diff[i + 1] for i in range(0, len(diff) - 1, 2) if diff[i] == "D"]

    protected_removed = sorted(p for p in deleted if is_protected(p, policy["protected_paths"]))
    fraction = len(deleted) / len(base_files) if base_files else 0.0
    reasons = []
    if len(deleted) > policy["max_deleted_files"]:
        reasons.append(f"MASS_DELETION_COUNT: {len(deleted)} > {policy['max_deleted_files']}")
    if fraction > policy["max_deleted_fraction"]:
        reasons.append(f"MASS_DELETION_FRACTION: {fraction:.4f} > {policy['max_deleted_fraction']}")
    if protected_removed:
        reasons.append(f"PROTECTED_PATH_REMOVED: {len(protected_removed)}")
    return {
        "verdict": "TRIPPED" if reasons else "PASS",
        "base": base,
        "head": head,
        "base_file_count": len(base_files),
        "deleted_count": len(deleted),
        "deleted_fraction": round(fraction, 6),
        "protected_removed": protected_removed,
        "reasons": reasons,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv)

    if args.base == NULL_SHA:
        print(json.dumps({"verdict": "CANNOT_EVALUATE", "reason": "base is the null SHA"}))
        return 2
    try:
        result = evaluate(args.base, args.head, args.repo)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"verdict": "CANNOT_EVALUATE", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["verdict"] == "TRIPPED" else 0


if __name__ == "__main__":
    sys.exit(main())
