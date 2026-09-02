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
- SMC validation: [`status/SMC_SKILL_VALIDATION.md`](status/SMC_SKILL_VALIDATION.md),
  [`status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md`](status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md),
  [`status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md`](status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md),
  and [`status/SMC_TRAP_GUARD_V1_STATUS.md`](status/SMC_TRAP_GUARD_V1_STATUS.md)
- Frozen phases: [`status/PHASE_1_4_FREEZE_STATUS.md`](status/PHASE_1_4_FREEZE_STATUS.md)
  and [`status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md`](status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md)
- Registry and skills: [`status/STRATEGY_REGISTRY_STATUS.md`](status/STRATEGY_REGISTRY_STATUS.md),
  [`status/LARGE_SMC_V1_REGISTRATION_STATUS.md`](status/LARGE_SMC_V1_REGISTRATION_STATUS.md),
  [`status/STRATEGY_WORKFLOW_RESOURCE_AUDIT_STATUS.md`](status/STRATEGY_WORKFLOW_RESOURCE_AUDIT_STATUS.md),
  and [`status/SKILL_OPTIMIZATION_STATUS.md`](status/SKILL_OPTIMIZATION_STATUS.md)
- Large-SMC contract resolution (`ST_LARGE_SMC_V1`, still `RESEARCH_DRAFT`):
  [`status/AG_SHARED_EVIDENCE_STRATEGY_ARCHITECTURE_V1_STATUS.md`](status/AG_SHARED_EVIDENCE_STRATEGY_ARCHITECTURE_V1_STATUS.md),
  [`status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md`](status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md`](status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md),
  [`status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md`](status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md`](status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md`](status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md) (correction: C14 downgraded to `PARTIALLY_RESOLVED`),
  [`status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`](status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md) (M-candidate identity implemented, Option B),
  [`status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`](status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md) (research-only engine, v1.0.5),
  [`status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`](status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md), and
  [`status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`](status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md) (C10 still unsigned; pending-entry expiry resolved as of v1.0.6, see below),
  [`status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`](status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md) (v1.0.6, pending-entry lifecycle), and
  [`status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`](status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md) (discovered gap, resolved same day), and
  [`status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`](status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md) (the fix, parity proof, corrected-replay evidence)
- Opportunity coverage: [`status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`](status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md)
  (FX `LONDON_NEWYORK` pilot activation; BTC Binance USDT-M market-data adapter,
  multi-occurrence research collection, and execution-domain gate)

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
