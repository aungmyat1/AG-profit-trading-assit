"""AGP-REGEN-R5.1: regeneration publishes only through a per-source bot PR, PR before content,
fast-forward only (no force-push), never main (AG_REGEN_OUTCOME_V1)."""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "governance"))

import regen_contract as rc  # noqa: E402
from post_merge_verify import workflow_contract_failures  # noqa: E402
from regen_publish import Git, RegenError, publish, title_for  # noqa: E402


def sh(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class FakePulls:
    """Records the order of GitHub actions against the remote branch state."""

    def __init__(self, work, fail_create=False):
        self.work, self.fail_create = work, fail_create
        self.prs, self.created, self.superseded, self.ci, self.events = [], [], [], [], []

    def open_regen_prs(self):
        return list(self.prs)

    def create(self, branch, title, body):
        self.events.append(("create", Git(self.work).remote_sha(branch)))
        if self.fail_create:
            raise RegenError("gh pr create failed: HTTP 502")
        self.created.append(title)
        self.prs.append({"number": 101 + len(self.created) - 1, "title": title, "headRefName": branch,
                         "headRefOid": Git(self.work).remote_sha(branch)})
        return self.prs[-1]["number"]

    def supersede(self, number, by):
        self.superseded.append(number)
        self.prs = [p for p in self.prs if p["number"] != number]

    def dispatch_ci(self, branch, correlation_id):
        self.ci.append((branch, correlation_id))

    def sync(self):
        for pr in self.prs:
            pr["headRefOid"] = Git(self.work).remote_sha(pr["headRefName"])


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(origin)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    sh(work, "config", "user.email", "t@example.com")
    sh(work, "config", "user.name", "t")
    for path in rc.GENERATED_PATHS | {"src/app.py"}:
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_text("v1\n", encoding="utf-8")
    sh(work, "add", "-A")
    sh(work, "commit", "-qm", "base")
    sh(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    return work, origin


def head(work):
    return sh(work, "rev-parse", "HEAD")


def regen(work, content="v2\n", path="status/facts.json"):
    (work / path).write_text(content, encoding="utf-8")


def reset_to(work, sha):
    sh(work, "checkout", "-q", "--detach", sha)
    sh(work, "reset", "-q", "--hard", sha)


def advance_main(work, base, text):
    reset_to(work, base)
    (work / "src/app.py").write_text(text, encoding="utf-8")
    sh(work, "commit", "-qam", f"source {text.strip()}")
    sh(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    return head(work)


@pytest.fixture
def pushes(monkeypatch):
    """Record every push and assert none is forced or targets main."""
    seen = []
    original = Git.__call__

    def call(self, *args, **kw):
        if args and args[0] == "push":
            seen.append(args)
            assert not any(a.startswith(("--force", "-f", "+")) or ":+" in a or a.startswith("+") for a in args[1:])
            assert not any(a.endswith("refs/heads/main") or a == "main" for a in args[1:])
        return original(self, *args, **kw)
    monkeypatch.setattr(Git, "__call__", call)
    return seen


def test_no_change_publishes_nothing(repo, pushes):
    work, _ = repo
    pulls = FakePulls(work)
    out = publish(Git(work), pulls, head(work), "c1")
    assert out["status"] == rc.REGEN_NO_CHANGE and rc.validate_outcome(out, head(work), "c1") == []
    assert pushes == [] and pulls.created == []


def test_first_publication_opens_pr_on_empty_bootstrap_before_any_content(repo, pushes):
    work, _ = repo
    base = head(work)
    regen(work)
    pulls = FakePulls(work)
    out = publish(Git(work), pulls, base, "c1")
    branch = rc.regen_branch(base)
    assert out["status"] == rc.REGEN_PR_CREATED and out["branch"] == branch and out["pr_number"] == 101
    assert rc.validate_outcome(out, base, "c1") == []
    # The PR was opened while the branch held only the bootstrap: no file changes vs base.
    (_, at_create), = pulls.events
    assert sh(work, "diff", "--name-only", base, at_create) == ""
    assert sh(work, "rev-parse", f"{at_create}^") == base
    # Content was pushed afterwards, as a fast-forward on the bootstrap.
    assert sh(work, "rev-parse", f"{out['pr_head_sha']}^") == at_create
    assert sh(work, "diff", "--name-only", base, out["pr_head_sha"]) == "status/facts.json"
    assert Git(work).remote_sha("main") == base and len(pushes) == 2
    assert pulls.ci == [(branch, f"regen-{out['pr_head_sha'][:12]}")]


def test_pr_creation_failure_leaves_only_the_empty_bootstrap_and_retry_recovers(repo, pushes):
    work, _ = repo
    base = head(work)
    regen(work)
    pulls = FakePulls(work, fail_create=True)
    with pytest.raises(RegenError, match="REGEN_PR_CREATE_FAILED"):
        publish(Git(work), pulls, base, "c1")
    published = Git(work).remote_sha(rc.regen_branch(base))
    assert sh(work, "diff", "--name-only", base, published) == ""  # no unreviewed change
    pulls.fail_create = False
    out = publish(Git(work), pulls, base, "c2")
    assert out["status"] == rc.REGEN_PR_CREATED
    assert sh(work, "rev-parse", f"{out['pr_head_sha']}^") == published  # reused, fast-forward


def test_duplicate_dispatch_is_pending_review_without_push(repo, pushes):
    work, _ = repo
    base = head(work)
    regen(work)
    pulls = FakePulls(work)
    first = publish(Git(work), pulls, base, "c1")
    pulls.sync()
    count = len(pushes)
    reset_to(work, base)
    regen(work)
    again = publish(Git(work), pulls, base, "c2")
    assert again["status"] == rc.REGEN_PENDING_REVIEW and again["pr_head_sha"] == first["pr_head_sha"]
    assert again["correlation_id"] == "c2" and len(pushes) == count and len(pulls.created) == 1


def test_existing_pr_with_bootstrap_only_is_completed_as_update(repo, pushes):
    work, _ = repo
    base = head(work)
    pulls = FakePulls(work, fail_create=True)
    regen(work)
    with pytest.raises(RegenError):
        publish(Git(work), pulls, base, "c1")
    branch = rc.regen_branch(base)
    pulls.prs = [{"number": 7, "title": title_for(base), "headRefName": branch,
                  "headRefOid": Git(work).remote_sha(branch)}]
    out = publish(Git(work), pulls, base, "c2")
    assert out["status"] == rc.REGEN_PR_UPDATED and out["pr_number"] == 7


def test_main_advancement_supersedes_old_pr_and_opens_a_new_one_without_rewriting(repo, pushes):
    work, _ = repo
    base = head(work)
    regen(work)
    pulls = FakePulls(work)
    first = publish(Git(work), pulls, base, "c1")
    pulls.sync()
    new_base = advance_main(work, base, "v2\n")
    regen(work, "v3\n")
    out = publish(Git(work), pulls, new_base, "c3")
    assert out["status"] == rc.REGEN_PR_CREATED and out["branch"] == rc.regen_branch(new_base)
    assert pulls.superseded == [101]
    assert Git(work).remote_sha(rc.regen_branch(base)) == first["pr_head_sha"]  # old branch untouched


def test_stale_target_fails_closed(repo, pushes):
    work, _ = repo
    base = head(work)
    advance_main(work, base, "later\n")
    reset_to(work, base)
    regen(work)
    with pytest.raises(RegenError, match="STALE_TARGET_SHA"):
        publish(Git(work), FakePulls(work), base, "c1")
    assert pushes == []


def test_unexpected_changed_path_fails_closed(repo, pushes):
    work, _ = repo
    (work / "src/app.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RegenError, match="UNEXPECTED_CHANGED_PATH:src/app.py"):
        publish(Git(work), FakePulls(work), head(work), "c1")
    assert pushes == []


def test_concurrent_publication_is_rejected_not_overwritten(repo, pushes, monkeypatch):
    work, _ = repo
    base = head(work)
    branch = rc.regen_branch(base)
    # Another run created the branch between our check and our push.
    sh(work, "commit", "-q", "--allow-empty", "-m", "other run")
    sh(work, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    other = head(work)
    reset_to(work, base)
    regen(work)
    real = Git.remote_sha
    monkeypatch.setattr(Git, "remote_sha", lambda self, ref: None if ref == branch else real(self, ref))
    with pytest.raises(RegenError, match="git push failed"):
        publish(Git(work), FakePulls(work), base, "c1")
    assert real(Git(work), branch) == other


def test_foreign_content_on_regen_branch_fails_closed(repo, pushes):
    work, _ = repo
    base = head(work)
    (work / "src/app.py").write_text("smuggled\n", encoding="utf-8")
    sh(work, "commit", "-qam", "smuggled")
    sh(work, "push", "-q", "origin", f"HEAD:refs/heads/{rc.regen_branch(base)}")
    reset_to(work, base)
    regen(work)
    with pytest.raises(RegenError, match="REGEN_BRANCH_UNEXPECTED_PATH:src/app.py"):
        publish(Git(work), FakePulls(work), base, "c1")


def test_duplicate_open_prs_and_moved_head_fail_closed(repo, pushes):
    work, _ = repo
    base = head(work)
    regen(work)
    branch = rc.regen_branch(base)
    pulls = FakePulls(work)
    pulls.prs = [{"number": 1, "headRefName": branch}, {"number": 2, "headRefName": branch}]
    with pytest.raises(RegenError, match="DUPLICATE_REGEN_PRS_OPEN"):
        publish(Git(work), pulls, base, "c1")
    pulls.prs = [{"number": 1, "headRefName": branch, "headRefOid": "f" * 40}]
    with pytest.raises(RegenError, match="REGEN_PR_HEAD_MOVED"):
        publish(Git(work), pulls, base, "c1")


def test_sha_identity_and_push_target_guard(repo):
    work, _ = repo
    with pytest.raises(RegenError, match="TARGET_SHA_INVALID"):
        publish(Git(work), FakePulls(work), "abc", "c1")
    with pytest.raises(RegenError, match="CHECKOUT_NOT_TARGET_SHA"):
        publish(Git(work), FakePulls(work), "a" * 40, "c1")
    for target in ("main", "feature/x"):
        with pytest.raises(RegenError, match="REFUSED_PUSH_TARGET"):
            Git(work).push_fast_forward(head(work), target)


def test_publisher_source_has_no_force_or_main_push():
    source = (ROOT / "scripts/governance/regen_publish.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith(("#", '"""')))
    assert "--force" not in code and "force-with-lease" not in source
    assert "refs/heads/main" not in source


def test_regeneration_workflow_passes_merge_gate_preflight():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    regen_text = (ROOT / ".github/workflows/regenerate-generated-files.yml").read_text(encoding="utf-8")
    assert workflow_contract_failures(ci, regen_text) == []
    assert "[skip ci]" not in regen_text and "git push" not in regen_text


def test_regeneration_workflow_permissions_are_minimal():
    wf = yaml.safe_load((ROOT / ".github/workflows/regenerate-generated-files.yml").read_text(encoding="utf-8"))
    assert wf["permissions"] == {"contents": "write", "pull-requests": "write", "actions": "write"}
    assert wf["concurrency"] == {"group": "regenerate-generated-files", "cancel-in-progress": False}
    upload = [s for s in wf["jobs"]["regenerate"]["steps"] if s.get("uses", "").startswith("actions/upload-artifact")]
    assert upload and upload[0]["if"] == "always()" and upload[0]["with"]["name"] == rc.ARTIFACT_NAME
