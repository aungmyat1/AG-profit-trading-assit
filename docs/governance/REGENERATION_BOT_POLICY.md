---
class: authority
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# Regeneration bot policy — PROPOSED, pending owner decision

**Status: PROPOSED.** Nothing in this document is authorized until the owner records a
decision in `docs/governance/OWNER_DECISION_REGISTER.md` (rows `REG-REGEN-BOOTSTRAP` and
`REG-REGEN-STALE-CLOSE`). It does not amend `AGENTS.md`.

**Shipped state (R6B): default deny.** Every regeneration side effect runs only if it is listed
in `config/governance/regen_permissions.json`. The actions are `bootstrap_push`,
`push_regen_branch`, `create_pr`, `close_superseded_pr` and `dispatch_ci`.

A missing or invalid config, or any unknown action name, denies everything. The checks live
in `scripts/governance/regen_permissions.py`. `regen_publish.publish()` applies them, and
again inside every `GhPulls`/`Git` mutating call.

The committed allowlist is `push_regen_branch`, `create_pr` and `dispatch_ci`. **E1
`bootstrap_push` and E2 `close_superseded_pr` are not listed:**

- A first publication fails closed with `REGEN_BOOTSTRAP_DENIED` and pushes nothing.
- Stale bot PRs are left untouched.

Approving E1 or E2 means the owner records the decision, and a reviewed PR then adds the
action to the allowlist. It grants no general permission to
push before a PR exists, to close PRs, or to bypass branch protection.

## Scope

The only actor covered is the `regenerate-generated-files` workflow
(`scripts/governance/regen_publish.py`), running as `github-actions[bot]`. It applies only
to branches named `regen/generated-files-<40-hex source SHA>` and to PRs whose head is such a
branch. Every other branch, PR, agent and person remains under `AGENTS.md` unchanged.

## E1 — bootstrap exception to PR-before-push (`REG-REGEN-BOOTSTRAP`)

GitHub cannot open a PR for a branch that does not exist or has no commits. The proposed
exception covers exactly one push before the PR exists: a branch holding a single **empty**
commit on the source SHA. That commit:

- has no file changes;
- carries the message `chore(regen): open regeneration PR for <sha> (no file changes)`;
- is authored by `github-actions[bot]`.

The draft PR is then opened. Generated content is pushed only after that, as a
fast-forward. If PR creation fails, only the empty commit exists and the next run reuses it.
No other content may precede the PR.

Alternative if rejected: the owner creates each regeneration PR by hand, or waives
PR-before-push for these branches. Either is an owner decision.

## E2 — closing superseded bot PRs (`REG-REGEN-STALE-CLOSE`)

When a newer `main` commit is regenerated, the bot may close an **open** PR when all of the
following hold:

1. its head is `regen/generated-files-<older sha>`;
2. it targets `main`;
3. the bot posts a comment naming the superseding PR or the no-change result.

The closed PR's branch is left unmodified. The bot never closes, edits or comments on any
other PR.

Alternative if rejected: the bot only comments `Superseded` and leaves closing to the owner.
The readiness audit already holds such PRs (`PR_BASE_NOT_CURRENT_MAIN`).

## Invariants (in force regardless of E1/E2)

- No push to `main`, and no force-push or lease-push of any kind.
- One branch per source SHA, advanced only by fast-forward.
- Merging a regeneration PR requires the owner merge gate with its exact head SHA.
- CI is dispatched for, and verified on, the exact published head before the outcome
  reports it.
