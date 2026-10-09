"""Publish regenerated files through a per-source bot PR (AG_REGEN_OUTCOME_V1).

    python scripts/governance/regen_publish.py --repo owner/name --target-sha <sha> \
        --correlation-id <id> --out regen-outcome.json

Run after the generators in a checkout of ``target_sha``. Always writes an outcome (also on
failure) and exits non-zero only for REGEN_FAILED.

Lifecycle (no force-push, no push to main, PR before content):
1. Branch ``regen/generated-files-<target_sha>`` is created holding only an empty bootstrap
   commit on ``target_sha`` (no file changes), because GitHub cannot open a PR for a branch
   that does not exist or has no commits.
2. The draft PR is opened. If that fails, nothing but the empty bootstrap is published; the
   next run reuses the branch and retries.
3. Only then is the generated commit pushed, as a fast-forward on the observed branch head.
4. CI is dispatched for that exact head. A retry that finds the head already published
   verifies its provenance and asks GitHub for the CI state of that exact head: it dispatches
   only when no run exists (CI_NOT_DISPATCHED), reports CI_PENDING / CI_SUCCESS without
   re-dispatching, and fails closed on CI_FAILED or CI_UNKNOWN. An existing PR is never taken
   as a verified publication.
Older open regeneration PRs for other sources are superseded (comment + close), never
rewritten. Every push is a plain fast-forward, so a concurrent writer makes it fail closed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regen_permissions  # noqa: E402
from regen_permissions import Permissions, PermissionDenied  # noqa: E402
from regen_contract import (  # noqa: E402
    GENERATED_PATHS, REGEN_BRANCH_PREFIX, REGEN_FAILED, REGEN_NO_CHANGE, REGEN_PENDING_REVIEW,
    REGEN_PR_CREATED, REGEN_PR_UPDATED, SHA, build_outcome, regen_branch, validate_outcome,
)

CI_NOT_DISPATCHED = "CI_NOT_DISPATCHED"
CI_PENDING = "CI_PENDING"
CI_SUCCESS = "CI_SUCCESS"
CI_FAILED = "CI_FAILED"
CI_UNKNOWN = "CI_UNKNOWN"
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class RegenError(RuntimeError):
    pass


def title_for(target_sha: str) -> str:
    return f"chore(docs): regenerate generated files for {target_sha}"


def bootstrap_message(target_sha: str) -> str:
    return f"chore(regen): open regeneration PR for {target_sha} (no file changes)"


def ci_correlation(head_sha: str) -> str:
    return f"regen-{head_sha[:12]}"


def ci_title(head_sha: str) -> str:
    """ci.yml's run-name for a dispatched run (post_merge_verify.ci_run_name)."""
    return f"CI dispatch {ci_correlation(head_sha)}"


def classify_ci_runs(runs: list[dict], head_sha: str) -> str:
    """CI state of exactly ``head_sha`` from its correlated workflow_dispatch runs."""
    mine = [run for run in runs if run.get("headSha") == head_sha and run.get("displayTitle") == ci_title(head_sha)]
    if not mine:
        return CI_NOT_DISPATCHED
    if any(run.get("status") != "completed" for run in mine):
        return CI_PENDING
    if all(run.get("conclusion") == "success" for run in mine):
        return CI_SUCCESS
    return CI_FAILED


class Git:
    def __init__(self, cwd: Path):
        self.cwd = cwd

    def __call__(self, *args: str, check: bool = True, env: dict | None = None) -> str:
        done = subprocess.run(["git", *args], cwd=self.cwd, capture_output=True, text=True, env=env)
        if check and done.returncode:
            raise RegenError(f"git {args[0]} failed: {done.stderr.strip()[:300]}")
        return done.stdout.strip() if done.returncode == 0 else ""

    def remote_sha(self, ref: str) -> str | None:
        out = self("ls-remote", "origin", f"refs/heads/{ref}")
        return out.split()[0] if out else None

    def push_fast_forward(self, sha: str, branch: str, perms: Permissions, action: str = "push_regen_branch") -> None:
        """Plain push (no --force, no lease): rejected unless it fast-forwards the branch."""
        if action not in ("push_regen_branch", "bootstrap_push"):
            raise RegenError(f"REFUSED_PUSH_ACTION:{action}")
        perms.require(action)
        if branch == "main" or not branch.startswith(REGEN_BRANCH_PREFIX):
            raise RegenError(f"REFUSED_PUSH_TARGET:{branch}")
        self("push", "--quiet", "origin", f"{sha}:refs/heads/{branch}")


class GhPulls:
    """The only GitHub API surface the publisher needs (gh CLI; GH_TOKEN from the workflow)."""

    def __init__(self, repo: str, perms: Permissions):
        self.repo = repo
        self.perms = perms

    def _gh(self, *args: str) -> str:
        done = subprocess.run(["gh", *args, "-R", self.repo], capture_output=True, text=True)
        if done.returncode:
            raise RegenError(f"gh {args[0]} {args[1]} failed: {done.stderr.strip()[:300]}")
        return done.stdout.strip()

    def open_regen_prs(self) -> list[dict]:
        rows = json.loads(self._gh("pr", "list", "--state", "open", "--limit", "100", "--base", "main",
                                   "--json", "number,title,headRefName,headRefOid"))
        return [row for row in rows if str(row.get("headRefName", "")).startswith(REGEN_BRANCH_PREFIX)]

    def create(self, branch: str, title: str, body: str) -> int:
        self.perms.require("create_pr")
        url = self._gh("pr", "create", "--draft", "--base", "main", "--head", branch,
                       "--title", title, "--body", body)
        return int(url.rstrip("/").rsplit("/", 1)[-1])

    def supersede(self, number: int, by: str) -> None:
        self.perms.require("close_superseded_pr")
        self._gh("pr", "comment", str(number), "--body", f"Superseded: {by}. This branch is left unmodified.")
        self._gh("pr", "close", str(number))

    def ci_state(self, branch: str, head_sha: str) -> str:
        try:
            runs = json.loads(self._gh("run", "list", "--workflow", "ci.yml", "--branch", branch,
                                       "--event", "workflow_dispatch", "--limit", "100",
                                       "--json", "headSha,status,conclusion,displayTitle"))
        except (RegenError, ValueError):
            return CI_UNKNOWN
        return classify_ci_runs(runs, head_sha) if isinstance(runs, list) else CI_UNKNOWN

    def dispatch_ci(self, branch: str, correlation_id: str) -> None:
        # A GITHUB_TOKEN-opened PR gets no pull_request CI; run CI on the bot branch head.
        self.perms.require("dispatch_ci")
        self._gh("workflow", "run", "ci.yml", "--ref", branch, "-f", f"correlation_id={correlation_id}")


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


def _commit(git: Git, tree: str, parent: str, message: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": BOT_NAME, "GIT_AUTHOR_EMAIL": BOT_EMAIL,
           "GIT_COMMITTER_NAME": BOT_NAME, "GIT_COMMITTER_EMAIL": BOT_EMAIL}
    return git("commit-tree", tree, "-p", parent, "-m", message, env=env)


def _verify_branch(git: Git, branch: str, head: str, target_sha: str) -> None:
    """An existing branch must descend from target_sha and differ from it only in outputs."""
    git("fetch", "--quiet", "origin", f"refs/heads/{branch}")
    if subprocess.run(["git", "merge-base", "--is-ancestor", target_sha, head], cwd=git.cwd).returncode:
        raise RegenError("REGEN_BRANCH_NOT_ON_TARGET")
    extra = set(git("diff", "--name-only", target_sha, head).splitlines()) - GENERATED_PATHS
    if extra:
        raise RegenError("REGEN_BRANCH_UNEXPECTED_PATH:" + ",".join(sorted(extra)))


def _verify_provenance(git: Git, target_sha: str, head: str) -> None:
    """Every bot-branch commit is the bootstrap or a generated commit for exactly target_sha."""
    for line in git("log", "--format=%H%x00%an%x00%B%x1e", f"{target_sha}..{head}").split("\x1e"):
        if not line.strip():
            continue
        sha, author, message = line.strip().split("\x00", 2)
        generated = message.startswith(title_for(target_sha)) and f"Source: {target_sha}" in message
        if author != BOT_NAME or not (generated or message.strip() == bootstrap_message(target_sha)):
            raise RegenError(f"REGEN_BRANCH_PROVENANCE_INVALID:{sha[:12]}")
    if git("log", "-1", "--format=%B", head).strip() == bootstrap_message(target_sha):
        raise RegenError("REGEN_BRANCH_HEAD_IS_BOOTSTRAP")


def _supersede_others(pulls, others: list[dict], by: str, perms: Permissions) -> None:
    if not perms.allows("close_superseded_pr"):
        return  # denied: stale bot PRs stay untouched; the readiness audit holds them
    for pr in others:
        pulls.supersede(pr["number"], by)


def publish(git: Git, pulls, target_sha: str, correlation_id: str, perms: Permissions | None = None) -> dict:
    """Return an AG_REGEN_OUTCOME_V1 dict. Raises RegenError for fail-closed conditions.

    ``perms`` defaults to the committed allowlist; every side effect is checked against it.
    """
    perms = perms if perms is not None else regen_permissions.load()
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

    branch = regen_branch(target_sha)
    open_prs = pulls.open_regen_prs()
    mine = [pr for pr in open_prs if pr.get("headRefName") == branch]
    others = [pr for pr in open_prs if pr.get("headRefName") != branch]
    if not paths:
        _supersede_others(pulls, others, f"regeneration at {target_sha} found no change", perms)
        return build_outcome(REGEN_NO_CHANGE, target_sha, correlation_id)
    if len(mine) > 1:
        raise RegenError("DUPLICATE_REGEN_PRS_OPEN")
    pr = mine[0] if mine else None
    observed = git.remote_sha(branch)
    if pr and pr.get("headRefOid") != observed:
        raise RegenError("REGEN_PR_HEAD_MOVED")

    if observed is None:
        if not perms.allows("bootstrap_push"):
            raise RegenError("REGEN_BOOTSTRAP_DENIED: pushing a branch before its PR exists is not "
                             "allowlisted (REG-REGEN-BOOTSTRAP); the owner must open the regeneration PR")
        bootstrap = _commit(git, git("rev-parse", f"{target_sha}^{{tree}}"), target_sha,
                            bootstrap_message(target_sha))
        git.push_fast_forward(bootstrap, branch, perms, "bootstrap_push")  # rejected if a concurrent run created the branch
        observed = bootstrap
    else:
        _verify_branch(git, branch, observed, target_sha)

    created = False
    if pr is None:
        body = (f"Generated-file regeneration for `{target_sha}` (correlation `{correlation_id}`).\n\n"
                f"Changed: {', '.join(paths)}. Merge only through the owner merge gate.")
        perms.require("create_pr")
        try:
            number = pulls.create(branch, title_for(target_sha), body)
        except RegenError as exc:
            # Only the empty bootstrap (or an earlier reviewed commit) is published; retry reuses it.
            raise RegenError(f"REGEN_PR_CREATE_FAILED: {exc}") from None
        created = True
    else:
        number = pr["number"]

    git("fetch", "--quiet", "origin", f"refs/heads/{branch}")
    if _same_outputs(git, observed):
        head = observed
        _verify_provenance(git, target_sha, head)  # already published: prove it, never assume it
        ci = pulls.ci_state(branch, head)
    else:
        git("add", "--", *paths)
        head = _commit(git, git("write-tree"), observed,
                       f"{title_for(target_sha)}\n\nSource: {target_sha}\nCorrelation: {correlation_id}")
        git.push_fast_forward(head, branch, perms)
        ci = CI_NOT_DISPATCHED
    _supersede_others(pulls, others, f"#{number} regenerates the newer source {target_sha}", perms)
    if ci == CI_FAILED:
        raise RegenError(f"REGEN_PR_CI_FAILED: CI failed on {head}; not re-dispatched")
    if ci == CI_UNKNOWN:
        raise RegenError(f"REGEN_PR_CI_UNKNOWN: cannot establish CI state of {head}")
    if ci == CI_NOT_DISPATCHED:
        perms.require("dispatch_ci")
        try:
            pulls.dispatch_ci(branch, ci_correlation(head))
        except RegenError as exc:
            # The content is published on the PR; the next run finds it and dispatches again.
            raise RegenError(f"REGEN_CI_DISPATCH_FAILED: {exc}") from None
        ci = CI_PENDING
    pushed = head != observed
    status = REGEN_PR_CREATED if created else REGEN_PR_UPDATED if pushed else REGEN_PENDING_REVIEW
    return build_outcome(status, target_sha, correlation_id, paths, branch, number, head, ci_state=ci)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    try:
        perms = regen_permissions.load()
        outcome = publish(Git(Path(args.root).resolve()), GhPulls(args.repo, perms), args.target_sha,
                          args.correlation_id, perms)
        failures = validate_outcome(outcome, args.target_sha, args.correlation_id)
        if failures:
            raise RegenError("OUTCOME_INVALID:" + ",".join(failures))
    except (RegenError, PermissionDenied) as exc:
        outcome = build_outcome(REGEN_FAILED, args.target_sha, args.correlation_id, reason=str(exc))
    Path(args.out).write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{outcome['status']} {outcome.get('reason') or ''}".strip())
    return 1 if outcome["status"] == REGEN_FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
