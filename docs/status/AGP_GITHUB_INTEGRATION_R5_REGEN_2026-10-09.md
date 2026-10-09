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
| Never push `main` | `regen_publish.py` pushes only `HEAD:refs/heads/regen/generated-files`. The workflow contains no `git push`. |
| Dedicated branch + PR | One bot branch `regen/generated-files`; one draft PR titled `chore(docs): regenerate generated files for <target_sha>` |
| Outcomes | `REGEN_NO_CHANGE`, `REGEN_PR_CREATED`, `REGEN_PR_UPDATED`, `REGEN_PENDING_REVIEW`, `REGEN_FAILED` (always written; artifact `regen-outcome` uploaded with `if: always()`) |
| Exact identity | `workflow_dispatch` inputs `target_sha` + `correlation_id`; checkout must equal `target_sha`; `run-name: regenerate at <target_sha> [<correlation_id>]` (push runs: `push-<run_id>`) |
| Duplicate prevention | Re-dispatch with identical outputs on the same `target_sha` is `REGEN_PENDING_REVIEW`, with no push and no edit. More than one open bot PR, or a bot PR head that differs from the branch, means `REGEN_FAILED`. |
| Stale source | `origin/main != target_sha` → `REGEN_FAILED: STALE_TARGET_SHA` |
| Path allowlist | Any changed path outside the four generated outputs → `REGEN_FAILED: UNEXPECTED_CHANGED_PATH` |
| No loop | Generated outputs are not generator inputs (enforced by R3's test), so after a bot PR merges the next run is `REGEN_NO_CHANGE` |
| Overwrite safety | `--force-with-lease=refs/heads/regen/generated-files:<observed head>` (empty lease when the branch must not exist) |
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
