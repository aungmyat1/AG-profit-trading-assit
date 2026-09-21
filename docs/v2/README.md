# AG Profit Trading V2 — Documentation Index

V2 is the backend/domain migration that reorganizes AG Profit Trading around two primary capabilities: **Opportunity Finder** and **Execution Engine**, while preserving existing canonical strategy/proposal/execution authorities and keeping the existing frontend unchanged.

These documents are planning/engineering contracts unless a dated status document explicitly records completed evidence. They do not authorize Demo or Live trading and do not establish strategy profitability.

## Core V2 documents

1. [`AG_V2_ARCHITECTURE.md`](AG_V2_ARCHITECTURE.md) — canonical target architecture, authority boundaries, Opportunity Finder/Execution Engine relationship, data-mode firewall, and frontend compatibility direction.
2. [`AG_V2_IMPLEMENTATION_ROADMAP.md`](AG_V2_IMPLEMENTATION_ROADMAP.md) — bounded V2-2A through V2-15 implementation sequence and exit-gate intent.
3. [`AG_V2_OPPORTUNITY_STRATEGY_MODEL.md`](AG_V2_OPPORTUNITY_STRATEGY_MODEL.md) — how strategies plug into the Opportunity Finder, universal funnel semantics, candidate/proposal separation, and strategy examples.
4. [`AG_V2_SAFETY_AND_AUTHORITY_INVARIANTS.md`](AG_V2_SAFETY_AND_AUTHORITY_INVARIANTS.md) — binding engineering invariants for safety, determinism, authority isolation, frontend freeze, shadow migration, and protected-data handling.

## Current implementation evidence

- [`../status/AG_V2_PRE_ARCHITECTURE_BASELINE_STATUS.md`](../status/AG_V2_PRE_ARCHITECTURE_BASELINE_STATUS.md) — current V2 baseline/core-contract implementation status and frontend-freeze addendum.
- [`../../AG_V2_BASELINE_MANIFEST_V1.json`](../../AG_V2_BASELINE_MANIFEST_V1.json) — machine-readable pre-architecture baseline manifest.
- [`../../PROJECT_STATUS.md`](../../PROJECT_STATUS.md) — rolling whole-project status; use this rather than assuming a design document describes current completion.
- [`../PROJECT_ROADMAP.md`](../PROJECT_ROADMAP.md) — master project readiness plan. V2 architecture does not replace economic/execution readiness gates.

## Current next gate

At the time this index was created, the next V2 implementation gate is:

```text
V2-2A_PURE_FUNNEL_TRANSITION_ENGINE
```

A newer dated status document or repository commit may supersede that statement; verify current HEAD and status before execution.

## Frontend constraint

There is no V2 frontend redesign phase. The existing frontend remains the presentation shell. Future backend V2 state must be mapped through compatibility/read-model adapters to existing frontend contracts. A truthful incompatibility is a blocker, not authorization to rewrite the UI.

## Authority reminder

```text
Opportunity detected ≠ proposal authorized
Proposal created ≠ risk approved
Risk approved ≠ execution authorized
Demo authorized ≠ Live authorized
Infrastructure ready ≠ profitable
```
