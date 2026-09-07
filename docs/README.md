# Documentation Index

This directory contains design contracts, implementation architecture, setup guidance,
and dated verification evidence. Read documents according to their authority, not just
their age.

## Start here

1. [`../README.md`](../README.md) — project purpose, safety model, quick start, and map.
2. [`../AGENTS.md`](../AGENTS.md) — mandatory rules for agents working in this repository.
3. [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) — current implementation state,
   safety gates, known gaps, and latest regression baseline.
4. [`setup/MT5_MCP_SETUP.md`](setup/MT5_MCP_SETUP.md) — local MT5 integration setup.
5. [`status/LIVE_STATUS_MAINTENANCE.md`](status/LIVE_STATUS_MAINTENANCE.md) — required
   update procedure for rolling status, dated evidence, strategy authorization, and
   live-validation claims.

## Architecture

- [`architecture/TRADE_ASSISTANT_ARCHITECTURE.md`](architecture/TRADE_ASSISTANT_ARCHITECTURE.md)
  — system responsibilities, execution authority, and runtime flow.
- [`architecture/ARCHITECTURE_CONFLICT_AUDIT.md`](architecture/ARCHITECTURE_CONFLICT_AUDIT.md)
  — recorded architecture conflicts and their disposition.
- [`architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md`](architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md)
  — D-drive strategy provenance and agent-skill workflow organization.

Architecture descriptions do not override Strategy YAML, frozen specifications, or
the execution gates in code and configuration.

## Specifications

The `specs/` directory contains behavior contracts. The most useful entry points are:

- [`specs/SESSION_TRADE_V1_SPEC.md`](specs/SESSION_TRADE_V1_SPEC.md)
- [`specs/LARGE_SMC_V1_SPEC.md`](specs/LARGE_SMC_V1_SPEC.md)
- [`specs/TRADE_MANAGEMENT_V1_SPEC.md`](specs/TRADE_MANAGEMENT_V1_SPEC.md)
- [`specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md`](specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md)
- [`specs/SMC_ASSISTANT_RUNTIME_V1_SPEC.md`](specs/SMC_ASSISTANT_RUNTIME_V1_SPEC.md)
- [`specs/SMC_CONDITIONAL_ENTRY_V2_RUNTIME_SPEC.md`](specs/SMC_CONDITIONAL_ENTRY_V2_RUNTIME_SPEC.md)
- [`specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md`](specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md)
- [`specs/ENTRY_CONFIRMATION_V1_SPEC.md`](specs/ENTRY_CONFIRMATION_V1_SPEC.md),
  [`specs/ENTRY_CONFIRMATION_V2_SPEC.md`](specs/ENTRY_CONFIRMATION_V2_SPEC.md), and
  [`specs/ENTRY_CONFIRMATION_V2_1_SPEC.md`](specs/ENTRY_CONFIRMATION_V2_1_SPEC.md)

Versioned specifications coexist intentionally. Check `PROJECT_STATUS.md` and the
matching status document before assuming a version is active or frozen.

## Status and evidence

Files in `status/` are dated evidence snapshots. They preserve the test counts and
observations from the named milestone; they are not rolling dashboards.

- Runtime: [`status/ASSISTANT_RUNTIME_V1.md`](status/ASSISTANT_RUNTIME_V1.md),
  [`status/ASSISTANT_RUNTIME_V1_STATUS.md`](status/ASSISTANT_RUNTIME_V1_STATUS.md), and
  [`status/FIVE_SKILL_ASSISTANT_RUNTIME_STATUS.md`](status/FIVE_SKILL_ASSISTANT_RUNTIME_STATUS.md)
- Trade Assistant Releases & Pilots: [`status/AG_TRADE_ASSISTANT_V1_0_2_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_2_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_1_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_1_STATUS.md), and
  [`status/AG_POST_ASIAN_LONDON_PILOT_V1_STATUS.md`](status/AG_POST_ASIAN_LONDON_PILOT_V1_STATUS.md)
- SMC validation: [`status/SMC_SKILL_VALIDATION.md`](status/SMC_SKILL_VALIDATION.md),
  [`status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md`](status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md),
  and [`status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md`](status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md)
- Frozen phases: [`status/PHASE_1_4_FREEZE_STATUS.md`](status/PHASE_1_4_FREEZE_STATUS.md)
  and [`status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md`](status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md)
- Registry and skills: [`status/STRATEGY_REGISTRY_STATUS.md`](status/STRATEGY_REGISTRY_STATUS.md),
  [`status/LARGE_SMC_V1_REGISTRATION_STATUS.md`](status/LARGE_SMC_V1_REGISTRATION_STATUS.md),
  [`status/STRATEGY_WORKFLOW_RESOURCE_AUDIT_STATUS.md`](status/STRATEGY_WORKFLOW_RESOURCE_AUDIT_STATUS.md),
  and [`status/SKILL_OPTIMIZATION_STATUS.md`](status/SKILL_OPTIMIZATION_STATUS.md)

When a historical test total differs from the current baseline, retain the historical
number and use `PROJECT_STATUS.md` for the latest result.

`PROJECT_STATUS.md` is the only rolling status page. A dated status document may be
superseded, but it must not be silently rewritten to look current. Follow
[`status/LIVE_STATUS_MAINTENANCE.md`](status/LIVE_STATUS_MAINTENANCE.md) whenever code,
configuration, execution authority, or validation evidence changes operational status.

## Strategy documentation

[`../strategies/STRATEGY_LEDGER.md`](../strategies/STRATEGY_LEDGER.md) indexes registered
strategies and unresolved strategy-authorship decisions. Strategy YAML remains the
authoritative machine-readable source.
