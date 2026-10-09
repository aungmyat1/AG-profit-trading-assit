"""Pure fail-closed PR readiness classification for the merge-gate audit."""
from __future__ import annotations

import re

HOLD_LANGUAGE = re.compile(
    r"\b(?:do not merge|don't merge|hold|parked|park this|await(?:ing)? owner|owner authorization)\b",
    re.IGNORECASE,
)
DEPENDENCY = re.compile(r"(?im)^\s*(?:depends[- ]on|blocked[- ]by|requires)\s*:?\s*#(\d+)\b")
EXECUTION_PATHS = (
    "execution/", "src/execution/", "mt5/", "src/mt5/", "trade_management/",
    "src/trade_management/", "config/trading.yaml",
)
STRATEGY_EVIDENCE_PATHS = ("strategies/", "artifacts/validation/")
GREEN_CONCLUSIONS = {"success", "neutral", "skipped"}
# GitHub review semantics: only APPROVED, CHANGES_REQUESTED, or a dismissal changes a
# reviewer's standing decision. COMMENTED/PENDING reviews never clear CHANGES_REQUESTED.
DECISIVE_REVIEW_STATES = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
NON_DECISIVE_REVIEW_STATES = {"COMMENTED", "PENDING"}


def explicit_dependencies(title: str, body: str) -> list[int]:
    return sorted({int(match) for match in DEPENDENCY.findall(f"{title}\n{body or ''}")})


def review_decision(reviews: list[dict]) -> tuple[bool | None, int | None]:
    """(changes_requested, approvals) from each reviewer's latest decisive review.

    Returns (None, None) when the review state cannot be established (an unknown review
    state, or a decisive review without a reviewer login), so callers fail closed.
    """
    ordered = sorted(enumerate(reviews), key=lambda item: (str(item[1].get("submitted_at") or ""), item[0]))
    standing: dict[str, str] = {}
    for _, review in ordered:
        state = str(review.get("state") or "").upper()
        if state in NON_DECISIVE_REVIEW_STATES:
            continue
        if state not in DECISIVE_REVIEW_STATES:
            return None, None
        login = (review.get("user") or {}).get("login")
        if not login:
            return None, None
        if state == "DISMISSED":
            standing.pop(login, None)
        else:
            standing[login] = state
    values = list(standing.values())
    return "CHANGES_REQUESTED" in values, values.count("APPROVED")


def checks_state(check_runs: list[dict], statuses: list[dict]) -> str:
    results = [str(row.get("conclusion") or row.get("status") or "").lower() for row in check_runs]
    results += [str(row.get("state") or "").lower() for row in statuses]
    if not results:
        return "UNKNOWN"
    if any(value in {"failure", "error", "timed_out", "cancelled", "action_required", "startup_failure"}
           for value in results):
        return "FAIL"
    if any(value in {"queued", "in_progress", "pending", "waiting", "requested"} for value in results):
        return "PENDING"
    if all(value in GREEN_CONCLUSIONS for value in results):
        return "PASS"
    return "UNKNOWN"


def classify_pull_request(pr: dict, peers: list[dict]) -> dict:
    """Return a recommendation only; this function never grants merge authority."""
    number = pr.get("number")
    reasons: list[str] = []
    data = pr.get("data", {})
    if not pr.get("data_complete", False):
        reasons.append("PR_DATA_INCOMPLETE")

    labels = {str(value).strip().lower() for value in pr.get("labels", [])}
    title, body = str(pr.get("title", "")), str(pr.get("body", "") or "")
    if any("park" in label for label in labels) or re.search(r"\bparked\b", title + "\n" + body, re.I):
        return {"number": number, "classification": "PARKED", "reasons": ["PARKED_BY_LABEL_OR_TEXT"], "merge_authorized": False}
    if pr.get("draft"):
        reasons.append("DRAFT_PR")
    issue_comments = "\n".join(pr.get("issue_comments", []))
    if pr.get("explicit_hold") or HOLD_LANGUAGE.search(title + "\n" + body + "\n" + issue_comments):
        reasons.append("EXPLICIT_HOLD_LANGUAGE")

    paths = sorted(set(pr.get("paths", [])))
    if any(path.startswith(EXECUTION_PATHS) for path in paths):
        reasons.append("EXECUTION_OR_TRADE_MANAGEMENT_PATH")
    if any(path.startswith(STRATEGY_EVIDENCE_PATHS) for path in paths):
        reasons.append("STRATEGY_OR_VALIDATION_AUTHORITY_REQUIRES_OWNER_REVIEW")

    if data.get("mergeable") is not True or data.get("mergeable_state") != "clean":
        reasons.append("MERGEABILITY_NOT_CLEAN_OR_UNKNOWN")
    state = data.get("checks_state", "UNKNOWN")
    if state != "PASS":
        reasons.append(f"CI_{state}")
    unresolved = data.get("unresolved_review_threads")
    if not isinstance(unresolved, int):
        reasons.append("REVIEW_THREAD_STATE_UNKNOWN")
    elif unresolved:
        reasons.append("UNRESOLVED_REVIEW_THREADS")
    if data.get("changes_requested") is not False:
        reasons.append("CHANGES_REQUESTED_OR_REVIEW_STATE_UNKNOWN")
    if not isinstance(data.get("approvals"), int) or data.get("approvals", 0) < 1:
        reasons.append("APPROVAL_ABSENT_OR_UNKNOWN")

    dependency_ids = pr.get("dependencies", [])
    dependency_open = []
    for dep in dependency_ids:
        dep_state = pr.get("dependency_states", {}).get(str(dep), "UNKNOWN")
        if dep_state == "OPEN":
            dependency_open.append(dep)
        elif dep_state != "MERGED":
            reasons.append(f"DEPENDENCY_{dep}_{dep_state}")

    overlap_numbers = []
    for peer in peers:
        if peer.get("number") == number:
            continue
        if set(paths).intersection(peer.get("paths", [])):
            overlap_numbers.append(peer.get("number"))
    if overlap_numbers:
        unresolved_overlap = set(overlap_numbers) - set(dependency_ids)
        if unresolved_overlap:
            reasons.extend(f"OVERLAPPING_FILES_WITH_PR_{peer}" for peer in sorted(unresolved_overlap))
        elif not dependency_open:
            reasons.append("DEPENDENCY_STACK_OVERLAP_REQUIRES_REAUDIT")

    if pr.get("base_ref") != "main":
        reasons.append("NON_MAIN_BASE_STACK")
    if pr.get("base_sha") != pr.get("main_sha"):
        reasons.append("PR_BASE_NOT_CURRENT_MAIN")

    if reasons:
        classification = "HOLD"
    elif dependency_open:
        classification = "MERGE_AFTER_DEPENDENCY"
        reasons.append("OPEN_DEPENDENCY")
    else:
        classification = "MERGE_NOW"
        reasons.append("ALL_READINESS_GATES_PASS")
    return {"number": number, "classification": classification, "reasons": reasons, "merge_authorized": False}


def validate_dispatch(pr: dict, requested_number: int, expected_head_sha: str,
                      denylist: dict | None = None) -> list[str]:
    """Validate one invocation's PR/SHA pair, readiness, and permanent deny rules."""
    reasons: list[str] = []
    if not pr or pr.get("number") != requested_number:
        reasons.append("PR_NUMBER_MISMATCH")
    if not pr or pr.get("head_sha") != expected_head_sha:
        reasons.append("EXPECTED_HEAD_SHA_MISMATCH")
    if not pr or pr.get("classification") != "MERGE_NOW":
        reasons.append("READINESS_NOT_MERGE_NOW")

    denylist = denylist or {}
    if requested_number in denylist.get("blocked_pr_numbers", []):
        reasons.append("PR_NUMBER_DENYLISTED")
    denied_labels = {str(label).strip().casefold() for label in denylist.get("blocked_labels", [])}
    pr_labels = {str(label).strip().casefold() for label in (pr or {}).get("labels", [])}
    reasons.extend(f"PR_LABEL_DENYLISTED:{label}" for label in sorted(pr_labels & denied_labels))
    return reasons
