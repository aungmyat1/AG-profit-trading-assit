# Best Money-Making Paths and Ticket Delivery Action Plan V1

Status: **OWNER-DIRECTED PLAN — NOT EXECUTION OR PROFITABILITY AUTHORITY**  
Recorded: **2026-09-08**
Upgraded: **2026-09-08 — proposal/watch-surface architecture added**
Sequencing decision: **2026-09-09 — strategy validation begins after proposal/watch setup**

## Purpose

Turn AG Profit Trading into a dependable, measurable decision-delivery product before
funding strategies or selling access to them. The first commercializable surface is an
informational ticket service; automated or managed execution is not part of this plan.

This plan separates two scopes that must not be confused:

- **Operational delivery core:** EURUSD and GBPUSD first, then the existing BTCUSDT
  linear-perpetual decision contract, then XAUUSD under a new Gold-specific candidate
  contract.
- **Expanded research/watch surface:** FX Major Three (EURUSD, GBPUSD, USDJPY), Crypto
  Two (BTCUSDT, ETHUSDT), plus XAUUSD as the already-requested Gold expansion. USDJPY,
  ETHUSDT, and XAUUSD may appear earlier as `RESEARCH`/`SHADOW_ONLY` watch candidates,
  but may not inherit another instrument's proposal or execution authority.

Accordingly, **Major FX V1 delivery** continues to mean EURUSD and GBPUSD. “FX Major
Three” means the wider proposal/watch universe, not a claim that the current validated
strategy covers USDJPY. BTCUSD means BTCUSDT unless a later signed contract changes the
instrument.

Strategy YAML remains signal authority. The ticket layer may archive, normalize, and
deliver a strategy result, but may not invent entry, stop, target, expiry, risk, cost,
or direction values and may not convert `WATCH`, `NO_TRADE`, or `BLOCKED` into `READY`.

## Product definition — AG Market Opportunity and Validation Platform

The upgraded commercial direction is broader than a multi-symbol signal bot:

```text
market monitoring
  -> deterministic strategy or signed candidate evaluation
  -> progressive opportunity watch
  -> canonical informational proposal
  -> immutable archive and exactly-once delivery
  -> outcome and cost resolution
  -> evidence envelope and validation
```

It supports six named instruments across delivery and research scopes:

| Market | Instrument | Deterministic proposal status | Watch status | Initial authority |
|---|---|---|---|---|
| FX | EURUSD | Existing strategy where contract-compatible | Session + SMC research | Current strategy authority only |
| FX | GBPUSD | Existing strategy where contract-compatible | Session + SMC research | Current strategy authority only |
| FX | USDJPY | New candidate contract required | SMC research/watch | `SHADOW_ONLY`, execution `NONE` |
| Metals/FX venue | XAUUSD | New Gold-specific candidate required | Research/watch after conventions freeze | `SHADOW_ONLY`, execution `NONE` |
| Crypto | BTCUSDT perpetual | Existing contract where compatible | Optional progressive watch | Proposal-only, execution disabled |
| Crypto | ETHUSDT perpetual | New candidate contract required | Optional progressive watch | `SHADOW_ONLY`, execution disabled |

Expansion of the watch surface is allowed before commercial promotion because a watch
state is research evidence, not trade authorization. A complete proposal remains
impossible until a compatible signed strategy or signed candidate contract supplies
all required fields.

The watcher component is named the **AG Opportunity Intelligence Layer**. It observes,
persists, and explains opportunity evidence; it is not a signal engine. AG Profit
Trading remains the product, with Strategy, Opportunity Intelligence, Proposal,
Delivery, Outcome, Evidence, and Validation as separate responsibilities.

## Watcher state, proposal state, and authorization are orthogonal

A proposal records that a deterministic strategy or signed candidate contract found a
sufficiently defined opportunity and constructed a complete informational plan. It
does not grant execution authority. Watcher progression, proposal resolution, and
execution authority are three independent schema dimensions and must never share one
enum.

Watcher state:

```text
SCANNING
CONTEXT_IDENTIFIED
LIQUIDITY_APPROACH
POI_APPROACH
LIQUIDITY_SWEPT
STRUCTURE_CONFIRMING
SETUP_QUALIFIED
INVALIDATED
EXPIRED
DATA_BLOCKED
```

Proposal state:

```text
NOT_EVALUATED
NO_TRADE
INCOMPLETE
STRATEGY_UNMATCHED
PROPOSAL_READY
PROPOSAL_INVALIDATED
PROPOSAL_EXPIRED
BLOCKED
```

Independent execution authority:

```text
NONE
DEMO_ELIGIBLE
DEMO_AUTHORIZED
LIVE_AUTHORIZED
```

The system may therefore display `PROPOSAL_READY` together with `execution_authority:
NONE`. It may also truthfully record `watcher_state: SETUP_QUALIFIED`,
`proposal_state: STRATEGY_UNMATCHED`, and `execution_authority: NONE` when valid research
evidence exists but no compatible signed strategy owns the proposal. The canonical
record, UI, alert formatter, and evidence export must carry all three fields explicitly.
No dimension may be inferred from another.

Generic AI analysis cannot create proposals. AI may explain deterministic evidence,
summarize why an instrument is at a watcher state, or rank attention priorities. It
may not invent or change direction, entry, stop, targets, expiry, risk, qualification,
proposal state, strategy match, or execution authority.

## Best money-making paths

In recommended order:

1. **Owner-operated decision support.** Use informational tickets to improve the
   owner's manual workflow while collecting complete forward evidence. This has the
   lowest operational and commercial overhead.
2. **Paid informational ticket subscription.** After economic promotion gates pass,
   offer timely FX, BTC, and Gold tickets with provenance, invalidation, and transparent
   performance reporting. No guaranteed-return language and no broker-order controls.
3. **Structured chart-assistance service.** Provide top-down evidence, matched-strategy
   status, confirmation requirements, and invalidation without presenting advisory
   analysis as an independent trade signal.
4. **Software licensing.** License the deterministic scheduler, ticket, journal,
   evidence, and risk-control platform to trading educators, analyst groups, or small
   trading teams after deployment and tenant-isolation requirements are met.
5. **Strategy research reports.** Sell or use cost-adjusted performance, regime,
   drawdown, and robustness research only when it reconciles to immutable evidence.

No strategy may be funded, advertised as profitable, or sold as an actionable signal
until it passes the prospective promotion gates in this plan. Any regulated offering,
personalized advice, copy trading, or management of client funds requires a separate
legal and compliance review for the operating jurisdiction.

## Problem statement

The project can already generate deterministic decisions and has much of the
exactly-once FX foundation, but it cannot yet support a defensible money-making claim.
Real external delivery is not proven, ticket outcomes are not completely resolved
after realistic costs, the FX and BTC forward campaigns are incomplete, and two known
safety/measurement defects remain. Adding more instruments before closing these gaps
would increase activity without proving reliability or positive net expectancy.

## Target outcome

Deliver one durable, normalized, informational ticket for every natural `READY`
occurrence in the authorized EURUSD, GBPUSD, BTCUSDT, and later XAUUSD pipelines, with:

- exactly one logical ticket identity across retries, restarts, and overlapping runs;
- archive-before-delivery and a durable delivery-attempt journal;
- complete source, strategy, market-data, timing, and cost provenance;
- deterministic outcome resolution, including an explicit unresolved state;
- net performance and drawdown computed from immutable evidence;
- prospective promotion thresholds and out-of-sample evaluation;
- no reachable broker-order path from ticket delivery.

## Non-negotiable gates

Work proceeds through the gates below in order. A failed gate stops dependent work and
marks it `NOT_EVALUATED`.

1. **Safety gate:** reconciliation failures fail closed and cannot cause a replacement
   order; message delivery has no execution imports or callbacks.
2. **Measurement gate:** drawdown and outcome ordering contracts are frozen and tested.
3. **Reliability gate:** exactly-once archive and delivery survive overlap, restart,
   timeout ambiguity, and missed checkpoints.
4. **Evidence gate:** every eligible occurrence is preserved and every terminal result
   is resolved or explicitly unresolved.
5. **Economic gate:** net out-of-sample expectancy and cost stress pass prospective
   thresholds.
6. **Expansion gate:** USDJPY, XAUUSD, and ETHUSDT may enter research/watch in
   `SHADOW_ONLY` mode after their conventions are signed. They may enter normalized
   ticket delivery only after gates 1–4 pass for the first pipeline and their own
   strategy, data-quality, cost, identity, and outcome contracts pass.

## Strategy-validation start gate

Proposal/watch setup is the prerequisite data-producing system for validation. For
each strategy cohort, formal validation begins when all of these are true:

- the canonical proposal adapter preserves the strategy's output without invention;
- the relevant proposal-delivery path is exactly-once and archive-first;
- the relevant watcher state is deterministic, persisted, idempotent, and recoverable;
- every `PROPOSAL_READY` occurrence enters outcome resolution automatically;
- required market-data provenance and complete-candle evidence are present;
- cost and outcome contracts are frozen for the cohort;
- promotion thresholds were approved before formal results are reviewed;
- proposal/watch code remains structurally isolated from broker execution.

At that point the project starts the strategy-validation process: collect or continue
the required forward sample, resolve every proposal outcome or explicit ambiguity,
calculate cost-adjusted performance, run out-of-sample and stress tests, and return
`PASS`, `FAIL`, or `INSUFFICIENT_EVIDENCE`.

This handoff is cohort-specific. EURUSD/GBPUSD validation need not wait for USDJPY,
XAUUSD, or ETHUSDT candidate completion. BTCUSDT has an independent validation cohort.
Research data from `STRATEGY_UNMATCHED` watcher occurrences may inform future strategy
design but cannot enter an existing strategy's trade-performance sample.

## Workstream 0 — Freeze the common proposal contract

Build one deep, strategy-neutral proposal module before adding more integrations. It
normalizes signed outputs but contains no detection logic and has no execution imports.
The envelope must include:

- proposal identity, strategy identity/version, and application release;
- market, venue, contract type, symbol, and timestamps;
- watcher state, proposal state, and execution authority as three independent fields;
- direction, entry, stop, targets, expected R, and expiry only when strategy-owned;
- setup, market context, liquidity, and confirmation evidence;
- data provenance, freshness, and complete-candle evidence;
- itemized cost assumptions and explicit missing-cost status;
- correction/version linkage and schema version.

Each watcher occurrence also freezes:

- `detected_at`: when the occurrence was first recognized;
- `state_entered_at`: when the current watcher state began;
- `last_evaluated_at`: the most recent deterministic evaluation;
- `evidence_candle_close`: the closed-candle boundary supporting the state;
- `expires_at`: the strategy- or candidate-owned expiry when defined;
- `evidence_complete`: the immutable evidence already satisfied;
- `next_required_evidence`: the signed evidence still required for the next valid
  transition.

Timestamp semantics, timezone, monotonicity, correction behavior, and missing-value
handling must be part of the versioned schema contract. `next_required_evidence` is
explanatory state derived from the compatible contract; it may not invent an unsigned
requirement.

All current strategy-specific decision vocabularies map losslessly into the common
envelope. The normalizer may map names, but may not upgrade a state or synthesize a
missing field. A missing required proposal field produces `BLOCKED`, not a partial
`PROPOSAL_READY`.

Deliverables:

- versioned canonical proposal schema and validation contract;
- separate watcher-state, proposal-state, and execution-authority contracts;
- opportunity timestamp and next-required-evidence contract;
- adapters for existing EURUSD/GBPUSD session decisions and BTCUSDT decisions;
- compatibility rules for future Large-SMC, USDJPY, XAUUSD, and ETHUSDT candidates;
- static and behavioral proof that the module cannot reach broker execution.

Exit: the same consumer can archive, display, deliver, and export proposals from
different strategies without knowing their internal detection rules.

## Workstream A — Close safety and measurement defects

### A1. Correct drawdown calculation

Freeze an equity-curve contract whose baseline starts at zero before the first trade.
Compute peak-to-trough drawdown from the cost-adjusted cumulative result and define the
handling of deposits, withdrawals, unresolved outcomes, corrections, and empty series.
Freeze deterministic ordering for records without resolution timestamps; never use an
ordering rule that can move losses to produce a better result.

Deliverables:

- signed drawdown and ordering contract;
- corrected performance calculation;
- regression fixture containing the real 13-loss case;
- tests for empty, all-win, first-trade loss, consecutive loss, correction, and
  missing-timestamp cases;
- dated evidence recording old versus corrected results without rewriting history.

Exit: independent fixtures reproduce expected equity, peak, drawdown amount, drawdown
percentage where defined, and drawdown duration.

### A2. Make broker reconciliation fail closed

Separate `CONFIRMED_NOT_FOUND` from `LOOKUP_FAILED`, `LOOKUP_AMBIGUOUS`, and
`LOOKUP_UNAVAILABLE`. Only a broker-confirmed absence may permit the independently
authorized execution workflow to consider recovery. All other states stop recovery and
emit actionable evidence. This change does not authorize any strategy or order.

Deliverables:

- typed reconciliation result with explicit reason codes;
- fail-closed recovery decision;
- tests for timeout, disconnected terminal, malformed response, duplicate matches,
  confirmed absence, and confirmed existing order;
- controlled Demo validation only under separate owner authorization.

Exit: no lookup exception, timeout, or ambiguity can be interpreted as “order absent.”

## Workstream B — Finish exactly-once Major FX delivery

Build on the existing Stage 1 foundation. Do not recreate completed identity, archive,
claim, catch-up, transport-adapter, or retry primitives.

1. Complete the delivery journal and verify retry/backoff at the real scheduled call
   site using the owner-approved policy.
2. Audit message configuration, destination allow-list, secret handling, payload size,
   redaction, timeout, and rate-limit behavior.
3. Separately authorize `MESSAGE_DELIVERY`; before authorization, keep the shipped
   mode at `ARCHIVE_ONLY`.
4. Send one synthetic, non-trading operational message and preserve its provider
   response identity.
5. Wait for and deliver one natural strategy-generated EURUSD or GBPUSD `READY`
   ticket. Do not manufacture readiness.
6. Prove overlap, restart-after-archive, timeout-after-send, retry, missed-run catch-up,
   weekend, stale-data, and corrupted-store behavior at the scheduled boundary.
7. Run a monitored reliability period covering both FX cycles and report delivery
   success, latency, duplicate count, archive completeness, and unresolved failures.

FX delivery exit criteria:

- every evaluated symbol/cycle/date has one immutable archived decision;
- every natural `READY` has one logical ticket and zero duplicate logical tickets;
- every delivery attempt is journaled and linked to the logical ticket;
- archive completeness is 100% for eligible evaluations;
- duplicate delivered logical tickets are zero;
- retries never change ticket identity;
- execution remains structurally unreachable;
- operational failures are visible and recoverable without deleting evidence.

## Workstream C — Finish exactly-once BTCUSD delivery

Preserve the existing BTCUSDT strategy and daily observation contract. Create a shared
ticket-delivery boundary only where semantics are genuinely common; do not force FX
cycles and crypto observation windows into one strategy model.

1. Map the BTC decision output into the canonical ticket envelope without recomputing
   strategy fields.
2. Define BTC logical identity from strategy/version, instrument/venue/contract type,
   UTC observation date and period, and occurrence identity.
3. Archive every decision state before delivery, including data-quality failure,
   `WATCH`, `NO_TRADE`, and `READY`.
4. Reuse the proven delivery-attempt journal, deduplication, retry, and redaction
   interfaces.
5. Enforce the frozen complete-candle audit, publication window, venue metadata, and
   data-freshness checks before ticket registration.
6. Include explicit spread, fee, slippage, and funding fields or mark the missing cost
   input; never silently assume zero cost.
7. Prove one synthetic transport message, then one natural BTC ticket when the engine
   produces it. Crypto execution remains disabled.

BTC delivery exit criteria mirror FX and additionally require correct venue, linear
contract, UTC period, complete-candle, and funding provenance.

## Workstream C2 — Build the reuse-first opportunity watcher

The watcher is a durable opportunity funnel, not a second signal engine. Reuse the
existing market-structure, supply/demand, liquidity, entry-confirmation,
multi-timeframe-context, and Large-SMC research outputs. Do not redetect their evidence
inside the watcher and do not create a competing SMC vocabulary.

Initial FX watch universe:

```text
EURUSD + GBPUSD + USDJPY
  -> structure / liquidity / POI evidence
  -> progressive watcher state
  -> compatible registered-strategy resolution
  -> PROPOSAL_READY only when that strategy produces it
```

XAUUSD enters the watcher after its market conventions are frozen. BTCUSDT and ETHUSDT
may use the same watcher interface later, but crypto-specific strategies and evidence
remain independent.

### Multi-timeframe roles

Use role-based profiles from the existing multi-timeframe context contract. The
initial FX profile may use D1/H4 for directional context, H1 for POI and liquidity,
M15 for setup qualification, M5 for confirmation, and M1 only for optional precision
evidence. This is a configured profile, not a universal hard-coded hierarchy. A lower
timeframe pattern cannot override invalid higher-timeframe context or strategy rules.

### Watcher state machine

```text
SCANNING
  -> CONTEXT_IDENTIFIED
  -> LIQUIDITY_APPROACH or POI_APPROACH
  -> LIQUIDITY_SWEPT
  -> STRUCTURE_CONFIRMING
  -> SETUP_QUALIFIED
  -> strategy resolver
       -> compatible signed strategy -> proposal evaluation
       -> no compatible strategy -> proposal_state: STRATEGY_UNMATCHED

Watcher terminal: INVALIDATED | EXPIRED | DATA_BLOCKED
```

Every transition records the closed-candle evidence, source component/version,
analysis time, `detected_at`, `state_entered_at`, `last_evaluated_at`,
`evidence_candle_close`, `expires_at`, symbol, timeframe role, reason code, prior state,
`evidence_complete`, and `next_required_evidence`. A transition must be idempotent and
restart-persistent. `SETUP_QUALIFIED` is still not a proposal unless a compatible
registered strategy owns that conversion. When no such strategy exists, preserve the
research occurrence as `proposal_state: STRATEGY_UNMATCHED`; do not misclassify it as
`NO_TRADE`, operational `BLOCKED`, or `PROPOSAL_READY`.

The watcher may reuse signed Large-SMC E/M concepts and existing structure, liquidity,
POI, order-block, imbalance, and entry-confirmation terms. Any currently unsigned
Large-SMC rule remains unsigned and cannot be completed by the watcher.

### Progressive notifications

Limit user-facing notifications to material transitions. These are presentation
classes, not additional watcher or proposal states:

- **WATCH:** context identified and price materially approaching signed liquidity or a
  POI; no trade plan.
- **SETUP FORMING:** a signed liquidity/POI event occurred and named confirmation is
  pending; no trade plan.
- **PROPOSAL READY:** the compatible deterministic strategy produced a complete
  informational plan; execution authority shown separately.
- **TERMINAL/FAILURE:** invalidation, expiry, data block, or actionable operational
  failure.

Repeated polls in the same state remain quiet. Delivery uses the same durable logical
event and attempt journal as tickets so restart or retry cannot create duplicate
transition alerts.

### Opportunity board and ranking

Provide one board row per strategy × symbol occurrence, showing symbol, system,
watcher state, candidate direction when strategy-owned, context, pending evidence,
proposal status, freshness, update time, and execution authority. The detail view
shows the immutable evidence chain and next required transition.

Do not implement the Opportunity Board until M2A has proven the persisted watcher
model, valid transitions, idempotency, and restart recovery. The board is a read model
over backend truth; it must never become the state owner or write watcher/proposal
transitions. Delivery proof may proceed independently under its own authorization.

Ranking is attention prioritization only. Its inputs are deterministic state,
freshness, distance, completeness, and expiry facts. AI may explain why one existing
state deserves attention before another, but cannot add points that change the state,
qualify a setup, or promote a proposal. Ties and missing evidence must be visible.

Watcher exit criteria:

- transitions are deterministic, idempotent, durable, and closed-candle based;
- no duplicated detection logic or second SMC engine exists;
- USDJPY remains research/shadow until its own candidate contract is signed;
- the board reproduces state from persisted evidence after restart;
- `SETUP_QUALIFIED` without a compatible signed strategy resolves to
  `STRATEGY_UNMATCHED` without losing the watcher evidence;
- opportunity timestamps and next required evidence reproduce deterministically;
- progressive alerts occur once per material transition and remain quiet otherwise;
- no watcher or ranking path can create strategy readiness or execution authority.

## Workstream D — Resolve every ticket outcome after realistic costs

Freeze separate FX and BTC outcome contracts. XAUUSD adopts an FX-style contract only
after its symbol-specific conventions are signed.

For every logical proposal, persist a lifecycle such as:

```text
READY -> ENTRY_NOT_REACHED | ENTERED -> TARGET | STOP | EXPIRED | UNRESOLVED
      -> gross R -> itemized costs -> net R
```

Requirements:

- use bid/ask-aware entry and exit tests appropriate to direction;
- resolve same-bar stop/target ambiguity conservatively or leave it unresolved;
- model spread, commission, slippage, swap for FX, and fees/funding for BTC;
- preserve partial fills and missing market data as explicit states;
- never overwrite the original ticket or historical outcome; corrections append;
- link each result to strategy version, data version/source, and resolver version;
- reconcile aggregate metrics to the immutable ticket population.

Exit: every campaign ticket is terminally resolved or explicitly `UNRESOLVED` with a
reason; no omitted ticket disappears from the denominator.

Every `PROPOSAL_READY` record automatically enters this pipeline. Earlier watch states
remain research evidence but do not enter trade-outcome statistics. The outcome record
then feeds a versioned canonical trade export and validation evidence envelope so
performance can be segmented by strategy × symbol × setup × session × regime.

Maintain two explicitly separate metric families:

```text
Trading performance
PROPOSAL_READY -> entry -> outcome -> costs -> net R

Opportunity funnel performance
context -> watch -> setup -> qualified -> matched/unmatched -> proposal -> entry
```

The funnel may measure transition counts, conversion rates, time in state, expiry,
invalidation, strategy-unmatched frequency, and proposal latency. Segment by strategy,
symbol, session, setup type, regime, weekday, and volatility only when the evidence
contract supplies those fields. Funnel conversion is diagnostic research and must not
be presented as trading expectancy or used by AI to change strategy qualification.

## Workstream E — Complete forward observation campaigns

### FX campaign

Continue the authorized campaign using the frozen validity definitions. Complete at
least the currently required 20 valid trading days; excluded and invalid days do not
silently count. Reconcile both cycles and both V1 symbols daily. A campaign cannot pass
with unexplained missing decisions or outcome records.

### BTC campaign

Complete the authorized 30-valid-observation campaign within the frozen publication
window. Diagnostics, scheduler installation, late runs, or incomplete candle sets do
not count. Reconcile the archive, ticket, delivery, and outcome populations daily.

Campaign exit package:

- immutable observation manifest and inclusion/exclusion reasons;
- archive-to-ticket-to-delivery-to-outcome reconciliation;
- gross and net results with itemized costs;
- drawdown and tail-loss report using the corrected contract;
- data-quality, missed-run, duplicate, and correction summary;
- explicit `PASS`, `FAIL`, or `INSUFFICIENT_EVIDENCE`; no promotion implied.

## Workstream F — Freeze promotion thresholds prospectively

Thresholds must be owner-approved and committed before campaign results are unblinded
for promotion. Define them separately per strategy and portfolio. At minimum specify:

- minimum valid out-of-sample observations and valid coverage rate;
- minimum net expectancy after base costs;
- maximum drawdown rate, amount, and duration;
- maximum consecutive losses and tail loss;
- minimum robustness across symbol, cycle, time segment, and regime;
- maximum concentration in one symbol, session, or small subset of trades;
- required survival under elevated spread, commission/fee, slippage, and funding;
- acceptable operational failure, missing-outcome, unresolved, and duplicate rates;
- a holdout or walk-forward procedure and retest policy;
- automatic rejection conditions and the waiting period before re-evaluation.

Do not optimize these thresholds after seeing results. If sample size is insufficient,
the only valid classification is `INSUFFICIENT_EVIDENCE`.

## Workstream G — Cost stress and funding decision

For every candidate that meets the base case:

1. run out-of-sample evaluation only on untouched evidence;
2. apply independently defined adverse spread, commission/fee, slippage, swap/funding,
   and delayed-entry scenarios;
3. segment by symbol, cycle, market regime, and calendar period;
4. run walk-forward or time-split stability tests;
5. check dependence on the best few trades and worst plausible ordering;
6. calculate portfolio interaction and drawdown before combining strategies.

Only a prospectively passing strategy may advance to a separately authorized,
strictly limited owner-funded or paid-pilot phase. Passing research does not enable
Demo or LIVE execution, and commercial release still requires legal/compliance,
support, disclosure, billing, and privacy readiness.

## Workstream H — Add Gold, then USDJPY and ETH

### H1. XAUUSD

Start only after the first EURUSD/GBPUSD pipeline passes the reliability gate. Create a
new candidate strategy version or symbol contract; do not copy EURUSD constants.
Freeze broker aliases, tick/contract size, session behavior, spread limits, range
limits, stop geometry, minimum distances, sizing inputs, stale-data rules, and cost
model. Run offline tests, read-only market-data validation, shadow ticket delivery,
outcome resolution, and an independent forward campaign before economic promotion.

### H2. USDJPY and ETHUSDT

These may join the opportunity board earlier as explicitly labeled research/shadow
rows after their data and identity conventions are signed. Normalized
`PROPOSAL_READY` authority and external ticket delivery remain deferred until the
first pipelines are operationally reliable and each candidate has its own signed
strategy contract. ETH may reuse interfaces from BTC but not BTC thresholds or
empirical cost assumptions. USDJPY may reuse MT5 market-data interfaces but not
EURUSD/GBPUSD pip, range, spread, stop, sizing, session, or cost values.

## Target architecture

```text
FX Major Three + Gold                 Crypto Two
EURUSD GBPUSD USDJPY XAUUSD           BTCUSDT ETHUSDT
          |                                  |
session strategies / reuse-first watcher    crypto strategies/candidates
          +------------------+---------------+
                             |
                  canonical proposal normalizer
                             |
              proposal gate + separate authority gate
                   /         |          \
             NO_TRADE       WATCH    PROPOSAL_READY
                                          |
                              immutable archive first
                                          |
                              Telegram + opportunity board
                                          |
                                  outcome resolver
                                          |
                        canonical export/evidence envelope
                                          |
                                  validation engine
```

The proposal/watch service remains structurally isolated from order submission. The
fact that the underlying venue adapter has order capabilities is not permission for
this architecture to import or invoke them.

## Milestones and dependencies

| Milestone | Depends on | Completion evidence |
|---|---|---|
| M0 Plan recorded | None | This owner-directed document indexed in repository docs |
| M1 Safety and metrics corrected | M0 | Focused tests and dated status evidence |
| M1A Canonical proposal contract frozen | M1 measurement semantics | Versioned schema, adapters, state/authority separation tests |
| M2 Major FX message delivery proven | M1/M1A plus delivery authorization | Synthetic send, natural READY send, reliability report |
| M2A FX Major-Three watcher proven | M1A and reused evidence components | Durable transitions and watcher-store recovery; USDJPY shadow-only |
| M2B Opportunity Board read model | M2A persisted watcher proof | Read-only board recovery, next-evidence display, no state writes |
| M3 BTC exactly-once delivery proven | M1A and reusable delivery boundary | Natural scheduled ticket and reconciliation report |
| M3A Crypto-Two watch surface | M3 reliability pattern plus ETH candidate conventions | BTC row and ETH shadow row with explicit authority |
| M4 Strategy-validation process starts | Relevant proposal delivery + persisted watch setup; outcome/cost contracts and prospective thresholds frozen | Cohort opened with immutable manifest and no execution path |
| M5 Outcomes and campaigns complete | M4 per cohort | Population reconciliation, FX 20-valid-day and BTC 30-valid-observation packages |
| M6 Validation and promotion gates evaluated | M5 complete | Out-of-sample/cost-stress evidence and PASS/FAIL/INSUFFICIENT_EVIDENCE report |
| M7 Limited funding or paid pilot | M6 PASS plus separate authorization | Budget, disclosures, monitoring, stop conditions |
| M8 XAUUSD operationally reliable | M2 reliability pattern plus signed Gold contract | Watch, shadow campaign, outcome and delivery evidence |
| M9 USDJPY/ETH proposal candidates | M2A/M3A and separate signed contracts | Candidate proposals and independent campaign plans |

M1's drawdown and reconciliation tracks may proceed independently, but M1 must be
verified as a whole before M1A. After M1A, M2 delivery and M2A watcher work may proceed
independently. M2B begins only after M2A persistence and recovery pass. Outcome
resolution consumes backend proposal/watcher truth and must not be designed around an
unproven UI model. No downstream milestone may claim completion while a prerequisite
is incomplete.

## User stories

1. As the owner, I want every scheduled decision archived so that missed opportunities
   and losses cannot disappear from the record.
2. As the owner, I want one logical ticket across retries so that duplicate alerts do
   not create duplicate trades or distorted statistics.
3. As a ticket recipient, I want provenance and invalidation on every READY ticket so
   that I can understand what produced it and when it is no longer valid.
4. As a risk reviewer, I want broker lookup failures to block recovery so that an
   infrastructure error cannot create a replacement order.
5. As a performance reviewer, I want drawdown measured from a zero baseline so that
   early losses and loss streaks are represented honestly.
6. As a strategy owner, I want every ticket outcome resolved after itemized costs so
   that gross wins cannot conceal negative net expectancy.
7. As a researcher, I want ambiguous paths preserved as unresolved so that the resolver
   cannot choose the favorable result.
8. As a potential customer, I want performance based on forward out-of-sample evidence
   so that product claims are auditable.
9. As the owner, I want thresholds frozen before results are reviewed so that promotion
   is not fitted to the observed campaign.
10. As the owner, I want new symbols gated by proven reliability so that expansion does
    not multiply operational defects.
11. As a regulator or auditor, I want informational delivery separated from execution
    so that the product's actual authority is clear.
12. As an operator, I want actionable failure alerts and restart-safe recovery so that
    unattended scheduling is dependable.
13. As the owner, I want a single opportunity board so that I can compare the current
    deterministic state of all watched instruments without operating separate bots.
14. As the owner, I want progressive WATCH and SETUP FORMING alerts so that I can focus
    attention before a proposal without receiving repeated micro-event noise.
15. As a strategy owner, I want proposal status separated from execution authority so
    that research usefulness cannot silently enable trading.
16. As a researcher, I want USDJPY, XAUUSD, and ETH clearly labeled as candidates so
    that their evidence cannot be attributed to validated EURUSD or BTC contracts.
17. As an auditor, I want every watcher transition linked to closed-candle evidence so
    that state progression can be reproduced without lookahead.
18. As a user, I want rankings to explain existing deterministic facts without changing
    readiness so that prioritization remains advisory.

## Testing decisions

Tests assert externally observable contracts rather than internal implementation:

- pure fixtures for drawdown, ordering, outcome paths, and cost arithmetic;
- contract tests for canonical ticket envelopes across FX and BTC;
- state-machine tests for allowed, rejected, duplicate, corrected, expired, and
  restart-recovered watcher transitions;
- cross-strategy schema conformance tests proving lossless normalization without
  invented fields;
- fault-injection tests for archive, store corruption, provider timeout, retry, restart,
  overlap, and reconciliation failure;
- static and behavioral guards proving ticket delivery cannot reach order submission;
- scheduled-entry-point tests, not only isolated helper tests;
- shadow/live-data checks are recorded separately from unit tests and never presented
  as execution or profitability validation;
- full regression runs only at material milestones or broad shared-surface changes.

## Commercial readiness checklist

- [ ] Major FX and BTC reliability gates passed.
- [ ] Canonical proposal state and execution authority are independently represented.
- [ ] Opportunity board and progressive alerts recover without duplicate transitions.
- [ ] Opportunity Board is a read-only projection over a proven persisted watcher.
- [ ] `STRATEGY_UNMATCHED`, lifecycle timestamps, and `next_required_evidence` conform
      to their frozen contracts.
- [ ] XAUUSD separately contracted and reliability-tested.
- [ ] All campaign tickets reconciled to outcomes.
- [ ] Prospective promotion thresholds recorded before evaluation.
- [ ] Net out-of-sample and adverse-cost tests passed.
- [ ] Performance claims reproduce from immutable evidence.
- [ ] Product disclosures clearly say informational, not guaranteed and not an order.
- [ ] Jurisdiction-specific legal/compliance review completed.
- [ ] Customer data, secrets, billing, support, retention, and incident processes ready.
- [ ] A limited paid pilot has explicit monitoring and stop conditions.

## Out of scope

- changing frozen strategy behavior in place;
- authorizing Demo or LIVE trading;
- autonomous execution, copy trading, or management of client funds;
- guaranteed returns or profitability claims;
- giving USDJPY, XAUUSD, or ETH proposal authority by copying another instrument's
  constants (research/watch rows with explicit shadow status remain in scope);
- silently repairing historical evidence or excluding losing tickets;
- frontend work unrelated to ticket visibility and auditability.

## Immediate next action

The next implementation task is deliberately bounded to **M1 -> M1A -> STOP**:

1. freeze and correct the drawdown/ordering contract;
2. make broker reconciliation fail closed;
3. verify M1 with focused tests and required dated status evidence;
4. freeze the common canonical proposal contract, including the independent watcher,
   proposal, and execution-authority dimensions, `STRATEGY_UNMATCHED`, lifecycle
   timestamps, and `next_required_evidence`;
5. verify adapters for existing EURUSD/GBPUSD and BTCUSDT outputs without activating
   delivery or adding new instrument behavior;
6. stop and report before M2 delivery, M2A watcher runtime, or M2B UI implementation.

WP7 Major FX delivery preparation may be inspected but cannot bypass its separate
authorization. Do not activate network delivery or perform any broker mutation without
the separately required owner authorization.
