# Runtime discovery mirror — not canonical

## Token minimum usage policy (owner rule, applies to every task)
- Do only what the task asks; no extra features, refactors or docs.
- No polling, scheduled check-ins or PR subscriptions unless explicitly asked.
- Don't ask questions mid-task: make conservative choices, record them, continue.
- Read only files needed; prefer grep/targeted reads over full-file or repo-wide dumps.
- Don't re-run unchanged failing steps; report the blocker once and stop.
- Batch tool calls; avoid repeated verification of the same fact.
- Reports: concise — status, key results, blockers, next step. No restating the prompt,
  no long learning sections unless asked.
- Stop immediately when the task is done.

This directory (`.claude/skills/`) exists only as a **runtime discovery adapter** for
the Claude Code runtime. It is not an independent source of skill semantics.

The **canonical, vendor-neutral skill source** is `.agents/skills/` — see
`.agents/skills/_CANONICAL_SOURCE.md`.

Do not edit a skill here first. Edit it under `.agents/skills/`, copy the change here,
and run `python scripts/check_skill_mirror_drift.py` to confirm the two stay identical.
If a future runtime needs its own discovery directory, add it the same way (a mirror of
`.agents/skills/`, never an independently authored copy) — see
`docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md` ("Universal skill contract
(vendor/model/runtime neutrality)").
