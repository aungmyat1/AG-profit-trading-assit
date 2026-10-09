#!/usr/bin/env python3
"""Generated-file policy gate for CI (classify drift; decide by event).

    python scripts/docs/check_generated_files.py --mode strict|pr|advisory [--head-ref BRANCH]

Run after the generators have rewritten the four outputs in the workspace; HEAD is the
committed state. Policy (AG_REGEN_OUTCOME_V1: outputs reach main only via a regeneration PR):
  strict    every output FRESH or FINGERPRINT_ONLY (merge-gate main CI, workflow_dispatch).
  pr        a pull_request merge checkout (HEAD^1 = current base):
            * regeneration PR (head regen/generated-files-<sha>): <sha> must equal the
              current base, the PR may change only the four outputs, and every output must
              be byte-exact FRESH -- a stale or hand-edited regeneration PR fails;
            * any other PR: outputs it changes must be byte-exact FRESH (no hand edits that
              disagree with the generators); drift in outputs it does not change is
              REGEN_REQUIRED_AFTER_MERGE (warning), published by the post-merge regeneration PR.
  advisory  report only (push runs; main may legitimately wait on a regeneration PR).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generated_files import GENERATED_FILES  # noqa: E402

REGEN_PREFIX = "regen/generated-files-"
SHA = re.compile(r"^[0-9a-f]{40}$")

FINGERPRINT = re.compile(r"(?m)^inputs_sha256: `[0-9a-f]{64}`\.?$")


def normalized(path: str, content: str) -> object:
    if path.endswith(".json"):
        value = json.loads(content)
        if isinstance(value, dict):
            value.pop("inputs_sha256", None)
        return value
    return FINGERPRINT.sub("inputs_sha256: <fingerprint>", content)


def committed_content(path: str, revision: str = "HEAD") -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(f"cannot read {revision}:{path}: {result.stderr.strip()}")
    return result.stdout


def classify(path: str, committed: str, generated: str) -> str:
    if committed == generated:
        return "FRESH"
    if normalized(path, committed) == normalized(path, generated):
        return "FINGERPRINT_ONLY"
    return "CONTENT_STALE"


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def decide(mode: str, results: dict, pr_changed: set, head_ref: str, base_sha: str | None) -> tuple:
    """(failures, warnings) for the classified outputs under one CI policy mode."""
    failures, warnings = [], []
    for path, result in results.items():
        if result == "FINGERPRINT_ONLY":
            warnings.append(f"{path}: generated input fingerprint changed; content is unchanged")
    if mode == "advisory":
        warnings += [f"{p}: CONTENT_STALE (advisory)" for p, r in results.items() if r == "CONTENT_STALE"]
        return failures, warnings
    if mode == "strict":
        failures += [f"{p}: generated content differs" for p, r in results.items() if r == "CONTENT_STALE"]
        return failures, warnings
    if head_ref.startswith(REGEN_PREFIX):
        target = head_ref[len(REGEN_PREFIX):]
        if not SHA.match(target):
            failures.append(f"REGEN_PR_BRANCH_INVALID: {head_ref}")
        elif target != base_sha:
            failures.append(f"REGEN_PR_STALE: built for {target}, base is now {base_sha}")
        extra = sorted(pr_changed - set(GENERATED_FILES))
        if extra:
            failures.append("REGEN_PR_UNEXPECTED_PATH: " + ", ".join(extra))
        failures += [f"{p}: REGEN_PR_NOT_EXACT ({r})" for p, r in results.items() if r != "FRESH"]
        return failures, warnings
    for path, result in results.items():
        if path in pr_changed and result != "FRESH":
            failures.append(f"{path}: changed by this PR but differs from the generators ({result})")
        elif result == "CONTENT_STALE":
            warnings.append(f"{path}: REGEN_REQUIRED_AFTER_MERGE (published by the regeneration PR)")
    return failures, warnings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("strict", "pr", "advisory"), default="strict")
    parser.add_argument("--head-ref", default="")
    args = parser.parse_args(argv)
    results, failures = {}, []
    for relative in GENERATED_FILES:
        try:
            expected = committed_content(relative)
            actual = (ROOT / relative).read_text(encoding="utf-8")
            results[relative] = classify(relative, expected, actual)
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f"{relative}: {exc}")
            continue
        print(f"{relative}: {results[relative]}")
    pr_changed, base_sha = set(), None
    if args.mode == "pr":
        try:
            # actions/checkout of a pull_request is the merge commit: HEAD^1 is the current base.
            base_sha = _git("rev-parse", "HEAD^1")
            _git("rev-parse", "HEAD^2")
            pr_changed = set(_git("diff", "--name-only", base_sha, "HEAD").splitlines())
        except RuntimeError as exc:
            failures.append(f"PR_CONTEXT_UNAVAILABLE: {exc}")
    decided_failures, warnings = decide(args.mode, results, pr_changed, args.head_ref, base_sha)
    failures += decided_failures
    for warning in warnings:
        print(f"::warning::{warning}")
    for failure in failures:
        print(f"::error::{failure}")
    print(f"GENERATED_FILES_POLICY mode={args.mode} failures={len(failures)} warnings={len(warnings)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
