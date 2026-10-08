"""Owner merge gate: preflight required main workflows, then verify them on the exact merged SHA.

    python scripts/governance/post_merge_verify.py preflight --head-sha <sha>
    python scripts/governance/post_merge_verify.py verify --pr <n> --expected-head-sha <sha>

A merge made with the workflow's GITHUB_TOKEN does not emit workflow-triggering push events,
so ``verify`` dispatches the regeneration workflow and main CI explicitly (workflow_dispatch is
exempt from that restriction), binds each run to the exact commit, and waits with a bounded
timeout. Missing workflows, unexpected main movement, a wrong-commit run, a non-success
conclusion, or a timeout all exit non-zero. This script never merges and never pushes.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from audit_pr_readiness import GitHubAPI, _token

CI_WORKFLOW = "ci.yml"
REGEN_WORKFLOW = "regenerate-generated-files.yml"
GENERATED_PATHS = frozenset({
    "PROJECT_STATUS.md", "docs/status/PROJECT_LIVE_STATUS.md",
    "status/facts.json", "docs/agents/CONTEXT_PACK.md",
})
REGEN_COMMIT_PREFIX = "chore(docs): regenerate generated files"
BOT_LOGIN = "github-actions[bot]"
DISPATCH_SKEW = timedelta(seconds=10)


def workflow_contract_failures(ci_text: str | None, regen_text: str | None) -> list[str]:
    """Static check that both required workflows exist and accept the dispatch we send."""
    failures = []
    dispatch = re.compile(r"(?m)^\s*workflow_dispatch\s*:")
    if ci_text is None:
        failures.append(f"WORKFLOW_MISSING:{CI_WORKFLOW}")
    elif not dispatch.search(ci_text):
        failures.append(f"WORKFLOW_NOT_DISPATCHABLE:{CI_WORKFLOW}")
    if regen_text is None:
        failures.append(f"WORKFLOW_MISSING:{REGEN_WORKFLOW}")
    elif not dispatch.search(regen_text) or not re.search(r"(?m)^\s*target_sha\s*:", regen_text):
        failures.append(f"WORKFLOW_NOT_DISPATCHABLE:{REGEN_WORKFLOW}")
    return failures


def resolve_final_main(merge_sha: str, main_sha: str, commit: dict | None) -> tuple[str | None, str | None]:
    """(final_sha, failure). main may equal the merge or be exactly one regeneration bot commit on it."""
    if main_sha == merge_sha:
        return merge_sha, None
    if not commit:
        return None, "MAIN_ADVANCED_UNVERIFIED"
    parents = [p.get("sha") for p in commit.get("parents", [])]
    message = str((commit.get("commit") or {}).get("message") or "")
    login = (commit.get("author") or {}).get("login")
    paths = {f.get("filename") for f in commit.get("files", [])}
    if (parents == [merge_sha] and message.startswith(REGEN_COMMIT_PREFIX) and login == BOT_LOGIN
            and paths and paths <= GENERATED_PATHS):
        return main_sha, None
    return None, "MAIN_ADVANCED_UNEXPECTEDLY"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def select_run(runs: list[dict], head_sha: str, dispatched_at: datetime,
               display_title: str | None = None) -> dict | None:
    """Newest workflow_dispatch run on main for exactly ``head_sha`` created after our dispatch."""
    matches = [
        run for run in runs
        if run.get("event") == "workflow_dispatch" and run.get("head_branch") == "main"
        and run.get("head_sha") == head_sha and run.get("created_at")
        and _parse_time(run["created_at"]) >= dispatched_at - DISPATCH_SKEW
        and (display_title is None or run.get("display_title") == display_title)
    ]
    return max(matches, key=lambda run: (run["created_at"], run.get("id", 0))) if matches else None


def run_outcome(run: dict | None) -> str:
    if run is None:
        return "MISSING"
    if run.get("status") != "completed":
        return "PENDING"
    return "SUCCESS" if run.get("conclusion") == "success" else f"FAILED:{run.get('conclusion')}"


def _file_text(api: GitHubAPI, path: str, ref: str) -> str | None:
    try:
        body = api.request("GET", f"/repos/{api.repo}/contents/{path}?ref={ref}")
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    return base64.b64decode(body.get("content", "")).decode("utf-8", "replace")


def dispatch_and_wait(api: GitHubAPI, workflow: str, inputs: dict, head_sha: str, timeout_s: int,
                      poll_s: int, display_title: str | None = None) -> dict:
    dispatched_at = datetime.now(timezone.utc)
    api.request("POST", f"/repos/{api.repo}/actions/workflows/{workflow}/dispatches",
                {"ref": "main", "inputs": inputs})
    deadline = time.monotonic() + timeout_s
    while True:
        runs = api.request("GET", f"/repos/{api.repo}/actions/workflows/{workflow}/runs"
                                  "?event=workflow_dispatch&branch=main&per_page=50").get("workflow_runs", [])
        run = select_run(runs, head_sha, dispatched_at, display_title)
        outcome = run_outcome(run)
        if outcome not in {"MISSING", "PENDING"} or time.monotonic() >= deadline:
            if outcome in {"MISSING", "PENDING"}:
                outcome = f"TIMEOUT_{outcome}"
            return {"workflow": workflow, "head_sha": head_sha, "outcome": outcome,
                    "run_id": (run or {}).get("id"), "run_url": (run or {}).get("html_url")}
        time.sleep(poll_s)


def main_sha(api: GitHubAPI) -> str:
    return api.request("GET", f"/repos/{api.repo}/git/ref/heads/main")["object"]["sha"]


def preflight(api: GitHubAPI, head_sha: str) -> list[str]:
    # Readiness requires the PR base to be current main, so the head tree is what main becomes.
    return workflow_contract_failures(_file_text(api, f".github/workflows/{CI_WORKFLOW}", head_sha),
                                      _file_text(api, f".github/workflows/{REGEN_WORKFLOW}", head_sha))


def verify(api: GitHubAPI, pr_number: int, expected_head: str, timeout_s: int, poll_s: int) -> dict:
    result: dict = {"pr": pr_number, "expected_head_sha": expected_head, "failures": []}
    pr = api.request("GET", f"/repos/{api.repo}/pulls/{pr_number}")
    merge_sha = pr.get("merge_commit_sha")
    result["merge_sha"] = merge_sha
    if not pr.get("merged") or not merge_sha:
        result["failures"].append("PR_NOT_MERGED")
        return result
    if (pr.get("head") or {}).get("sha") != expected_head:
        result["failures"].append("MERGED_HEAD_NOT_AUTHORIZED_HEAD")
        return result
    if main_sha(api) != merge_sha:
        result["failures"].append("MAIN_NOT_AT_MERGE_SHA")
        return result
    regen = dispatch_and_wait(api, REGEN_WORKFLOW, {"target_sha": merge_sha}, merge_sha, timeout_s, poll_s,
                              display_title=f"regenerate at {merge_sha}")
    result["regeneration"] = regen
    if regen["outcome"] != "SUCCESS":
        result["failures"].append(f"REGENERATION_{regen['outcome']}")
        return result
    current = main_sha(api)
    commit = api.request("GET", f"/repos/{api.repo}/commits/{current}") if current != merge_sha else None
    final_sha, failure = resolve_final_main(merge_sha, current, commit)
    result["final_main_sha"] = final_sha
    if failure:
        result["failures"].append(failure)
        return result
    ci = dispatch_and_wait(api, CI_WORKFLOW, {}, final_sha, timeout_s, poll_s)
    result["ci"] = ci
    if ci["outcome"] != "SUCCESS":
        result["failures"].append(f"MAIN_CI_{ci['outcome']}")
    elif main_sha(api) != final_sha:
        result["failures"].append("MAIN_ADVANCED_DURING_CI")
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
    else:
        report = verify(api, args.pr, args.expected_head_sha, args.timeout_seconds, args.poll_seconds)
        failures = report["failures"]
        print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
