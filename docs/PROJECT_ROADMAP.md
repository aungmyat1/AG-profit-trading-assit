# AG Profit Trading — Profit-Seeking Product Roadmap

Status: **OWNER-DIRECTED, REGENERATED 2026-09-07**

Planning baseline: `main` @ `b89eddbc30d5c6c5d48f203f8d5e48e065a18fbd`

This roadmap converts the project objective into an ordered product and evidence plan.
It does not authorize broker execution, change a frozen strategy, or claim that any
current strategy is profitable. Strategy YAML owns signal behavior; the registry owns
execution authority; immutable evidence owns performance claims.

## Objective

Build a deterministic trade assistant that:

1. publishes informational FX tickets after the Asian and London sessions for
   EURUSD, GBPUSD, USDJPY, and XAUUSD;
2. publishes preset-time crypto tickets for BTCUSDT and ETHUSDT;
3. watches an approved Large-SMC universe, exposes funnel status, and alerts on entry
   confirmation;
4. assists the owner during chart-led top-down analysis by coordinating the relevant
   market-structure, supply/demand, liquidity, and entry-confirmation skills, resolving
   any matching registered strategy, and tracking confirmation from higher-timeframe
   context into the strategy's related lower timeframe;
5. measures resolved outcomes after costs and promotes only strategies with credible
   positive out-of-sample evidence;
6. preserves `WATCH`, `NO_TRADE`, `DATA_ERROR`, `EXPIRED`, and `BLOCKED` as valid
   products rather than forcing activity.

The commercial product is dependable decision delivery. The profit-seeking objective
is to identify and scale positive net expectancy while controlling drawdown and
execution risk. More tickets, indicators, or wins are not substitutes for positive
net expectancy.

## Current baseline

| Area | Verified current state | Gap |
|---|---|---|
| FX strategy | EURUSD/GBPUSD decisions and READY rendering work for both cycles | USDJPY/XAUUSD not operationally contracted |
| FX scheduling | Two Windows tasks installed, enabled, and successfully fired on 2026-09-07 | restart, overlap, and missed-run recovery unverified |
| Ticket storage | decision/proposal journals and local reports exist | per-cycle immediate archive contract incomplete |
| External delivery | no transport on `main` | message-only delivery required |
| BTC | scheduled BTCUSDT production-data decision path | no delivered normalized ticket; evidence 0/30 |
| ETH | declared in strategy profile | feed/report/ticket path absent |
| Large-SMC | EURUSD research engine, batch watcher, version-safe ledger, funnel calculator | no live forward run, scheduler, alert delivery, or outcome resolver |
| Performance | normalized gross/net model and adapters committed | drawdown defect; timestamp-order ambiguity; costs/OOS incomplete |
| Demo execution | separate `SESSION_TRADE_V1` Asian→London path is authorized | reconciliation lookup fails open; recovery safety unreliable |
| Live execution | unauthorized | intentionally out of scope |

## Contracts to freeze first

### Logical ticket identity

One market occurrence produces one logical ticket. `proposal_id` is the current
canonical equivalent and may remain the identifier unless cross-strategy normalization
requires a separate `ticket_id`.

```text
strategy occurrence -> logical ticket -> archive -> delivery attempt(s)
```

A scheduler rerun resolves to the same ticket. A delivery timeout may create a new
`delivery_attempt_id`, but never a new ticket. Exactly-once means one logical ticket
and one durable delivered-state transition; an external network call may be retried
idempotently.

### Ticket content

Only `READY` receives a complete informational ticket. It contains only strategy-owned
values: strategy/version, instrument, cycle, direction, entry, stop, targets,
expiry/invalidation, signed risk data, reason codes, venue/freshness, and proposal
identity. It must display `INFORMATIONAL PROPOSAL — NOT A BROKER ORDER`.

Missing strategy-owned data stays missing or causes `BLOCKED`; the ticket layer never
invents it.

### Interactive top-down analysis

When the owner analyzes a chart from higher to lower timeframe, the assistant should:

1. establish higher-timeframe regime, structure, dealing range, and directional
   context;
2. map relevant supply/demand and liquidity areas without inventing levels;
3. search the strategy registry for a strategy whose signed universe, timeframe chain,
   session, and setup contract match the observed context;
4. report `NO_REGISTERED_STRATEGY_MATCH` when none applies rather than borrowing rules;
5. run the matched deterministic strategy and preserve its decision as the authority;
6. monitor the strategy-defined crossover from context timeframe to entry timeframe,
   using closed-candle evidence for structure shift, liquidity reclaim, displacement,
   rejection, or the strategy's own confirmation model;
7. distinguish advisory confirmation (`CONFIRMED`, `PARTIAL`, `NOT_CONFIRMED`, or
   `INDETERMINATE`) from a strategy `TradeSignal`;
8. produce a ticket only when the registered strategy itself reaches `READY`.

The agent skill set organizes and explains evidence; it does not create an independent
signal, silently select an unsigned threshold, or override `WATCH`/`NO_TRADE`.

### Profit measurement

```text
net out-of-sample expectancy
  -> drawdown and tail loss
  -> robustness across time/symbol/session/regime
  -> capacity and operational reliability
  -> gross metrics for diagnosis only
```

Performance must reconcile to immutable proposal/outcome/fill evidence and itemized
spread, commission, slippage, and funding where applicable. Metrics remain
`NOT_EVALUATED` when required inputs are absent.

## Roadmap

### Stage 0 — Safety and measurement hygiene

Run alongside ticket work without expanding into execution development.

1. Fix the performance drawdown baseline so the equity curve starts at zero; add the
   real 13-loss regression case.
2. Decide and test the canonical ordering for missing resolution timestamps.
3. Change broker reconciliation failure from “not found” to a fail-closed result.
   Until fixed, do not rely on crash recovery for the separately authorized
   `SESSION_TRADE_V1` Demo path.
4. Do not rewrite historical outcomes or strategy versions.

Exit: metrics obey a frozen calculation contract and broker lookup failure cannot
trigger a replacement order.

### Stage 1 — Exactly-once FX ticket product

Scope: current `ST_ASIAN_SWEEP_5R_V1` behavior, EURUSD/GBPUSD, both cycles.

1. Freeze logical-ticket and delivery-attempt identity.
2. Persist and archive each cycle result immediately after its checkpoint.
3. Verify overlapping scheduler invocations, restart recovery, and missed-run catch-up.
4. Reuse only the message/formatting portion of the paused Telegram branch after a
   secret, authorization, logging, and payload audit.
5. Add a delivery journal with retry state and durable deduplication.
6. Notify on new READY tickets and actionable operational failures; retain quiet local
   summaries for WATCH/NO_TRADE.
7. Exclude approval buttons, broker callbacks, and execution wiring.

Exit: one archived decision per symbol/cycle/date; one logical ticket per READY
occurrence; retries preserve identity; restart/overlap creates no duplicate; real
external delivery is verified without an order path.

### Stage 2 — Coverage expansion

For FX, create a new candidate version for USDJPY and XAUUSD. Freeze per-symbol
pip/tick conventions, aliases, sessions, spread filters, range limits, stop geometry,
sizing inputs, and data-quality requirements. Do not copy EURUSD constants.

For crypto, preserve BTCUSDT semantics while generalizing the feed/report/ticket
boundary for ETHUSDT. Freeze venue, contract type, metadata, UTC observation period,
preset publication time, complete-candle checks, and cost fields.

Exit: all six target instruments produce deterministic archived decisions and
normalized informational tickets when READY; execution remains disabled.

### Stage 3 — Large-SMC operational funnel

1. Run one controlled read-only EURUSD live batch to establish first forward evidence.
2. Install a watcher schedule only after batch output and version identity pass.
3. Persist material transitions: context candidate, E-qualified, M-engaged,
   entry-eligible, READY, invalidated, and expired.
4. Add restart-safe transition delivery and exactly-once confirmation alerts.
5. Keep EURUSD-only authority until a candidate expansion is signed.
6. Keep `ST_LARGE_SMC_V1` `RESEARCH_ONLY`; funnel alerts are not trade authority.

Exit: every watched instrument exposes a current explainable state; each transition is
durable; each new confirmation emits one informational alert.

### Stage 3A — Interactive chart-assistance workflow

1. Define a normalized top-down analysis request: symbol, current chart timeframe,
   analysis time, candidate direction if any, and optional named strategy.
2. Route the request through structure → supply/demand → liquidity → entry-confirmation
   skills, reusing each layer's output rather than re-detecting it downstream.
3. Resolve related registered strategies by signed symbol, session, setup, and
   timeframe-chain compatibility; never match by a strategy name alone.
4. Present a single traceable report containing HTF thesis, zones/liquidity, matched
   strategy status, next lower-timeframe confirmation required, invalidation, and
   current decision state.
5. Persist a watch candidate only when the relevant strategy contract permits it, then
   update it on newly closed bars until confirmed, invalidated, or expired.
6. Hand a strategy-produced READY result to the same canonical ticket pipeline used by
   scheduled decisions.

Exit: a user can begin from a chart, receive a deterministic multi-timeframe evidence
chain, see whether a registered strategy applies, and be assisted through entry
confirmation without the advisory skills being presented as signal authority.

### Stage 4 — Outcome resolution and economic validation

```text
proposal -> entry evidence -> SL/target/expiry outcome -> gross R
         -> costs -> net R -> portfolio equity
```

1. Sign outcome-resolution contracts separately for FX, crypto, and Large-SMC.
2. Preserve ambiguous sequences as unresolved; never choose the favorable path.
3. Reconcile periodic equity with trade/fill ledgers.
4. Separate development, validation, and untouched out-of-sample periods.
5. Report net expectancy first, then gross expectancy, payoff, hit rate, profit factor,
   drawdown/duration, loss streaks, exposure, turnover, holding time, and costs.
6. Attribute by version, instrument, cycle, direction, regime, and setup family.
7. Quantify uncertainty when sample size permits; do not annualize short or overlapping
   samples without warnings.
8. Run walk-forward, parameter perturbation, cost/slippage stress, and regime tests.

Promotion gates must be owner-signed before evaluation. At minimum they require:

- positive **net** out-of-sample expectancy;
- drawdown and loss streaks within an explicit capital budget;
- no excessive dependence on one symbol, session, or regime;
- survival under conservative costs and plausible slippage;
- stable behavior across validation windows;
- sufficient independent observations for the strategy frequency;
- zero unresolved safety or evidence-integrity blockers.

Exact numeric thresholds remain `UNSIGNED`; they must not be tuned after seeing the
validation result.

Exit: each strategy receives `PASS`, `FAIL`, or `INSUFFICIENT_EVIDENCE`. Only `PASS`
may be considered for Demo eligibility; it does not grant Demo authorization.

### Stage 5 — Portfolio selection and risk budgeting

Only strategies passing Stage 4 enter portfolio research.

1. Rank by conservative net expectancy and drawdown, not READY count or win rate.
2. Measure cross-strategy correlation, clustered losses, session overlap, and shared
   USD/crypto exposure.
3. Allocate a small explicit risk budget per strategy and a portfolio loss ceiling.
4. Reject edges that disappear after costs, concentration, capacity, or execution
   assumptions.
5. Define pause/retire rules for degradation before assigning capital.

Exit: a versioned portfolio candidate with explicit risk limits and independent
evidence.

### Stage 6 — Optional controlled Demo program

Demo eligibility, Demo authorization, and live authorization remain separate. After
Stage 0 safety closure and Stage 4/5 passage: mocked end-to-end validation, broker
`order_check`, one minimum-size Demo order, reconciliation, restart testing, then a
larger Demo observation program. Live trading remains outside this roadmap unless
separately authorized.

## Priority backlog

| Priority | Work item | Profit role | Gate |
|---|---|---|---|
| P0 | Exactly-once FX archive/recovery | captures every current opportunity reliably | Stage 1 acceptance |
| P0 | External message-only delivery | makes decisions actionable to the human | real delivery, no execution path |
| P0-Safety | Fail-closed broker reconciliation | prevents duplicate Demo orders | before trusted Demo use |
| P1 | USDJPY/XAUUSD contracts and tickets | expands opportunity set safely | candidate contract + shadow evidence |
| P1 | ETHUSDT feed/decision/ticket | adds second crypto stream | production data-quality proof |
| P1 | Large-SMC forward funnel and alerts | captures selective asymmetric candidates | durable transition evidence |
| P1 | Interactive top-down analysis workflow | converts chart context into a traceable strategy/confirmation watch | strategy match + closed-bar confirmation evidence |
| P1-Validation | Outcome resolvers and net metrics | determines economic value | reconciled immutable outcomes |
| P2 | Robustness and portfolio selection | reduces overfit and concentration | signed promotion/risk gates |
| Deferred | Demo/live execution expansion | monetizes only validated edge | separate authorization |

## Stop conditions

- Stop product expansion if ticket identity, freshness, or evidence integrity is
  unreliable.
- Stop promotion on non-positive net OOS expectancy, unacceptable drawdown, cost
  fragility, concentration, or insufficient evidence.
- Stop adding analytical concepts when the bottleneck is delivery or outcomes.
- Never delete losses, alter frozen attribution, or optimize gates after results.

## Immediate next milestone

`AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1`

It is limited to EURUSD/GBPUSD, the two current FX cycles, current strategy outputs,
per-cycle archive, recovery, and message-only delivery. See
`plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`.
