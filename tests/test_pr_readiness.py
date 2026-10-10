import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.governance.pr_readiness import (
    checks_state, classify_pull_request, explicit_dependencies, owner_approved, validate_dispatch,
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


@pytest.mark.parametrize("labels,label_data_complete", [(None, None), ([""], False), ([], False)])
def test_missing_or_ambiguous_label_data_fails_closed(labels, label_data_complete):
    record = ready(labels=labels)
    if label_data_complete is not None:
        record["label_data_complete"] = label_data_complete
    result = classify_pull_request(record, [])
    assert result["classification"] == "HOLD"
    assert "PR_LABEL_DATA_INCOMPLETE" in result["reasons"]


def test_stale_main_base_is_held():
    result = classify_pull_request(ready(base_sha="old-sha"), [])
    assert result["classification"] == "HOLD"
    assert "PR_BASE_NOT_CURRENT_MAIN" in result["reasons"]


def test_draft_and_execution_paths_are_held():
    draft = classify_pull_request(ready(draft=True), [])
    execution = classify_pull_request(ready(paths=["execution/executor.py"]), [])
    assert draft["classification"] == "HOLD"
    assert execution["classification"] == "HOLD"
    assert "PROTECTED_EXECUTION_PATH_REQUIRES_OWNER_GATED_REVIEW" in execution["reasons"]


@pytest.mark.parametrize("label", [
    "do-not-merge", "DO NOT MERGE", "do_not_merge", "hold", "HOLD", "owner-gated",
    "OWNER_GATED", "owner authorization", "OWNER-AUTHORIZATION", "execution", "EXECUTION",
])
def test_protected_label_spellings_are_held(label):
    result = classify_pull_request(ready(labels=[label]), [])
    assert result["classification"] == "HOLD"
    assert any(reason.startswith("PROTECTED_LABEL_HOLD:") for reason in result["reasons"])


@pytest.mark.parametrize("path", [
    "assistant/commands.py", "execution/executor.py", "trade_management/manager.py",
    "src/host_delivery/telegram_confirm.py", "src/authorization/strategy_authority.py",
    "config/v1_tickets/ready_authority.yaml", "config/v1_tickets/crypto_cfd_ticket_policy.yaml",
    "config/governance/pr_merge_denylist.json", ".github/workflows/manual-pr-merge.yml",
    ".github/workflows/pr-merge-readiness.yml", "scripts/governance/pr_readiness.py",
    "config/trading.yaml", "config/owner_ticket.yaml", "config/ticket_delivery.yaml",
    "config/broker_symbol_map/vt_markets_demo.yaml", "docs/agents/INVARIANTS.md",
])
def test_execution_and_authority_paths_are_held_for_owner_review(path):
    result = classify_pull_request(ready(paths=[path]), [])
    assert result["classification"] == "HOLD", path
    assert any("OWNER_GATED_REVIEW" in reason for reason in result["reasons"]), path


def test_protected_paths_do_not_block_unrelated_documentation_prs():
    result = classify_pull_request(ready(paths=["docs/how-to-read-reports.md"]), [])
    assert result["classification"] == "MERGE_NOW"


def test_parked_and_explicit_hold_are_not_mergeable():
    parked = classify_pull_request(ready(labels=["parked"]), [])
    held = classify_pull_request(ready(body="Owner authorization required"), [])
    hyphenated = classify_pull_request(ready(body="DO_NOT_MERGE until owner review"), [])
    assert parked["classification"] == "PARKED"
    assert held["classification"] == "HOLD"
    assert hyphenated["classification"] == "HOLD"


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


def test_owner_approval_evidence_uses_latest_decisive_review():
    reviews = [
        {"state": "APPROVED", "submitted_at": "2026-10-01", "user": {"login": "aungmyat1"}},
        {"state": "COMMENTED", "submitted_at": "2026-10-02", "user": {"login": "aungmyat1"}},
    ]
    assert owner_approved(reviews)
    reviews.append({"state": "CHANGES_REQUESTED", "submitted_at": "2026-10-03",
                    "user": {"login": "aungmyat1"}})
    assert not owner_approved(reviews)


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


@pytest.mark.parametrize("label", ["DO_NOT_MERGE", "Owner Authorization", "EXECUTION"])
def test_dispatch_denylist_normalizes_alternate_protected_labels(label):
    pr = {"number": 7, "head_sha": "abc123", "classification": "MERGE_NOW", "labels": [label]}
    assert any(reason.startswith("PROTECTED_LABEL_HOLD:")
               for reason in validate_dispatch(pr, 7, "abc123"))


def test_dispatch_fails_closed_when_label_evidence_is_missing():
    pr = {"number": 7, "head_sha": "abc123", "classification": "MERGE_NOW", "labels": None}
    assert "PR_LABEL_DATA_INCOMPLETE" in validate_dispatch(pr, 7, "abc123")
