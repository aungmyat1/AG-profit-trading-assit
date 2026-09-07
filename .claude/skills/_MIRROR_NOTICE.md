# Runtime discovery mirror — not canonical

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
