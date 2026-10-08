"""AGP-MERGE-GATE-REMEDIATION-R2: F01 review state and F02 check pagination (preserved by R3)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "governance"))

from audit_pr_readiness import counted_pages  # noqa: E402
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
