"""AG_REGEN_OUTCOME_V1: the contract between the merge gate and the regeneration workflow.

Policy (R3): generated files are published only through a pull request. The regeneration
workflow never pushes to ``main`` and never force-pushes. It writes one machine-readable outcome per run:

    python scripts/governance/regen_contract.py emit --out regen-outcome.json \
        --status REGEN_NO_CHANGE --target-sha <sha> --correlation-id <id> [--changed-path P ...] \
        [--branch regen/generated-files-<sha> --pr-number N --pr-head-sha <sha>] [--reason TEXT]

and uploads it as the artifact ``regen-outcome``. ``validate_outcome`` is the gate's reader.
Fixed point: the four outputs are a pure function of non-generated inputs (no output is a
collector input), so regenerating on the merge of a regeneration PR yields REGEN_NO_CHANGE.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

SCHEMA = "AG_REGEN_OUTCOME_V1"
ARTIFACT_NAME = "regen-outcome"
ARTIFACT_FILE = "regen-outcome.json"
# One branch per source identity: regen/generated-files-<target_sha>. Branches are never
# rewritten; a stale regeneration PR is superseded by a new one for the newer source.
REGEN_BRANCH_PREFIX = "regen/generated-files-"
GENERATED_PATHS = frozenset({
    "PROJECT_STATUS.md", "docs/status/PROJECT_LIVE_STATUS.md",
    "status/facts.json", "docs/agents/CONTEXT_PACK.md",
})
REGEN_NO_CHANGE = "REGEN_NO_CHANGE"
REGEN_PR_CREATED = "REGEN_PR_CREATED"
REGEN_PR_UPDATED = "REGEN_PR_UPDATED"
REGEN_PENDING_REVIEW = "REGEN_PENDING_REVIEW"
REGEN_FAILED = "REGEN_FAILED"
PR_STATUSES = frozenset({REGEN_PR_CREATED, REGEN_PR_UPDATED, REGEN_PENDING_REVIEW})
STATUSES = frozenset({REGEN_NO_CHANGE, REGEN_FAILED}) | PR_STATUSES
SHA = re.compile(r"^[0-9a-f]{40}$")


def regen_branch(target_sha: str) -> str:
    return f"{REGEN_BRANCH_PREFIX}{target_sha}"


def branch_target(branch: str) -> str | None:
    """The source SHA a regeneration branch is bound to, or None for any other branch."""
    if not branch.startswith(REGEN_BRANCH_PREFIX):
        return None
    target = branch[len(REGEN_BRANCH_PREFIX):]
    return target if SHA.match(target) else None


def run_name(target_sha: str, correlation_id: str) -> str:
    """The regeneration workflow's ``run-name``; the gate matches it exactly."""
    return f"regenerate at {target_sha} [{correlation_id}]"


def build_outcome(status: str, target_sha: str, correlation_id: str, changed_paths=(), branch=None,
                  pr_number=None, pr_head_sha=None, reason=None) -> dict:
    return {"schema": SCHEMA, "status": status, "target_sha": target_sha,
            "correlation_id": correlation_id, "changed_paths": sorted(set(changed_paths)),
            "branch": branch, "pr_number": pr_number, "pr_head_sha": pr_head_sha, "reason": reason}


def validate_outcome(outcome, target_sha: str, correlation_id: str) -> list[str]:
    """Failures for an outcome that does not prove its status for exactly this dispatch."""
    if not isinstance(outcome, dict) or outcome.get("schema") != SCHEMA:
        return ["REGEN_OUTCOME_SCHEMA_INVALID"]
    failures = []
    status = outcome.get("status")
    if status not in STATUSES:
        failures.append("REGEN_OUTCOME_STATUS_UNKNOWN")
    if outcome.get("target_sha") != target_sha:
        failures.append("REGEN_OUTCOME_TARGET_SHA_MISMATCH")
    if outcome.get("correlation_id") != correlation_id:
        failures.append("REGEN_OUTCOME_CORRELATION_MISMATCH")
    changed = outcome.get("changed_paths")
    if not isinstance(changed, list) or not set(changed) <= GENERATED_PATHS:
        failures.append("REGEN_OUTCOME_UNEXPECTED_PATH")
    if status == REGEN_NO_CHANGE and changed:
        failures.append("REGEN_OUTCOME_NO_CHANGE_WITH_PATHS")
    if status in PR_STATUSES:
        if not changed:
            failures.append("REGEN_OUTCOME_PR_WITHOUT_CHANGES")
        if outcome.get("branch") != regen_branch(target_sha):
            failures.append("REGEN_OUTCOME_BRANCH_INVALID")
        if not isinstance(outcome.get("pr_number"), int) or outcome["pr_number"] < 1:
            failures.append("REGEN_OUTCOME_PR_NUMBER_INVALID")
        if not SHA.match(str(outcome.get("pr_head_sha") or "")):
            failures.append("REGEN_OUTCOME_PR_HEAD_INVALID")
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("emit",))
    parser.add_argument("--out", required=True)
    parser.add_argument("--status", required=True, choices=sorted(STATUSES))
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--branch")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--pr-head-sha")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    outcome = build_outcome(args.status, args.target_sha, args.correlation_id, args.changed_path,
                            args.branch, args.pr_number, args.pr_head_sha, args.reason)
    failures = validate_outcome(outcome, args.target_sha, args.correlation_id)
    if args.status != REGEN_FAILED and failures:
        print("REGEN_OUTCOME_INVALID: " + ", ".join(failures), file=sys.stderr)
        return 1
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(outcome, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
