# AG Profit Trading — Product Roadmap

Status: **OWNER-DIRECTED, 2026-09-07**

This document records the current product direction. It does not authorize broker
execution, modify a frozen strategy, or reclassify research evidence. Strategy YAML
and the strategy registry remain authoritative for strategy behavior and execution
permission.

## Product objective

AG Profit Trading is a deterministic, proposal-only trade assistant whose primary
operational product is a timely **informational trade ticket**:

1. **FX Session Trade:** evaluate three major FX pairs plus gold after the Asian
   session and again after the London session, producing an explicit decision for
   every configured symbol and cycle.
2. **Crypto Session Trade:** evaluate two crypto instruments at owner-specified preset
   times, producing the same explicit decision/ticket product.
3. **Large-SMC Watch:** monitor an owner-specified pair watchlist, persist each setup's
   funnel status, and alert when the frozen strategy reaches entry confirmation.

The default proposed universe, pending contract freeze, is:

```text
FX      EURUSD, GBPUSD, USDJPY, XAUUSD
CRYPTO  BTCUSDT, ETHUSDT
```

`XAUUSD` is the canonical product symbol; broker aliases such as `XAUUSD.crp` must be
resolved by configuration. No symbol-specific thresholds may be copied from EURUSD to
USDJPY, XAUUSD, or crypto without a versioned strategy contract.

## Decision and ticket contract

Every scheduled evaluation must return one explicit state, including when no trade is
available. Existing strategy-specific states remain authoritative; the operational
normalization is `READY`, `WATCH`, `NO_TRADE`, `DATA_ERROR`, `EXPIRED`, or `BLOCKED`.

Only `READY` produces a complete informational trade ticket. A ticket should contain,
where supplied by the current frozen strategy:

- strategy id and version;
- instrument, market, session/cycle, and evaluation time;
- direction, entry, stop loss, targets, and invalidation/expiry;
- risk information already authorized by the strategy contract;
- proposal/ticket identity and decision reason codes;
- market-data venue and freshness;
- the label `INFORMATIONAL PROPOSAL — NOT A BROKER ORDER`.

A missing strategy-owned value must remain missing or `BLOCKED`; the ticket layer must
never invent direction, entry, stop, target, risk, or confirmation.

## Delivery sequence

### Stage 1 — Current-strategy trade-ticket operations

Goal: deliver useful tickets now from current frozen strategy behavior, before the
separate strategy-validation program.

1. Preserve the existing EURUSD/GBPUSD `ASIAN_LONDON` and `LONDON_NEWYORK` proposal
   paths and complete Entry Ticket renderer.
2. Produce and archive a cycle result immediately after each configured session,
   rather than relying only on the combined end-of-day FX report.
3. Install restart-safe scheduling and missed-run recovery for both FX cycles.
4. Add deduplicated notification delivery for new READY tickets and operational
   failures; WATCH/NO_TRADE summaries remain available without alert spam.
5. Add USDJPY and XAUUSD only through a new candidate strategy/config version with
   signed pip/tick, spread, range, stop, sizing, and broker-symbol conventions.
6. Keep order submission disabled. The milestone ends at ticket publication.

Acceptance: every configured symbol/cycle produces exactly one archived decision per
eligible day; every READY decision produces exactly one complete informational ticket;
restart does not duplicate decisions or notifications.

### Stage 2 — Two-asset crypto ticket operations

1. Preserve the current scheduled BTCUSDT Bybit decision path.
2. Generalize the BTC-only market-data/report orchestration for ETHUSDT without
   changing the frozen BTC strategy semantics.
3. Freeze the preset evaluation time(s), venue, contract type, and complete-candle
   requirements for both assets.
4. Archive and deliver deduplicated informational tickets; crypto execution remains
   fail-closed and out of scope.

Acceptance: BTCUSDT and ETHUSDT each produce one deterministic, archived decision at
their preset time; READY produces a normalized informational ticket.

### Stage 3 — Large-SMC funnel watch and confirmation alerts

1. Freeze the initial watchlist; retain EURUSD-only authority until expansion is
   explicitly contracted.
2. Use the existing research engine and live-batch ledger as the baseline.
3. Add incremental closed-bar observation, durable funnel-stage transitions, expiry,
   invalidation, and restart recovery.
4. Publish alerts only on material state transitions, especially entry confirmation.
5. Keep `ST_LARGE_SMC_V1` `RESEARCH_ONLY`; an entry-confirmation alert is not proposal,
   demo, or live execution authority.

Acceptance: each watched instrument exposes a current explainable funnel state, and a
new confirmation transition emits exactly one alert.

### Stage 4 — Strategy validation and promotion

Validation is deliberately sequenced after the initial current-strategy ticket
operation is stable. It includes:

- FX forward-shadow evidence by symbol and cycle;
- independent BTC and ETH observation ledgers;
- Large-SMC funnel-transition and confirmation evidence;
- data quality, missed-run, duplicate-ticket, and duplicate-alert measurements;
- outcome/performance analysis without retroactively rewriting historical evidence;
- promotion of candidate strategy versions only after explicit owner review.

Software correctness and ticket delivery do not establish profitability or trading
edge. Until Stage 4 passes, all products remain decision support.

### Stage 5 — Optional execution program

Demo/live execution, Telegram approval-to-broker wiring, and crypto order routing are
not part of the current product milestone. They require separate strategy risk
contracts, authorization, safety validation, and explicit owner direction.

## Immediate implementation backlog

| Priority | Deliverable | Current state | Completion gate |
|---|---|---|---|
| P0 | Per-cycle FX ticket run/archive | Renderer and two-cycle engine exist | exactly-once post-session artifact |
| P0 | Persistent FX scheduling/recovery | CLI is scheduler-ready; no durable multi-cycle deployment confirmed | unattended run and missed-run evidence |
| P0 | Ticket notification transport | local sinks exist; external delivery not operational on `main` | real delivery plus dedup/retry evidence |
| P1 | USDJPY and XAUUSD candidate support | declared in broader contracts, not operational pilot | signed per-symbol conventions and tests |
| P1 | ETHUSDT scheduled ticket | strategy lists ETH; production feed/report is BTC-only | production-data and complete-candle validation |
| P1 | Large-SMC funnel status publication | research engine and batch ledger exist | durable transition model and query/report |
| P1 | Large-SMC confirmation alert | confirmation components exist; no complete operational delivery path | exactly-once research alert |
| P2 | Strategy-validation campaigns | existing FX/BTC campaigns incomplete | Stage 4 evidence gates |
| Deferred | Broker execution | independently gated/disabled | separate owner authorization |

## Authority preservation

- Current frozen strategies may produce tickets only from values they already own.
- Adding instruments or changing behavior requires a new candidate strategy version.
- `NO_TRADE` and fail-closed states are valid products and must never be promoted by
  the ticket or alert layer.
- Large-SMC remains research-only until separately validated and promoted.
- No roadmap item implicitly changes `demo_authorized`, `live_authorized`, or crypto
  execution authority.
