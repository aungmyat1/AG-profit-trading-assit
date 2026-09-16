# AG PROFIT TRADING — ACCELERATED VALIDATION PLAN V1

**Repository:** `aungmyat1/AG-profit-trading-assit`  
**Purpose:** Reduce validation elapsed time as much as possible **without weakening evidence integrity, holdout discipline, execution safety, or strategy-governance boundaries**.  
**Primary objective:** Compress compute, agent, and idle time through reuse, parallelism, fast-fail gates, deterministic artifacts, and evidence-triggered readiness.  
**Non-objective:** This plan does **not** authorize Demo or Live trading, does not guarantee a strategy reaches `DEMO_ELIGIBLE` within 10–14 days, and does not allow future-market evidence to be replaced with synthetic or repeatedly reused historical evidence.

---

## 1. Executive Summary

The project should no longer use a long, strictly sequential validation process where one strategy blocks another.

Instead, validation is split into parallel lanes:

```text
                         FROZEN STRATEGY
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
      LANE A                LANE B               LANE C
  REAL-MARKET EVIDENCE   HISTORICAL VALIDATION  ENGINE/GOVERNANCE
          │                    │                    │
          │                    │                    │
 friction / forward       populations /         deterministic
 observations             stress / robustness   replay / hashes /
                                               containment tests
          │                    │                    │
          └────────────────────┼────────────────────┘
                               ▼
                         EVIDENCE JOIN
                               │
                               ▼
                         ECONOMIC GATE
                               │
                               ▼
                   ROBUSTNESS / OOS / WF
                               │
                               ▼
                        FINAL HOLDOUT
                               │
                               ▼
                     FORWARD / SHADOW
                               │
                               ▼
                     DEMO ELIGIBILITY
                               │
                               ▼
                      DEMO EXECUTION
                               │
                               ▼
                    LIVE ELIGIBILITY REVIEW
```

The target is therefore:

> **10–14 calendar days for a major research-validation decision sprint where evidence permits — not 10–14 days to Live trading.**

The sprint should identify which candidates:

- are terminally weak and should stop,
- deserve continued research,
- are economically credible,
- are robust enough to approach holdout,
- or are blocked only by future evidence that cannot be accelerated safely.

---

# 2. Core Time-Compression Principle

Validation time consists of three fundamentally different categories.

## 2.1 Compute Time — compress aggressively

Examples:

- historical replay,
- deterministic population generation,
- hashing,
- statistics,
- friction stress tests,
- walk-forward computations,
- robustness matrices,
- artifact generation.

Target:

```text
COMPUTE TIME ↓↓↓
```

Use local Python, deterministic manifests, cached immutable datasets, and reusable validation components.

---

## 2.2 Agent Time — automate and minimize

Examples:

- Claude implementation,
- DeepSeek independent audits,
- artifact reconciliation,
- validation-status reporting,
- evidence packaging.

Target:

```text
AGENT TIME ↓↓↓
```

Agents should be used primarily at **important gates**, not after every routine collection event.

---

## 2.3 Evidence Time — preserve

Examples:

- future-market observations,
- forward-shadow occurrences,
- real Demo fills,
- regime exposure,
- real slippage measurements,
- sufficiently large prospective occurrence counts.

Target:

```text
EVIDENCE TIME = DO NOT FAKE OR COMPRESS
```

AI cannot legitimately convert:

```text
5 trading days        → 1 trading day
20 future occurrences → synthetic occurrences
forward observation   → ordinary backtest
Demo fills            → simulated fills
sealed holdout         → repeatedly queried validation set
```

The acceleration strategy must therefore reduce compute, agent, and idle time while preserving genuine evidence time.

---

# 3. Current Project Baseline

At adoption of this plan, the project already has a substantial reusable foundation.

Approximate active validation state:

```text
AG PROFIT TRADING
│
├── VALIDATION SYSTEM
│      └── G0–G10 foundation        COMPLETE / FROZEN
│
├── SSC
│      ├── HYP_002                  VALIDATED_NEGATIVE / TERMINAL
│      └── HYP_001                  prospective confirmation
│
├── LARGE SMC
│      ├── lifecycle                FORWARD_RESEARCH
│      └── WP3A.1 friction          collecting real EURUSD evidence
│
├── BTC SWEEP
│      └── lifecycle                FORWARD_RESEARCH
│
├── ASIAN SWEEP
│      └── lifecycle                OPERATIONAL_SHADOW
│
└── EXECUTION
       ├── research Demo authority  false
       └── research Live authority  false
```

This plan must reuse existing frozen infrastructure wherever possible rather than rebuilding equivalent systems.

---

# 4. Accelerated 10–14 Day Validation Sprint

The following schedule is an **execution framework**, not a promise that all strategies progress at the same speed.

| Period | Primary Work | Parallel Work | Expected Output |
|---|---|---|---|
| Day 1 | Reuse/freeze deterministic engine checks | Claude + DeepSeek integrity | Engine/adapter qualified |
| Days 1–5 | Real friction / forward evidence collection | Historical populations + stress tests | Empirical evidence accumulates |
| Days 1–5 | Historical economic validation | Robustness / sensitivity | Candidate evidence packages |
| Days 5–6 | Evidence aggregation | Independent reproduction | Friction/evidence model |
| Days 6–8 | Economic gate | Cost-stress matrix | PASS / FAIL / INCONCLUSIVE |
| Days 8–10 | Robustness / walk-forward / OOS | Cross-period analysis | Robustness decision |
| Days 10–12 | Final candidate freeze | Red-team audit | Holdout-ready or blocked |
| Days 12–14 | Controlled final holdout, only where prerequisites pass | Independent audit | PASS / FAIL / INCONCLUSIVE |
| After Day 14 | Forward / operational shadow | Demo-readiness evidence | Demo eligibility only when evidence permits |

Important:

- A candidate may stop on Day 2 if it fails a preregistered fast-fail gate.
- A candidate may remain blocked after Day 14 if future evidence is insufficient.
- No strategy receives Demo or Live authority merely because the calendar sprint ended.

---

# 5. Phase 1 — Deterministic Engine Reuse

Do **not** spend a full day rebuilding validation infrastructure that is already frozen and independently audited.

For every strategy adapter, reuse the existing validation foundation and check only what is strategy-specific.

Minimum adapter qualification:

```text
strategy identity/version
        ↓
semantic freeze
        ↓
dataset authority
        ↓
deterministic replay
        ↓
no-lookahead checks
        ↓
canonical population identity
        ↓
artifact hashes
        ↓
execution containment
```

Target engineering time when the reusable foundation applies:

```text
~1–3 hours per strategy adapter
```

Do not fork a second validation methodology unless a documented architectural incompatibility requires it.

---

# 6. Data-Zone Architecture

Do not use a simple 70/30 split where the 30% is both parameter-selection data and the final holdout.

Use three strict zones.

```text
HISTORICAL MARKET DATA
│
├── DEVELOPMENT
│     hypothesis generation
│     exploratory analysis
│     parameter search where allowed
│
├── VALIDATION / WALK-FORWARD
│     model selection
│     robustness
│     parameter neighborhoods
│     cross-period confirmation
│
└── FINAL HOLDOUT
      SEALED
      controlled one-time/frozen-policy access
```

## Rules

1. Development data may inform hypotheses.
2. Validation data may test preregistered candidates and robustness.
3. Final holdout must not be used to search risk-reward parameters.
4. A dataset used to choose a parameter can no longer be described as untouched final holdout evidence.
5. Holdout access must remain governed, logged, and fail-closed.

---

# 7. Friction Validation Architecture

The current Large-SMC WP3A.1 campaign remains frozen and must continue unchanged.

Real empirical evidence and synthetic stress testing should run in parallel:

```text
REAL FRICTION LANE              STRESS LANE

Vantage EURUSD spread          historical population
        ↓                             ↓
WP3A.1 campaign                baseline friction
        ↓                       1.25× friction
multi-session                  1.50× friction
multi-day evidence             2.00× friction
        ↓                             ↓
empirical distribution         edge-decay profile
```

Synthetic friction is a **stress test only**.

It does not replace broker evidence.

Recommended descriptive stress levels:

```text
1.00×
1.25×
1.50×
2.00×
```

These values are for robustness analysis, not automatic strategy parameter modification.

---

# 8. Friction Evidence Interpretation

Keep empirical components separate:

```text
TOTAL EXECUTION FRICTION
│
├── Spread      → empirical campaign where available
├── Commission  → broker-specific empirical evidence required
└── Slippage    → execution evidence required
```

Do not convert missing evidence into fabricated empirical values.

Example classifications:

```text
SPREAD = EMPIRICALLY_OBSERVED
COMMISSION = UNAVAILABLE
SLIPPAGE = INSUFFICIENT_EVIDENCE
COMPLETE_COST_MODEL_AVAILABLE = FALSE
```

A spread campaign alone does not constitute a complete transaction-cost model.

---

# 9. Economic Gate Metrics

Do not impose universal metrics such as:

```text
PF > 1.4
Sharpe > 1.2
Max DD < 12%
```

unless these are explicitly preregistered for the strategy and appropriate to the sample structure.

For sparse event-driven trading systems, primary analysis should focus on:

```text
net expectancy in R
sample adequacy
uncertainty / confidence
profit factor
drawdown
MFE / MAE
cost sensitivity
cross-period stability
setup-specific stability
```

Thresholds must be fixed **before** evaluating the relevant validation evidence.

Do not create a PASS threshold after seeing what the candidate achieved.

---

# 10. Fast-Fail Validation Ladder

Expensive validation stages should be conditional.

```text
candidate
   ↓
economic gate
   ↓ PASS
cheap friction stress
   ↓ PASS
parameter-neighborhood test
   ↓ PASS
cross-period stability
   ↓ PASS
walk-forward / OOS
   ↓ PASS
cross-symbol / venue replication where justified
   ↓ PASS
final holdout
```

If the candidate fails an earlier valid gate, later expensive stages should not run unless a separately preregistered remediation/hypothesis is opened.

This reduces wasted computation and agent effort.

---

# 11. Preregistered Futility / Stop-Early Rules

Where statistically and methodologically appropriate, preregister an interim futility rule before looking at the decision evidence.

```text
candidate
    ↓
preregistered checkpoint
    ↓
 ┌───────────────┬────────────────┐
 ▼               ▼
clearly futile   still plausible
 ▼               ▼
TERMINATE        CONTINUE
```

Possible use cases:

- treatment expectancy remains materially negative,
- sample adequacy reached and primary gate fails,
- extreme friction sensitivity destroys the edge,
- strategy cannot satisfy required occurrence frequency,
- validation-lineage evidence is invalid/non-counting.

Never create a futility rule after observing the result it will judge.

---

# 12. Event-Count Validation, Not Calendar Quotas

Do not require a fixed number of live trades within an arbitrary number of days.

Bad rule:

```text
15–20 trades in 5 days
```

Better rule:

```text
minimum occurrences
+
minimum complete sessions
+
minimum regime exposure
+
preregistered adequacy rule
```

The strategy must control setup quality; validation deadlines must not pressure the system into loosening entry criteria merely to increase trade count.

---

# 13. Demo and Live Authorization

The accelerated sprint must **not** automatically advance a strategy to real capital.

Required lifecycle:

```text
RESEARCH PASS
      ↓
ROBUSTNESS PASS
      ↓
FINAL HOLDOUT PASS
      ↓
FORWARD / SHADOW PASS
      ↓
DEMO_ELIGIBILITY REVIEW
      ↓
explicit owner authorization
      ↓
DEMO EXECUTION
      ↓
real execution evidence
      ↓
slippage / attribution / stability
      ↓
LIVE_ELIGIBILITY REVIEW
      ↓
explicit owner authorization
      ↓
MICRO LIVE
```

`0.01` lot is still real capital and is not a substitute for Demo validation.

---

# 14. Multi-Strategy Parallelization

Independent strategies should validate concurrently whenever their evidence lanes do not contaminate each other.

Example:

```text
DAY 1 ───────────────────────────────────── DAY 14

LARGE SMC
████ real friction
     █ economic
       █ robustness
          █ holdout-ready assessment

SSC
████ fresh acquisition
    █ HYP_001 adequacy
       █ economics when checkpoint permits
          █ robustness

BTC SWEEP
████████ forward observations
    █ historical robustness
       █ evidence reconciliation

ASIAN SWEEP
████████ operational shadow
    █ historical evidence reconciliation
       █ eligibility evaluation
```

One strategy waiting for future evidence must not block computation on another independent strategy.

---

# 15. Two-Agent Operating Model

Use strict separation of duties.

## Claude Code — implementation/operator

Responsibilities:

- implement frozen specifications,
- run deterministic pipelines,
- collect scheduled evidence,
- generate hashes/manifests,
- produce compact evidence packets,
- run tests,
- report `NEXT_SAFE_ACTION`.

Claude must not self-promote strategies or reinterpret failed gates.

---

## DeepSeek — independent auditor

Responsibilities:

- reproduce hashes,
- independently calculate important statistics,
- inspect provenance,
- detect lineage contamination,
- verify strategy/execution containment,
- challenge Claude reports,
- classify disagreements by severity.

DeepSeek should default to read-only mode and should not silently fix the implementation it audits.

---

## Owner / Gate Decision

Important transitions remain governance decisions.

Agents may produce:

```text
READY_FOR_AGGREGATION
READY_FOR_ECONOMIC_EVALUATION
READY_FOR_HOLDOUT
PROMOTION_ELIGIBLE
```

They must not automatically turn these into:

```text
SIGNED POLICY
DEMO_AUTHORIZED
LIVE_AUTHORIZED
```

without the required explicit authority.

---

# 16. Audit Cadence Optimization

Do not audit every routine collection event with two agents.

Use automation for routine events and two-agent review for important gates.

Example WP3A.1 cadence:

```text
first real window
    ↓
Claude verification

first complete day
    ↓
Claude evidence packet
    ↓
DeepSeek independent audit

Days 2–4
    ↓
automation / scheduler / fail-closed health checks

campaign completion
    ↓
Claude aggregation
    ↓
DeepSeek independent aggregation audit
    ↓
owner policy decision
```

This minimizes agent usage while preserving independent review at meaningful points.

---

# 17. Evidence-Triggered Readiness

The system should automatically compute **readiness**, not automatically approve policy changes.

Example:

```text
IF
    friction.complete_days >= 5
AND valid_windows >= 20
AND campaign_manifest_hash == frozen_hash
AND provenance_valid == true
THEN
    READY_FOR_AGGREGATION = TRUE
```

But:

```text
DO NOT automatically sign friction policy
```

SSC example:

```text
IF
    HYP001.treatment_N >= frozen_minimum_N
AND acquisition_checkpoint_reached == true
AND lineage_valid == true
AND data_role_counting == true
THEN
    READY_FOR_ECONOMIC_EVALUATION = TRUE
```

Again, readiness is not the same as authorization.

---

# 18. Validation Orchestrator — Recommended Upgrade

Introduce a read-only validation-status orchestrator that calculates current gate state and the next safe action from canonical evidence.

Conceptual output:

```text
VALIDATION STATUS
│
├── ST_SESSION_SWEEP_CONTINUATION_V1
│      G0 PASS
│      G1 PASS
│      HYP_001 WAITING_DATA
│      ECONOMIC_GATE LOCKED
│
├── ST_LARGE_SMC_V1
│      FOUNDATION PASS
│      FRICTION COLLECTING
│      READY_FOR_AGGREGATION false
│      ECONOMIC_GATE LOCKED
│
├── ST_LIQUIDITY_SWEEP_RETEST_V1
│      FORWARD_RESEARCH
│      evidence status ...
│
└── ST_ASIAN_SWEEP_5R_V1
       OPERATIONAL_SHADOW
       evidence status ...
```

Recommended fields:

```text
strategy_id
semantic_version
lifecycle_stage
current_gate
furthest_verified_gate
blocking_reasons
evidence_status
dataset_role_status
holdout_status
demo_authorized
live_authorized
next_safe_action
```

The orchestrator must be **read-only** and must not mutate lifecycle or execution authority.

---

# 19. Current Large-SMC WP3A.1 Campaign

The current campaign must remain frozen while this accelerated architecture is adopted.

Campaign:

`LSMC_EURUSD_FRICTION_WP3A1_V1`

Frozen properties include approximately:

```text
4 windows/day
120 scheduled observations/window
5-second sampling grid
minimum 5 complete FX trading days
minimum 2400 scheduled observations
no adaptive sampling
no evidence backfill
no unfavorable-window deletion
```

During the campaign:

Do not:

- modify C10,
- change the campaign manifest,
- change session windows,
- change sample count,
- replace missing evidence,
- sign the friction policy early,
- treat early observations as strategy-performance evidence.

The accelerated plan works **around** this campaign, not by changing it.

---

# 20. Repeated Tick Interpretation

Fixed-grid sampling may capture the same latest broker tick across multiple scheduled observations during quiet markets.

Keep separate metrics:

```text
DUPLICATE_SCHEDULED_GRID_ROWS
REPEATED_BROKER_TICK_TIMESTAMP_ROWS
REPEATED_IDENTICAL_QUOTES
```

Only true duplicate scheduled-grid identity represents a collector duplication defect.

Repeated broker ticks can be legitimate under time-grid sampling and must not be silently deduplicated.

Interpret campaign output as a **time-sampled visible-spread distribution**, not necessarily a tick-event-weighted distribution.

---

# 21. Strategy Failure Handling

Never optimize a failed version until it passes under the same validation identity.

Correct pattern:

```text
V1
 ↓
FAIL
 ↓
failure decomposition
 ↓
new preregistered hypothesis
 ↓
V1.1 candidate
 ↓
new candidate manifest
 ↓
new validation lineage
```

Incorrect pattern:

```text
FAIL
 ↓
change parameter
 ↓
rerun same validation
 ↓
change again
 ↓
repeat until PASS
```

The latter converts validation evidence into tuning data and undermines the claimed out-of-sample status.

---

# 22. AI Optimization Boundaries

AI is encouraged for:

- deterministic implementation,
- evidence packaging,
- hash verification,
- statistical computation,
- artifact reconciliation,
- leakage detection,
- status dashboards,
- test execution,
- red-team audits,
- fast-fail execution,
- parallel strategy orchestration.

AI must not autonomously:

- lower PASS thresholds,
- choose favorable parameters after seeing validation results,
- open final holdout early,
- convert failed evidence into PASS by reinterpretation,
- modify C10 from preliminary friction data,
- loosen setup rules to hit trade-count targets,
- authorize Demo execution,
- authorize Live execution.

---

# 23. Promotion Logic

The preferred lifecycle remains evidence-gated:

```text
IDEA
 ↓
CONTRACT FREEZE
 ↓
PREREGISTRATION
 ↓
CANONICAL POPULATION
 ↓
ECONOMIC PASS
 ↓
ROBUSTNESS PASS
 ↓
OOS / WALK-FORWARD PASS
 ↓
FINAL HOLDOUT PASS
 ↓
FORWARD / SHADOW PASS
 ↓
DEMO_ELIGIBLE
 ↓
DEMO_EXECUTION
 ↓
LIVE_ELIGIBILITY REVIEW
```

A candidate may terminate permanently at any valid gate.

That is a feature, not a validation failure.

---

# 24. Completion Definition for the 10–14 Day Sprint

The accelerated sprint is successful when the project has produced, for each active candidate, one of the following defensible classifications:

```text
TERMINAL_FAIL
VALIDATED_NEGATIVE
INCONCLUSIVE_INSUFFICIENT_EVIDENCE
WAITING_FOR_FUTURE_EVIDENCE
READY_FOR_ECONOMIC_EVALUATION
ECONOMIC_PASS
ROBUSTNESS_PASS
READY_FOR_HOLDOUT
HOLDOUT_PASS
```

The sprint is **not** required to produce a Demo-eligible strategy.

A successful sprint can legitimately conclude that all candidates should stop or continue collecting evidence.

---

# 25. Near-Term Execution Order

## Large SMC

```text
finish frozen WP3A.1 campaign
        ↓
aggregate real friction evidence
        ↓
DeepSeek independent reproduction
        ↓
friction-policy review
        ↓
validation admission
        ↓
economic gate
        ↓
fast-fail robustness ladder
```

Do not alter the running campaign.

---

## SSC

```text
continue HYP_001 prospective acquisition
        ↓
reach frozen checkpoint / adequacy rule
        ↓
run economics only when authorized by protocol
        ↓
PASS / FAIL / INCONCLUSIVE
```

`HYP_002` remains terminal and must not be reopened.

---

## BTC Sweep

Continue independent forward-research evidence while historical robustness and provenance checks run in parallel where permitted.

Do not substitute historical replay for required future campaign evidence.

---

## Asian Sweep

Continue operational-shadow evidence while reconciling historical evidence and eligibility gates in parallel.

Do not infer Demo authority from `OPERATIONAL_SHADOW` lifecycle alone.

---

# 26. Recommended Implementation Work Packages

The following upgrades can be implemented independently of the frozen trading experiments.

## AVP-WP1 — Validation Status Orchestrator

Create a read-only strategy validation status aggregator.

Must:

- consume canonical registries/artifacts,
- expose blockers,
- expose readiness,
- expose next safe action,
- never modify strategy or execution authority.

---

## AVP-WP2 — Gate Readiness Rules

Encode deterministic readiness predicates such as:

- ready for aggregation,
- ready for economics,
- ready for robustness,
- ready for holdout review.

These predicates must not authorize the transition themselves.

---

## AVP-WP3 — Fast-Fail Runner

Provide a strategy-neutral pipeline that executes inexpensive gates first and stops at the first preregistered terminal failure.

---

## AVP-WP4 — Parallel Validation Scheduler

Allow independent validation lanes to run concurrently without sharing mutable experiment state.

Must preserve:

- immutable manifests,
- strategy identity,
- dataset roles,
- holdout firewalls,
- evidence lineage.

---

## AVP-WP5 — Compact Agent Handoff Packets

Standardize small evidence packets for Claude → DeepSeek handoff.

Prefer:

- hashes,
- summaries,
- paths,
- reproducibility commands,
- blocker state,
- exact diffs.

Avoid bulk raw-tick ingestion by LLMs except targeted spot checks.

---

## AVP-WP6 — Cross-Strategy Validation Dashboard

Expose a read-only view such as:

```text
Strategy | Lifecycle | Current gate | Evidence | Blocker | Next action
```

This is for observability only.

No execution controls should be added as part of this work package.

---

# 27. Safety Invariants

The accelerated plan must preserve all of the following:

```text
strategy semantics cannot change silently
validation thresholds cannot change after seeing judged evidence
holdout cannot be opened casually
non-counting evidence cannot satisfy gates
missing evidence cannot be fabricated
failed evidence cannot be deleted
campaign data cannot be backfilled silently
Demo authority remains explicit
authority for Live remains explicit
agents cannot self-promote strategies
```

Any acceleration that violates one of these invariants is rejected.

---

# 28. Expected Benefit

The primary improvement is not a guaranteed shorter market-evidence horizon.

The improvement is that while one lane waits for real evidence, other independent work proceeds immediately.

Before:

```text
wait friction
 ↓
run economics
 ↓
run robustness
 ↓
wait next strategy
```

After:

```text
              ┌─ friction collection
              ├─ historical validation
NOW ──────────┼─ robustness preparation
              ├─ forward evidence
              ├─ engine verification
              └─ agent audits

                     ↓
               evidence joins
                     ↓
                gate decisions
```

This reduces idle time and repeated agent work while retaining scientific discipline.

---

# 29. Primary Project Objective

Do not optimize toward:

> "Finish validation by a specific date."

Optimize toward:

```text
FIRST CREDIBLE EDGE
       ↓
positive after realistic costs
       ↓
replicable
       ↓
robust
       ↓
survives unseen data
       ↓
survives forward observation
       ↓
DEMO_ELIGIBLE
```

Then:

```text
DEMO execution
       ↓
real execution evidence
       ↓
controlled Live eligibility review
```

The validation system succeeds even when it rejects every current strategy.

---

# 30. Adoption Rule

This document is a **validation-process optimization plan**.

It does not itself:

- modify any strategy,
- mutate G0–G10 methodology,
- authorize a lifecycle promotion,
- authorize holdout access,
- approve friction policy,
- enable Demo execution,
- enable Live execution.

Implementation work packages should be separately reviewed, tested, and independently audited before becoming canonical infrastructure.

---

## Final Target

```text
COMPUTE TIME      ↓↓↓
AGENT TIME        ↓↓↓
IDLE TIME         ↓↓ through parallelism
EVIDENCE QUALITY  PRESERVED
HOLDOUT INTEGRITY PRESERVED
EXECUTION SAFETY  PRESERVED
```

The intended result is the **fastest defensible path to identifying a real trading edge**, not the fastest path to putting capital at risk.
