# AG Profit Trading — Master Project Readiness Plan V4

Status: **AUTHORITATIVE MASTER PLAN — V2 INTEGRATED 2026-09-21**

This plan supersedes the V3 implementation ordering while preserving the R0–R9 readiness gates and their safety meaning. Historical plans and dated status documents remain evidence of earlier decisions.

`PROJECT_STATUS.md` and generated live-status evidence own the rolling current classification. This roadmap owns the target architecture, gate ordering, and implementation direction.

**Owner-approved governance layer (2026-09-22):** `docs/governance/AG_MULTI_AGENT_EXECUTION_PROTOCOL_V1.md` records the approved multi-agent operating model (Owner / ChatGPT Architect+Auditor / Claude Builder), a three-class engineering/audit/owner gate model, and a WP-0 through WP-11 work-package sequence layered over the V2-x phases below. It also records the owner-approved decision that `ST_ASIAN_SWEEP_5R_V1@1.1.1` becomes the planned active FX V2 integration target (inserting a new V2-3C phase), replacing `ST_SESSION_SWEEP_CONTINUATION_V1` in that routing role while preserving SSC's code, tests, replay, and evidence unchanged. That governance document does not alter this roadmap's R0-R9 readiness gates or grant any Demo/Live authority; read it alongside this document rather than in place of it.

This document does **not** authorize broker execution, alter strategy semantics, promote a strategy, claim profitability, or grant Demo/Live authority.

## Readiness questions

Project readiness is evaluated through five independent questions:

1. Can the system safely **WATCH**?
2. Can it produce **TRUSTWORTHY PROPOSALS**?
3. Does the strategy have a **VALIDATED EDGE**?
4. Can it **EXECUTE SAFELY**?
5. Has execution **PRESERVED THE EDGE**?

## Master target architecture

All V2 implementation work converges on one canonical authority pipeline:

```text
Market/Data Authority
        ↓
MarketEvent
        ↓
StrategyBinding
        ↓
Strategy Adapter
        ↓
Universal Funnel
        ↓
OpportunityCandidate
        ↓
Proposal Eligibility
        ↓
CanonicalProposal
        ↓
Portfolio RiskDecision
        ↓
ExecutionDecision
        ↓
┌────────────┬───────────────┐
│            │               │
SVOS       Manual          Broker
first      execution       later
```

### Meaning of the three execution branches

- **SVOS first** — deterministic virtual execution and strategy-capacity validation are the first downstream consumer of `ExecutionDecision`. This proves lifecycle, risk, ledger, restart, and parity behavior without granting broker authority.
- **Manual execution** — owner-reviewed execution may be supported under its existing independent authority boundaries. A proposal or `ExecutionDecision` never grants authority by itself.
- **Broker later** — scanner/system-driven broker execution remains gated behind strategy economic qualification, explicit Demo authorization, execution safety, and subsequent Demo qualification.

The branch ordering is deliberate: **SVOS before automatic broker mutation**. Manual execution and existing explicit owner paths remain separately governed and do not prove automatic broker readiness.

## Authority model

```text
MARKET / DATA TRUTH
Broker feed, admitted replay data, or explicitly classified research source
        ↓
EVENT TRUTH
MarketEvent with time, source, mode, provenance, and data authority
        ↓
STRATEGY IDENTITY
StrategyBinding resolves the exact registered strategy/version and authority
        ↓
STRATEGY TRUTH
Canonical strategy implementation through a non-authorizing adapter
        ↓
OPPORTUNITY TRUTH
Universal Funnel + persistent OpportunityCandidate lifecycle
        ↓
PROPOSAL TRUTH
Proposal Eligibility + existing CanonicalProposal + proposal ledger
        ↓
RISK TRUTH
Portfolio RiskDecision
        ↓
EXECUTION-AUTHORITY TRUTH
ExecutionDecision + registry/governance/account/venue authority
        ↓
EXECUTION TRUTH
SVOS first; owner/manual path independently governed; broker automation later
```

AI and advisory agents may diagnose, explain, compare, propose experiments, summarize evidence, and assist operations. They are not an alternative source of market, strategy, proposal, risk, governance, or execution truth.

## Non-negotiable separations

```text
DESIGN != IMPLEMENTED
IMPLEMENTED != VALIDATED
VALIDATED != STRATEGY_AUTHORIZED
MarketEvent != StrategyDecision
OpportunityCandidate != CanonicalProposal
CanonicalProposal != RiskDecision
RiskDecision != ExecutionDecision
ExecutionDecision != BrokerOrder
SVOS_PASS != ECONOMIC_GATE_PASS
ECONOMIC_GATE_PASS != DEMO_AUTHORIZATION
DEMO_QUALIFIED != LIVE_AUTHORIZED
```

Synthetic, replay, research, and real-market modes must retain their identity through the pipeline. No downstream adapter may silently upgrade evidence or authority.

## Current readiness matrix

Current rolling truth remains in `PROJECT_STATUS.md`; this table records the roadmap position known at the V4 integration point.

| Capability | Classification | Master gate |
|---|---|---|
| Safety containment | `READY` | R0 |
| Research/watch foundation | `READY / RESEARCH_ONLY` where applicable | R1 |
| Real-market watch | `READY` | R2 |
| Canonical strategy decisions | `READY` | R3 |
| Canonical proposal operation | `READY / PASS` | R4 |
| Proposal/outcome evidence | `PARTIAL / STRATEGY_DEPENDENT` | R5 |
| Economic edge qualification | `NOT_PASS / NOT_ESTABLISHED` | R5–R6 |
| Controlled Demo execution | `BLOCKED` pending preceding gates and authorization | R7 |
| Demo execution qualification | `BLOCKED` | R8 |
| Controlled Live | `BLOCKED` | R9 |

R2/R3/R4 reached `READY`/`PASS` on 2026-09-11. V2 modernizes and generalizes the architecture without revoking that evidence and without treating V2 engineering completion as economic validation.

---

# Part I — Master readiness gates R0–R9

## R0 — Safe Foundation

Objective: prevent research, display, proposal, V2, or SVOS functionality from acquiring trading authority by capability alone.

Current classification: **READY / maintain**.

Required invariant:

```text
research/synthetic/replay capability
        ↓
observation / evidence
        ↓
NO implicit broker authority
```

Exit: safety boundaries remain fail-closed and independently tested.

## R1 — Research Watch Ready

Objective: safely observe strategy behavior using synthetic, replay, forward-research, or explicitly admitted data.

```text
research data → MarketEvent → strategy research → opportunity evidence → STOP
```

Current classification: **READY** for the established research surfaces. Research output never substitutes for unavailable real market truth.

## R2 — Real Market Watch Ready

Objective: make authoritative broker market data the source of real-market truth.

Required properties include symbol/feed validation, closed-candle semantics, UTC normalization, decision-time/as-of-time separation, freshness/completeness/duplicate protection, explicit market-data mode, and fail-closed handling.

Current classification: **READY** for the proven scope since 2026-09-11.

V2 mapping: `Market/Data Authority → MarketEvent` must preserve all R2 provenance and temporal guarantees.

## R3 — Canonical Strategy Ready

Objective: keep each deterministic strategy implementation as the strategy authority while V2 supplies shared platform contracts around it.

```text
MarketEvent
   ↓
StrategyBinding
   ↓
Strategy Adapter
   ↓
canonical strategy implementation
```

A V2 adapter may normalize inputs/outputs and project funnel state. It may not rewrite strategy semantics, invent geometry, alias a different strategy, or promote a research state.

Current classification: **READY** for the established canonical runtime scope since 2026-09-11.

## R4 — Canonical Proposal Ready

Objective: turn technically eligible strategy opportunities into immutable, non-executable canonical proposals.

V2 target path:

```text
Universal Funnel
      ↓
OpportunityCandidate
      ↓
Proposal Eligibility
      ↓
CanonicalProposal
      ↓
persistent proposal ledger
```

Proposal formation remains non-economic. It proves representability, identity, lineage, freshness, and required geometry; it does not prove profitability or execution eligibility.

Current classification: **READY / PASS** for the established canonical proposal pipeline since 2026-09-11.

**STOP #1:** proposals may be observed and resolved for evidence. They do not authorize broker execution.

## R5 — Edge Validation Ready

Objective: turn strategy occurrences and resolved proposals into complete, immutable economic evidence.

Required dimensions include data integrity, no-lookahead controls, sample completeness, spread, commission, slippage, net expectancy in R, profit factor, drawdown, session/symbol/setup/regime decomposition, robustness, independent replication, and prospective evidence where required.

V2 engineering and R5 validation run in parallel from strategy-adapter integration onward. Do not wait until the end of V2 to discover whether a strategy lacks edge.

Possible evidence outcomes include:

```text
PASS
FAIL / VALIDATED_NEGATIVE
INSUFFICIENT_EVIDENCE
BLOCKED
```

## R6 — Edge Validated / Economic Qualification

Objective: establish strategy-version-specific economic eligibility without granting execution authority.

```text
implementation = READY
watch = READY
proposal = READY
evidence = COMPLETE
economic_edge = VALIDATED
demo_authorization = BLOCKED until separately granted
live_authorization = BLOCKED
```

Thresholds must be frozen prospectively. Agents may diagnose and propose experiments but may not waive failed evidence or promote a strategy.

**STOP #2:** economic qualification permits controlled Demo consideration; it does not authorize Demo or Live trading.

## R7 — Controlled Demo Execution Ready

Objective: allow Demo execution only after economic eligibility, explicit authorization, and safe execution infrastructure are independently established.

```text
DEMO_ELIGIBILITY_GATE
        ↓
DEMO_AUTHORIZATION_GATE
        ↓
DEMO_EXECUTION_GATE
```

V2 contributes `Portfolio RiskDecision` and `ExecutionDecision`. Neither object is a broker order.

The preferred progression is:

```text
ExecutionDecision
      ↓
SVOS automatic virtual execution
      ↓
parity / lifecycle / risk evidence
      ↓
controlled owner-authorized Demo execution
```

Existing explicit/manual execution remains separately governed.

## R8 — Demo Execution Qualified

Objective: prove that validated theoretical edge survives actual Demo broker execution.

Measure actual fills, spread, slippage, latency, commission, realized R, rejected/missed trades, restart recovery, reconciliation, duplicate prevention, risk enforcement, and operational reliability.

Passing `order_send()` is not sufficient.

**STOP #3:** Demo qualification permits evaluation for controlled Live; it does not grant Live authority.

## R9 — Controlled Live

Objective: introduce small capital only after R8 and a separate explicit Live authorization process.

Required controls include per-trade and portfolio ceilings, daily loss/position limits, kill switch, owner-controlled authorization, broker reconciliation, and staged capital scaling.

---

# Part II — V2 engineering implementation roadmap

V2 is the engineering implementation roadmap beneath R0–R9. It does not replace the master readiness gates.

## V2-0A — Mission-1 Authority Finalization

Finalize and commit the one-year replay/data-authority state. Preserve protected-data boundaries and canonical historical authority.

## V2-0B — Pre-V2 Baseline Freeze

Freeze registry/config fingerprints, canonical model inventory, test baseline, strategy authority, replay authority, and execution/proposal boundaries.

## V2-1 — Core Contracts

Implement and freeze:

- `MarketEvent`
- funnel stage/outcome contracts
- `OpportunityCandidate`
- candidate geometry
- `StrategyBinding`
- strategy adapter protocol
- proposal-eligibility vocabulary

## V2-1B — Shared Evidence Authorities

Implement and freeze shared evidence contracts:

- `DataAuthority`
- warmup authority/requirements
- `FrictionEvidence`
- provenance and mode firewalls

## V2-2A — Pure Funnel Transition Engine (`VERIFIED`, 2026-09-21)

Implement a deterministic, storage-independent transition engine:

```text
MarketEvent + FunnelState
        ↓
FunnelTransition + updated OpportunityCandidate
```

No strategy authority or broker authority is granted. Identity continuity, semantic no-op detection, and terminal-outcome stickiness are implemented and test-verified; see `docs/status/AG_V2_2A_2B_IMPLEMENTATION_STATUS.md`.

## V2-2B — Candidate Store + Transition Ledger (`VERIFIED`, 2026-09-21)

Add persistent candidate identity, append-only transitions, restart reconstruction, deduplication, and lifecycle querying. Implemented on top of the existing `runtime_state.store.JsonKeyValueStore`; see `docs/status/AG_V2_2A_2B_IMPLEMENTATION_STATUS.md`.

## V2-3A — Large-SMC Shadow Adapter (`RE_AUDIT_PASS`, 2026-09-22)

Bind the existing Large-SMC research engine to V2 without changing its canonical semantics or `RESEARCH_ONLY` authority. Implemented as a thin adapter over the pre-existing `large_smc_research.watch_lifecycle` projection. Independent audit (`AG_V2_INDEPENDENT_AUDIT_02`) found one blocking defect (a terminal-transition stage regression violating Safety Invariant #9); fixed generically in `opportunity.engine.evaluate_funnel`, then independently re-audited (`AG_V2_3A_REMEDIATION_REAUDIT`, 2026-09-22) with no remaining or new defect found. See `docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md`.

## V2-3B — SSC Shadow / Replay Adapter (`IMPLEMENTED_AND_LOCALLY_VERIFIED`, 2026-09-22)

Bind the canonical SSC evaluator/replay path to V2. Preserve exact strategy identity and prohibit substitution through another runtime strategy. Implemented as a thin adapter over `strategy_contract.decision.StrategyDecision` (itself built from the unchanged `session_sweep_continuation.replay.run_replay`). Independent audit found no defect for this strategy; re-confirmed by the subsequent re-audit. See `docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md`.

## Parity Checkpoint #1 — Large-SMC + SSC (`PASS`, 2026-09-22)

Require canonical/V2 parity for decisions, time, provenance, replay behavior, candidate determinism, future-data isolation, and strategy identity. An independent audit found one blocking Large-SMC defect; the shared-engine remediation was independently re-audited and confirmed clean, and SSC remained clean throughout. See `docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md` for the full audit findings, remediation, re-audit evidence, and remaining non-blocking debt.

`SAFE_TO_ADVANCE_TO_V2_4 = YES` for the bounded, non-authorizing ProposalEligibility bridge. No proposal, Demo, Live, broker, or execution authority is granted, and this does not by itself authorize V2-5.

## V2-3C — Asian Sweep Shadow Adapter (planned, WP-1)

Owner-approved (2026-09-22, `docs/governance/AG_MULTI_AGENT_EXECUTION_PROTOCOL_V1.md`) as the planned active FX V2 integration target, replacing `ST_SESSION_SWEEP_CONTINUATION_V1` in that routing role. Bind the canonical `ST_ASIAN_SWEEP_5R_V1@1.1.1` `strategy_engine/` evaluator to V2 following the same thin-adapter, no-rule-duplication discipline already proven by V2-3A/V2-3B. Preserves the strategy's existing `research: true` / `demo_authorized: false` / `live_authorized: false` registry authority and its existing negative R5 evidence unchanged; becoming the active V2 integration target is not an economic promotion. `LEVEL B` gate (independent audit required).

## SSC Active Routing Removal (planned, WP-2)

After V2-3C's gate passes, remove SSC from active V2 FX operational/reference routing. SSC's source, V2 adapter, tests, replay evidence, and validation artifacts are preserved unchanged — this is a routing change (`SSC_ACTIVE_ROUTING_REMOVAL`), not deletion or reattribution of SSC's history. `LEVEL B` gate.

## V2-4 — Formation / ProposalEligibility Bridge

Evaluate whether a candidate is technically eligible to form a canonical proposal using strategy identity, data authority, evidence completeness, freshness, geometry, and research/proposal firewalls.

This is not an economic qualification gate.

## V2-5 — CanonicalProposal Integration

Reuse the existing `CanonicalProposal`, formation gate, occurrence identity, and proposal ledger. Preserve candidate-to-proposal lineage.

## V2-6 — BTC + Asian / Session Adapters

Add independently contracted adapters for BTC liquidity-sweep and Asian/session strategies. Shared platform contracts must not collapse distinct strategy semantics.

## Parity Checkpoint #2 — Multi-Strategy

Prove that Large-SMC, SSC, BTC, and Asian/session strategies can share platform infrastructure while retaining independent identity, semantics, authority, and evidence.

## V2-7 — Portfolio RiskDecision Engine

Introduce portfolio-level feasibility after proposal formation:

- risk budget
- max concurrent positions
- symbol conflicts
- correlated exposure
- account constraints
- portfolio exposure

Risk remains outside strategy signal logic.

## V2-8 — ExecutionDecision + Authority Model

Combine proposal validity, `RiskDecision`, strategy authorization, account/venue authority, data-mode restrictions, and owner/manual approval requirements into a fail-closed `ExecutionDecision`.

```text
CanonicalProposal
       ↓
Portfolio RiskDecision
       ↓
ExecutionDecision
```

`ExecutionDecision` does not call a broker and does not upgrade authorization.

## V2-9 — SVOS Automatic Virtual Execution

Make SVOS the first automatic execution consumer:

```text
ExecutionDecision
       ↓
virtual exchange
       ↓
virtual account
       ↓
ledger
       ↓
lifecycle outcome
```

Primary purposes:

- strategy-capacity validation
- deterministic lifecycle proof
- restart parity
- risk parity
- friction determinism
- engineering parity

SVOS results do not substitute for economic qualification or broker evidence.

## V2-10 — Scheduler → MarketEvent Bridge

Route governed scheduler windows through `MarketEvent` and the V2 pipeline while preserving existing session/time authority, catch-up rules, deduplication, and research/proposal boundaries.

Target operational path:

```text
Market/Data Authority
        ↓
MarketEvent
        ↓
StrategyBinding
        ↓
Strategy Adapter
        ↓
Universal Funnel
        ↓
OpportunityCandidate
        ↓
Proposal Eligibility
        ↓
CanonicalProposal
        ↓
Portfolio RiskDecision
        ↓
ExecutionDecision
        ↓
SVOS first / Manual execution / Broker later
```

## V2-11 — Existing API Compatibility Integration

The existing frontend is frozen for the V2 migration. Map V2 internal objects through compatibility/presentation adapters into existing API contracts.

Do not redesign the frontend or upgrade research states to actionable states to satisfy presentation fields.

## V2-12 — Existing Frontend Regression Validation

Prove existing pages, routes, fields, controls, and fail-closed execution behavior remain compatible. Frontend execution controls must not gain authority from V2 serialization.

## V2-13 — Replay / Virtual / Live-Observation Parity Campaign

Compare historical replay, SVOS/Virtual Demo, and live observation for:

- MarketEvent parity
- strategy decision parity
- candidate parity
- proposal parity
- risk parity
- temporal parity
- friction determinism
- restart parity
- lifecycle parity

No automatic Demo authorization follows from parity alone.

## V2-14 — Strategy Economic Qualification

This is the formal consolidation gate for R5/R6, **not the beginning of strategy validation**.

For each strategy/version:

```text
development evidence
      ↓
failure decomposition
      ↓
hypothesis testing
      ↓
independent replication
      ↓
friction analysis
      ↓
robustness
      ↓
prospective / virtual evidence
      ↓
protected holdout when authorized
      ↓
economic qualification
```

Allowed outcomes:

```text
QUALIFIED
VALIDATED_NEGATIVE
INSUFFICIENT_EVIDENCE
BLOCKED
```

Never force a pass to advance the engineering roadmap.

## V2-15 — Per-Strategy Controlled Demo Qualification

Replace the earlier concept of automatic `AUTO_DEMO` promotion with controlled, strategy-specific Demo qualification.

Prerequisites:

```text
V2 engineering gates PASS
        +
R5 evidence gate PASS
        +
R6 economic qualification PASS
        +
explicit Demo authorization
        ↓
controlled Demo campaign
```

Validate broker checks/fills, actual friction, margin, SL/TP lifecycle, reconciliation, restart recovery, duplicate prevention, risk enforcement, ledger parity, and operational reliability.

A later separately approved sub-gate may authorize automatic Demo execution. Controlled Demo qualification does not imply Live authorization.

## Future — Live Qualification

Live remains a separate program after Demo qualification:

```text
DEMO_QUALIFIED
      ↓
explicit owner decision
      ↓
Live readiness audit
      ↓
capital/risk contract
      ↓
venue/account authorization
      ↓
controlled Live pilot
      ↓
Live evidence
      ↓
possible strategy-specific LIVE_QUALIFIED
```

---

# Part III — Parallel strategy-validation lane

V2 engineering and strategy research must progress in parallel.

```text
V2 ENGINEERING
V2-2 → V2-3 → V2-4 → ... → V2-14
             │
             └───────────────┐
                             ▼
                    CONTINUOUS R5/R6
                    STRATEGY VALIDATION
```

From V2-3 onward, each integrated strategy should continue collecting admissible evidence. Do not complete the entire platform before asking whether the strategies have economic edge.

Engineering completion cannot rescue a losing strategy. A negative result is a valid research outcome.

---

# Part IV — Strategy readiness remains independent

Maintain independent dimensions for each strategy version:

```yaml
strategy_readiness:
  implementation:
    status: READY | PARTIAL | BLOCKED
  market_watch:
    status: READY | PARTIAL | BLOCKED
  proposal:
    status: READY | BUILDING | BLOCKED
  evidence:
    status: COMPLETE | VALIDATING | INSUFFICIENT_EVIDENCE | BLOCKED
  economic_edge:
    status: VALIDATED | FAILED | INSUFFICIENT_EVIDENCE | NOT_EVALUATED
  demo:
    eligibility: ELIGIBLE | BLOCKED | NOT_EVALUATED
    authorization: AUTHORIZED | BLOCKED
    execution: READY | PARTIAL | BLOCKED
  live:
    eligibility: ELIGIBLE | BLOCKED | NOT_EVALUATED
    authorization: AUTHORIZED | BLOCKED
    execution: READY | PARTIAL | BLOCKED
```

This roadmap does not itself update the registry or grant any of these statuses.

---

# Part V — Priority progression

The shortest defensible path toward a monetizable trading system is:

```text
trustworthy market/data authority
        ↓
canonical multi-strategy opportunities
        ↓
trustworthy proposals
        ↓
complete outcome evidence
        ↓
credible positive economic edge
        ↓
SVOS capacity/parity proof
        ↓
controlled Demo execution
        ↓
Demo edge preservation
        ↓
separately authorized controlled Live
```

Do not optimize UI breadth, READY count, proposal count, automatic broker features, or strategy count ahead of evidence quality and the current gate.

## Immediate implementation order

```text
Documentation maintenance (parallel, non-blocking where safe)
        │
        ├─────────────────────────────┐
        ▼                             ▼
V2-2A Pure Funnel Engine       Continuous R5/R6 evidence
        ↓
V2-2B Candidate Store + Ledger
        ↓
V2-3A Large-SMC Adapter ──────→ Large-SMC evidence continues
        ↓
V2-3B SSC Adapter ────────────→ SSC validation continues
        ↓
Parity Checkpoint #1
        ↓
V2-3C Asian Sweep Adapter (WP-1, planned) ──→ Asian Sweep evidence continues, PAUSED_BY_OWNER
        ↓
SSC Active Routing Removal (WP-2, planned, after V2-3C gate) ──→ SSC preserved as reference
        ↓
V2-4 ProposalEligibility
        ↓
V2-5 CanonicalProposal integration
        ↓
V2-6 Additional strategy adapters
        ↓
V2-7 Portfolio RiskDecision
        ↓
V2-8 ExecutionDecision
        ↓
V2-9 SVOS automatic virtual execution
        ↓
V2-10 Scheduler MarketEvent bridge
        ↓
V2-11 / V2-12 compatibility validation
        ↓
V2-13 system parity campaign
        ↓
V2-14 formal economic qualification
        ↓
QUALIFIED strategies only
        ↓
V2-15 controlled Demo qualification
        ↓
Future R9 Live qualification
```

## Final governing principle

> **Engineering completion must never be interpreted as evidence of trading edge, and economic qualification must never automatically grant execution authority.**

The target system is therefore not merely a strategy runner. It is a governed chain from authoritative market data to strategy identity, opportunity lifecycle, canonical proposals, portfolio risk, explicit execution decisions, virtual proof, controlled human execution, and only later separately authorized broker automation.
