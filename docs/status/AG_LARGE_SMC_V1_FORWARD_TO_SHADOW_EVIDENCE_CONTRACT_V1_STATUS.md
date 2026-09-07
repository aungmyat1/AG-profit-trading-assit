# LARGE_SMC_FORWARD_TO_SHADOW_EVIDENCE_CONTRACT_V1 -- Owner Decision Packet (DRAFT)

Status: **DRAFT_OWNER_DECISION_REQUIRED**. This is a decision packet, not a signed
contract. It exists because `AG_EGSVF_V1`'s evaluator correctly reports
`ST_LARGE_SMC_V1`'s `FORWARD_RESEARCH -> OPERATIONAL_SHADOW` transition as blocked on
`SHADOW_ENTRY_EVIDENCE_UNRESOLVED_FOR_STRATEGY` -- no repository governance has ever
defined what evidence would satisfy that milestone for Large-SMC (unlike FX's signed
`FX_SHADOW_ENTRY_PREFLIGHT_PASS` or BTC's `NATURAL_CAMPAIGN_ACCRUAL`). This packet does
not invent that gate's satisfying condition; it presents the owner with real discovery
evidence and a bounded set of defensible options.

`ST_LARGE_SMC_V1 v1.0.7` remains unchanged and frozen. This packet describes how to
*judge* future forward-research observations -- it does not alter the strategy that
produces them.

## Real discovery evidence used to ground this packet

From `artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json`
(EURUSD, a 2-calendar-month window, the same frozen dataset the golden vertical slice
test uses):

```text
total qualified E-events   = 18
  E1 = 3
  E2 = 4
  E3 = 11
direction split             = SHORT 12, LONG 6
```

This is the only quantitative discovery evidence currently available. It measures
**E-condition qualification frequency only** -- it does not measure M1/M2/M3
confirmation rate (a separate downstream step), READY-state frequency, or C10
computability rate (spread/ATR availability), none of which have been measured over
any real window. Those would need a small, cheap, offline analysis (running
`LargeSMCResearchEngine.evaluate()` across a historical window, entirely additive and
research-only) before any option below could be selected with real confidence.

**Immediate implication**: E1 alone qualifies roughly 1.5 times per calendar month in
this sample. Any contract requiring a meaningful sample of E1-driven combinations needs
either a long duration or a low per-model minimum -- both matter for how the following
options are compared.

## Combination reachability -- classified, not assumed

Per this task's own instruction not to require impossible 3x3 coverage, and lacking
M-model confirmation data, combinations are classified by what is actually known:

```text
E1xM1, E1xM2, E1xM3   = NOT_YET_PROVEN_REACHABLE (M-model confirmation rate unmeasured)
E2xM1, E2xM2, E2xM3   = NOT_YET_PROVEN_REACHABLE
E3xM1, E3xM2, E3xM3   = NOT_YET_PROVEN_REACHABLE
```

None are classified `STRUCTURALLY_UNREACHABLE` -- there is no evidence any combination
is impossible, only that none has been measured yet. A contract that hard-requires
every cell before promotion would be requiring something never yet observed to occur at
all, which this task's own instruction (section 33/35 of the originating prompts)
explicitly warns against inventing.

## Option A -- Duration + minimum total qualified observations

```text
requirement = N calendar days of natural OPERATIONAL_SHADOW exposure
              AND >= K naturally-occurring RESEARCH_QUALIFIED decisions
```

- Strength: simplest to implement and audit; matches FX/BTC's own precedent shape
  (calendar duration + a count).
- Weakness: says nothing about whether the K observations are diverse (all from one
  E-model, one direction) -- could pass with a narrow, unrepresentative sample.
- Scarcity risk: LOW for reaching *some* count given ~9 E-events/month system-wide, but
  the count of E-events that additionally reach READY+C10-computable is unmeasured.
- Bias risk: MODERATE (sample could be dominated by E3/SHORT, the most frequent
  category in the one window measured).

## Option B -- Duration + minimum E-model coverage + minimum resolved outcomes

```text
requirement = N calendar days
              AND >= 1 RESEARCH_QUALIFIED observation from each of E1, E2, E3
                 (or an explicit, owner-approved exception for a model proven rare)
              AND >= K resolved outcomes (target hit / stop hit / structural invalidation)
```

- Strength: forces at least minimal breadth across the three E-conditions before
  promotion, directly addressing Option A's bias risk.
- Weakness: E1's ~3-per-2-months rate means "N calendar days" must be long enough to
  make E1 coverage likely, not merely possible -- this couples duration to the rarest
  model's frequency, which was not previously true of FX/BTC's contracts.
- Scarcity risk: MODERATE-HIGH for E1 specifically unless duration is generous (a
  multi-month window, not FX/BTC's 20-30 day precedent).
- Bias risk: LOW (explicitly forces breadth).

## Option C -- Duration + E/M coverage + friction-evaluable + C10-compatible sample

```text
requirement = Option B's requirements
              AND >= K2 of the resolved outcomes have complete friction-evaluable data
                 (spread available at decision time, matching FX's FRICTION_STRESS_TEST
                 evidence-source discipline)
              AND >= K3 of the resolved outcomes had a computable C10 stop (no
                 ATR_NOT_READY/MISSING_SPREAD/MIN_STOP_VIOLATION failure) -- measuring
                 how often the signed C10 policy actually produces a usable geometry
                 in practice, not just in the unit-test fixtures
```

- Strength: most rigorous; directly measures whether the newly-signed C10 policy is
  *practically* computable often enough to matter, and produces evidence usable for a
  later FRICTION_STRESS_TEST gate rather than needing a second data-collection pass.
- Weakness: most parameters to freeze (K, K2, K3, N) and most sub-conditions that could
  each independently stall promotion; longest realistic duration of the three options.
- Scarcity risk: HIGH without a longer observation window than FX/BTC's precedent,
  given ATR/spread availability failures are themselves unmeasured.
- Bias risk: LOWEST (explicitly measures the exact things a later promotion decision
  would need to trust).

## What this packet does NOT do

- Does not select an option -- `owner_decision = PENDING`.
- Does not encode any numeric threshold (duration, minimum count, or coverage
  requirement) into `MILESTONE_GATE_MAP` or any adapter -- `SHADOW_ENTRY_EVIDENCE`
  remains `UNRESOLVED_FOR_STRATEGY` for `ST_LARGE_SMC_V1` until a decision is signed.
- Does not modify `ST_LARGE_SMC_V1 v1.0.7`, its C10 parameters, or any detection logic.
- Does not run a natural observation mechanism -- see the companion finding below.

## Companion finding: no natural forward-observation mechanism currently exists

Unlike BTC (`scripts/run_btc_daily_report.py`, a scheduled task already installed) and
FX (the existing daily pilot cycle), **no scheduled, natural forward-observation runner
for Large-SMC was found anywhere in this repository** (searched `scripts/`, found no
`run_large_smc_daily*`/`run_large_smc_observation*`/similar). `LargeSMCResearchEngine`
is currently only invoked from tests and one-off research scripts
(`scripts/run_large_smc_discovery.py`, `scripts/run_large_smc_outcome_lifecycle_check.py`),
never on a recurring schedule against live data. This is reported as an
**implementation backlog item**, not solved here: even once an evidence-contract option
above is signed, natural evidence cannot begin accruing until a scheduled observation
runner exists. Building one is out of this packet's scope (a research/infrastructure
task, not a governance decision) and is not attempted in this task.

## Addendum (2026-09-07): a fourth, simpler option and its verification against discovery data

A simpler "hybrid statistical minimum" shape has since been proposed:

```text
OPTION D -- HYBRID STATISTICAL MINIMUM
minimum 10 resolved setups
+ coverage across at least 2 distinct M models
+ full C10 structural stop computation on each
+ complete provenance
```

This is **RECOMMENDED as a reasonable starting shape** -- it is simpler to audit than
Options A-C above and directly requires the one thing this task cares most about
(C10 actually producing a usable stop in practice, not just in unit tests). It is
**NOT owner-signed**; no authorization for it exists in any repository record.

**Attainability check against the only real discovery evidence available** (18
E-qualified events / ~2 months: E1=3, E2=4, E3=11): this cannot be verified as
practically attainable without knowing the E→M confirmation rate, which remains
genuinely unmeasured (the same gap already flagged above). If, hypothetically, even
30% of E-events reach an M-confirmation, 18 events over 2 months would yield roughly
5-6 confirmed setups per 2 months -- suggesting Option D's "10 resolved setups" target
is plausible on a multi-month horizon, but this is an illustrative arithmetic check
against an assumed confirmation rate, **not measured evidence**, and must not be
treated as a validated estimate. The "≥2 distinct M models" clause is likely the
harder constraint given M1's typically-scarcer inducement-based confirmation pattern
relative to M2/M3 in comparable SMC implementations -- again, not measured for this
engine specifically.

**Recommendation to the owner**: before signing Option D (or any option), commission
the small offline analysis already flagged above (running `LargeSMCResearchEngine`
across a longer historical window with `historical_data_context`, entirely additive
and research-only) to measure actual E→M confirmation rates and C10-computability rate.
Signing a quota before that data exists risks freezing an unattainable or trivially-easy
threshold by chance rather than by design.
