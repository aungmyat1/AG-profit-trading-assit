# AG Profit Trading — Current Roadmap Implementation Action Plan V1

Status: **PLANNED — NOT IMPLEMENTED**  
Recorded: **2026-09-08**  
Planning baseline: `main` at `5185035`  
Authority: `docs/PROJECT_ROADMAP.md`, reconciled with the current checkout

## Objective

Complete dependable informational decision delivery first, then expand instrument
coverage and forward monitoring, and only then evaluate economic edge and portfolio
risk. This plan does not authorize Demo or live execution and does not change any
frozen strategy rule.

## Current baseline

- EURUSD and GBPUSD deterministic decisions exist for both current FX cycles.
- FX and BTC scheduler tasks exist, but overlap, restart, and missed-run recovery are
  not proven.
- Local persistence exists; durable external delivery and delivery-attempt
  reconciliation remain incomplete.
- FastAPI, authorization, Telegram, and MT5 execution-handler code is now present on
  `main`, while `PROJECT_STATUS.md` still describes part of it as isolated. The status
  record must be reconciled before this is treated as an operational surface.
- BTCUSDT has a scheduled read-only decision path; ETHUSDT does not. Crypto execution
  remains unimplemented.
- Large-SMC has a research funnel but no proven forward watcher and alert lifecycle.
- Performance drawdown/timestamp-ordering contracts and fail-closed broker
  reconciliation remain Stage 0 blockers.
- Live trading stays disabled. Eligibility and authorization remain separate.

## Phased action plan

### Phase 0 — Reconcile and freeze the baseline

1. Audit the current API, authorization, Telegram, and execution-handler paths.
2. Classify each as implemented, unit-tested, Demo-verified, or unverified.
3. Correct `PROJECT_STATUS.md` and user-facing documentation without changing
   authority or runtime gates.
4. Record the source commit and affected test baseline.

Exit: documentation matches the checkout and makes no unsupported verification claim.

### Phase 1 — Close Stage 0 safety and measurement defects

1. Fix maximum drawdown so the equity curve starts at zero.
2. Add the documented 13-loss regression.
3. Freeze missing-timestamp ordering: timestamped records first; unknown timestamps
   last, ordered by immutable record identity and visibly flagged.
4. Make broker reconciliation query failure fail closed instead of appearing as “not
   found.”
5. Prove unavailable broker state cannot lead to a replacement Demo order.

Exit: metrics follow a frozen calculation contract and reconciliation ambiguity cannot
permit submission.

### Phase 2 — Complete Stage 1 exactly-once FX ticket delivery

Scope: `ST_ASIAN_SWEEP_5R_V1`, EURUSD/GBPUSD, both current cycles, informational
delivery only.

1. Freeze logical ticket identity and a separate delivery-attempt identity.
2. Define not-applicable, pending, delivered, retryable-failure, terminal-failure, and
   ambiguous-delivery states.
3. Render READY tickets only from persisted strategy-owned fields; missing required
   fields block rendering.
4. Archive every symbol/cycle/date decision immediately after the checkpoint and
   before networking, including WATCH, NO_TRADE, DATA_ERROR, and BLOCKED.
5. Add atomic run claims and a bounded, signed missed-run catch-up rule.
6. Test overlap, duplicate triggers, restart, premature runs, stale data, weekends,
   missed checkpoints, and subsequent recovery.
7. Extract message-only Telegram delivery after a secrets, destination, logging,
   timeout, and payload audit. Exclude buttons, callbacks, broker handlers, and all
   execution imports.
8. Add a durable delivery journal with ticket ID, attempt ID, state, timestamps,
   provider response identity, retry count, and redacted failure evidence.
9. Notify only for new READY tickets and actionable operational failures; retain quiet
   local records for WATCH and NO_TRADE.
10. Verify mocked transport, the affected suite, one real synthetic message when
    credentials permit, and one natural READY ticket when it occurs. Never manufacture
    a READY strategy result.

Exit: one archived decision per symbol/cycle/date, one logical ticket per natural READY
occurrence, no logical duplication after overlap/restart, and evidenced external
message delivery with no reachable order path.

### Phase 3 — Stage 2 coverage expansion

1. Create new candidate versions for USDJPY and XAUUSD; never modify the frozen
   EURUSD/GBPUSD strategy in place.
2. Sign per-symbol aliases, precision, pip/tick, sessions, spreads, ranges, stop
   geometry, sizing, and data-quality contracts.
3. Shadow-validate candidates before operational inclusion.
4. Generalize the BTC feed/report/ticket boundary for ETHUSDT while preserving BTC
   semantics.
5. Freeze ETH venue, contract type, metadata, UTC window, publication time,
   complete-candle rules, and costs.

Exit: all six target instruments produce deterministic archived decisions and
normalized informational tickets; execution remains disabled.

### Phase 4 — Stage 3 Large-SMC operational funnel

1. Run one controlled read-only EURUSD forward batch and verify version identity.
2. Persist context-candidate, E-qualified, M-engaged, entry-eligible, READY,
   invalidated, and expired transitions.
3. Install a watcher only after the batch passes.
4. Add restart-safe, exactly-once transition alerts.
5. Keep EURUSD-only and `RESEARCH_ONLY` authority until a separately validated
   expansion is signed.

Exit: funnel state is durable and explainable; each new confirmation emits one
informational alert.

### Phase 5 — Stage 3A interactive chart assistance

1. Freeze normalized analysis request and response contracts.
2. Reuse one evidence chain across structure, supply/demand, liquidity, and entry
   confirmation.
3. Match strategies by signed universe, session, setup, and timeframe compatibility;
   return `NO_REGISTERED_STRATEGY_MATCH` when none qualifies.
4. Persist only contract-permitted watches and update them from closed bars.
5. Route strategy-produced READY results through the canonical ticket pipeline.

Exit: chart-led analysis is traceable while the deterministic strategy remains the
sole signal authority.

### Phase 6 — Stage 4 economic validation

1. Sign separate outcome-resolution contracts for FX, crypto, and Large-SMC.
2. Preserve ambiguous sequences as unresolved.
3. Reconcile proposal, outcome, fill, cost, and equity evidence.
4. Separate development, validation, and untouched out-of-sample periods.
5. Report net expectancy first and run walk-forward, parameter, cost/slippage, and
   regime robustness tests.
6. Freeze owner-signed promotion thresholds before evaluating results.

Exit: each strategy receives PASS, FAIL, or INSUFFICIENT_EVIDENCE. PASS provides only
Demo eligibility, never authorization.

### Phase 7 — Stage 5 portfolio selection

For Stage 4 PASS strategies only, measure correlation, clustered losses, session and
currency exposure, costs, and capacity. Freeze per-strategy risk budgets, a portfolio
loss ceiling, and pause/retire rules.

Exit: a versioned portfolio candidate exists with explicit risk limits and independent
evidence.

### Phase 8 — Stage 6 optional controlled Demo program

After Stage 0 closure and Stage 4/5 passage: mocked end-to-end validation, broker
`order_check`, one separately authorized minimum-size Demo order, reconciliation and
restart tests, then a larger Demo observation program. Live trading remains outside
this plan unless separately authorized.

## Priority backlog

| Priority | Deliverable | Dependency |
|---|---|---|
| P0 | Reconcile current status documentation with `main` | none |
| P0-Safety | Drawdown, timestamp ordering, fail-closed reconciliation | baseline freeze |
| P0 | Exactly-once FX archive and scheduler recovery | shared Stage 0 safety |
| P0 | Message-only delivery and durable delivery journal | canonical archive |
| P1 | USDJPY/XAUUSD candidate contracts | Stage 1 accepted |
| P1 | ETHUSDT data/decision/ticket path | Stage 1 accepted |
| P1 | Large-SMC forward funnel and alerts | durable transition/delivery primitives |
| P1 | Interactive chart assistance | strategy matching and closed-bar evidence |
| P1-Validation | Outcome resolvers and net metrics | immutable tickets/outcomes |
| P2 | Robustness, portfolio selection, and risk budgeting | Stage 4 PASS evidence |
| Deferred | Demo expansion and live execution | separate authorization |

## Verification and stop rules

- Use focused tests per work package and the affected suite at phase completion.
- Run the full suite only for a milestone or broad shared-surface change.
- Record exact commands, results, dates, environments, and deferred live checks.
- Mocked delivery is not live delivery; market-data validation is not execution
  validation; Demo verification is not live authorization.
- Stop expansion when identity, freshness, or evidence integrity is unreliable.
- Stop execution work while Stage 0 safety is open.
- Never rewrite historical evidence or modify a frozen strategy in place.

