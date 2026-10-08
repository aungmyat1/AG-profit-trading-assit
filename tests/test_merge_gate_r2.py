"""AGP-MERGE-GATE-REMEDIATION-R2: F01 review state, F02 check pagination, F03 post-merge dispatch."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "governance"))

from audit_pr_readiness import counted_pages  # noqa: E402
from post_merge_verify import (  # noqa: E402
    resolve_final_main, run_outcome, select_run, workflow_contract_failures,
)
from pr_readiness import checks_state, review_decision  # noqa: E402


def review(login, state, at):
    return {"user": {"login": login}, "state": state, "submitted_at": f"2026-10-08T0{at}:00:00Z"}


# F01 -------------------------------------------------------------------------------------
def test_later_comment_does_not_clear_changes_requested():
    reviews = [review("alice", "CHANGES_REQUESTED", 1), review("alice", "COMMENTED", 2)]
    assert review_decision(reviews) == (True, 0)


def test_later_approval_or_dismissal_clears_changes_requested():
    assert review_decision([review("alice", "CHANGES_REQUESTED", 1), review("alice", "APPROVED", 2)]) == (False, 1)
    assert review_decision([review("alice", "DISMISSED", 1), review("bob", "COMMENTED", 2)]) == (False, 0)


def test_comment_does_not_clear_approval_and_order_uses_submitted_at():
    reviews = [review("bob", "COMMENTED", 3), review("bob", "APPROVED", 1)]
    assert review_decision(reviews) == (False, 1)
    reviews = [review("bob", "CHANGES_REQUESTED", 2), review("bob", "APPROVED", 1)]
    assert review_decision(reviews) == (True, 0)


def test_unknown_review_state_fails_closed():
    assert review_decision([review("alice", "SOMETHING_NEW", 1)]) == (None, None)
    assert review_decision([{"user": None, "state": "APPROVED", "submitted_at": "x"}]) == (None, None)


# F02 -------------------------------------------------------------------------------------
def pages_of(rows, total=None, per_page_cap=None):
    calls = []

    def fetch(page, per_page):
        size = per_page_cap or per_page
        calls.append(page)
        return {"total_count": len(rows) if total is None else total,
                "check_runs": rows[(page - 1) * size: page * size]}
    return fetch, calls


def test_failing_check_on_a_later_page_is_seen():
    rows = [{"status": "completed", "conclusion": "success"}] * 34 + [{"status": "completed", "conclusion": "failure"}]
    fetch, calls = pages_of(rows, per_page_cap=30)  # server caps pages at 30 rows
    collected = counted_pages(fetch, "check_runs")
    assert len(collected) == 35 and calls == [1, 2]
    assert checks_state(collected, []) == "FAIL"
    # The pre-R2 single request saw only the first 30 rows and reported PASS.
    assert checks_state(rows[:30], []) == "PASS"


def test_incomplete_pagination_fails_closed():
    fetch, _ = pages_of([{"conclusion": "success"}] * 3, total=5)
    with pytest.raises(RuntimeError, match="pagination incomplete"):
        counted_pages(fetch, "check_runs")
    with pytest.raises(RuntimeError, match="lacks total_count"):
        counted_pages(lambda page, per_page: {"check_runs": []}, "check_runs")
    fetch, _ = pages_of([{"conclusion": "success"}] * 250, per_page_cap=100)
    with pytest.raises(RuntimeError, match="pagination incomplete"):
        counted_pages(fetch, "check_runs", max_pages=2)


def test_total_count_change_during_pagination_fails_closed():
    def fetch(page, per_page):
        return {"total_count": 150 + page, "check_runs": [{"conclusion": "success"}] * 100}
    with pytest.raises(RuntimeError, match="total_count changed"):
        counted_pages(fetch, "check_runs")


# F03 -------------------------------------------------------------------------------------
DISPATCHED = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def run(**overrides):
    base = {"id": 1, "event": "workflow_dispatch", "head_branch": "main", "head_sha": "merge",
            "created_at": "2026-10-08T12:00:05Z", "status": "completed", "conclusion": "success",
            "display_title": "regenerate at merge"}
    base.update(overrides)
    return base


def test_run_selection_binds_to_exact_sha_and_dispatch_time():
    assert select_run([run(head_sha="other")], "merge", DISPATCHED) is None
    assert select_run([run(created_at="2026-10-08T11:00:00Z")], "merge", DISPATCHED) is None
    assert select_run([run(event="push")], "merge", DISPATCHED) is None
    assert select_run([run(display_title="regenerate at x")], "merge", DISPATCHED, "regenerate at merge") is None
    newest = select_run([run(id=1), run(id=2, created_at="2026-10-08T12:01:00Z")], "merge", DISPATCHED)
    assert newest["id"] == 2


def test_run_outcomes_fail_closed():
    assert run_outcome(None) == "MISSING"
    assert run_outcome(run(status="in_progress", conclusion=None)) == "PENDING"
    assert run_outcome(run(conclusion="failure")) == "FAILED:failure"
    assert run_outcome(run()) == "SUCCESS"


def bot_commit(**overrides):
    commit = {"parents": [{"sha": "merge"}], "author": {"login": "github-actions[bot]"},
              "commit": {"message": "chore(docs): regenerate generated files [skip ci]"},
              "files": [{"filename": "status/facts.json"}, {"filename": "PROJECT_STATUS.md"}]}
    commit.update(overrides)
    return commit


def test_final_main_is_merge_or_one_verified_regeneration_commit():
    assert resolve_final_main("merge", "merge", None) == ("merge", None)
    assert resolve_final_main("merge", "bot", bot_commit()) == ("bot", None)
    for bad in (bot_commit(parents=[{"sha": "other"}]), bot_commit(author={"login": "someone"}),
                bot_commit(files=[{"filename": "src/x.py"}]), bot_commit(commit={"message": "feat: x"})):
        assert resolve_final_main("merge", "bot", bad) == (None, "MAIN_ADVANCED_UNEXPECTEDLY")
    assert resolve_final_main("merge", "bot", None) == (None, "MAIN_ADVANCED_UNVERIFIED")


def test_workflow_contract_requires_both_dispatchable_workflows():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    regen = "on:\n  workflow_dispatch:\n    inputs:\n      target_sha:\n        required: true\n"
    assert workflow_contract_failures(ci, regen) == []
    assert workflow_contract_failures(ci, None) == ["WORKFLOW_MISSING:regenerate-generated-files.yml"]
    assert workflow_contract_failures("on:\n  push:\n", regen) == ["WORKFLOW_NOT_DISPATCHABLE:ci.yml"]
    assert workflow_contract_failures(ci, "on:\n  workflow_dispatch:\n") == [
        "WORKFLOW_NOT_DISPATCHABLE:regenerate-generated-files.yml"]


def test_merge_workflow_preserves_owner_gate_and_adds_only_actions_write():
    wf = yaml.safe_load((ROOT / ".github/workflows/manual-pr-merge.yml").read_text(encoding="utf-8"))
    assert wf["permissions"] == {"actions": "write", "contents": "write", "deployments": "write",
                                 "pull-requests": "write", "issues": "read", "checks": "read"}
    job = wf["jobs"]["merge"]
    assert job["if"] == "github.actor == 'aungmyat1' && github.ref == 'refs/heads/main'"
    assert job["timeout-minutes"] <= 120
    steps = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "--match-head-commit" in steps
    assert steps.index("post_merge_verify.py', 'preflight'") < steps.index("gh', 'pr', 'merge'")
    assert "post_merge_verify.py verify" in steps and "gh run list" not in steps
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert "workflow_dispatch" in ci[True]
