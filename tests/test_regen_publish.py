"""AGP-GITHUB-INTEGRATION-R5: regeneration publishes only through the bot PR (AG_REGEN_OUTCOME_V1)."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "governance"))

import regen_contract as rc  # noqa: E402
from post_merge_verify import workflow_contract_failures  # noqa: E402
from regen_publish import Git, RegenError, publish, title_for  # noqa: E402


def sh(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class FakePulls:
    def __init__(self):
        self.prs, self.created, self.edited, self.ci = [], [], [], []

    def open_regen_prs(self):
        return list(self.prs)

    def create(self, title, body):
        self.created.append(title)
        return 101

    def edit(self, number, title, body):
        self.edited.append((number, title))

    def dispatch_ci(self, correlation_id):
        self.ci.append(correlation_id)


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


def target(work):
    return sh(work, "rev-parse", "HEAD")


def regen(work, content="v2\n", path="status/facts.json"):
    (work / path).write_text(content, encoding="utf-8")


def reset_to(work, sha):
    sh(work, "checkout", "-q", "--detach", sha)
    sh(work, "reset", "-q", "--hard", sha)


def test_no_change_is_no_change_and_publishes_nothing(repo):
    work, origin = repo
    pulls = FakePulls()
    out = publish(Git(work), pulls, target(work), "c1")
    assert out["status"] == rc.REGEN_NO_CHANGE and rc.validate_outcome(out, target(work), "c1") == []
    assert pulls.created == [] and Git(work).remote_sha(rc.REGEN_BRANCH) is None


def test_changed_output_creates_bot_branch_and_pr_never_main(repo):
    work, origin = repo
    base = target(work)
    regen(work)
    pulls = FakePulls()
    out = publish(Git(work), pulls, base, "c1")
    assert out["status"] == rc.REGEN_PR_CREATED and out["pr_number"] == 101
    assert out["changed_paths"] == ["status/facts.json"] and rc.validate_outcome(out, base, "c1") == []
    assert Git(work).remote_sha("main") == base  # main untouched
    bot = Git(work).remote_sha(rc.REGEN_BRANCH)
    assert out["pr_head_sha"] == bot and sh(work, "rev-parse", f"{bot}^") == base
    assert pulls.created == [title_for(base)] and pulls.ci


def test_identical_redispatch_is_pending_review_without_push(repo):
    work, origin = repo
    base = target(work)
    regen(work)
    pulls = FakePulls()
    first = publish(Git(work), pulls, base, "c1")
    pulls.prs = [{"number": 101, "title": title_for(base), "headRefOid": first["pr_head_sha"]}]
    reset_to(work, base)
    regen(work)
    again = publish(Git(work), pulls, base, "c2")
    assert again["status"] == rc.REGEN_PENDING_REVIEW and again["pr_head_sha"] == first["pr_head_sha"]
    assert again["correlation_id"] == "c2" and pulls.edited == [] and len(pulls.created) == 1


def test_new_source_updates_the_one_pr_with_lease(repo):
    work, origin = repo
    base = target(work)
    regen(work)
    pulls = FakePulls()
    first = publish(Git(work), pulls, base, "c1")
    pulls.prs = [{"number": 101, "title": title_for(base), "headRefOid": first["pr_head_sha"]}]
    reset_to(work, base)
    (work / "src/app.py").write_text("v2\n", encoding="utf-8")
    sh(work, "commit", "-qam", "source change")
    sh(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    new_base = target(work)
    regen(work, "v3\n")
    out = publish(Git(work), pulls, new_base, "c3")
    assert out["status"] == rc.REGEN_PR_UPDATED and out["pr_number"] == 101
    assert sh(work, "rev-parse", f"{out['pr_head_sha']}^") == new_base
    assert pulls.edited == [(101, title_for(new_base))] and len(pulls.created) == 1


def test_stale_target_fails_closed(repo):
    work, origin = repo
    base = target(work)
    (work / "src/app.py").write_text("later\n", encoding="utf-8")
    sh(work, "commit", "-qam", "later")
    sh(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    reset_to(work, base)
    regen(work)
    with pytest.raises(RegenError, match="STALE_TARGET_SHA"):
        publish(Git(work), FakePulls(), base, "c1")


def test_unexpected_changed_path_fails_closed(repo):
    work, origin = repo
    (work / "src/app.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RegenError, match="UNEXPECTED_CHANGED_PATH:src/app.py"):
        publish(Git(work), FakePulls(), target(work), "c1")


def test_duplicate_open_prs_and_moved_pr_head_fail_closed(repo):
    work, origin = repo
    regen(work)
    pulls = FakePulls()
    pulls.prs = [{"number": 1}, {"number": 2}]
    with pytest.raises(RegenError, match="DUPLICATE_REGEN_PRS_OPEN"):
        publish(Git(work), pulls, target(work), "c1")
    pulls.prs = [{"number": 1, "title": "x", "headRefOid": "f" * 40}]
    with pytest.raises(RegenError, match="REGEN_PR_HEAD_MOVED"):
        publish(Git(work), pulls, target(work), "c1")


def test_checkout_and_sha_identity(repo):
    work, origin = repo
    with pytest.raises(RegenError, match="TARGET_SHA_INVALID"):
        publish(Git(work), FakePulls(), "abc", "c1")
    with pytest.raises(RegenError, match="CHECKOUT_NOT_TARGET_SHA"):
        publish(Git(work), FakePulls(), "a" * 40, "c1")


def test_regeneration_workflow_passes_merge_gate_preflight():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    regen_text = (ROOT / ".github/workflows/regenerate-generated-files.yml").read_text(encoding="utf-8")
    assert workflow_contract_failures(ci, regen_text) == []
    publisher = (ROOT / "scripts/governance/regen_publish.py").read_text(encoding="utf-8")
    assert "refs/heads/main" not in publisher and "[skip ci]" not in regen_text


def test_regeneration_workflow_permissions_are_minimal():
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/regenerate-generated-files.yml").read_text(encoding="utf-8"))
    assert wf["permissions"] == {"contents": "write", "pull-requests": "write", "actions": "write"}
    assert wf["concurrency"] == {"group": "regenerate-generated-files", "cancel-in-progress": False}
    upload = [s for s in wf["jobs"]["regenerate"]["steps"] if s.get("uses", "").startswith("actions/upload-artifact")]
    assert upload and upload[0]["if"] == "always()" and upload[0]["with"]["name"] == rc.ARTIFACT_NAME
