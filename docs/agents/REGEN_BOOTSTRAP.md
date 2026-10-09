---
class: design
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# Regeneration first-PR bootstrap (owner, manual; no allowlist change)
Use when a regeneration run fails with `REGEN_BOOTSTRAP_DENIED`. Let `SHA` be the run's `target_sha`, which must equal current `main`.
1. Check `git rev-parse origin/main` = `SHA`. If `main` moved, dispatch regeneration again on the new head instead.
2. `git switch --detach SHA`
3. `git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" commit --allow-empty -m "chore(regen): open regeneration PR for SHA (no file changes)"`. The message must be exact: the publisher's provenance check accepts only this bootstrap.
4. `git push origin HEAD:refs/heads/regen/generated-files-SHA` (a plain push; the commit adds no files).
5. `gh pr create --draft --base main --head regen/generated-files-SHA --title "chore(docs): regenerate generated files for SHA"`
6. `gh workflow run regenerate-generated-files.yml -f target_sha=SHA -f correlation_id=owner-bootstrap-1`. The bot then pushes the generated commit as a fast-forward and dispatches CI. Expected outcome: `REGEN_PR_UPDATED`, `ci_state=CI_PENDING`.
7. When CI is green, mark the draft PR ready for review: `gh pr ready regen/generated-files-SHA`.
8. Invoke `manual-pr-merge.yml` with that PR number and exact head SHA; merge only when its gate passes.
Do not edit `config/governance/regen_permissions.json`. Do not add files in step 3.
Verified offline by `tests/test_regen_publish.py::test_owner_manual_bootstrap_runbook_works_with_committed_allowlist`.
