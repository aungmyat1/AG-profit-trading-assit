import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.governance.pr_readiness import (
    checks_state, classify_pull_request, explicit_dependencies, validate_dispatch,
)


def ready(number=1, **overrides):
    record = {
        "number": number, "title": "Routine docs", "body": "", "labels": [], "draft": False,
        "base_ref": "main", "base_sha": "main-sha", "main_sha": "main-sha",
        "paths": ["docs/example.md"], "dependencies": [],
        "dependency_states": {}, "data_complete": True,
        "data": {"mergeable": True, "mergeable_state": "clean", "checks_state": "PASS",
                 "unresolved_review_threads": 0, "changes_requested": False, "approvals": 1},
    }
    record.update(overrides)
    return record


def test_complete_clean_pr_is_recommendation_only():
    result = classify_pull_request(ready(), [])
    assert result["classification"] == "MERGE_NOW"
    assert result["merge_authorized"] is False


def test_missing_evidence_fails_closed():
    record = ready(data_complete=False)
    result = classify_pull_request(record, [])
    assert result["classification"] == "HOLD"
    assert "PR_DATA_INCOMPLETE" in result["reasons"]


def test_stale_main_base_is_held():
    result = classify_pull_request(ready(base_sha="old-sha"), [])
    assert result["classification"] == "HOLD"
    assert "PR_BASE_NOT_CURRENT_MAIN" in result["reasons"]


def test_draft_and_execution_paths_are_held():
    draft = classify_pull_request(ready(draft=True), [])
    execution = classify_pull_request(ready(paths=["execution/executor.py"]), [])
    assert draft["classification"] == "HOLD"
    assert execution["classification"] == "HOLD"


def test_parked_and_explicit_hold_are_not_mergeable():
    parked = classify_pull_request(ready(labels=["parked"]), [])
    held = classify_pull_request(ready(body="Owner authorization required"), [])
    assert parked["classification"] == "PARKED"
    assert held["classification"] == "HOLD"


def test_overlap_holds_unstacked_pr():
    result = classify_pull_request(ready(), [ready(2, paths=["docs/example.md"])])
    assert result["classification"] == "HOLD"
    assert "OVERLAPPING_FILES_WITH_PR_2" in result["reasons"]


def test_explicit_open_dependency_waits_and_merged_dependency_releases():
    record = ready(dependencies=[2], dependency_states={"2": "OPEN"})
    waiting = classify_pull_request(record, [ready(2)])
    assert waiting["classification"] == "MERGE_AFTER_DEPENDENCY"
    record["dependency_states"]["2"] = "MERGED"
    released = classify_pull_request(record, [])
    assert released["classification"] == "MERGE_NOW"


def test_checks_and_dependency_parser_fail_closed():
    assert checks_state([], []) == "UNKNOWN"
    assert checks_state([{"conclusion": "failure"}], []) == "FAIL"
    assert checks_state([{"conclusion": "success"}], []) == "PASS"
    assert explicit_dependencies("task", "Depends-On: #12\nblocked-by #8") == [8, 12]


def test_dispatch_inputs_are_the_one_run_allowlist():
    pr = {"number": 7, "head_sha": "abc123", "classification": "MERGE_NOW", "labels": []}
    assert validate_dispatch(pr, 7, "abc123") == []
    assert "PR_NUMBER_MISMATCH" in validate_dispatch(pr, 8, "abc123")
    assert "EXPECTED_HEAD_SHA_MISMATCH" in validate_dispatch(pr, 7, "changed")
    assert "READINESS_NOT_MERGE_NOW" in validate_dispatch(
        {**pr, "classification": "HOLD"}, 7, "abc123")


def test_committed_denylist_blocks_numbers_and_labels_case_insensitively():
    pr = {"number": 7, "head_sha": "abc123", "classification": "MERGE_NOW", "labels": ["Do-Not-Merge"]}
    denylist = {"blocked_pr_numbers": [7], "blocked_labels": ["do-not-merge"]}
    reasons = validate_dispatch(pr, 7, "abc123", denylist)
    assert "PR_NUMBER_DENYLISTED" in reasons
    assert "PR_LABEL_DENYLISTED:do-not-merge" in reasons
