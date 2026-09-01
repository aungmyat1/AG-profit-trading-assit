# Strategy Workflow and D-Drive Resource Map

Status: operational organization guide. This document does not authorize trading or
make another repository authoritative for AG Profit Trading.

## Authority rule

```text
Local strategy YAML -> local deterministic engine -> local risk/execution gates -> MT5
External D-drive repositories -> research/reference evidence only
Agent skills -> advisory/orchestration only
```

No file is copied merely because it contains SMC terminology. A foreign rule enters a
local strategy only through an explicit specification revision, provenance record,
tests, and separate authorization.

## Strategy resource inventory

| Resource | Relevant material | Classification | Use here |
|---|---|---|---|
| `D:\ddev\AG profit trading` | Registered strategies, shared SMC primitives, risk/execution gates | Local authority | Implementation and operational source of truth |
| `D:\ddev\smc-lss-platform` | ST-C1 v1.1.0, SMC-LSS v3.6, ST-C3, validation governance | Research reference | Primary Large-SMC rule/provenance source; adapt only by signed revision |
| `D:\ddev\Session Trade Codex` | SESSION_TRADE_V1 implementation and SMC_3R_V1 | Separate session/day-trading authority | Keep separate; reference only through existing registry entries |
| `D:\ddev\Session-SMC\session-smc-trading-bot` | Strategy B SMC and SVOS governance | Locked session research | Do not use as Large-SMC authority; governance ideas may be reviewed separately |
| `D:\ddev\Integrated_Claude_Forex_PQTA_System_upgraded` | Account-specific SMC-LSS runbook and toolkit | Operational/historical reference | Import only data-safety lessons; never restore decommissioned auto-execution |
| `D:\ddev\Session trade hybrid Workflow` | Hybrid session workflow | No matching Large-SMC contract found | Exclude from Large-SMC definition unless a later scoped audit finds one |

### Large-SMC source precedence

1. `strategies/ST_LARGE_SMC_V1.yaml` and `docs/specs/LARGE_SMC_V1_SPEC.md`.
2. For proposed rule resolution, review `smc-lss-platform/strategies/candidates/ST-C1_v1.1.0.yaml`.
3. For D1/H1 event models and multi-horizon lifecycle research, review
   `smc-lss-platform/specs/v3.6.yaml`.
4. Reimplement accepted rules against AG Profit Trading's shared primitives; do not
   transplant execution or account configuration.
5. Preserve external IDs and results as provenance only. They do not become local
   validation evidence.

ST-C3 may inform rejection-code/state-machine design, but it is not the Large-SMC
contract: its active v1.x lineage uses H4/M15/M3 and deliberately excludes material
stages. Session-SMC Strategy B and SMC_3R_V1 remain session strategies.

## Skill workflow map

### A. Registered strategy evaluation

```text
strategy-management
  -> registry + named contract
  -> deterministic engine/adapter
  -> strategy result
```

Load no generic skill unless the contract explicitly requires it. An inactive,
research-only, or unimplemented strategy returns its fail-closed state.

### B. Session Day Trading

```text
market-data
  -> session-box-drawing
  -> trend-range-classification / sweep-detection-range-v2 (contract-dependent)
  -> deterministic session strategy
  -> risk-position-sizing (eligible signal only)
  -> trade-management-analysis (advisory milestones only)
```

### C. Large SMC research/advisory

```text
market-data
  -> market-structure-analysis
  -> supply-demand-analysis
  -> liquidity-analysis
  -> entry-confirmation-analysis
  -> trade-management-analysis
```

For `ST_LARGE_SMC_V1 RESEARCH_DRAFT`, this produces evidence, not an actionable
proposal. `risk-position-sizing` is deferred until a frozen engine produces an eligible
signal and the strategy signs its risk limits.

### D. Strategy research and promotion

```text
strategy-specification
  -> multi-asset-conventions
  -> market-data-quality
  -> backtest-engineering
  -> robustness-validation
  -> performance-analysis
  -> owner promotion decision
  -> registry/ledger update
```

### E. Manual-entry position management

```text
position-monitor
  -> risk-manager
  -> partial-profit-manager
  -> breakeven-manager
  -> exit-manager
```

This pathway applies only to a manually opened position explicitly claimed by ticket.
It is independent of proposal generation and cannot open a position.

## Skill-set audit

The `.agents/skills` and `.claude/skills` trees contain the same 22 `SKILL.md` files by
hash. The deterministic dual-axis scan covered the 17 top-level skills. It reported no
high-severity findings, but all scores were below its generic merge threshold because
these project skills are intentionally thin, code-delegating wrappers and generally do
not contain their own scripts/tests. Treat those scores as packaging-coverage signals,
not evidence that the delegated deterministic modules are incorrect.

Audit artifact:
`.agents/reports/workflow_skill_audit/skill_review_all_2026-09-01_143835.json`.

## Organization decisions

- Keep `.agents/skills` and `.claude/skills` structurally mirrored.
- Keep trade-management skills nested because they represent an independently gated
  operational pathway.
- Keep other skill directories flat; organize through this workflow map and `AGENTS.md`
  rather than moving paths and breaking discovery.
- Add a strategy-specific skill only when it delegates to a real local engine. A
  research-only Large-SMC engine now exists (`src/large_smc_research/`, 2026-09-02,
  `RESEARCH_ONLY_FUNNEL_V1` — see `docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`),
  but a dedicated `large-smc` skill remains deliberately out of scope until explicitly
  requested — that phase's own instructions excluded skill-specific wrapper
  infrastructure. Engine existing is necessary but not sufficient to justify a skill.
- Add per-skill tests only where the wrapper contains executable behavior; otherwise
  test the delegated module and keep the skill declarative.

