# AG Multi-Agent Execution Protocol V1

Status: **APPROVED GOVERNANCE / NON-AUTHORIZING**
Date: 2026-09-22

This document records the owner-approved multi-agent operating model, the
platform work-package roadmap (WP-0 through WP-11), the gate model that governs
each work package, and the owner-approved strategy-routing decision for the
active FX V2 integration target. It supplements `docs/PROJECT_ROADMAP.md` and
`docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md`; it does not replace either, does not
change strategy semantics or registry authorization, and does not grant Demo or
Live execution authority. `PROJECT_STATUS.md` remains the rolling current-state
authority; this document owns process/governance structure and the forward WP
sequence.

---

## 1. Active FX V2 strategy-routing decision

The owner has decided that `ST_ASIAN_SWEEP_5R_V1@1.1.1` will replace
`ST_SESSION_SWEEP_CONTINUATION_V1` as the **planned active FX V2
operational/reference strategy** for the V2 opportunity/adapter pipeline going
forward.

This is a platform-integration-target decision, not a strategy-economics
decision:

```text
ACTIVE V2 FX INTEGRATION TARGET
        !=
ECONOMICALLY QUALIFIED / DEMO ELIGIBLE / LIVE ELIGIBLE
```

`ST_ASIAN_SWEEP_5R_V1`'s registry authority is unchanged by this document:

```text
strategy_id = ST_ASIAN_SWEEP_5R_V1
version     = 1.1.1
role        = planned primary active FX V2 integration target
registered  = true
active      = true
research    = true
demo_authorized = false
live_authorized = false
```

Its existing negative economic evidence is **not** reinterpreted as positive
because it is becoming the active V2 integration target: the only resolved R5
evidence on record remains 13/13 losing trades (gross expectancy `-1.00R`, net
`-3.38R` under the one signed cost scenario), R6 is
`NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS`, and strategy research is
`PAUSED_BY_OWNER` per `PROJECT_STATUS.md`. This document does not alter any of
that. Verify current values in `strategies/registry.yaml` and
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml` before relying on the summary above, as
this document does not itself track drift.

### SSC preservation

`ST_SESSION_SWEEP_CONTINUATION_V1` is **not deleted or downgraded** by this
decision. The implementation action is `SSC_ACTIVE_ROUTING_REMOVAL` — removing
SSC from the *active* V2 FX routing target once the replacement adapter (WP-1)
passes its gate — not destruction of SSC. The following remain preserved
exactly as they exist today:

- SSC source (`src/session_sweep_continuation/`)
- the existing SSC V2 adapter (`src/opportunity/ssc_adapter.py`)
- SSC tests and regression suites
- SSC replay evidence
- SSC validation artifacts
- SSC historical architecture/parity evidence (`docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md`)

SSC continues to exist as source code, adapter, tests, replay evidence,
validation artifacts, and a research/reference implementation. No new
machine-readable lifecycle enum (e.g. a `HISTORICAL_REFERENCE_NOT_ACTIVE`
status value) is introduced by this document, since the existing registry
schema does not define one; this preservation is recorded descriptively here
and is expected to be reflected the same way in `strategies/STRATEGY_LEDGER.md`
at the time WP-2 actually executes, not before.

---

## 2. Approved multi-agent operating model

```text
                         OWNER
                           |
              roadmap / authority decisions
                           |
             +-------------+-------------+
             v                           v
      ChatGPT Architect             Claude Builder
      + Independent Auditor          Repository Writer
             |                           |
             | contract                  |
             +-------------------------->|
                                         |
                                   implementation
                                         |
                                   tests + evidence
                                         |
             <---------------------------+
             |
          independent
             audit
             |
       PASS / REMEDIATE
```

### Owner

Final authority for: project roadmap changes, lifecycle promotion, strategy
economic promotion, risk-policy changes, Demo activation, Live activation, and
order authorization.

### ChatGPT — Architect / Independent Auditor

Responsibilities: architecture, roadmap, bounded WP contracts, acceptance
criteria, independent audit, remediation specification, strategy/economic
interpretation, cross-workstream consistency review. ChatGPT is not the normal
repository writer in this operating model.

### Claude — Builder

Responsibilities: bounded repository implementation, repository investigation,
local tests, evidence collection, implementation documentation, commits when
authorized. Claude must not self-authorize lifecycle promotion merely because
its own tests pass.

---

## 3. One-writer rule

```text
ONE WRITER PER BRANCH / WORKTREE
```

Never allow multiple coding agents to independently modify the same
branch/worktree concurrently. Each implementation WP starts from an explicit
baseline commit:

```text
baseline commit
      |
bounded work package
      |
focused tests
      |
regressions
      |
evidence report
      |
commit
      |
independent audit where required
      |
next work package
```

Avoid broad missions containing several roadmap phases at once.

---

## 4. Gate model

### LEVEL A — Engineering Gate

Closes using predefined deterministic acceptance criteria. Example: WP-0
baseline/documentation freeze.

### LEVEL B — Independent Architecture Gate

```text
Claude implementation -> Claude evidence -> independent ChatGPT audit -> PASS / REMEDIATION_REQUIRED
```

Applies to WP-1, WP-2, WP-3, WP-4, WP-5, WP-6, WP-7, WP-9, WP-10, WP-11.

### LEVEL C — Owner Authority Gate

Independent audit plus explicit owner authorization. Applies to WP-8 (Manual
Demo execution activation), strategy Demo promotion, Demo activation, Live
activation, Live execution changes, and material risk-policy changes. No
automated agent may promote itself through a Level C gate.

---

## 5. Platform roadmap V3 (WP-0 through WP-11)

This roadmap is a governance/tracking layer over the existing V2 engineering
sequence in `docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md`. It does not renumber or
replace the V2-x phase identifiers used there; it assigns an owner-facing WP
number and an explicit gate class to each forward step, and inserts one new V2
phase (V2-3C) for the Asian Sweep adapter.

| WP | Scope | Corresponding V2 phase | Gate |
|---|---|---|---|
| WP-0 | V2-3 re-audit baseline freeze | (freezes V2-3A/V2-3B state) | LEVEL A |
| WP-1 | Asian Sweep V2-3C adapter | V2-3C (new, inserted after Parity Checkpoint #1 / before V2-4) | LEVEL B |
| WP-2 | SSC active-routing removal | (routing change only; no V2-x renumbering) | LEVEL B |
| WP-3 | ProposalEligibility bridge | V2-4 | LEVEL B |
| WP-4 | CanonicalProposal bridge | V2-5 | LEVEL B |
| WP-5 | Risk engine integration | V2-7 | LEVEL B |
| WP-6 | ExecutionDecision | V2-8 | LEVEL B |
| WP-7 | MT5 runtime truth and reconciliation | (read-only truth hardening; no strategy/order authority) | LEVEL B |
| WP-8 | Manual Demo execution gate | (first owner-authorized Demo `order_send()` path) | LEVEL C |
| WP-9 | Scheduler migration | V2-10 | LEVEL B |
| WP-10 | Frontend state synchronization | V2-11 / V2-12 | LEVEL B |
| WP-11 | System E2E qualification | V2-13 (qualification scope) | LEVEL B |

### WP-0 — V2-3 Re-audit Baseline Freeze

Objective: freeze the independently reproduced V2-3A/3B parity checkpoint and
the approved roadmap/governance documentation.

```text
V2_3_PARITY_CHECKPOINT = PASS
BASELINE_COMMIT = <future commit hash>
```

Excludes unrelated workspace changes (`.vscode/settings.json`, `web/server.ts`).

### WP-1 — Asian Sweep V2-3C Adapter

Contract: `AG_V2_3C_ASIAN_SWEEP_ADAPTER`.

```text
ST_ASIAN_SWEEP_5R_V1@1.1.1
              |
       canonical evaluator
              |
       AsianSweepAdapter
              |
     OpportunityProjection
              |
       Universal Funnel
```

Requirements: reuse the canonical Asian Sweep engine (`strategy_engine/`); no
strategy-rule duplication; preserve exact strategy/session semantics; preserve
research-only authority; preserve session-pair identity (`ASIAN_LONDON` /
`LONDON_NEWYORK`); deterministic occurrence identity; repeated-observation
idempotence; restart identity; terminal behavior consistent with Safety
Invariant #9 (the same terminal-stage clamp already generically enforced in
`opportunity.engine.evaluate_funnel` for Large-SMC and SSC); no execution
imports; canonical-to-adapter semantic parity; explicit semantic-translation
documentation, following the same shadow-adapter pattern already proven by
V2-3A/V2-3B. Does not implement V2-4 inside WP-1.

### WP-2 — SSC Active Routing Removal

Objective: remove SSC from active V2 FX operational/reference routing after
WP-1 passes. Preserve SSC source, adapter, tests, replay, validation artifacts,
and historical evidence exactly as listed in Section 1. Do not delete or
rewrite SSC history.

### WP-3 — V2-4 ProposalEligibility

```text
OpportunityCandidate -> ProposalEligibility -> ELIGIBLE / INCOMPLETE / BLOCKED
```

Deterministic reason codes following existing repository conventions.
`ELIGIBLE != CanonicalProposal != RiskApproved != ExecutionReady != order
authorization`. No `CanonicalProposal` creation in this WP.

### WP-4 — CanonicalProposal Bridge

```text
OpportunityCandidate + ProposalEligibility(ELIGIBLE) -> ProposalFormationGate -> CanonicalProposal
```

Reuse existing proposal contracts. Do not introduce a parallel schema (e.g.
`OpportunityProposalV2`). Require complete lineage from market event through
candidate revision and eligibility decision into `CanonicalProposal`.

### WP-5 — Risk Engine Integration

```text
CanonicalProposal -> existing canonical risk engine -> RiskDecision
```

Reuse existing risk contracts. Do not invent unavailable broker authority
(leverage/margin values); missing broker-dependent authority fails closed or
follows existing deferred-authority semantics. Hard requirement:
`orders_dispatched = 0`.

### WP-6 — ExecutionDecision

```text
RiskDecision(APPROVED) -> ExecutionDecision -> EXECUTION_READY / OWNER_CONFIRMATION_REQUIRED
```

Creating an `ExecutionDecision` must not execute an order.
`automatic_execution = false` by default.

### WP-7 — MT5 Runtime Truth and Reconciliation

Objective: replace remaining mock runtime/account truth with canonical MT5
Demo terminal truth (`account_info()`, `positions_get()`, `orders_get()`,
`history_deals_get()`, `symbol_info()`, where appropriate to the existing
architecture). No strategy changes. No order authority. Named "MT5 Runtime
Truth" rather than "MT5 Live Data" to avoid confusing real terminal telemetry
with Live trading authority.

### WP-8 — Manual Demo Execution Gate

```text
ExecutionDecision -> owner-originated authorization proof -> order_check -> order_send -> MT5 Demo -> reconciliation
```

First inspect and reuse existing authorization mechanisms
(`assistant.commands.execute_command()`'s `user_confirmed=True` gate per
`AGENTS.md` Authority order point 3) before preregistering any new
cryptographic-token architecture. Required invariants: AI cannot authorize;
scheduler cannot authorize; stale authorization cannot authorize; authorization
for trade A cannot execute trade B; authorization cannot be replayed. This is
the first WP permitted to introduce an actual owner-authorized Demo
`order_send()` path. No Live trading authority.

### WP-9 — Scheduler Migration

```text
CLOCK -> MarketEvent -> Opportunity Finder -> Candidate Store -> Eligibility -> Proposal pipeline
```

No duplicated strategy semantics in the scheduler. Preserve existing approved
operating windows unless separately changed.

### WP-10 — Frontend State Synchronization

Backend remains authoritative. Frontend displays canonical backend state using
actual repository enums/contracts (not invented values). Frontend must not
independently calculate trading truth, risk, or setup state. This is
compatibility work, not the frontend redesign already excluded by the frozen-
frontend constraint recorded in `docs/v2/README.md` and `PROJECT_STATUS.md`.

### WP-11 — System E2E Qualification

Target chain:

```text
MT5 market data -> MarketSnapshot -> MarketEvent -> AsianSweepAdapter -> OpportunityCandidate
-> ProposalEligibility -> CanonicalProposal -> RiskDecision -> ExecutionDecision
-> OWNER_CONFIRMATION_REQUIRED
```

Covers at least: restart recovery, duplicate polling, duplicate confirmation,
stale market data, terminal disconnect, frontend reconnect, scheduler restart,
candidate expiry, proposal expiry, account mismatch, symbol mismatch, risk
rejection, authorization expiry, post-order reconciliation. Successful
completion may establish `PLATFORM_DEMO_READY` but must **not** imply
`STRATEGY_DEMO_ELIGIBLE` (see Section 6).

---

## 6. Critical readiness distinction

```text
PLATFORM_DEMO_READY
        !=
STRATEGY_DEMO_ELIGIBLE

PLATFORM_IMPLEMENTED
        !=
LIVE_AUTHORIZED
```

Demo trading for a strategy requires both appropriate platform readiness
(WP-0 through WP-11) and separate strategy authority (registry
`demo_authorized: true`, granted only by the owner after economic
qualification). Platform integration and economic qualification remain
separate for every strategy named in this document, including
`ST_ASIAN_SWEEP_5R_V1`.

---

## 7. Separate strategy-evidence roadmap

The platform roadmap (WP-0..WP-11 / V2-x) and strategy qualification roadmap
remain separate tracks.

**Asian Sweep** — current role: primary planned active FX V2 integration
strategy; research-only; not economically qualified. Research lane:
negative-result diagnosis -> hypothesis preregistration -> development testing
-> robustness/OOS as governed -> economic qualification. Do not modify v1.1.1
merely because current evidence is negative.

**Crypto Sweep** (`ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0`) — existing Binance
Vision BTC/ETH research remains `RESEARCH_DESCRIPTIVE`, not G3/Demo/Live
evidence. Planned lane: historical evidence freeze -> G3 preregistration ->
robustness -> prospective evidence -> economic qualification. Do not
reinterpret already-peeked data as untouched holdout evidence.

**Large SMC** — continues as a research/watch evidence lane independently of
platform engineering. Its V2 adapter remains valuable architecture evidence.

**SSC** — preserve its negative/validation history. Do not erase unsuccessful
strategy evidence merely because it is no longer the planned active FX route.

---

## 8. Parallel worktree protocol

```text
main
  |
  +-- engineering worktree
  |     `-- one bounded WP branch at a time
  |
  `-- research worktree
        +-- Asian Sweep diagnostics
        +-- Crypto G3 research
        `-- Large-SMC research
```

Rules: one writer per branch/worktree; research changes do not directly merge
into production architecture; a research change intended for production must
become a formal audited WP; each WP begins from an explicit baseline commit;
do not mix unrelated owner WIP into WP commits.

---

## 9. Cross-references

- `PROJECT_STATUS.md` — rolling current-state authority.
- `docs/PROJECT_ROADMAP.md` — master readiness plan (R0-R9) and V2 engineering
  sequence (V2-0..V2-15); this document layers WP-0..WP-11 governance tracking
  over that sequence and records the Asian Sweep/SSC routing decision.
- `docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md` — detailed V2 phase contracts,
  including the inserted V2-3C phase.
- `docs/v2/README.md` — V2 navigation/current gate.
- `strategies/registry.yaml`, `strategies/STRATEGY_LEDGER.md` — strategy
  authorization authority (unchanged by this document).
- `AGENTS.md` — repository-wide authority order and safety rules (unchanged by
  this document).
