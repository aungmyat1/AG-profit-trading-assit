# Canonical universal skill root

`.agents/skills/` is the **canonical, vendor-neutral source** for every AG Agent Skill
in this repository (designated 2026-09-07,
`AG_UNIVERSAL_AGENT_SKILLS_PORTABILITY_REMEDIATION_V1`).

- Edit skill content (`SKILL.md`, `references/`, etc.) here first.
- `.claude/skills/` is a **runtime discovery mirror** for the Claude Code runtime only —
  see `.claude/skills/_MIRROR_NOTICE.md`. It must never carry skill semantics that don't
  also exist here.
- After editing a skill under this root, copy the changed files into `.claude/skills/`
  (or any future runtime-adapter directory) so they stay identical, then run
  `python scripts/check_skill_mirror_drift.py` to confirm no drift remains.
- `SKILL_REGISTRY.yaml` in this directory is the canonical registry; `.claude/skills/SKILL_REGISTRY.yaml`
  is its mirror.

See `docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md` ("Universal skill contract
(vendor/model/runtime neutrality)") for the full architectural rule.
