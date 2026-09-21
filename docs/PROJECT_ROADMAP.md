# AG Profit Trading — Master Project Readiness Plan V3

Status: **AUTHORITATIVE MASTER PLAN — APPROVED WITH HARDENING 2026-09-10**

> **Note (2026-09-21):** The readiness matrix below was last updated 2026-09-10 and
> reflects the state at plan adoption. R2/R3/R4 have since reached `READY`/`PASS`
> (2026-09-11). See `PROJECT_STATUS.md` for the current rolling classification and
> the R0–R9 gate table there for the authoritative current status. The individual
> R2/R3/R4 section descriptions below retain their original plan language; the
> current classification is recorded in the gate table in `PROJECT_STATUS.md`.

This is the project's authoritative readiness progression. It supersedes the prior
delivery-stage ordering. Historical plans remain evidence of earlier decisions, but
this capability-gate sequence governs new implementation work.

This plan does not authorize broker execution, alter a frozen strategy, promote a
candidate, or claim profitability. Strategy YAML owns signal behavior; the strategy
engine owns decisions; the proposal ledger owns proposal identity; validation evidence
owns performance claims; the registry owns strategy authorization; and the execution
gateway owns broker mutation.

## Readiness questions

Project readiness is evaluated through five independent questions:

1. Can the system safely **WATCH**?
2. Can it produce **TRUSTWORTHY PROPOSALS**?
3. Does the strategy have a **VALIDATED EDGE**?
4. Can it **EXECUTE SAFELY**?
5. Has execution **PRESERVED THE EDGE**?

## North-star progression

```text
PRESET STRATEGIES → WATCH REAL MARKETS → DETECT QUALIFIED SETUPS
                  → GENERATE CANONICAL PROPOSALS → COLLECT OUTCOME EVIDENCE
                  → VALIDATE ECONOMIC EDGE → DEMO AUTO-EXECUTION
                  → VALIDATE BROKER EXECUTION → SMALL LIVE → CONTROLLED SCALING
```

The current engineering program is
`AG_CANONICAL_SCANNER_PROPOSAL_PIPELINE_V1`: R2 Real Market Watch → R3 Canonical
Strategy → R4 Canonical Proposal → scanner integration → automated tests → natural
end-to-end proof → **STOP**.

## One authority per layer

```text
MARKET TRUTH       Broker / authoritative market feed
        ↓
STRATEGY TRUTH     Canonical Python strategy engine
        ↓
PROPOSAL TRUTH     Persistent proposal ledger
        ↓
EVIDENCE TRUTH     Canonical outcome and evidence layer
        ↓
GOVERNANCE TRUTH   Lifecycle, validation, and authorization gates
        ↓
EXECUTION TRUTH    Fresh broker state and execution gateway
```

AI and advisory skills sit beside this chain. They may diagnose, explain, compare,
recommend, and propose experiments. They are not an alternative source of market,
strategy, proposal, governance, or execution truth.

## Current readiness matrix

| Capability | Current classification | Target gate |
|---|---|---|
| Safety containment | `READY` | Maintain R0 |
| Synthetic research scanner | `READY / RESEARCH_ONLY` | Maintain R1 |
| Real-market watch | `READY` (since 2026-09-11) | R2 |
| Canonical Python decisions | `READY` (since 2026-09-11) | R3 |
| Canonical proposals | `READY / PASS` (since 2026-09-11) | R4 primary target |
| Proposal persistence and scanner consumption | `READY / PASS` (since 2026-09-11) | R4 primary target |
| Proposal outcome evidence | `PARTIAL` | R5 |
| Edge validation | `NOT_PASS` | R5–R6 |
| Scanner-driven Demo execution | `BLOCKED` | R7 |
| Demo auto-execution validation | `BLOCKED` | R8 |
| Controlled Live | `BLOCKED` | R9 |

> **Updated 2026-09-21:** R2/R3/R4 classifications promoted from `PARTIAL`/`NOT_READY`
> to match the actual `PASS`/`READY` status proven on 2026-09-11 and recorded in
> `PROJECT_STATUS.md`. The original 2026-09-10 classifications (`PARTIAL`/`NOT_READY`)
> were the state at plan adoption; the R2–R4 pipeline completed the next day.

`PARTIAL` real-market watch means the backend has read-only MT5 connectivity and
closed-candle evidence for the current FX path, but the canonical guarded end-to-end
scanner/watch pipeline has not passed R2. Existing execution infrastructure or a
separately authorized strategy path does not advance scanner-driven execution.

This roadmap answers "where are we going." For "where are we right now" —
per-strategy validation state, current git/provenance identity, active blockers, and
concurrent/foreign working-tree state — see the generated, deterministic
`docs/status/PROJECT_LIVE_STATUS.md` (regenerate with
`python scripts/generate_live_status.py`; never hand-edit it). Historical dated
snapshots under `docs/status/` remain "how did we get here" evidence.

## R0 — Safe Foundation

Objective: prevent research or display functionality from acquiring trading authority.

Current classification: **READY / maintain**.

```text
synthetic scanner → SYNTHETIC / OBSERVATION ONLY
                  → executionEligible = false → STOP

explicit owner order → USER_EXPLICIT_ORDER → existing guards → Demo gateway
```

Recorded invariant:

```text
scanner_ui_containment = PASS
synthetic_scanner_execution_via_supported_path = NO
server_side_synthetic_proposal_execution_invariant = NOT_YET_APPLICABLE
reason = no scanner proposal execution endpoint exists
```

Existing execution-gateway regressions do not prove scanner market-data, proposal, or
authority behavior. Record those test surfaces separately.

Exit: safety boundaries remain fail-closed and independently tested.

## R1 — Research Watch Ready

Objective: safely observe strategy and UI behavior using synthetic, replay, or forward
research data.

```text
research data → strategy research → candidate / READY / NO_TRADE → display → STOP
```

Current classification: **READY — `SCANNER_SAFE_FOR_RESEARCH_ONLY`**.

This supports development, visualization, UI work, and research. Synthetic output is
never trading truth and never replaces unavailable broker data in a real-market mode.

## R2 — Real Market Watch Ready

Objective: make actual broker market data the scanner/watch source of market truth.

```text
Vantage Demo MT5 → real closed candles → canonical timestamps
                 → validated symbols → strategy engine
```

Required gates:

- MT5 connection and correct Demo account.
- Explicit symbol resolution and feed validation for each in-scope instrument.
- M15 closed candles, plus M1 execution/context data only where a signed contract
  requires it.
- UTC normalization and decision-time/as-of-time separation.
- stale-data, missing-data, duplicate-bar, and incomplete-bar protection.
- fail-closed `DATA_UNAVAILABLE`; never substitute synthetic candles and report READY.
- FX and crypto feed gates recorded independently.
- An explicit `market_data_mode` enum (`REAL`, `REPLAY`, or `SYNTHETIC`) originating at
  `MarketSnapshot` and propagated unchanged through `StrategyDecision`, `Proposal`,
  `EvidenceEnvelope`, API, and UI. R2 can pass only with `market_data_mode=REAL`.

Mixing modes within one decision/proposal/evidence chain is invalid and must fail
closed. Replay and synthetic objects remain valid research inputs under R1, but they
cannot be relabeled or silently promoted to real-market truth downstream.

Current classification: **READY** (achieved 2026-09-11). Read-only MT5 connectivity and closed M15 candles
are verified for the current EURUSD/GBPUSD backend path. The end-to-end scanner/watch
integration, all required guards, and separately-authorized crypto market truth passed
under WP1–WP3. See `PROJECT_STATUS.md` R0–R4 gate table and
`docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md`.

Exit milestone: `AG_REAL_MARKET_WATCH_READY_V1`.

## R3 — Canonical Strategy Ready

Objective: make the deterministic Python strategy engine the only strategy authority;
the frontend becomes a renderer.

```text
MT5 → canonical Python strategy engine → StrategyDecision → UI
```

The UI displays `READY`, `WATCH`, `NO_TRADE`, and fail-closed states exactly as the
backend returns them. It never implements an approximate strategy or independently
upgrades `CANDIDATE` to `READY`.

Required decision contract:

```text
strategy_id, strategy_version
symbol, timeframe, session
evaluated_at, market_data_asof
state: WATCHING | CANDIDATE | QUALIFYING | READY | NO_TRADE | INVALIDATED | DATA_ERROR
direction, entry, stop_loss, targets
setup_reason, confirmation, invalidation
config_hash, code_identity, market_data_fingerprint
```

Only strategy-owned fields may be populated. Missing required strategy geometry blocks
the proposal; the UI or proposal layer does not invent it.

Current classification: **READY** (achieved 2026-09-11). WP4–WP5 + WP5.2 passed;
`AG_CANONICAL_STRATEGY_RUNTIME_READY_V1 = PASS`. See `PROJECT_STATUS.md`.

Exit milestone: `AG_CANONICAL_STRATEGY_RUNTIME_READY_V1`.

## R4 — Canonical Proposal Ready — Primary Product Target

Objective: convert each real canonical `READY` decision into an immutable,
non-executable proposal and expose it consistently through persistence, API, and UI.

```text
authoritative feed → canonical strategy → canonical proposal service
                   → persistent proposal ledger → scanner/dashboard
                   → OBSERVATION ONLY
```

Required proposal contract:

```text
proposal_id
proposal_occurrence_key
strategy_id, strategy_version
symbol, direction, timeframe, session
decision_bar_close, setup_identity
entry, stop_loss, take_profit[]
risk_R, reward_R
ready_at, created_at, expires_at
market_data_source, market_data_asof, market_data_fingerprint
market_data_mode
config_hash, git_commit, engine_release
strategy_decision_state, proposal_state, freshness_status, edge_status
execution_eligible = false
execution_authority = NONE
```

Proposal geometry comes only from the canonical backend. The browser cannot create a
proposal from a frontend-only object or become authoritative for trade geometry.

### Proposal Formation Gate

A canonical `StrategyDecision.READY` is necessary but not sufficient to create a
proposal. A non-economic formation gate must verify:

```text
strategy identity and version known       PASS
market_data_mode = REAL                    PASS
market fingerprint and as-of time present PASS
entry, stop, and targets present           PASS
risk geometry valid                        PASS
underlying data not stale                  PASS
decision not expired                       PASS
```

Only a complete event becomes `Proposal.ACTIVE`. A failure produces a durable,
reason-coded `PROPOSAL_REJECTED`; it never causes the proposal layer or frontend to
guess missing values. This gate establishes technical representability only. It does
not assess profitability or grant execution eligibility.

### Proposal identity and lifecycle

One strategy occurrence creates one logical `proposal_id`. Reruns and delivery retries
preserve that identity. The stable idempotency input is:

```text
proposal_occurrence_key = hash(
    strategy_id
    + strategy_version
    + symbol
    + session
    + decision_bar_close
    + setup_identity
)
```

The hash encoding, normalization, and algorithm must be versioned before
implementation. The same occurrence key resolves to the same proposal ID across
scheduler overlap, restart, repeated bar evaluation, duplicate API calls, and delivery
retries; a different market occurrence resolves to a new proposal ID.

```text
              ┌──→ INVALIDATED
              │
CREATED → ACTIVE ──→ EXPIRED
              │
              └──→ RESOLVED
```

`READY` is exclusively a strategy-decision state; `ACTIVE` is the initial usable
proposal state. Execution states (`AUTHORIZED`, `EXECUTED`) are not part of R4. Reload
must return the same strategy identity, original geometry, timestamps, occurrence key,
market fingerprint, data mode, freshness, and lifecycle state.

Proposal lifecycle and market freshness are independent:

```text
proposal_state   = ACTIVE | INVALIDATED | EXPIRED | RESOLVED
freshness_status = FRESH | STALE | EXPIRED
```

An `ACTIVE` proposal may become `STALE` before its strategy-defined expiry. Freshness
is informational in R4 and must be preserved for R7 fresh-price revalidation; it does
not silently rewrite proposal lifecycle.

### R4 acceptance proof

Automated tests are necessary but not sufficient. Approval requires a natural,
end-to-end, read-only proof in the intended environment:

- A real EURUSD or GBPUSD closed-bar evaluation reaches `READY`, creates one persistent
  proposal, is returned by the API, and is rendered **OBSERVATION ONLY**, with source,
  as-of time, strategy, and proposal identity visible and execution blocked.
- A real `NO_TRADE` evaluation renders `NO_TRADE` and creates no frontend proposal.
- Reload, rerun, overlap, and restart preserve identity without duplication.
- Zero broker order is submitted.

Exit milestones: `AG_CANONICAL_SCANNER_PROPOSAL_PIPELINE_V1` and
`AG_PROPOSAL_OPERATION_READY_V1`.

Current classification: **READY / PASS** (achieved 2026-09-11). WP6–WP11A + WP12 natural
proof completed; `AG_PROPOSAL_OPERATION_READY_V1 = PASS`. A real LONDON_NEWYORK cycle
produced a GBPUSD `READY` decision that flowed through the full pipeline with
`execution_eligible=false` and zero broker mutation. See `PROJECT_STATUS.md`.

**STOP #1:** operate the proposal system and collect evidence. Canonical proposals do
not authorize or trigger scanner execution.

## R5 — Edge Validation Ready

Objective: turn canonical proposals into complete, immutable economic evidence.

```text
proposal → outcome resolver → canonical trade export
         → evidence envelope → validation gates → economic gates
```

Required dimensions include sample completeness, data integrity, no-lookahead checks,
spread, slippage, commission, net expectancy in R, profit factor, maximum drawdown,
average/median R, and performance by session, symbol, setup, and regime. Validation
includes untouched out-of-sample data, walk-forward stability, and friction stress.

`EVIDENCE_COMPLETE` is not `ECONOMIC_GATE_PASS`. A completely measured losing strategy
is not a validated edge. Thresholds must be owner-signed prospectively and may not be
tuned after reviewing the result.

Exit: each strategy cohort receives `PASS`, `FAIL`, or `INSUFFICIENT_EVIDENCE` under a
versioned validation contract.

## R6 — Edge Validated

Objective: establish strategy-version-specific economic eligibility without granting
execution authority.

```text
implementation = READY
watch = READY
proposal = READY
evidence = COMPLETE
economic_edge = VALIDATED
demo_execution = BLOCKED
live_execution = BLOCKED
```

Validation agents may diagnose, compare, identify failure modes, propose experiments,
and report. They may not promote a strategy, change thresholds, set Demo authorization,
or waive failed evidence. Registry and governance records remain authoritative.

**STOP #2:** edge validation permits work on Demo execution; it does not authorize
Demo or Live trading.

## R7 — Demo Execution Ready

Objective: implement scanner-driven Demo execution only for a strategy that has passed
the preceding gates and received separate authorization.

Three distinct gates must pass in order:

```text
DEMO_ELIGIBILITY_GATE
  economic edge and prerequisite evidence permit Demo consideration
        ↓
DEMO_AUTHORIZATION_GATE
  owner/governance explicitly authorizes this strategy/version/scope
        ↓
DEMO_EXECUTION_GATE
  scanner execution infrastructure is verified safe and operational
```

`economic_edge=VALIDATED`, `demo_eligible=true`, and `demo_authorized=false` is a valid
state. Capability availability never supplies eligibility or authorization.

```text
proposal_id → server-side proposal resolution → lifecycle validation
            → strategy governance → edge eligibility → owner authorization
            → fresh-price revalidation → risk gate
            → MT5 order_check → MT5 order_send
```

The client supplies an identifier and fresh owner confirmation, not authoritative
entry, stop, target, volume, or strategy fields. **The client is never execution
geometry authority.** Existing explicit/manual execution paths remain independently
gated and do not prove this stage.

Exit: fail-closed, identifier-based, separately authorized Demo execution with
recovery, reconciliation, and duplicate protection.

## R8 — Demo Auto-Execution Validated

Objective: prove that the validated theoretical edge survives real Demo execution.

Reconcile proposal entry with actual fill, spread, slippage, latency, commission,
realized R, missed trades, rejection rates, restart recovery, and operational
reliability. Passing `order_send()` alone is insufficient.

Exit: Demo expectancy after actual execution costs passes signed gates.

**STOP #3:** successful Demo automation permits evaluation for small Live. It does not
grant Live authorization.

## R9 — Controlled Live

Objective: introduce small capital only after R8, under independently recorded Live
authorization.

Required controls include per-trade and portfolio risk ceilings, daily loss and
position limits, a kill switch, owner-controlled authorization, broker reconciliation,
and staged capital scaling. Performance, not infrastructure availability, determines
whether capital may scale.

## Strategy readiness is independent

Project capability and strategy readiness must not be conflated. Maintain these fields
for every strategy version:

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

This representation should become machine-readable in the appropriate governance
source only when its schema, allowed transitions, and authority owner are frozen. This
roadmap does not itself update the strategy registry or grant any status.

After R4 a strategy may legitimately be ready for implementation, watch, and proposals
while evidence is validating and Demo/Live remain blocked. Receiving proposals never
implies profitability.

## Priority and KPI progression

Shortest profit-seeking path:

```text
real market watch → trustworthy canonical proposals → clean resolved observations
                  → credible positive edge → Demo automation
```

KPI progression:

1. Percentage of the canonical watch/proposal pipeline passing its gates.
2. Proposal Integrity Rate: valid canonical proposals divided by all proposal formation
   attempts, with duplicate identity, missing geometry, stale input, wrong strategy
   version/source, invalid timestamps, and ledger mismatches counted as failures.
3. Number and completeness of trustworthy resolved proposals.
4. Number of strategy versions passing prospective economic gates.
5. Demo expectancy after actual execution costs.
6. Risk-adjusted Live return within signed risk limits.

At R4, Proposal Integrity Rate has priority over proposal count. Its numerator,
denominator, exclusions, and target threshold must be frozen before it is used as an
acceptance gate; this plan does not assume that less than 100% is acceptable.

Do not optimize READY count, win rate, UI breadth, or execution features ahead of the
current gate.

## Immediate implementation scope

```text
WP0  Baseline reconciliation
  ↓
WP1  Market truth contract, including market_data_mode propagation
  ↓
WP2  Real closed-candle scanner feed
  ↓
WP3  R2 fail-closed freshness, completeness, duplication, and mode guards
  ↓
WP4  Canonical StrategyDecision contract
  ↓
WP5  Renderer-only UI; remove frontend strategy authority
  ↓
WP6  Proposal Formation Gate
  ↓
WP7  Deterministic proposal occurrence identity
  ↓
WP8  Persistent proposal ledger and lifecycle/freshness separation
  ↓
WP9  Read-only proposal API
  ↓
WP10 Scanner rendering
  ↓
WP11 Restart, rerun, overlap, idempotency, and duplicate tests
  ↓
WP12 Natural READY and NO_TRADE end-to-end proof; zero broker orders
  ↓
AG_PROPOSAL_OPERATION_READY_V1
  ↓
STOP
```

Before implementation, decompose `AG_CANONICAL_SCANNER_PROPOSAL_PIPELINE_V1` into
acceptance-tested work packages that reuse existing market-data, strategy, journal,
API, and frontend surfaces. The exactly-once ticket-delivery plan becomes supporting
R4 work rather than the master milestone. External messaging, broader instrument
coverage, Large-SMC operationalization, and interactive chart assistance remain
valuable product tracks, but may not bypass the R2–R4 authority chain or R4 STOP.
