"""AGP-MERGE-GATE-RECOVERY-R3: PR-based regeneration contract, run correlation, post-merge states."""
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "governance"))

import regen_contract as rc  # noqa: E402
from post_merge_verify import (  # noqa: E402
    INTEGRATED, MERGED_PENDING_REGEN_PR, POST_MERGE_FAILED, ci_run_name, run_outcome, select_run,
    verify, workflow_contract_failures,
)

MERGE, HEAD, OTHER = "m" * 40, "h" * 40, "o" * 40
PR_HEAD = "ab" * 20


class FakeAPI:
    """Records dispatches and answers run listings from per-workflow run factories."""

    repo = "owner/repo"

    def __init__(self, regen_run=None, ci_run=None, main=None, merged=True, head=HEAD, extra_runs=()):
        self.mains = list(main or [MERGE] * 10)
        self.pr = {"merged": merged, "merge_commit_sha": MERGE if merged else None, "head": {"sha": head}}
        self.factories = {"regenerate-generated-files.yml": regen_run or (lambda title: run(title)),
                          "ci.yml": ci_run or (lambda title: run(title))}
        self.runs = {name: list(extra_runs) for name in self.factories}
        self.dispatched = []

    def request(self, method, path, payload=None):
        if path.endswith("/git/ref/heads/main"):
            sha = self.mains.pop(0) if len(self.mains) > 1 else self.mains[0]
            return {"object": {"sha": sha}}
        if "/pulls/" in path:
            return self.pr
        workflow = next(name for name in self.factories if f"/workflows/{name}/" in path)
        if method == "POST":
            self.dispatched.append((workflow, payload))
            corr = payload["inputs"]["correlation_id"]
            title = (rc.run_name(payload["inputs"]["target_sha"], corr) if "target_sha" in payload["inputs"]
                     else ci_run_name(corr))
            made = self.factories[workflow](title)
            if made:
                self.runs[workflow].append(made)
            return None
        return {"workflow_runs": self.runs[workflow]}


def run(title, **overrides):
    base = {"id": 7, "display_title": title, "event": "workflow_dispatch", "head_branch": "main",
            "head_sha": MERGE, "status": "completed", "conclusion": "success", "html_url": "u"}
    base.update(overrides)
    return base


def outcome_for(status=rc.REGEN_NO_CHANGE, **overrides):
    def fetch(repo, run_id):
        api_dispatch = fetch.api.dispatched[0][1]["inputs"]
        body = rc.build_outcome(status, api_dispatch["target_sha"], api_dispatch["correlation_id"])
        if status in rc.PR_STATUSES:
            body.update(changed_paths=["status/facts.json"], branch=rc.regen_branch(MERGE), pr_number=101,
                        pr_head_sha=PR_HEAD)
        body.update(overrides)
        return body
    return fetch


def go(api, fetch=None, **kw):
    fetch = fetch or outcome_for()
    fetch.api = api
    ids = iter(f"corr{n}" for n in range(10))
    return verify(api, 5, HEAD, timeout_s=60, poll_s=1, fetch_outcome=fetch, new_id=lambda: next(ids),
                  sleep=lambda s: None, **kw)


# Regeneration outcomes ---------------------------------------------------------------------
def test_no_change_then_green_main_ci_is_integrated():
    api = FakeAPI()
    report = go(api)
    assert report["state"] == INTEGRATED and report["failures"] == []
    assert [w for w, _ in api.dispatched] == ["regenerate-generated-files.yml", "ci.yml"]
    assert api.dispatched[0][1] == {"ref": "main", "inputs": {"target_sha": MERGE, "correlation_id": "corr0"}}


@pytest.mark.parametrize("status", sorted(rc.PR_STATUSES))
def test_regen_pr_stops_pending_review_and_never_runs_main_ci(status):
    api = FakeAPI()
    report = go(api, outcome_for(status))
    assert report["state"] == MERGED_PENDING_REGEN_PR
    assert report["regen_pr"] == {"status": status, "branch": rc.regen_branch(MERGE), "pr_number": 101,
                                  "pr_head_sha": PR_HEAD, "source_sha": MERGE}
    assert [w for w, _ in api.dispatched] == ["regenerate-generated-files.yml"]


def test_failed_regeneration_run_and_failed_outcome_fail_closed():
    api = FakeAPI(regen_run=lambda t: run(t, conclusion="failure"))
    assert go(api)["failures"] == ["REGENERATION_FAILED:failure"]
    report = go(FakeAPI(), outcome_for(rc.REGEN_FAILED, reason="stale"))
    assert report["state"] == POST_MERGE_FAILED and report["failures"] == ["REGENERATION_REGEN_FAILED"]


@pytest.mark.parametrize("overrides,failure", [
    ({"changed_paths": ["src/x.py"]}, "REGEN_OUTCOME_UNEXPECTED_PATH"),
    ({"target_sha": OTHER}, "REGEN_OUTCOME_TARGET_SHA_MISMATCH"),
    ({"correlation_id": "someone-else"}, "REGEN_OUTCOME_CORRELATION_MISMATCH"),
    ({"schema": "V0"}, "REGEN_OUTCOME_SCHEMA_INVALID"),
    ({"status": "REGEN_MAYBE"}, "REGEN_OUTCOME_STATUS_UNKNOWN"),
    ({"changed_paths": ["status/facts.json"]}, "REGEN_OUTCOME_NO_CHANGE_WITH_PATHS"),
])
def test_outcome_that_does_not_prove_itself_fails_closed(overrides, failure):
    report = go(FakeAPI(), outcome_for(**overrides))
    assert report["state"] == POST_MERGE_FAILED and failure in report["failures"]


def test_pr_outcome_needs_dedicated_branch_number_and_head():
    report = go(FakeAPI(), outcome_for(rc.REGEN_PR_CREATED, branch="feature/x", pr_number=None, pr_head_sha="x"))
    assert {"REGEN_OUTCOME_BRANCH_INVALID", "REGEN_OUTCOME_PR_NUMBER_INVALID",
            "REGEN_OUTCOME_PR_HEAD_INVALID"} <= set(report["failures"])


def test_missing_outcome_artifact_fails_closed():
    fetch = lambda repo, run_id: None  # noqa: E731
    assert go(FakeAPI(), fetch)["failures"] == ["REGEN_OUTCOME_MISSING"]


# Exact identity ----------------------------------------------------------------------------
def test_stale_main_and_exact_sha_mismatches_fail_closed():
    assert go(FakeAPI(main=[OTHER]))["failures"] == ["MAIN_NOT_AT_MERGE_SHA"]
    assert go(FakeAPI(main=[MERGE, OTHER]))["failures"] == ["MAIN_ADVANCED_DURING_REGENERATION"]
    assert go(FakeAPI(head=OTHER))["failures"] == ["MERGED_HEAD_NOT_AUTHORIZED_HEAD"]
    assert go(FakeAPI(merged=False))["failures"] == ["PR_NOT_MERGED"]


def test_wrong_commit_run_is_rejected():
    api = FakeAPI(regen_run=lambda t: run(t, head_sha=OTHER))
    assert go(api)["failures"] == ["REGENERATION_RUN_WRONG_COMMIT"]


def test_concurrent_dispatch_runs_with_other_correlation_ids_are_ignored():
    foreign = [run(rc.run_name(MERGE, "another-dispatch"), id=1, conclusion="failure"),
               run(ci_run_name("another-dispatch"), id=2, conclusion="failure")]
    assert go(FakeAPI(extra_runs=foreign))["state"] == INTEGRATED


def test_duplicate_correlation_is_ambiguous_not_guessed():
    title = rc.run_name(MERGE, "c")
    assert select_run([run(title, id=1), run(title, id=2)], MERGE, title) == (None, "RUN_CORRELATION_AMBIGUOUS")
    assert select_run([run(title, event="push")], MERGE, title) == (None, "RUN_NOT_MAIN_DISPATCH")
    assert select_run([], MERGE, title) == (None, None)


def test_timeout_reports_missing_or_pending():
    clock = iter(range(0, 1000, 100))
    api = FakeAPI(regen_run=lambda t: None)
    report = go(api, clock=lambda: next(clock))
    assert report["failures"] == ["REGENERATION_TIMEOUT_MISSING"]
    clock = iter(range(0, 1000, 100))
    api = FakeAPI(ci_run=lambda t: run(t, status="in_progress", conclusion=None))
    assert go(api, clock=lambda: next(clock))["failures"] == ["MAIN_CI_TIMEOUT_PENDING"]


def test_post_merge_main_ci_failure():
    report = go(FakeAPI(ci_run=lambda t: run(t, conclusion="failure")))
    assert report["state"] == POST_MERGE_FAILED and report["failures"] == ["MAIN_CI_FAILED:failure"]
    assert run_outcome(None) == "MISSING"


# Static contracts --------------------------------------------------------------------------
REGEN_OK = """name: regenerate-generated-files
run-name: regenerate at ${{ inputs.target_sha }} [${{ inputs.correlation_id }}]
on:
  workflow_dispatch:
    inputs:
      target_sha:
        required: true
      correlation_id:
        required: true
jobs:
  r:
    steps:
      - run: git push origin HEAD:refs/heads/regen/generated-files
      - uses: actions/upload-artifact@v4
        with:
          name: regen-outcome
"""


def test_workflow_contract_requires_dispatchable_correlated_pr_based_regeneration():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow_contract_failures(ci, REGEN_OK) == []
    assert workflow_contract_failures(ci, None) == ["WORKFLOW_MISSING:regenerate-generated-files.yml"]
    pushes_main = REGEN_OK + "      - run: git push origin HEAD:refs/heads/main\n"
    assert workflow_contract_failures(ci, pushes_main) == ["WORKFLOW_PUSHES_MAIN:regenerate-generated-files.yml"]
    no_corr = REGEN_OK.replace("correlation_id", "x")
    assert "WORKFLOW_NOT_DISPATCHABLE:regenerate-generated-files.yml" in workflow_contract_failures(ci, no_corr)
    assert "WORKFLOW_NOT_DISPATCHABLE:ci.yml" in workflow_contract_failures("on:\n  workflow_dispatch:\n", REGEN_OK)


def test_pr91_head_as_observed_fails_the_contract():
    # 25b6cfe pushes generated commits straight to main and has no correlation id.
    pr91 = "on:\n  workflow_dispatch:\n    inputs:\n      target_sha:\n        required: true\n" \
           "jobs:\n  r:\n    steps:\n      - run: git push origin HEAD:refs/heads/main\n"
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    failures = workflow_contract_failures(ci, pr91)
    assert "WORKFLOW_PUSHES_MAIN:regenerate-generated-files.yml" in failures
    assert "WORKFLOW_NOT_DISPATCHABLE:regenerate-generated-files.yml" in failures


def test_generated_outputs_are_not_regeneration_inputs_so_regen_has_a_fixed_point():
    facts = json.loads((ROOT / "status/facts.json").read_text(encoding="utf-8"))
    assert facts["input_paths"] and not set(facts["input_paths"]) & rc.GENERATED_PATHS


def test_emit_cli_writes_valid_outcome_and_refuses_invalid(tmp_path):
    out = tmp_path / "o.json"
    assert rc.main(["emit", "--out", str(out), "--status", rc.REGEN_NO_CHANGE, "--target-sha", MERGE,
                    "--correlation-id", "c"]) == 0
    assert rc.validate_outcome(json.loads(out.read_text()), MERGE, "c") == []
    assert rc.main(["emit", "--out", str(tmp_path / "bad.json"), "--status", rc.REGEN_PR_CREATED,
                    "--target-sha", MERGE, "--correlation-id", "c"]) == 1


def test_merge_workflow_keeps_owner_gate_and_minimal_permissions():
    wf = yaml.safe_load((ROOT / ".github/workflows/manual-pr-merge.yml").read_text(encoding="utf-8"))
    assert wf["permissions"] == {"actions": "write", "contents": "write", "deployments": "write",
                                 "pull-requests": "write", "issues": "read", "checks": "read"}
    job = wf["jobs"]["merge"]
    assert job["if"] == "github.actor == 'aungmyat1' && github.ref == 'refs/heads/main'"
    assert job["environment"]["name"] == "merge-gate" and job["timeout-minutes"] <= 120
    steps = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "--match-head-commit" in steps and "validate_dispatch" in steps
    assert steps.index("post_merge_verify.py', 'preflight'") < steps.index("gh', 'pr', 'merge'")
    assert "post_merge_verify.py verify" in steps and "--json-out" in steps
    artifacts = [step for step in job["steps"] if step.get("uses") == "actions/upload-artifact@v4"]
    assert artifacts and artifacts[-1].get("if") == "always()"
    artifact_paths = artifacts[-1]["with"]["path"]
    assert "audit.json" in artifact_paths and "audit.md" in artifact_paths
    assert "post-merge-result.json" in artifact_paths
    audit_workflow = (ROOT / ".github/workflows/pr-merge-readiness.yml").read_text(encoding="utf-8")
    assert "Safe dry-run" in audit_workflow
    for forbidden in ("order_send", "order_check", "execute_command", "mt5"):
        assert forbidden not in steps
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert ci[True]["workflow_dispatch"]["inputs"]["correlation_id"]["required"] is True
