from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.governance import wait_for_post_merge_workflows as gate
from scripts.governance.wait_for_post_merge_workflows import find_dispatched_run, run_outcome


def test_only_new_dispatch_for_target_sha_counts_as_started():
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    runs = [
        {"databaseId": 1, "event": "workflow_dispatch", "displayTitle": "CI at abc", "createdAt": "2026-10-09T11:59:00Z"},
        {"databaseId": 2, "event": "push", "displayTitle": "CI at abc", "createdAt": "2026-10-09T12:00:01Z"},
        {"databaseId": 3, "event": "workflow_dispatch", "displayTitle": "CI at abc", "createdAt": "2026-10-09T12:00:02Z"},
    ]
    assert find_dispatched_run(runs, "abc", now)["databaseId"] == 3


def test_no_matching_dispatch_means_not_started():
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    runs = [{"event": "workflow_dispatch", "displayTitle": "CI at other", "createdAt": "2026-10-09T12:00:02Z"}]
    assert find_dispatched_run(runs, "abc", now) is None


def test_completed_failure_fails_the_gate_and_running_job_stays_pending():
    assert run_outcome({"status": "in_progress"}) == "PENDING"
    assert run_outcome({"status": "completed", "conclusion": "success"}) == "SUCCESS"
    try:
        run_outcome({"databaseId": 9, "status": "completed", "conclusion": "failure", "url": "run-url"})
    except RuntimeError as exc:
        assert "concluded failure" in str(exc)
    else:
        raise AssertionError("a failed workflow must fail the post-merge gate")


def test_gate_fails_when_dispatched_workflows_do_not_start(monkeypatch):
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(gate, "_dispatch", lambda repo, workflow, sha: now)
    monkeypatch.setattr(gate, "_list_runs", lambda repo, workflow: [])
    monkeypatch.setattr(gate.time, "monotonic", lambda: 10.0)
    try:
        gate.dispatch_and_wait("owner/repo", "a" * 40, start_timeout=0)
    except TimeoutError as exc:
        assert "did not start within 0s" in str(exc)
        assert "ci.yml" in str(exc)
    else:
        raise AssertionError("a missing workflow_dispatch run must fail the gate")
