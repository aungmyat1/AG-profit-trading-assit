# AG Profit Trading — Project Implementation Plan, Roadmap, Status & Next Execution

**Document status:** Current execution index; non-authorizing  
**As of:** 2026-09-21  
**Repository:** `aungmyat1/AG-profit-trading-assit`  
**Authoritative branch:** `main`  
**Resolved HEAD at package generation:** `a6f4b7d1431e7571a802224846f91f8a97367b32`

This document consolidates the project implementation plan, roadmap, current status,
next task, and expected results in one place. It does not replace the repository,
dated evidence, strategy contracts, authorization configuration, or execution gates.
When this document conflicts with code or a newer dated status record, the repository
and newer dated evidence win.

## 1. Authority and source order

Use these sources in this order when deciding what is true:

1. Current repository files, resolved `main` ref, and local working-tree state.
2. `PROJECT_STATUS.md` for the rolling whole-project classification and historical status evidence.
3. `docs/PROJECT_ROADMAP.md` for the master R0–R9 readiness progression.
4. `docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md` for the V2 implementation sequence.
5. Dated status documents under `docs/status/` for milestone evidence.
6. Design and planning documents for intended behavior only, unless a dated status document records implementation and verification.

A plan, passing unit test, proposal, or readiness label does not by itself authorize a broker order, Demo execution, Live execution, or a profitability claim.

## 2. Current project status

### 2.1 Overall classification

```text
PROJECT_STATUS = ACTIVE / PARTIAL
CURRENT_PROGRAM = V2 transition plus documentation-governance completion
CURRENT_EXECUTION_AUTHORITY = unchanged existing repository authority only
V2_EXECUTION_AUTHORITY = NONE
LIVE_AUTHORITY = NONE unless separately granted by existing contracts
```

### 2.2 Readiness gates

| Area | Current status | Interpretation |
|---|---|---|
| R0 safe foundation | `READY` | Safety containment is maintained. |
| R1 research watch | `READY / RESEARCH_ONLY` | Research and display paths do not authorize orders. |
| R2 real-market watch | `READY` | Read-only real-market watch evidence exists for the current scoped path. |
| R3 canonical strategy | `READY` | The canonical Python strategy remains authoritative. |
| R4 canonical proposals | `READY / PASS` | Proposal formation and persistence are available as informational output. |
| R5 outcome evidence | `PARTIAL` | Evidence collection is incomplete. |
| R6 edge validation | `NOT_PASS` | Economic qualification is not established. |
| R7 scanner-driven Demo | `BLOCKED` | Requires later, separately authorized gates. |
| R8 Demo validation | `BLOCKED` | Not started as an authority promotion. |
| R9 controlled Live | `BLOCKED` | No Live authority is granted. |

### 2.3 V2 status

The V2 contract layer exists under `src/opportunity/`. Current completion must be read from the latest repository status and commits rather than this dated package snapshot. The active sequence is documented in `docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md`.

### 2.4 Documentation status

The documentation package captured a remediated worktree with:

```text
BROKEN_RELATIVE_LINKS = 0
UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = 0
DOCS_LINK_CHECK = PASS
focused checker tests = 4 passed
```

These results become repository evidence only after the corresponding navigation/test changes are committed and re-verified.

## 3. Active implementation roadmap

### Phase 0 — Documentation system remediation

Required work:

- normalize `docs/README.md` navigation;
- link this project execution index, the V2 index, and documentation governance;
- repair stale relative links;
- add focused tests for `scripts/check_docs_links.py`;
- run the checker and record the result.

Exit gate:

```text
DOCS_LINK_CHECK = PASS
BROKEN_RELATIVE_LINKS = 0
UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = 0
focused checker tests = PASS
```

### Phase 1 — V2-2A pure funnel transition engine

Implement deterministic, storage-agnostic, strategy-neutral transition semantics over the existing V2 contracts. The engine must remain side-effect free and must not pull persistence, proposals, risk, execution, scheduler, broker, SVOS, frontend, ranking, or real-strategy migration into the common funnel.

Exit gate:

```text
AG_V2_PURE_FUNNEL_ENGINE_READY
```

### Phase 2 — V2-2B candidate store and transition ledger

Add persistent occurrence identity, append-only transition evidence, current-state materialization, restart reconstruction, deduplication, expiry, and provenance. This phase owns persistence.

### Phase 3 — V2-3 shadow strategy adapters

Implement shadow-only adapters in bounded order, beginning with Large-SMC research and then canonical SSC. Preserve raw strategy state and strategy identity; require parity evidence before authoritative use.

### Phase 4 — Proposal bridge

```text
OpportunityCandidate
    -> ProposalEligibilityDecision
    -> existing formation gate
    -> CanonicalProposal
    -> existing proposal ledger
```

Do not create a second canonical proposal model.

### Phase 5 — Risk and execution authority

Add platform-level risk and execution decisions only after the candidate/proposal boundary is proven. Risk and execution authority are not strategy-funnel stages.

### Phase 6 — Virtual execution and scheduler bridge

Use SVOS as the first automatic consumer where appropriate, then bridge scheduler activity to common `MarketEvent` evaluation without moving strategy rules into the scheduler.

### Phase 7 — Compatibility, parity, and qualification

- preserve the existing frontend through compatibility/read-model adapters;
- prove replay/live semantic parity;
- perform independent economic qualification;
- qualify automatic Demo per strategy;
- treat Live qualification as a separate future authority gate.

## 4. Expected project result

The target is a deterministic, evidence-first trading-assistant platform with:

- one authoritative source per market, strategy, proposal, evidence, governance, and execution layer;
- an observation-first opportunity funnel separating candidate, proposal, risk, and execution authority;
- pure/testable transition semantics;
- explicit persistence and provenance only after pure semantics are proven;
- shadow adapters preserving strategy identity and raw state;
- existing canonical proposal/execution authorities reused rather than duplicated;
- synthetic, replay, and real market-data modes kept separate;
- a frozen frontend preserved through compatibility/read-model adapters;
- economic qualification kept separate from software readiness;
- no implicit Demo or Live promotion.

The expected result is not an automatic profitability claim, a forced daily trade, or unconditional broker execution.

## 5. Stop conditions

Stop and report rather than widening scope if a task would require:

- changing strategy semantics without a separately approved mission;
- accessing protected data outside its declared gate;
- inventing missing market, trade, broker, or timestamp evidence;
- adding platform risk/proposal/execution readiness stages to the strategy funnel;
- pulling persistence, proposal formation, risk, execution, or ranking into the pure funnel engine;
- changing the frozen frontend or breaking existing API contracts;
- resetting, normalizing, rewriting, or committing unrelated operational ledger drift;
- bypassing repository commit/push safeguards;
- treating tests alone as proof of readiness or authority.

## 6. Linked source documents

- [Current rolling project status](../../PROJECT_STATUS.md)
- [Master project readiness roadmap](../PROJECT_ROADMAP.md)
- [V2 documentation index](../v2/README.md)
- [V2 implementation roadmap](../v2/AG_V2_IMPLEMENTATION_ROADMAP.md)
- [V2 baseline/core-contract status](../status/AG_V2_PRE_ARCHITECTURE_BASELINE_STATUS.md)
- [Documentation governance contract](../DOCUMENTATION_GOVERNANCE.md)
- [Documentation maintenance rules](../status/LIVE_STATUS_MAINTENANCE.md)
