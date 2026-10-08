"""Dispatch post-merge workflows at an exact commit and fail if they do not pass."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

WORKFLOWS = ("ci.yml", "regenerate-generated-files.yml")
FIELDS = "databaseId,displayTitle,event,status,conclusion,createdAt,url"
START_TIMEOUT_SECONDS = 180
COMPLETION_TIMEOUT_SECONDS = 2700
POLL_INTERVAL_SECONDS = 10


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def find_dispatched_run(runs: list[dict], target_sha: str, not_before: datetime) -> dict | None:
    """Select only a new workflow_dispatch run whose run-name includes target_sha."""
    matches = []
    threshold = not_before - timedelta(seconds=5)
    for run in runs:
        if run.get("event") != "workflow_dispatch":
            continue
        if target_sha not in str(run.get("displayTitle") or ""):
            continue
        created_at = run.get("createdAt")
        if not created_at or _timestamp(created_at) < threshold:
            continue
        matches.append(run)
    return max(matches, key=lambda row: _timestamp(row["createdAt"])) if matches else None


def run_outcome(run: dict) -> str:
    """Return PENDING/SUCCESS and raise for any completed non-success result."""
    if run.get("status") != "completed":
        return "PENDING"
    if run.get("conclusion") == "success":
        return "SUCCESS"
    raise RuntimeError(
        f"Workflow run {run.get('databaseId')} concluded {run.get('conclusion') or 'unknown'}: "
        f"{run.get('url', '')}"
    )


def _gh_json(args: list[str]) -> list[dict]:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or ""
        raise RuntimeError(f"gh {' '.join(args[:4])} failed: {detail.strip()[:400]}") from None
    return json.loads(result.stdout)


def _dispatch(repo: str, workflow: str, sha: str) -> datetime:
    started = datetime.now(timezone.utc)
    try:
        subprocess.run(
            ["gh", "workflow", "run", workflow, "--repo", repo, "--ref", "main", "-f", f"target_sha={sha}"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or ""
        raise RuntimeError(f"Dispatch of {workflow} failed: {detail.strip()[:400]}") from None
    return started


def _list_runs(repo: str, workflow: str) -> list[dict]:
    return _gh_json([
        "run", "list", "--repo", repo, "--workflow", workflow, "--branch", "main",
        "--event", "workflow_dispatch", "--limit", "100", "--json", FIELDS,
    ])


def dispatch_and_wait(repo: str, sha: str, *, start_timeout: int = START_TIMEOUT_SECONDS,
                      completion_timeout: int = COMPLETION_TIMEOUT_SECONDS,
                      poll_interval: int = POLL_INTERVAL_SECONDS) -> list[dict]:
    if len(sha) != 40 or any(char not in "0123456789abcdefABCDEF" for char in sha):
        raise ValueError("merge commit must be a full 40-character SHA")

    dispatched_at = {workflow: _dispatch(repo, workflow, sha) for workflow in WORKFLOWS}
    deadline = time.monotonic() + start_timeout
    selected: dict[str, dict] = {}
    while len(selected) != len(WORKFLOWS):
        for workflow in WORKFLOWS:
            if workflow in selected:
                continue
            candidate = find_dispatched_run(_list_runs(repo, workflow), sha, dispatched_at[workflow])
            if candidate:
                selected[workflow] = candidate
                print(f"started {workflow}: {candidate.get('url', '')}")
        if len(selected) == len(WORKFLOWS):
            break
        if time.monotonic() >= deadline:
            missing = sorted(set(WORKFLOWS) - set(selected))
            raise TimeoutError(f"Workflows did not start within {start_timeout}s: {', '.join(missing)}")
        time.sleep(poll_interval)

    deadline = time.monotonic() + completion_timeout
    completed: set[str] = set()
    while len(completed) != len(WORKFLOWS):
        for workflow, original in selected.items():
            if workflow in completed:
                continue
            current = next((row for row in _list_runs(repo, workflow)
                            if row.get("databaseId") == original.get("databaseId")), original)
            if run_outcome(current) == "SUCCESS":
                completed.add(workflow)
                print(f"passed {workflow}: {current.get('url', '')}")
        if len(completed) == len(WORKFLOWS):
            return [selected[workflow] for workflow in WORKFLOWS]
        if time.monotonic() >= deadline:
            pending = sorted(set(WORKFLOWS) - completed)
            raise TimeoutError(f"Workflows did not complete within {completion_timeout}s: {', '.join(pending)}")
        time.sleep(poll_interval)
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        dispatch_and_wait(args.repo, args.sha)
    except Exception as exc:
        print(f"POST_MERGE_CI_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
