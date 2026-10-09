"""Owner merge gate: preflight required workflows, then drive one merged PR to a post-merge state.

    python scripts/governance/post_merge_verify.py preflight --head-sha <sha>
    python scripts/governance/post_merge_verify.py verify --pr <n> --expected-head-sha <sha>

A merge made with the workflow's GITHUB_TOKEN emits no workflow-triggering push events, so
``verify`` dispatches regeneration and main CI explicitly (workflow_dispatch is exempt from that
restriction). Each dispatch carries a fresh correlation id that the target workflow echoes in its
``run-name``; exactly one run must carry it, on exactly the expected commit, or verify fails.

Generated-file policy (R3): regeneration publishes changes only through a pull request
(``regen_contract.py``). States, in order: MERGED_PENDING_REGENERATION ->
MERGED_PENDING_REGEN_PR (stop: generated changes await separate review) or
MERGED_PENDING_MAIN_CI -> INTEGRATED. Any failure is POST_MERGE_FAILED. Exit 0 only for
INTEGRATED. This script never merges, never pushes and never touches a broker or host.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid

from audit_pr_readiness import GitHubAPI, _token
from regen_contract import (
    ARTIFACT_FILE, ARTIFACT_NAME, PR_STATUSES, REGEN_NO_CHANGE, run_name, validate_outcome,
)

CI_WORKFLOW = "ci.yml"
REGEN_WORKFLOW = "regenerate-generated-files.yml"
MERGED_PENDING_REGENERATION = "MERGED_PENDING_REGENERATION"
MERGED_PENDING_REGEN_PR = "MERGED_PENDING_REGEN_PR"
MERGED_PENDING_MAIN_CI = "MERGED_PENDING_MAIN_CI"
INTEGRATED = "INTEGRATED"
POST_MERGE_FAILED = "POST_MERGE_FAILED"
EXIT_CODES = {INTEGRATED: 0, MERGED_PENDING_REGEN_PR: 3}

_DISPATCH = re.compile(r"(?m)^\s*workflow_dispatch\s*:")
_PUSH_MAIN = re.compile(r"git\s+push\b[^\n]*?\s(?:\S*:)?(?:refs/heads/)?main\b")


def ci_run_name(correlation_id: str) -> str:
    """ci.yml's ``run-name`` for a dispatched run; the gate matches it exactly."""
    return f"CI dispatch {correlation_id}"


def _has_input(text: str, name: str) -> bool:
    return re.search(rf"(?m)^\s*{name}\s*:", text) is not None


def workflow_contract_failures(ci_text: str | None, regen_text: str | None) -> list[str]:
    """Static check that both workflows exist, accept our dispatch and echo the correlation id."""
    failures = []
    if ci_text is None:
        failures.append(f"WORKFLOW_MISSING:{CI_WORKFLOW}")
    elif not (_DISPATCH.search(ci_text) and _has_input(ci_text, "correlation_id")
              and "inputs.correlation_id" in ci_text and _has_input(ci_text, "run-name")):
        failures.append(f"WORKFLOW_NOT_DISPATCHABLE:{CI_WORKFLOW}")
    if regen_text is None:
        failures.append(f"WORKFLOW_MISSING:{REGEN_WORKFLOW}")
    else:
        if not (_DISPATCH.search(regen_text) and _has_input(regen_text, "target_sha")
                and _has_input(regen_text, "correlation_id") and "inputs.correlation_id" in regen_text):
            failures.append(f"WORKFLOW_NOT_DISPATCHABLE:{REGEN_WORKFLOW}")
        if _PUSH_MAIN.search(regen_text):
            failures.append(f"WORKFLOW_PUSHES_MAIN:{REGEN_WORKFLOW}")
        if ARTIFACT_NAME not in regen_text:
            failures.append(f"WORKFLOW_NO_OUTCOME_ARTIFACT:{REGEN_WORKFLOW}")
    return failures


def select_run(runs: list[dict], head_sha: str, title: str) -> tuple[dict | None, str | None]:
    """(run, failure): the single workflow_dispatch run on main titled ``title``.

    The title embeds a per-dispatch correlation id, so a second match means the correlation is
    not unique and nothing can be trusted (fail closed). A titled run on another commit is a
    wrong-commit run, never a missing one.
    """
    titled = [run for run in runs if run.get("display_title") == title]
    if len(titled) > 1:
        return None, "RUN_CORRELATION_AMBIGUOUS"
    if not titled:
        return None, None
    run = titled[0]
    if run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main":
        return None, "RUN_NOT_MAIN_DISPATCH"
    if run.get("head_sha") != head_sha:
        return None, "RUN_WRONG_COMMIT"
    return run, None


def run_outcome(run: dict | None) -> str:
    if run is None:
        return "MISSING"
    if run.get("status") != "completed":
        return "PENDING"
    return "SUCCESS" if run.get("conclusion") == "success" else f"FAILED:{run.get('conclusion')}"


def dispatch_and_wait(api, workflow: str, inputs: dict, head_sha: str, title: str,
                      timeout_s: int, poll_s: int, sleep=time.sleep, clock=time.monotonic) -> dict:
    api.request("POST", f"/repos/{api.repo}/actions/workflows/{workflow}/dispatches",
                {"ref": "main", "inputs": inputs})
    deadline = clock() + timeout_s
    while True:
        runs = api.request("GET", f"/repos/{api.repo}/actions/workflows/{workflow}/runs"
                                  "?event=workflow_dispatch&branch=main&per_page=100").get("workflow_runs", [])
        run, failure = select_run(runs, head_sha, title)
        outcome = failure or run_outcome(run)
        if outcome not in {"MISSING", "PENDING"} or clock() >= deadline:
            if outcome in {"MISSING", "PENDING"}:
                outcome = f"TIMEOUT_{outcome}"
            return {"workflow": workflow, "head_sha": head_sha, "title": title, "outcome": outcome,
                    "run_id": (run or {}).get("id"), "run_url": (run or {}).get("html_url")}
        sleep(poll_s)


def download_outcome(repo: str, run_id: int) -> dict | None:
    """The run's ``regen-outcome`` artifact (gh follows the signed redirect), or None."""
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run(["gh", "run", "download", str(run_id), "-R", repo, "-n", ARTIFACT_NAME, "-D", tmp],
                              capture_output=True, text=True)
        path = os.path.join(tmp, ARTIFACT_FILE)
        if done.returncode != 0 or not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except ValueError:
                return None


def _file_text(api: GitHubAPI, path: str, ref: str) -> str | None:
    try:
        body = api.request("GET", f"/repos/{api.repo}/contents/{path}?ref={ref}")
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    return base64.b64decode(body.get("content", "")).decode("utf-8", "replace")


def main_sha(api) -> str:
    return api.request("GET", f"/repos/{api.repo}/git/ref/heads/main")["object"]["sha"]


def preflight(api: GitHubAPI, head_sha: str) -> list[str]:
    # Readiness requires the PR base to be current main, so the head tree is what main becomes.
    return workflow_contract_failures(_file_text(api, f".github/workflows/{CI_WORKFLOW}", head_sha),
                                      _file_text(api, f".github/workflows/{REGEN_WORKFLOW}", head_sha))


def verify(api, pr_number: int, expected_head: str, timeout_s: int, poll_s: int,
           fetch_outcome=download_outcome, new_id=lambda: uuid.uuid4().hex, **wait) -> dict:
    result: dict = {"pr": pr_number, "expected_head_sha": expected_head, "state": POST_MERGE_FAILED,
                    "failures": []}

    def fail(reason: str) -> dict:
        result["failures"].append(reason)
        result["state"] = POST_MERGE_FAILED
        return result

    pr = api.request("GET", f"/repos/{api.repo}/pulls/{pr_number}")
    merge_sha = pr.get("merge_commit_sha")
    result["merge_sha"] = merge_sha
    if not pr.get("merged") or not merge_sha:
        return fail("PR_NOT_MERGED")
    if (pr.get("head") or {}).get("sha") != expected_head:
        return fail("MERGED_HEAD_NOT_AUTHORIZED_HEAD")
    if main_sha(api) != merge_sha:
        return fail("MAIN_NOT_AT_MERGE_SHA")
    result["state"] = MERGED_PENDING_REGENERATION

    regen_id = new_id()
    regen = dispatch_and_wait(api, REGEN_WORKFLOW, {"target_sha": merge_sha, "correlation_id": regen_id},
                              merge_sha, run_name(merge_sha, regen_id), timeout_s, poll_s, **wait)
    result["regeneration"] = regen
    if regen["outcome"] != "SUCCESS":
        return fail(f"REGENERATION_{regen['outcome']}")
    outcome = fetch_outcome(api.repo, regen["run_id"])
    result["regeneration"]["result"] = outcome
    if outcome is None:
        return fail("REGEN_OUTCOME_MISSING")
    failures = validate_outcome(outcome, merge_sha, regen_id)
    if failures:
        result["failures"].extend(failures)
        result["state"] = POST_MERGE_FAILED
        return result
    if main_sha(api) != merge_sha:
        return fail("MAIN_ADVANCED_DURING_REGENERATION")
    if outcome["status"] in PR_STATUSES:
        # Generated changes await their own review and separately authorized merge.
        result["state"] = MERGED_PENDING_REGEN_PR
        result["regen_pr"] = {key: outcome[key] for key in ("status", "branch", "pr_number", "pr_head_sha")}
        result["regen_pr"]["source_sha"] = merge_sha
        return result
    if outcome["status"] != REGEN_NO_CHANGE:
        return fail(f"REGENERATION_{outcome['status']}")

    result["state"] = MERGED_PENDING_MAIN_CI
    ci_id = new_id()
    ci = dispatch_and_wait(api, CI_WORKFLOW, {"correlation_id": ci_id}, merge_sha, ci_run_name(ci_id),
                           timeout_s, poll_s, **wait)
    result["ci"] = ci
    if ci["outcome"] != "SUCCESS":
        return fail(f"MAIN_CI_{ci['outcome']}")
    if main_sha(api) != merge_sha:
        return fail("MAIN_ADVANCED_DURING_CI")
    result["state"] = INTEGRATED
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("preflight", "verify"))
    parser.add_argument("--repo", default="aungmyat1/AG-profit-trading-assit")
    parser.add_argument("--head-sha")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--expected-head-sha")
    parser.add_argument("--timeout-seconds", type=int, default=2700)
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args(argv)
    api = GitHubAPI(_token(), args.repo)
    if args.command == "preflight":
        failures = preflight(api, args.head_sha)
        print(json.dumps({"head_sha": args.head_sha, "failures": failures}))
        return 1 if failures else 0
    report = verify(api, args.pr, args.expected_head_sha, args.timeout_seconds, args.poll_seconds)
    print(json.dumps(report, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Post-merge state: `{report['state']}`\n\n```json\n{json.dumps(report, indent=2)}\n```\n")
    return EXIT_CODES.get(report["state"], 1)


if __name__ == "__main__":
    sys.exit(main())
