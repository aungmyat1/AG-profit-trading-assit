# AG Profit Trading V2 — System Architecture

Status: **PROGRAM ARCHITECTURE / NON-AUTHORIZING**  
Date: 2026-09-21

This document describes the target V2 architecture. It does not change strategy semantics, strategy parameters, proposal authority, Demo/Live authority, broker execution authority, or frontend behavior. Current dated status evidence remains under `docs/status/`; `strategies/registry.yaml` remains authoritative for strategy authorization.

## Product objective

AG Profit Trading V2 is organized around two primary backend capabilities:

1. **Opportunity Finder** — observe authoritative market events, route them to eligible strategy adapters, track strategy-neutral funnel progress, persist opportunity occurrences, and hand only eligible opportunities to the canonical proposal path.
2. **Execution Engine** — consume canonical proposals, apply portfolio risk and explicit execution authority, then route permitted actions to virtual, manual, Demo, or later separately-authorized Live execution paths.

The existing frontend is frozen. V2 changes backend/domain architecture underneath the current presentation contracts.

## Canonical flow

```text
Market/Data Authority
        ↓
MarketSnapshot
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
ProposalEligibilityDecision
        ↓
CanonicalProposal
        ↓
Portfolio RiskDecision
        ↓
ExecutionDecision
        ↓
Execution Route
```

The semantic boundaries are strict:

```text
candidate ≠ proposal ≠ risk approval ≠ execution authorization ≠ order
execution capability ≠ execution authority
validation status ≠ economic edge ≠ Demo authorization ≠ Live authorization
```

## One authority per layer

| Layer | Authority |
|---|---|
| Market truth | existing broker/feed + canonical `MarketSnapshot` |
| Event normalization | V2 `MarketEvent` |
| Strategy truth | canonical strategy engine owned by each strategy |
| Strategy routing | `StrategyBinding` |
| Opportunity lifecycle | V2 funnel + candidate/transition infrastructure |
| Proposal truth | existing `CanonicalProposal`, formation gate, proposal ledger |
| Risk truth | future portfolio `RiskDecision` |
| Governance truth | registry/lifecycle/validation/authorization gates |
| Execution truth | execution authority + execution gateway |
| Presentation | existing frontend through compatibility/read-model adapters |

AI may summarize, diagnose, compare, and support research. AI is not a source of market truth, strategy truth, authority, or broker mutation.

## Opportunity Finder

The Opportunity Finder is not a trading strategy. Strategies own setup logic; the finder owns common lifecycle infrastructure.

```text
MarketEvent
   ↓
StrategyBinding
   ├── SSC adapter
   ├── Large-SMC adapter
   ├── BTC adapter
   ├── Asian/session adapter
   └── future adapters
          ↓
   Universal Funnel
          ↓
 OpportunityCandidate
```

Strategies answer **what constitutes a setup**. The Opportunity Finder answers **which occurrences exist, how far each has progressed, whether it is waiting/invalid/expired, and whether it is eligible to enter the proposal path**.

### Funnel vocabulary

Stages:

```text
MARKET_ELIGIBLE
CONTEXT_VALID
LOCATION_VALID
SETUP_DETECTED
TRIGGER_ARMED
ENTRY_CONFIRMED
OPPORTUNITY_READY
```

Outcomes are an independent axis:

```text
ACTIVE
WAIT
REJECT
INVALIDATED
EXPIRED
ERROR
```

Portfolio risk is deliberately outside the strategy funnel. `RISK_FEASIBLE`, proposal readiness, and execution readiness are not funnel stages.

### Strategy adapters

A strategy adapter translates canonical strategy output into normalized funnel evidence. It must not duplicate or reinterpret strategy rules and must not build proposals or reach execution.

Conceptually:

```text
Strategy Engine
    ↓
StrategyObservation
    ↓
FunnelProjection
    ↓
Pure Funnel Engine
    ↓
FunnelState / FunnelTransition
```

Raw strategy states remain preserved. For example, `RESEARCH_QUALIFIED` must never be silently upgraded to actionable `READY`.

## Strategy identity and authority

Registration, dispatchability, proposal authority, and execution authority are separate facts. Current V2 baseline evidence establishes that only `SESSION_TRADE_V1` is manager-dispatchable; the registered SSC, Asian Sweep, Large-SMC, and BTC liquidity-sweep strategies are not thereby dispatchable or execution-authorized.

V2 must never propagate authority through aliases, similar names, adapters, or common funnel stages.

## Data-mode firewall

Data mode is explicit and preserved end-to-end:

```text
SYNTHETIC → cannot become runtime-executable proposal
REPLAY    → cannot reach real broker execution
REAL      → still requires proposal, risk, and execution authority
```

Missing required evidence fails closed. V2 must not invent entry, stop, target, timestamp, friction, lineage, broker metadata, margin, strategy identity, or authority.

## Execution Engine target

Execution is downstream from opportunity discovery and canonical proposal formation:

```text
CanonicalProposal
       ↓
Portfolio RiskDecision
       ↓
ExecutionDecision
       ↓
┌─────────────┬──────────────┬──────────────┐
│ SVOS/Virtual│ Manual route │ Broker route │
└─────────────┴──────────────┴──────────────┘
```

Interaction and environment authority should remain separable so that future combinations such as `AUTOMATIC + VIRTUAL`, `CONFIRM_REQUIRED + DEMO`, or later qualified `AUTOMATIC + DEMO` do not imply `AUTOMATIC + LIVE`.

SVOS is the intended first automatic consumer because virtual execution can validate orchestration without granting broker authority.

## Frontend freeze

The existing frontend layout, pages, components, navigation, controls, styling, routes, API calls, and visible semantics are frozen for this migration.

Compatibility direction:

```text
V2 internal object
      ↓
presentation/API compatibility adapter
      ↓
existing API response
      ↓
existing frontend
```

Do not redesign the UI to expose V2 internals. If a backend state cannot be represented truthfully through existing contracts, report `BLOCKED_FRONTEND_COMPATIBILITY`; do not upgrade research or blocked states for presentation convenience.

## Migration principle

V2 is additive and compatibility-first. Existing canonical infrastructure is reused rather than replaced. Strategy adapters begin in shadow mode and must pass parity gates before becoming authoritative consumers.

No V2 infrastructure-readiness milestone is evidence of profitability or permission to trade.