"""Collect read-only GitHub evidence and emit a fail-closed PR readiness report."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pr_readiness import classify_pull_request, explicit_dependencies


class GitHubAPI:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.owner, self.name = repo.split("/", 1)
        self.rate_limit: dict = {}

    def request(self, method: str, path: str, payload: dict | None = None):
        url = "https://api.github.com" + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ag-pr-readiness-audit",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                self._capture_rate(response.headers)
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            self._capture_rate(exc.headers)
            message = exc.read(2048).decode("utf-8", "replace")
            # API messages are useful evidence; credentials are never included in the output.
            raise RuntimeError(f"GitHub API HTTP {exc.code}: {message[:500]}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"GitHub API network failure: {type(exc).__name__}") from None

    def _capture_rate(self, headers):
        for key in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"):
            if headers.get(key) is not None:
                self.rate_limit[key.lower()] = headers.get(key)

    def paged(self, path: str) -> list:
        result = []
        page = 1
        while True:
            delimiter = "&" if "?" in path else "?"
            rows = self.request("GET", f"{path}{delimiter}per_page=100&page={page}")
            if not isinstance(rows, list):
                raise RuntimeError(f"Expected list response for {path}")
            result.extend(rows)
            if len(rows) < 100:
                return result
            page += 1

    def review_thread_count(self, number: int) -> int:
        query = "query($owner:String!,$name:String!,$number:Int!,$cursor:String){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100,after:$cursor){nodes{isResolved}pageInfo{hasNextPage endCursor}}}}}"
        count, cursor = 0, None
        while True:
            result = self.request("POST", "/graphql", {"query": query, "variables": {
                "owner": self.owner, "name": self.name, "number": number, "cursor": cursor,
            }})
            if result.get("errors"):
                raise RuntimeError("GraphQL review thread query failed")
            connection = result["data"]["repository"]["pullRequest"]["reviewThreads"]
            count += sum(1 for thread in connection["nodes"] if not thread["isResolved"])
            if not connection["pageInfo"]["hasNextPage"]:
                return count
            cursor = connection["pageInfo"]["endCursor"]


def _token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(["gh", "auth", "token"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("No GitHub token available; set GH_TOKEN or authenticate gh") from None
    return result.stdout.strip()


def audit(repo: str) -> dict:
    api = GitHubAPI(_token(), repo)
    main = api.request("GET", f"/repos/{repo}/git/ref/heads/main")
    main_sha = main["object"]["sha"]
    listed = api.paged(f"/repos/{repo}/pulls?state=open")
    records = []
    errors = []
    for item in listed:
        number = item.get("number")
        record = {
            "number": number, "title": item.get("title"), "body": item.get("body"),
            "draft": item.get("draft"), "labels": [x.get("name", "") for x in item.get("labels", [])],
            "base_ref": (item.get("base") or {}).get("ref"),
            "base_sha": (item.get("base") or {}).get("sha"),
            "main_sha": main_sha,
            "head_sha": (item.get("head") or {}).get("sha"),
            "issue_comments": [],
            "paths": [], "dependencies": explicit_dependencies(item.get("title") or "", item.get("body") or ""),
            "dependency_states": {}, "data_complete": False,
        }
        try:
            detail = api.request("GET", f"/repos/{repo}/pulls/{number}")
            record["base_ref"] = detail["base"]["ref"]
            record["base_sha"] = detail["base"]["sha"]
            record["head_sha"] = detail["head"]["sha"]
            files = api.paged(f"/repos/{repo}/pulls/{number}/files")
            record["paths"] = [f["filename"] for f in files]
            reviews = api.paged(f"/repos/{repo}/pulls/{number}/reviews")
            comments = api.paged(f"/repos/{repo}/issues/{number}/comments")
            record["issue_comments"] = [str(comment.get("body") or "") for comment in comments]
            latest_by_user = {}
            for review in reviews:
                login = (review.get("user") or {}).get("login")
                if login:
                    latest_by_user[login] = review.get("state", "")
            record["data"] = {
                "mergeable": detail.get("mergeable"), "mergeable_state": detail.get("mergeable_state"),
                "unresolved_review_threads": api.review_thread_count(number),
                "changes_requested": any(state == "CHANGES_REQUESTED" for state in latest_by_user.values()),
                "approvals": sum(1 for state in latest_by_user.values() if state == "APPROVED"),
            }
            check_runs = api.request("GET", f"/repos/{repo}/commits/{record['head_sha']}/check-runs").get("check_runs", [])
            statuses = api.request("GET", f"/repos/{repo}/commits/{record['head_sha']}/status").get("statuses", [])
            from pr_readiness import checks_state
            record["data"]["checks_state"] = checks_state(check_runs, statuses)
            for dep in record["dependencies"]:
                dependency = next((p for p in listed if p.get("number") == dep), None)
                if dependency:
                    record["dependency_states"][str(dep)] = "OPEN"
                else:
                    dep_details = api.request("GET", f"/repos/{repo}/pulls/{dep}")
                    record["dependency_states"][str(dep)] = "MERGED" if dep_details.get("merged") else "CLOSED"
            record["data_complete"] = True
        except Exception as exc:  # preserve a per-PR fail-closed result
            record["error"] = str(exc)
            errors.append({"number": number, "error": str(exc)})
        records.append(record)

    report_prs = []
    for record in records:
        result = classify_pull_request(record, records)
        result.update({"title": record.get("title"), "url": f"https://github.com/{repo}/pull/{record['number']}",
                       "head_sha": record.get("head_sha"), "base_ref": record.get("base_ref"), "base_sha": record.get("base_sha"),
                       "paths": record.get("paths", []), "labels": record.get("labels", []),
                       "error": record.get("error")})
        report_prs.append(result)
    main_after = api.request("GET", f"/repos/{repo}/git/ref/heads/main")["object"]["sha"]
    if main_after != main_sha:
        errors.append({"number": None, "error": "main advanced during the audit; rerun against a stable base"})
    return {
        "schema": "AG_PR_MERGE_READINESS_V1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": repo, "main_sha": main_sha, "main_sha_after": main_after, "api_rate_limit": api.rate_limit,
        "audit_errors": errors, "pull_requests": report_prs,
        "merge_authorized": False,
    }


def markdown(report: dict) -> str:
    lines = ["# PR merge readiness audit", "", f"- Repository: `{report['repository']}`",
             f"- Main SHA: `{report['main_sha']}`", f"- Generated: {report['generated_at']}",
             "- This report is advisory. Merge authorization: **false**.", "", "| PR | Classification | Reasons |", "|---:|---|---|"]
    for pr in report["pull_requests"]:
        lines.append(f"| [#{pr['number']}]({pr['url']}) | {pr['classification']} | {', '.join(pr['reasons'])} |")
    if report["audit_errors"]:
        lines += ["", "## Incomplete evidence"]
        lines += [f"- PR #{row['number']}: {row['error']}" for row in report["audit_errors"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="aungmyat1/AG-profit-trading-assit")
    parser.add_argument("--json", type=Path, default=Path("pr-merge-readiness.json"))
    parser.add_argument("--markdown", type=Path, default=Path("pr-merge-readiness.md"))
    args = parser.parse_args()
    try:
        report = audit(args.repo)
    except Exception as exc:
        print(f"AUDIT_FAILED: {exc}", file=sys.stderr)
        return 2
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(f"main_sha={report['main_sha']} open_prs={len(report['pull_requests'])} audit_errors={len(report['audit_errors'])}")
    return 2 if report["audit_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
