---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-MERGE-GATE-REMEDIATION-R2 — merge-gate defect repair (2026-10-09)

> **Superseded in part by R3** ([`AGP_MERGE_GATE_RECOVERY_R3_2026-10-09.md`](AGP_MERGE_GATE_RECOVERY_R3_2026-10-09.md)):
> the F03 assumption below that regeneration may add one bot commit to `main` is replaced by
> PR-based regeneration. F01 and F02 stand unchanged. This record is kept as historical evidence.

Repairs four defects in the merge-readiness system merged by PR #92 (`d7b4995`). The audit is
still advisory (`merge_authorized: false`). Merging stays owner-only through
`manual-pr-merge.yml`: actor `aungmyat1`, the `merge-gate` environment, and one exact
`pr_number` + `expected_head_sha` pair per run. No broker or Windows host action was taken.

| ID | Defect (pre-R2) | Fix | Paths |
|---|---|---|---|
| F01 | The audit kept each reviewer's latest review of any state, so a later `COMMENTED` review cleared `CHANGES_REQUESTED`. | `review_decision()` keeps each reviewer's latest decisive review (`APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`), ordered by `submitted_at`. `COMMENTED` and `PENDING` reviews are ignored. An unknown state or a decisive review without a login returns `None`, and the PR is held. | `scripts/governance/pr_readiness.py`, `audit_pr_readiness.py` |
| F02 | Check runs came from one request at GitHub's default page size of 30. A failure on page 2 was not seen. | `counted_pages()` reads every page (100 rows each) until it holds `total_count` rows, for check runs and for commit statuses. A missing `total_count`, a count that changes between pages, a short collection, or more than 50 pages all raise an error. The PR is then recorded as incomplete and held. | `scripts/governance/audit_pr_readiness.py` |
| F03 | The post-merge step ran `gh run list` for the merge commit. A merge made with `GITHUB_TOKEN` does not trigger push workflows, so no run existed, and nothing was dispatched or waited for. | **Preflight (before merging):** at the authorized head SHA, `ci.yml` must declare `workflow_dispatch`, and `regenerate-generated-files.yml` must exist and declare `workflow_dispatch` with `target_sha`. If either check fails, the PR is not merged. **Verify (after merging):** the PR is merged with the authorized head, and `main` equals the merge SHA. The step then dispatches regeneration (`target_sha` = merge SHA) and binds the run by exact SHA, `run-name`, and dispatch time. After regeneration, `main` must be either the merge SHA or one `github-actions[bot]` commit on it that touches only the four generated paths. The step then dispatches CI on `main` and requires the run's `head_sha` to equal that final SHA. Each wait has a 45 min timeout, and the job has a 120 min cap. A missing run, a wrong commit, a non-success conclusion, a timeout, or unexpected movement of `main` exits non-zero. | `.github/workflows/manual-pr-merge.yml`, `.github/workflows/ci.yml` (adds `workflow_dispatch`), `scripts/governance/post_merge_verify.py` |
| F04 | No status record | This document, the `PROJECT_STATUS.md` snapshot, and the `docs/README.md` index | — |

Permissions: the only addition is `actions: write` on the merge job, which `workflow_dispatch`
needs. `workflow_dispatch` is exempt from the `GITHUB_TOKEN` rule that stops other events from
triggering workflows. Nothing else was broadened.

## PR #91 interface (not edited; owner/writer action)

PR #91 (`codex/gen-files-ci-1`, head `25b6cfe`) adds `regenerate-generated-files.yml`. R2 relies
on this interface from it:

- File name `.github/workflows/regenerate-generated-files.yml`.
- A `workflow_dispatch` input named `target_sha`.
- `run-name: regenerate at <target_sha>`.
- It pushes at most one bot commit onto exactly `target_sha`. The commit message starts with
  `chore(docs): regenerate generated files` and it touches only the four generated paths.

PR #91 already matches all four points. Incompatibilities and the actions they require:

1. Both PRs edit `.github/workflows/ci.yml`. R2 adds `workflow_dispatch` under `on:`, and #91
   edits the `docs-drift` job. Whichever merges second must keep both changes.
2. Until #91 merges, preflight refuses **every** gated merge (`WORKFLOW_MISSING:regenerate-generated-files.yml`).
   This is fail-closed by design. #91 itself passes preflight only once its head also carries the
   `ci.yml` `workflow_dispatch` trigger (after R2 merges and #91 merges `main` in).
3. #91's `push: branches: [main]` trigger never fires for a `GITHUB_TOKEN` merge. R2 dispatches
   it instead. If the owner merges by hand, push and dispatch runs can both occur. They are
   serialized by #91's concurrency group, and the second finds nothing to commit.
4. Any rename of the file, the `target_sha` input, the `run-name` format, or the commit-message
   prefix in #91 must be mirrored in `post_merge_verify.py`, or verify fails closed.

**Merge order:** this PR cannot pass its own preflight, because no regeneration workflow exists
on `main` yet. The owner merges R2 manually. #91's writer then merges `main` into #91, keeping
both `ci.yml` edits. #91 can then go through the gate, or be merged manually.

## Tests (2026-10-09, Linux cloud container, Python 3)

- `python -m pytest -q tests/test_merge_gate_r2.py tests/test_pr_readiness.py`: 22 passed (12 new).
  F01 covers comment after changes requested (held), approval/dismissal clearing it, and
  `submitted_at` ordering. F02 covers 35 check runs with a failure on page 2 under a 30-row cap
  (FAIL; pre-R2 the first page alone reported PASS), plus short, changing, and over-long
  pagination (all raise). F03 covers run binding (SHA, event, title, time), the final-main
  bot-commit rules, the workflow contract, and the merge workflow's permissions and owner gate.
- `python -m pytest -q`: 1519 passed, 2 skipped.
- The docs gates pass: `generate_live_status.py --check`, `collect_facts.py` (no diff), `cog --check`,
  `check_drift.py` (0 errors), and `build_context_pack.py --check`.
- Workflow YAML parsed with PyYAML. `actionlint` is not installed in this container, so it was
  not run.

## Limits

- Nothing was dispatched, merged, or polled against live GitHub. All verification is unit
  tests and static YAML checks. The live behavior of `manual-pr-merge.yml` is unverified until
  the owner's first gated run.
- Run binding uses the dispatch time with a 10 s skew allowance, plus the exact head SHA (and
  `run-name` for regeneration), because the dispatch API returns no run id.
