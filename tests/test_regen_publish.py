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
import regen_permissions as rperm  # noqa: E402
import regen_publish as rp  # noqa: E402
from post_merge_verify import workflow_contract_failures  # noqa: E402
from regen_publish import Git, RegenError, publish, title_for  # noqa: E402


def sh(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class FakePulls:
    """Records the order of GitHub actions against the remote branch state."""

    def __init__(self, work, fail_create=False):
        self.work, self.fail_create = work, fail_create
        self.prs, self.created, self.superseded, self.ci, self.events = [], [], [], [], []
        self.runs, self.fail_dispatch, self.ci_unknown = [], False, False

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

    def ci_state(self, branch, head_sha):
        return rp.CI_UNKNOWN if self.ci_unknown else rp.classify_ci_runs(self.runs, head_sha)

    def dispatch_ci(self, branch, correlation_id):
        if self.fail_dispatch:
            raise RegenError("gh workflow run failed: HTTP 500")
        self.ci.append((branch, correlation_id))
        head_sha = Git(self.work).remote_sha(branch)
        assert correlation_id == rp.ci_correlation(head_sha)
        self.runs.append({"headSha": head_sha, "displayTitle": rp.ci_title(head_sha),
                          "status": "queued", "conclusion": None})

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


ALL = rperm.Permissions(rperm.ACTIONS)


@pytest.fixture(autouse=True)
def granted(monkeypatch, request):
    """Lifecycle tests run with every action allowlisted; deny tests (@pytest.mark.denied) use the
    committed config/governance/regen_permissions.json."""
    if "denied" not in request.keywords:
        monkeypatch.setattr(rperm, "load", lambda path=None: ALL)


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
    assert again["ci_state"] == rp.CI_PENDING and len(pulls.ci) == 1  # no duplicate dispatch


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
            Git(work).push_fast_forward(head(work), target, ALL)


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


# R5.2: interrupted publication recovery -----------------------------------------------------
def _published_then(work, pulls, base):
    """Publish once; return the first outcome (or None if it raised) and the remote head."""
    regen(work)
    try:
        first = publish(Git(work), pulls, base, "c1")
    except RegenError:
        first = None
    pulls.sync()
    return first, Git(work).remote_sha(rc.regen_branch(base))


def _retry(work, pulls, base, correlation="c2"):
    reset_to(work, base)
    regen(work)
    return publish(Git(work), pulls, base, correlation)


def test_push_succeeds_dispatch_fails_then_retry_dispatches_exact_head_without_new_commit(repo, pushes):
    work, _ = repo
    base = head(work)
    pulls = FakePulls(work)
    pulls.fail_dispatch = True
    regen(work)
    with pytest.raises(RegenError, match="REGEN_CI_DISPATCH_FAILED"):
        publish(Git(work), pulls, base, "c1")
    pulls.sync()
    published = Git(work).remote_sha(rc.regen_branch(base))
    count = len(pushes)
    pulls.fail_dispatch = False
    out = _retry(work, pulls, base)
    assert out["status"] == rc.REGEN_PENDING_REVIEW and out["pr_head_sha"] == published
    assert out["ci_state"] == rp.CI_PENDING
    assert pulls.ci == [(rc.regen_branch(base), rp.ci_correlation(published))]
    assert len(pushes) == count and len(pulls.created) == 1  # no new commit, no new PR


def test_process_stopped_after_push_before_dispatch_is_recovered(repo, pushes, monkeypatch):
    work, _ = repo
    base = head(work)
    pulls = FakePulls(work)

    def crash(*a, **k):
        raise KeyboardInterrupt("runner lost")
    monkeypatch.setattr(pulls, "dispatch_ci", crash)
    with pytest.raises(KeyboardInterrupt):
        _published_then(work, pulls, base)
    monkeypatch.undo()
    pulls.sync()
    published = Git(work).remote_sha(rc.regen_branch(base))
    out = _retry(work, pulls, base)
    assert out["pr_head_sha"] == published and out["ci_state"] == rp.CI_PENDING
    assert [corr for _, corr in pulls.ci] == [rp.ci_correlation(published)]


@pytest.mark.parametrize("status,conclusion,state", [
    ("in_progress", None, rp.CI_PENDING), ("completed", "success", rp.CI_SUCCESS)])
def test_retry_with_ci_running_or_green_does_not_redispatch(repo, pushes, status, conclusion, state):
    work, _ = repo
    base = head(work)
    pulls = FakePulls(work)
    first, published = _published_then(work, pulls, base)
    pulls.runs[0].update(status=status, conclusion=conclusion)
    out = _retry(work, pulls, base)
    assert out["status"] == rc.REGEN_PENDING_REVIEW and out["ci_state"] == state and len(pulls.ci) == 1


def test_retry_with_failed_or_unknown_ci_fails_closed_without_redispatch(repo, pushes):
    work, _ = repo
    base = head(work)
    pulls = FakePulls(work)
    _published_then(work, pulls, base)
    pulls.runs[0].update(status="completed", conclusion="failure")
    with pytest.raises(RegenError, match="REGEN_PR_CI_FAILED"):
        _retry(work, pulls, base)
    pulls.runs[0].update(conclusion="success")
    pulls.ci_unknown = True
    with pytest.raises(RegenError, match="REGEN_PR_CI_UNKNOWN"):
        _retry(work, pulls, base)
    assert len(pulls.ci) == 1


def test_ci_runs_for_other_heads_or_titles_do_not_count():
    sha = "a" * 40
    other = {"headSha": "b" * 40, "displayTitle": rp.ci_title("b" * 40), "status": "completed", "conclusion": "success"}
    wrong_title = {"headSha": sha, "displayTitle": "CI dispatch something-else", "status": "completed",
                   "conclusion": "success"}
    assert rp.classify_ci_runs([other, wrong_title], sha) == rp.CI_NOT_DISPATCHED
    from post_merge_verify import ci_run_name
    assert rp.ci_title(sha) == ci_run_name(rp.ci_correlation(sha))


def test_retry_rejects_published_head_with_wrong_source_or_foreign_author(repo, pushes):
    work, _ = repo
    base = head(work)
    pulls = FakePulls(work, fail_create=True)
    regen(work)
    with pytest.raises(RegenError):
        publish(Git(work), pulls, base, "c1")  # leaves the bootstrap only
    branch = rc.regen_branch(base)
    boot = Git(work).remote_sha(branch)
    # A generated-looking commit that names the wrong source SHA.
    reset_to(work, boot)
    regen(work)
    env_bot = ["-c", f"user.name={rp.BOT_NAME}", "-c", f"user.email={rp.BOT_EMAIL}"]
    subprocess.run(["git", *env_bot, "commit", "-qam", f"{title_for(base)}\n\nSource: {'c' * 40}"],
                   cwd=work, check=True)
    sh(work, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    pulls.fail_create = False
    pulls.prs = [{"number": 9, "title": title_for(base), "headRefName": branch,
                  "headRefOid": Git(work).remote_sha(branch)}]
    with pytest.raises(RegenError, match="REGEN_BRANCH_PROVENANCE_INVALID"):
        _retry(work, pulls, base)
    assert pulls.ci == []


# R6B: default-deny allowlist -------------------------------------------------------------------
def _config(tmp_path, body):
    path = tmp_path / "perms.json"
    path.write_text(body if isinstance(body, str) else __import__("json").dumps(body), encoding="utf-8")
    return path


@pytest.mark.denied
def test_missing_or_invalid_config_denies_every_action(tmp_path):
    cases = [tmp_path / "absent.json", _config(tmp_path, "{not json"),
             _config(tmp_path, {"schema": "OTHER", "allow": list(rperm.ACTIONS)}),
             _config(tmp_path, {"schema": rperm.SCHEMA, "allow": "create_pr"}),
             _config(tmp_path, {"schema": rperm.SCHEMA, "allow": ["create_pr", "merge_pr"]})]
    for path in cases:
        perms = rperm.load(path)
        assert perms.error and not any(perms.allows(a) for a in rperm.ACTIONS)
        with pytest.raises(rperm.PermissionDenied):
            perms.require("create_pr")


@pytest.mark.denied
def test_unlisted_action_denied_and_listed_action_permitted(tmp_path):
    perms = rperm.load(_config(tmp_path, {"schema": rperm.SCHEMA, "allow": ["dispatch_ci"]}))
    assert perms.allows("dispatch_ci")
    perms.require("dispatch_ci")
    for action in rperm.ACTIONS - {"dispatch_ci"}:
        assert not perms.allows(action)
    assert not perms.allows("merge_pr")  # not a known action at all


@pytest.mark.denied
def test_committed_config_denies_pending_owner_actions():
    perms = rperm.load()
    assert perms.error is None
    assert perms.allowed == {"push_regen_branch", "create_pr", "dispatch_ci"}
    assert not perms.allows("bootstrap_push") and not perms.allows("close_superseded_pr")


MUTATING = [("create", ("regen/generated-files-" + "a" * 40, "t", "b"), "create_pr"),
            ("supersede", (5, "by"), "close_superseded_pr"),
            ("dispatch_ci", ("regen/generated-files-" + "a" * 40, "c"), "dispatch_ci")]


@pytest.mark.parametrize("method,args,action", MUTATING)
def test_gh_mutations_never_reach_github_without_their_allowlist_entry(monkeypatch, method, args, action):
    calls = []
    pulls = rp.GhPulls("o/r", rperm.Permissions(rperm.ACTIONS - {action}))
    monkeypatch.setattr(pulls, "_gh", lambda *a: calls.append(a) or "https://x/pull/1")
    with pytest.raises(rperm.PermissionDenied, match=action):
        getattr(pulls, method)(*args)
    assert calls == []
    allowed = rp.GhPulls("o/r", rperm.Permissions({action}))
    monkeypatch.setattr(allowed, "_gh", lambda *a: calls.append(a) or "https://x/pull/1")
    getattr(allowed, method)(*args)
    assert calls  # the allowlisted action does reach the API


def test_every_mutating_gh_call_sits_behind_a_permission_check():
    """Static proof: in regen_publish, any `gh pr <mutating>` / `gh workflow run` / `gh api` call is
    in a method whose first statement is self.perms.require(...); no other governance or workflow
    file calls a PR-mutating gh command."""
    import ast
    source = (ROOT / "scripts/governance/regen_publish.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    mutating = {("pr", v) for v in ("create", "comment", "close", "edit", "merge", "ready", "reopen")}
    mutating |= {("workflow", "run"), ("api", None)}
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GhPulls")
    for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
        for call in [n for n in ast.walk(fn) if isinstance(n, ast.Call)]:
            if getattr(call.func, "attr", "") != "_gh":
                continue
            words = [a.value for a in call.args[:2] if isinstance(a, ast.Constant)]
            key = (words[0], words[1] if len(words) > 1 else None)
            if key in mutating or (key[0] == "api"):
                first = fn.body[0].value if isinstance(fn.body[0], ast.Expr) else None
                if isinstance(first, ast.Constant):  # docstring
                    first = fn.body[1].value
                assert isinstance(first, ast.Call) and getattr(first.func, "attr", "") == "require", fn.name
    others = list((ROOT / "scripts/governance").glob("*.py")) + list((ROOT / ".github/workflows").glob("*.yml"))
    import re
    pattern = re.compile(r"gh\W+pr\W+(create|comment|close|edit|merge|ready|reopen)|pr['\"],\s*['\"](comment|close|edit)")
    for path in others:
        if path.name in ("regen_publish.py", "manual-pr-merge.yml"):
            continue  # manual-pr-merge is the owner-gated merge path, not regeneration
        assert not pattern.search(path.read_text(encoding="utf-8")), path


def test_pushes_require_their_allowlist_entry(repo):
    work, _ = repo
    branch = rc.regen_branch(head(work))
    with pytest.raises(rperm.PermissionDenied, match="push_regen_branch"):
        Git(work).push_fast_forward(head(work), branch, rperm.Permissions())
    with pytest.raises(rperm.PermissionDenied, match="bootstrap_push"):
        Git(work).push_fast_forward(head(work), branch, rperm.Permissions({"push_regen_branch"}), "bootstrap_push")
    with pytest.raises(RegenError, match="REFUSED_PUSH_ACTION"):
        Git(work).push_fast_forward(head(work), branch, ALL, "anything")
    assert Git(work).remote_sha(branch) is None


@pytest.mark.denied
def test_committed_config_blocks_bootstrap_without_any_push(repo, pushes):
    work, _ = repo
    base = head(work)
    regen(work)
    pulls = FakePulls(work)
    with pytest.raises(RegenError, match="REGEN_BOOTSTRAP_DENIED"):
        publish(Git(work), pulls, base, "c1")
    assert pushes == [] and pulls.created == [] and Git(work).remote_sha(rc.regen_branch(base)) is None


@pytest.mark.denied
def test_committed_config_leaves_stale_bot_prs_untouched(repo, pushes):
    work, _ = repo
    pulls = FakePulls(work)
    pulls.prs = [{"number": 5, "headRefName": rc.regen_branch("d" * 40), "headRefOid": "d" * 40}]
    out = publish(Git(work), pulls, head(work), "c1")
    assert out["status"] == rc.REGEN_NO_CHANGE and pulls.superseded == [] and len(pulls.prs) == 1


@pytest.mark.parametrize("missing,match", [("create_pr", "create_pr"), ("dispatch_ci", "dispatch_ci"),
                                           ("push_regen_branch", "push_regen_branch")])
def test_publish_fails_closed_when_a_needed_action_is_not_allowlisted(repo, pushes, missing, match):
    work, _ = repo
    base = head(work)
    regen(work)
    pulls = FakePulls(work)
    with pytest.raises(rperm.PermissionDenied, match=match):
        publish(Git(work), pulls, base, "c1", rperm.Permissions(rperm.ACTIONS - {missing}))
    if missing == "create_pr":
        assert pulls.created == []
    if missing == "dispatch_ci":
        assert pulls.ci == []


def test_main_writes_failed_outcome_on_invalid_config(tmp_path, monkeypatch, repo):
    import json
    work, _ = repo
    monkeypatch.setattr(rperm, "load", lambda path=None: rperm.Permissions(error="config unavailable: X"))
    out = tmp_path / "o.json"
    regen(work)
    code = rp.main(["--repo", "o/r", "--target-sha", head(work), "--correlation-id", "c",
                    "--out", str(out), "--root", str(work)])
    body = json.loads(out.read_text())
    assert code == 1 and body["status"] == rc.REGEN_FAILED


@pytest.mark.denied
def test_owner_manual_bootstrap_runbook_works_with_committed_allowlist(repo, pushes):
    """docs/agents/REGEN_BOOTSTRAP.md: the owner pushes the empty bootstrap and opens the PR; the
    bot then publishes content and dispatches CI with no allowlist change."""
    work, _ = repo
    base = head(work)
    branch = rc.regen_branch(base)
    subprocess.run(["git", "-c", f"user.name={rp.BOT_NAME}", "-c", f"user.email={rp.BOT_EMAIL}",
                    "commit", "-q", "--allow-empty", "-m", rp.bootstrap_message(base)], cwd=work, check=True)
    sh(work, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    pulls = FakePulls(work)
    pulls.prs = [{"number": 42, "title": title_for(base), "headRefName": branch,
                  "headRefOid": Git(work).remote_sha(branch)}]
    reset_to(work, base)
    regen(work)
    out = publish(Git(work), pulls, base, "owner-1")
    assert out["status"] == rc.REGEN_PR_UPDATED and out["pr_number"] == 42
    assert out["ci_state"] == rp.CI_PENDING and pulls.created == [] and pulls.superseded == []
    pulls.sync()
    reset_to(work, base)
    regen(work)
    again = publish(Git(work), pulls, base, "owner-2")  # retry passes provenance, no re-dispatch
    assert again["status"] == rc.REGEN_PENDING_REVIEW and len(pulls.ci) == 1
