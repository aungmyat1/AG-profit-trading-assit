---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP Regeneration R6B milestone (2026-10-09)

This is dated repository and workflow evidence. It records merged revisions and the
regeneration control review; it grants no operational or broker authority. No broker
access or broker mutation was used for this milestone.

## Merged revisions

- PR #99 merged at `373a37e57c8ca796daebc74135aa584268eb3601`.
- PR #100 merged at `8a53baf94a94cbda3c5eef004bac0856652c8d45`.

## Enforcement call-site audit

At the reviewed #100 head, each GitHub mutation checks the committed allowlist before
the side effect: bootstrap and generated-branch pushes require their respective actions;
PR creation requires `create_pr`; superseded-PR comment and close require
`close_superseded_pr`; and CI dispatch requires `dispatch_ci`. No GitHub mutation was
reachable without prior authorization. Local-only Git object/index preparation is not a
GitHub mutation.

## Post-merge and freshness evidence

- Post-merge workflow run `37893327231`, triggered by the #99 merge, recorded
  `REGEN_NO_CHANGE` (neither `REGEN_BOOTSTRAP_DENIED` nor `POST_MERGE_FAILED`).
- At `373a37e`, `scripts/docs/collect_facts.py --check` reported `FACTS_FRESH`.
- The `AGENTS.md` lines 230-232 scope question was resolved as **no conflict**: those
  lines govern a push to an existing PR branch after the PR is merged or closed; they do
  not require opening a PR before publishing a new branch.
