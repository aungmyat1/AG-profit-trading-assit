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

**Shipped state (R6B step 0): both E1 and E2 are DENIED.** In `scripts/governance/regen_publish.py`:

- `ALLOW_BOOTSTRAP_PUSH = False`: a first publication fails closed with `REGEN_BOOTSTRAP_DENIED` and pushes nothing.
- `ALLOW_SUPERSEDE_CLOSE = False`: stale bot PRs are left untouched.

The owner opens regeneration PRs until E1 is approved. It grants no general permission to
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
