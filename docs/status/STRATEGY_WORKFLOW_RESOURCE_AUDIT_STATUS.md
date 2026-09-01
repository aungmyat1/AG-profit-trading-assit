# Strategy Workflow Resource Audit Status (2026-09-01)

## Scope

Read-only inventory of SMC/strategy resources under `D:\ddev`, deterministic review of
the project skill wrappers, and conceptual organization of skills by authoritative
strategy workflow. No external repository was modified and no strategy/execution code
was moved or copied.

## Result

- AG Profit Trading remains the local operational authority.
- `smc-lss-platform` is the primary research reference for Large-SMC contract work,
  specifically ST-C1 v1.1.0 and SMC-LSS v3.6; neither transfers authorization or
  validation results.
- Session-SMC, SMC_3R_V1, and Session Trade assets remain separate session strategies.
- The integrated PQTA auto-signal path remains decommissioned and must not be restored.
- `.agents/skills` and `.claude/skills` are fully mirrored: 22/22 matching hashes.
- The deterministic reviewer scanned 17 top-level skills, found zero high-severity
  findings, and exposed generic packaging/test expectations that do not distinguish
  thin advisory wrappers from standalone executable skills.

## Authority and safety

`ST_LARGE_SMC_V1` remains `RESEARCH_DRAFT`, inactive, without an engine, proposal
authority, demo authorization, or live authorization. `ST_ASIAN_SWEEP_5R_V1` was not
changed. `config/trading.yaml` and all broker gates were untouched.

