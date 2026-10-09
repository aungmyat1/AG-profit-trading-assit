---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-MERGE-GATE-RECOVERY-R3 — PR-based regeneration contract (2026-10-09)

R3 replaces R2's F03 assumption that regeneration may push one bot commit directly to
`main`. The PR #91 review finding (P1, "Route generated-file updates through a PR") is
consistent with `AGENTS.md`, and no owner exception for direct-to-main bot commits exists.
Nothing in this change alters trading, strategy or registry authority; `MERGES_EXECUTED = 0`.

## Policy: generated files are published only through a pull request

The four generated outputs are `PROJECT_STATUS.md`, `docs/status/PROJECT_LIVE_STATUS.md`,
`status/facts.json` and `docs/agents/CONTEXT_PACK.md`.

The regeneration workflow never pushes to `main`. When its outputs differ from the target
commit, it publishes them on the dedicated bot branch `regen/generated-files` and opens or
updates one PR from that branch. That PR is merged only by a separate owner dispatch of
`manual-pr-merge.yml`, with its own PR number and head SHA.

**Fixed point.** No generated output is an input to the generators: `status/facts.json`
`input_paths` and the four outputs do not intersect, and a test enforces this. So after a
regeneration PR merges, regenerating on that merge returns `REGEN_NO_CHANGE`, and no second
PR is created.

## Contract `AG_REGEN_OUTCOME_V1` (`scripts/governance/regen_contract.py`)

| Item | Requirement |
|---|---|
| Trigger | `workflow_dispatch` with inputs `target_sha` (40-hex, required) and `correlation_id` (required). A `push` trigger may stay; such runs are not read by the gate. |
| `run-name` | Exactly `regenerate at <target_sha> [<correlation_id>]` (`regen_contract.run_name`). |
| Checkout | `target_sha`. If `origin/main` is not `target_sha` when publishing → `REGEN_FAILED` (stale source). |
| Changed paths | Must be within the four outputs; any other path → `REGEN_FAILED`. |
| Outputs equal target | `REGEN_NO_CHANGE`. |
| Outputs differ, no open bot PR | Push `regen/generated-files` = `target_sha` + one commit, open the PR, title citing `target_sha` → `REGEN_PR_CREATED`. |
| Open bot PR already holds identical outputs for the same `target_sha` | No push → `REGEN_PENDING_REVIEW` (duplicate dispatch is idempotent). |
| Open bot PR holds a different source or outputs | `git push --force-with-lease=regen/generated-files:<observed bot head>` (bot-owned branch only) and retitle → `REGEN_PR_UPDATED`. |
| Never | Push to `main`, force-push any other branch, or touch a path outside the four outputs. |
| Outcome | `python scripts/governance/regen_contract.py emit --out regen-outcome.json ...`, uploaded as artifact `regen-outcome` with `if: always()`. PR statuses carry `branch`, `pr_number` and `pr_head_sha`. |
| Run conclusion | `success` for every status except `REGEN_FAILED`. |
| Permissions | `contents: write` (bot branch), `pull-requests: write` (open/retitle), `actions: write` only to dispatch `ci.yml` on the bot branch, because a `GITHUB_TOKEN`-opened PR triggers no `pull_request` CI. |
| Concurrency | `group: regenerate-generated-files`, `cancel-in-progress: false`. |

## Merge gate (`manual-pr-merge.yml`, `scripts/governance/post_merge_verify.py`)

| State | Meaning |
|---|---|
| `MERGED_PENDING_REGENERATION` | Merged at the authorized head. `main` equals the merge SHA. Regeneration has been dispatched. |
| `MERGED_PENDING_REGEN_PR` | Regeneration opened, updated or already holds a reviewed-pending PR. Branch, PR number, PR head and source SHA are recorded; main CI is not run. Exit 3. **Not integrated.** |
| `MERGED_PENDING_MAIN_CI` | `REGEN_NO_CHANGE`. Main CI has been dispatched on the merge SHA. |
| `INTEGRATED` | Main CI succeeded on the exact merge SHA, and `main` has not moved. Exit 0. |
| `POST_MERGE_FAILED` | Any failure: not merged; head or main SHA mismatch; `main` moved; run missing, ambiguous, on the wrong commit, failed or timed out; outcome missing or not proving itself (schema, status, target, correlation, paths, branch, PR fields). Exit 1. |

**Correlation (R3-F02).** Each dispatch sends a fresh `uuid4` correlation id. `ci.yml` now
takes a required `correlation_id` input and sets `run-name: CI dispatch <id>` for dispatched
runs (push and PR runs keep their usual titles). The gate accepts only the single run with
that exact title, on `main`, from `workflow_dispatch`, at the exact head SHA:

- A second run with the same title → `RUN_CORRELATION_AMBIGUOUS`.
- A titled run on another commit → `RUN_WRONG_COMMIT`.
- Runs from concurrent dispatches carry other ids and are ignored.

The R2 timestamp-window match is removed. The regeneration outcome must echo the same
`target_sha` and `correlation_id`.

**Preflight**, before merging, at the authorized head:

- `ci.yml` declares a dispatchable `correlation_id` input and `run-name`.
- The regeneration workflow exists, declares `target_sha` and `correlation_id`, references
  the `regen-outcome` artifact, and contains no `git push ... main`.

Otherwise the PR is not merged.

Permissions are unchanged from R2. `actions: write` is the only addition over #92.

## Preserved R2 gates (retested)

- F01: a later `COMMENTED` review does not clear `CHANGES_REQUESTED`, and an unknown review
  state holds the PR.
- F02: all check-run and status pages are read, and incomplete pagination holds the PR. No
  checks at all gives `UNKNOWN`, which holds.
- Owner actor + `merge-gate` environment, `--match-head-commit`, `validate_dispatch` and the
  denylist are unchanged.
- No order, broker or MT5 path appears in the merge workflow (asserted).

## PR #91 handoff (writer: Codex, branch `codex/gen-files-ci-1`, head `25b6cfe`; not edited)

`25b6cfe` fails the R3 preflight with `WORKFLOW_PUSHES_MAIN` and `WORKFLOW_NOT_DISPATCHABLE`
(asserted in `test_pr91_head_as_observed_fails_the_contract`). Required changes:

1. Remove `git push origin HEAD:refs/heads/main` and the `[skip ci]` bot-commit-on-main path.
2. Implement the contract table above.
3. Add `correlation_id` input and `run-name: regenerate at ${{ inputs.target_sha }} [${{ inputs.correlation_id }}]`.
4. Emit and upload `regen-outcome` with `if: always()`.
5. Add tests for no-change, changed-output (created), identical re-dispatch (pending, no push),
   different source (updated with lease), stale main (failed), unexpected path (failed),
   and an assertion that the workflow has no `main` push.
6. Merge current `main` (after #96) and keep both `ci.yml` edits: #96's `run-name` +
   `workflow_dispatch.inputs.correlation_id`, and #91's `docs-drift` changes.
7. Resolve thread `PRRT_kwDOUHMgtM6qkrGk` only once the above is pushed.

## Tests (2026-10-09, Linux cloud container, Python 3.12-compatible)

- `python -m pytest -q tests/test_merge_gate_r3.py tests/test_merge_gate_r2.py tests/test_pr_readiness.py`:
  41 passed.
  - R3: 25 tests. They cover no-change → INTEGRATED, PR created/updated/pending → MERGED_PENDING_REGEN_PR
    (main CI not dispatched), failed run or outcome, unexpected path, target, correlation and
    schema mismatches, the missing artifact, stale or moved main, head mismatch, the wrong-commit
    run, concurrent foreign runs, ambiguous correlation, timeouts, main CI failure, the static
    workflow contract, the fixed point, the emit CLI, and owner-gate permissions.
  - R2 F01/F02: 7 tests.
  - Existing readiness: 9 tests.
- `python -m pytest -q`: 1538 passed, 2 skipped.
- Docs gate: `generate_live_status.py --check`, `collect_facts.py` (no diff), `cog --check`,
  `check_drift.py` (0 errors), `build_context_pack.py --check`, and
  `tests/test_docs_live.py tests/test_context_pack.py` (23 passed).

## Limits and deferred validation

- No live gated run, dispatch or artifact download has happened. Behavior is proven by unit
  tests with a fake API. The first owner-dispatched run is the live validation.
- `actionlint` is not installed here. Workflow YAML is validated with PyYAML plus structural
  assertions.
- Every gated merge refuses at preflight until #91 implements this contract. This is
  fail-closed by design.
