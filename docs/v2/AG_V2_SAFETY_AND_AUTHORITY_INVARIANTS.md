# AG V2 — Safety and Authority Invariants

Status: **BINDING V2 ENGINEERING CONSTRAINTS / NON-AUTHORIZING**  
Date: 2026-09-21

These invariants constrain V2 implementation. They do not themselves grant trading authority.

## 1. Semantic separation

Always preserve:

```text
candidate ≠ proposal
proposal ≠ risk approval
risk approval ≠ execution authorization
execution authorization ≠ order
execution capability ≠ execution authority
validation status ≠ economic edge
Demo eligibility ≠ Demo execution
Demo authority ≠ Live authority
```

## 2. Strategy ownership

Strategy rules live in the canonical strategy implementation. Do not duplicate strategy logic in the Opportunity Finder, scheduler, frontend, risk engine, or execution engine.

Adapters translate; they do not reinterpret or optimize strategy semantics.

## 3. Authority isolation

A common funnel stage, adapter, binding, API serializer, UI field, alias, or similarly named strategy must never promote authority.

Current authority remains whatever the authoritative registry/governance evidence says. Infrastructure readiness is not authorization.

## 4. Research-state preservation

Research states remain research states. In particular, do not translate `RESEARCH_QUALIFIED` into actionable `READY` unless the owning strategy contract explicitly defines that equivalence and the relevant proposal/authority gates independently permit it.

## 5. Missing evidence fails closed

Never fabricate:

- market timestamps;
- entry, invalidation, stop, or targets;
- friction/commission/slippage evidence;
- broker/account/margin metadata;
- dataset lineage or identity;
- strategy identity/version;
- proposal eligibility;
- risk approval;
- execution authority.

Missing required evidence yields explicit incomplete/blocked/unavailable behavior.

## 6. Data-mode firewall

```text
SYNTHETIC → no runtime-executable proposal
REPLAY    → no real broker execution
REAL      → still requires all downstream gates
```

Mode must remain explicit through normalization, candidates, proposal eligibility, and execution decisions.

## 7. Funnel purity

The common funnel owns generic lifecycle legality, not trading logic.

It must not contain portfolio risk or execution readiness stages. It must not import real strategy engines, proposal persistence, broker execution, SVOS mutation, frontend code, or AI authority logic.

## 8. Determinism

Pure transition decisions must not depend on wall-clock time, random identity, filesystem state, network state, broker state, mutable globals, or hidden process state. Required values are explicit inputs.

Equivalent normalized semantic input must not create new semantic transitions merely because the system polled again.

## 9. Terminal truth

Entering a terminal outcome is a semantic state change. Once an occurrence is terminal, ordinary evaluation cannot reactivate it. A later valid setup belongs to a new occurrence under the persistence/identity layer.

Terminal invalidation/expiry preserves the highest stage actually reached; history is not rewritten by moving the stage backward.

## 10. Persistence truth

Semantic transition history belongs in an append-only transition ledger. `OpportunityCandidate` should represent current opportunity truth rather than carry an ever-growing history.

Persistent candidate/occurrence identity belongs to the candidate-store/ledger layer. Earlier pure-engine work must not invent persistence identity solely for hashing convenience.

## 11. Proposal boundary

Only an explicit `ELIGIBLE` `ProposalEligibilityDecision` may proceed to the existing canonical proposal formation path. The strategy adapter must not construct `CanonicalProposal` directly.

Existing `CanonicalProposal`, formation gate, and proposal ledger remain canonical unless a separately approved migration changes that authority.

## 12. Risk boundary

Portfolio risk is downstream of canonical proposal formation. Strategy funnels must not contain `RISK_FEASIBLE` or equivalent platform-risk stages.

## 13. Execution boundary

Execution requires an explicit execution decision and environment authority. A broker-capable gateway or existing manual control does not independently authorize mutation.

Live authority is always separately qualified from virtual/Demo authority.

## 14. Frontend freeze

Frontend source, layout, navigation, controls, styling, existing routes/API calls, and visible semantics are frozen during V2 migration.

Required compatibility direction:

```text
V2 backend → compatibility/read model → existing API contract → existing frontend
```

If truthful mapping is impossible, return/report `BLOCKED_FRONTEND_COMPATIBILITY`; do not rewrite the frontend or upgrade blocked/research states.

## 15. Shadow migration

Initial real-strategy V2 adapters run in shadow mode beside the existing authoritative path. Compare results as `MATCH`, `MISMATCH`, or `NOT_COMPARABLE`. No adapter becomes primary until parity is demonstrated.

## 16. Protected-data firewall

Protected OOS/holdout data may be accessed only under its explicit validation gate. Architecture migration is not authorization to inspect protected data.

## 17. Operational-state isolation

Mutable scheduler/proposal ledger drift produced by background processes is not automatically part of a V2 coding mission. Do not reset, normalize, stage, or commit unrelated operational state merely to obtain a clean tree.

## 18. AI boundary

AI may help summarize opportunities, explain evidence, diagnose failures, compare outcomes, and propose research hypotheses. AI must not silently convert WAIT to READY, invent geometry, mutate authority, bypass risk, or issue broker mutations outside deterministic governed paths.

## 19. Qualification independence

Engineering readiness, integration readiness, parity readiness, economic qualification, Demo qualification, and Live qualification are independent gates. Passing an earlier gate never implies a later one.

## 20. Change control

Each bounded V2 mission should:

1. inspect current repository authority before coding;
2. reuse existing canonical contracts;
3. run focused tests before broader regressions;
4. report skipped/not-evaluated tests truthfully;
5. inspect sensitive-path diffs before commit;
6. exclude unrelated operational drift;
7. preserve repository push safeguards;
8. stop rather than silently widen scope when an invariant cannot be satisfied.