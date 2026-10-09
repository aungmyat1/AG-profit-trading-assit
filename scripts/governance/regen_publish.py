"""Publish regenerated files through the dedicated bot PR (AG_REGEN_OUTCOME_V1); never push main.

    python scripts/governance/regen_publish.py --target-sha <sha> --correlation-id <id> --out regen-outcome.json

Run after the generators in a checkout of ``target_sha``. Always writes an outcome (also on
failure) and exits non-zero only for REGEN_FAILED. The only ref this script ever pushes is
``refs/heads/regen/generated-files``, with an explicit lease on the head it observed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regen_contract import (  # noqa: E402
    GENERATED_PATHS, REGEN_BRANCH, REGEN_FAILED, REGEN_NO_CHANGE, REGEN_PENDING_REVIEW,
    REGEN_PR_CREATED, REGEN_PR_UPDATED, SHA, build_outcome, validate_outcome,
)

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
PUSH_REFSPEC = f"HEAD:refs/heads/{REGEN_BRANCH}"


class RegenError(RuntimeError):
    pass


def title_for(target_sha: str) -> str:
    return f"chore(docs): regenerate generated files for {target_sha}"


class Git:
    def __init__(self, cwd: Path):
        self.cwd = cwd

    def __call__(self, *args: str, check: bool = True) -> str:
        done = subprocess.run(["git", *args], cwd=self.cwd, capture_output=True, text=True)
        if check and done.returncode:
            raise RegenError(f"git {args[0]} failed: {done.stderr.strip()[:300]}")
        return done.stdout.strip() if done.returncode == 0 else ""

    def remote_sha(self, ref: str) -> str | None:
        out = self("ls-remote", "origin", f"refs/heads/{ref}")
        return out.split()[0] if out else None


class GhPulls:
    """The only GitHub API surface the publisher needs (gh CLI; GH_TOKEN from the workflow)."""

    def __init__(self, repo: str):
        self.repo = repo

    def _gh(self, *args: str) -> str:
        done = subprocess.run(["gh", *args, "-R", self.repo], capture_output=True, text=True)
        if done.returncode:
            raise RegenError(f"gh {args[0]} {args[1]} failed: {done.stderr.strip()[:300]}")
        return done.stdout.strip()

    def open_regen_prs(self) -> list[dict]:
        return json.loads(self._gh("pr", "list", "--state", "open", "--head", REGEN_BRANCH,
                                   "--json", "number,title,headRefOid,author"))

    def create(self, title: str, body: str) -> int:
        url = self._gh("pr", "create", "--draft", "--base", "main", "--head", REGEN_BRANCH,
                       "--title", title, "--body", body)
        return int(url.rstrip("/").rsplit("/", 1)[-1])

    def edit(self, number: int, title: str, body: str) -> None:
        self._gh("pr", "edit", str(number), "--title", title, "--body", body)

    def dispatch_ci(self, correlation_id: str) -> None:
        # A GITHUB_TOKEN-opened PR gets no pull_request CI; run CI on the bot branch head.
        self._gh("workflow", "run", "ci.yml", "--ref", REGEN_BRANCH, "-f", f"correlation_id={correlation_id}")


def changed_paths(git: Git) -> list[str]:
    done = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                          cwd=git.cwd, capture_output=True, text=True, check=True)
    entries = done.stdout.split("\0")
    paths, i = [], 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) > 3:
            paths.append(entry[3:])
            if entry[0] in "RC":  # rename/copy: the source path follows as its own entry
                paths.append(entries[i + 1])
                i += 1
        i += 1
    return sorted(set(paths))


def _same_outputs(git: Git, ref: str) -> bool:
    for path in sorted(GENERATED_PATHS):
        remote = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=git.cwd, capture_output=True)
        local = (git.cwd / path).read_bytes() if (git.cwd / path).exists() else None
        if (remote.stdout if remote.returncode == 0 else None) != local:
            return False
    return True


def publish(git: Git, pulls, target_sha: str, correlation_id: str) -> dict:
    """Return an AG_REGEN_OUTCOME_V1 dict. Raises RegenError for fail-closed conditions."""
    if not SHA.match(target_sha):
        raise RegenError("TARGET_SHA_INVALID")
    if git("rev-parse", "HEAD") != target_sha:
        raise RegenError("CHECKOUT_NOT_TARGET_SHA")
    paths = changed_paths(git)
    unexpected = [p for p in paths if p not in GENERATED_PATHS]
    if unexpected:
        raise RegenError("UNEXPECTED_CHANGED_PATH:" + ",".join(unexpected))
    if git.remote_sha("main") != target_sha:
        raise RegenError("STALE_TARGET_SHA: main is no longer target_sha")
    if not paths:
        return build_outcome(REGEN_NO_CHANGE, target_sha, correlation_id)

    prs = pulls.open_regen_prs()
    if len(prs) > 1:
        raise RegenError("DUPLICATE_REGEN_PRS_OPEN")
    observed = git.remote_sha(REGEN_BRANCH)
    pr = prs[0] if prs else None
    if pr and pr.get("headRefOid") != observed:
        raise RegenError("REGEN_PR_HEAD_MOVED")
    if pr and observed:
        git("fetch", "--quiet", "origin", f"+refs/heads/{REGEN_BRANCH}:refs/remotes/origin/{REGEN_BRANCH}")
        parent = git("rev-parse", f"origin/{REGEN_BRANCH}^")
        if parent == target_sha and pr.get("title") == title_for(target_sha) \
                and _same_outputs(git, f"origin/{REGEN_BRANCH}"):
            return build_outcome(REGEN_PENDING_REVIEW, target_sha, correlation_id, paths,
                                 REGEN_BRANCH, pr["number"], observed)

    git("add", "--", *paths)
    git("-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}", "commit", "--quiet",
        "-m", f"{title_for(target_sha)}\n\nSource: {target_sha}\nCorrelation: {correlation_id}")
    head = git("rev-parse", "HEAD")
    # Lease on the observed bot head ("" = the branch must not exist). Never any other ref.
    git("push", "--quiet", f"--force-with-lease=refs/heads/{REGEN_BRANCH}:{observed or ''}", "origin", PUSH_REFSPEC)
    body = (f"Generated-file regeneration for `{target_sha}` (correlation `{correlation_id}`).\n\n"
            f"Changed: {', '.join(paths)}. Merge only through the owner merge gate.")
    if pr:
        pulls.edit(pr["number"], title_for(target_sha), body)
        number, status = pr["number"], REGEN_PR_UPDATED
    else:
        number, status = pulls.create(title_for(target_sha), body), REGEN_PR_CREATED
    pulls.dispatch_ci(f"regen-{head[:12]}")
    return build_outcome(status, target_sha, correlation_id, paths, REGEN_BRANCH, number, head)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    try:
        outcome = publish(Git(Path(args.root).resolve()), GhPulls(args.repo), args.target_sha, args.correlation_id)
        failures = validate_outcome(outcome, args.target_sha, args.correlation_id)
        if failures:
            raise RegenError("OUTCOME_INVALID:" + ",".join(failures))
    except RegenError as exc:
        outcome = build_outcome(REGEN_FAILED, args.target_sha, args.correlation_id, reason=str(exc))
    Path(args.out).write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{outcome['status']} {outcome.get('reason') or ''}".strip())
    return 1 if outcome["status"] == REGEN_FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
