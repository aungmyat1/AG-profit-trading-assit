---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-GITHUB-INTEGRATION-R5 — PR-based regeneration workflow (2026-10-09)

This change implements the `AG_REGEN_OUTCOME_V1` contract that merged PR #96 expects. It
supersedes PR #91, which stays unedited.

- **Writer of #91:** Codex, branch `codex/gen-files-ci-1`, head `25b6cfe`. It received no
  handoff reply.
- **Commits carried over:** #91's three commits are cherry-picked here with their authorship
  intact (`.gitattributes` LF rules, `generated_files.py`, `check_generated_files.py`,
  `ci.yml` docs-drift, tests).
- **What is replaced:** #91's direct-to-`main` bot commit. This resolves #91's P1 review
  finding, "Route generated-file updates through a PR".

No merge, dispatch, broker or host action was taken.

| Requirement | Implementation |
|---|---|
| Never push `main` | `regen_publish.py` pushes only to `regen/generated-files-<target_sha>` (`push_fast_forward` refuses any other ref). The workflow contains no `git push`. |
| Dedicated branch + PR | One bot branch per source identity, `regen/generated-files-<target_sha>`, with one draft PR titled `chore(docs): regenerate generated files for <target_sha>`. Older open regeneration PRs are superseded (comment + close), never rewritten. |
| Outcomes | `REGEN_NO_CHANGE`, `REGEN_PR_CREATED`, `REGEN_PR_UPDATED`, `REGEN_PENDING_REVIEW`, `REGEN_FAILED` (always written; artifact `regen-outcome` uploaded with `if: always()`) |
| Exact identity | `workflow_dispatch` inputs `target_sha` + `correlation_id`; checkout must equal `target_sha`; `run-name: regenerate at <target_sha> [<correlation_id>]` (push runs: `push-<run_id>`) |
| Duplicate prevention | Re-dispatch with identical outputs on the same `target_sha` is `REGEN_PENDING_REVIEW`, with no push and no edit. More than one open bot PR, or a bot PR head that differs from the branch, means `REGEN_FAILED`. |
| Stale source | `origin/main != target_sha` → `REGEN_FAILED: STALE_TARGET_SHA` |
| Path allowlist | Any changed path outside the four generated outputs → `REGEN_FAILED: UNEXPECTED_CHANGED_PATH` |
| No loop | Generated outputs are not generator inputs (enforced by R3's test), so after a bot PR merges the next run is `REGEN_NO_CHANGE` |
| Overwrite safety | No force-push of any kind (R5.1). Every push is a plain fast-forward, so a concurrent writer's push is rejected and the run fails closed. |
| CI on the bot PR | A PR opened with `GITHUB_TOKEN` gets no `pull_request` CI, so the publisher dispatches `ci.yml` on the bot branch |
| Permissions | `contents: write`, `pull-requests: write`, `actions: write`; concurrency `regenerate-generated-files`, no cancel; job timeout 20 min |

## Merge-gate compatibility (static; no live run)

`workflow_contract_failures(ci.yml, regenerate-generated-files.yml) == []`, asserted in
`tests/test_regen_publish.py`. #96's `post_merge_verify.py` covers:

- dispatch on the exact SHA and binding by correlation;
- bounded waits with timeouts;
- `MERGED_PENDING_REGEN_PR` for any PR outcome, never `INTEGRATED`;
- missing or failed workflows giving `POST_MERGE_FAILED`.

`tests/test_merge_gate_r3.py` checks all of these, and they are unchanged here.

**First live run readiness:** this needs the owner to merge this PR. The gate cannot merge
it, because `main` holds no compliant regeneration workflow yet. The first owner-dispatched
`manual-pr-merge.yml` run after that is the live validation. Until then, nothing in this
record is live-verified.

## Supersession plan for #91

1. The owner reviews and merges this PR by hand at an exact head SHA.
2. The owner closes #91 as superseded. Its commits are carried here, and its P1 finding is
   resolved by this implementation.

## R5.1 review remediation (2026-10-09)

This resolves the three P1 findings raised on PR #97 at `6970650`.

| Finding | Fix | Evidence |
|---|---|---|
| CI deadlock: source PRs that change generator inputs failed `CONTENT_STALE`, though only the post-merge regeneration PR may publish outputs | `check_generated_files.py` now applies one policy per event (details below). `test_context_pack` builds its pack from freshly collected facts instead of committed outputs. | `tests/test_generated_files_ci.py` (6 new policy tests). A real merge-commit run of a register-changing source PR gives `--mode pr`: 0 failures (`REGEN_REQUIRED_AFTER_MERGE` warnings) and `--mode strict`: 2 failures. |
| PR before push: the bot branch was pushed before its PR existed | GitHub cannot open a PR for a branch that does not exist or has no commits. The publisher therefore pushes the branch holding only an **empty bootstrap commit** on `target_sha` (no file changes), opens the draft PR, and only then pushes the generated commit. If PR creation fails, only the empty bootstrap is published, and the next run reuses it. | `test_first_publication_opens_pr_on_empty_bootstrap_before_any_content`, `test_pr_creation_failure_leaves_only_the_empty_bootstrap_and_retry_recovers` |
| Force-push of the shared branch | Branch per source SHA. Plain fast-forward pushes only. When main advances, a new PR is opened and the old one is superseded with its branch untouched. | `test_main_advancement_supersedes_old_pr_and_opens_a_new_one_without_rewriting`, `test_concurrent_publication_is_rejected_not_overwritten`, the `pushes` fixture (asserts no forced or main push on every test), `test_publisher_source_has_no_force_or_main_push` |

**CI policy per event:**

- **`pull_request`:**
  - A regeneration PR must be built for the current base, change only the four outputs, and
    be byte-exact `FRESH`.
  - Any other PR may change outputs only to their exact generated content. Drift in outputs it
    does not change is `REGEN_REQUIRED_AFTER_MERGE` (warning).
- **`workflow_dispatch`** (merge-gate main CI and the bot-branch CI): strict.
- **`push`:** advisory.

The bootstrap commit is a documented, reviewable exception. It carries no file change, and
it is the minimum GitHub requires before a PR can exist. If the owner rejects it, the
alternative is an owner decision to waive PR-before-push for bot regeneration branches.
`regen_contract.validate_outcome` now requires `branch == regen/generated-files-<target_sha>`.

## R5.2 retry recovery (2026-10-09)

This fixes the P1 finding raised on `a62dffe`. Previously, if a generated commit was pushed
and then CI dispatch failed or the process stopped, every retry returned
`REGEN_PENDING_REVIEW` and never dispatched CI for that head.

A retry that finds the head already published now does the following:

1. It verifies provenance. Every commit in `target..head` must be authored by the bot and be
   either the bootstrap or a generated commit carrying `Source: <target>`. A head that is
   only the bootstrap does not count as published.
2. It asks GitHub for the CI state of that exact head, matching `ci.yml` runs by head SHA and
   by `run-name`, which is `CI dispatch regen-<head12>`:
   - `CI_NOT_DISPATCHED`: dispatch now.
   - `CI_PENDING` or `CI_SUCCESS`: no re-dispatch.
   - `CI_FAILED`: `REGEN_FAILED: REGEN_PR_CI_FAILED`.
   - `CI_UNKNOWN`: `REGEN_FAILED: REGEN_PR_CI_UNKNOWN`.
3. A dispatch failure is reported as `REGEN_CI_DISPATCH_FAILED`, and the next run retries
   it. The outcome records `ci_state`.

Tests in `tests/test_regen_publish.py`:

- dispatch fails, then a retry dispatches the exact head;
- the process stops after the push, then is recovered;
- CI is already running or already green, so there is no re-dispatch;
- failed or unknown CI fails closed;
- runs for other heads or titles are ignored;
- a wrong source SHA in the commit provenance is rejected;
- no duplicate commit, PR or dispatch.

The proposed bootstrap exception and bot-PR closure policy are recorded in
`docs/governance/REGENERATION_BOT_POLICY.md` as PENDING_OWNER (`REG-REGEN-BOOTSTRAP`,
`REG-REGEN-STALE-CLOSE`).
