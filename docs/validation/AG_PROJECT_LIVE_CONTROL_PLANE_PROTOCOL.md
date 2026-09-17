# AG Project Live Control Plane — Operating Protocol

Status: CURRENT_PLAN / AUTHORITATIVE_CONTRACT for the live-status generator and
concurrency rule described below. This is the runbook referenced by
`docs/status/PROJECT_LIVE_STATUS.md`'s generator provenance section.

## Mandatory live-state protocol

Any agent or session about to plan or execute work in this repository should:

1. Read `docs/status/PROJECT_LIVE_STATUS.md`.
2. Run `python scripts/generate_live_status.py --check`.
3. Run `git status --short`.
4. Identify any foreign/concurrent WIP (untracked paths not owned by this session).
5. If live state is `LIVE_STATUS_STALE` or `LIVE_STATUS_MISSING`, regenerate
   (`python scripts/generate_live_status.py`) before planning further.
6. Execute exactly one authorized gate.
7. Update authoritative evidence (never foreign WIP).
8. Run tests.
9. Regenerate live status.
10. Run `--check` again to confirm it is now fresh.
11. Stage only mission-owned files.
12. Commit only mission-owned files.
13. Report.
14. STOP.

**Never run two write-capable agents against the same working tree.** Commit
`873dd68` demonstrated the failure mode: a shared working tree accumulated
independently-prepared, unrelated content into one mixed commit. The content
happened to survive audit intact (see
`docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md`), but that was verified after the
fact, not guaranteed by the workflow.

## Concurrency governance — one writer per worktree

Recommended model:

- **Main worktree** — owner/integration only.
- **Agent worktree per active write-capable mission** (e.g. one for SSC work, one for
  external-source work, one for Large-SMC work), each on its own branch.

Read-only audits (status checks, `--check`, evidence review) may run concurrently
against any worktree, including the main one. Write-capable missions must not share a
working tree with another write-capable mission. Merge deliberately (review + PR/merge
commit) rather than relying on two agents interleaving writes into the same tree.

This repository already has many parallel worktrees under `.claude/worktrees/` and
sibling paths (visible via `git worktree list` / `git branch -vv`) — this rule
formalizes existing practice, it does not introduce new tooling. No distributed lock
is implemented; this is a documented convention, not an enforced mechanism.

## What the live-status generator is and is not

- It is a **read-only** deterministic snapshot generator
  (`src/validation_orchestrator/live_status.py` +
  `src/validation_orchestrator/render.py` + `scripts/generate_live_status.py`) built
  on top of the existing AVO-WP1 state model (`src/validation_orchestrator/status.py`).
- It never trades, promotes a strategy to Demo or Live, opens a holdout, or optimizes
  a strategy. It only reads canonical registry/lifecycle/validation evidence and git
  state, and renders what that evidence already says.
- It does not treat untracked/foreign working-tree content as authoritative. An
  untracked directory appearing in `docs/status/PROJECT_LIVE_STATUS.md` section 8 is
  exposed for visibility only — its presence never advances any strategy's
  `validation_state`, `demo_authorized`, or `live_authorized`.
- Its state fingerprint excludes every timestamp field by construction
  (`LiveStatusSnapshot.semantic_tuple()` / `StrategyValidationStatus.semantic_tuple()`)
  so that regenerating against unchanged evidence never produces a spurious diff, while
  any real change (HEAD, a registry/lifecycle value, a validation state, an
  authorization flag, a blocker) does.
