# VD V1 virtual exchange contract

`VirtualExchange` consumes admitted proposals, clock events, execution observations, an immutable `ExecutionProfile`, and account pretrade limits. It emits order transitions and fills; `VirtualAccount` owns cash, exposure, and positions. All models are pure, versioned, and hash-bound. No exchange component imports or calls MT5, `execution/`, `order_check`, or `order_send`.

| Model | Required input and output |
|---|---|
| `OrderValidator` | Proposal lineage, signed SSC decision, symbol metadata, account snapshot, admissible time and exposure → accepted order or stable rejection code. |
| `LatencyModel` | Submission time, profile, deterministic seed/ordinal → earliest eligibility time; never before submission. |
| `SpreadModel` | Source bid/ask or frozen spread assumption and quality → bid/ask quote or unavailable. |
| `SlippageModel` | Side, quantity, quote, observation, profile/seed → signed adverse or explicitly modeled improvement; record amount and source. |
| `FeeModel` | Venue/instrument, notional, fill/close → currency fee, timing, and conversion provenance. |
| `FillModel` | Eligible order, post-cutoff observation, quote, liquidity rule → fill/reject/partial fill with observation ID and quality. |

Allowed order states: `CREATED → VALIDATED → QUEUED → PARTIALLY_FILLED → FILLED`, with `REJECTED`, `CANCELLED`, `EXPIRED`, and `UNRESOLVED_END_OF_DATA` terminal branches. Every transition has time, reason, prior state hash, and immutable event ID. Rejections are ledger events and never silently converted into `NO_TRADE`. A duplicate proposal/order ID is idempotent only when payload hash matches; mismatch is a hard error. Deterministic tie breaks and partial-fill policy belong to the frozen profile.

Market entry from a close is eligible no earlier than the next distinct execution interval after latency. Limit/stop triggers use executable side prices (ask for buy, bid for sell), source quality, and strict interval ordering. OHLC M1 cannot establish tick path, queue position, exact latency fill, or exact intrabar sequencing. If the profile cannot price an eligible order under its declared quality, reject or leave unresolved with a reason. Same-bar or future-informed execution is forbidden even when it would improve outcomes. Existing SVOS next-bar-open and friction behavior may be adapted only after parity tests establish matching semantics; it is not automatically an execution authority.

Execution quality is independent of MI quality. `REAL_TICK` requires actual timestamped bid/ask ticks; `BID_ASK_M1` requires sourced synchronized bid and ask M1 bars; `OHLC_M1` requires sourced trade/mid OHLC plus an explicitly frozen spread model; `SYNTHETIC_INTRABAR` is a modeled path and cannot be labeled observed. Admit only classes supported by the selected dataset manifest. This baseline establishes an M1 OHLC source, not a verified tick or bid/ask source, so the initial admissible ceiling is `OHLC_M1` if metadata and spread assumptions pass; otherwise execution is unavailable.

If both SL and TP are reachable inside one M1 bar and no admissible sub-bar sequence resolves order, record `INTRABAR_AMBIGUOUS`. A preregistered conservative profile may resolve stop first and label the outcome `MODELED_WORST_CASE`; an ambiguity-rejection profile leaves the outcome unresolved. Never silently choose TP first or call the inferred path a tick observation. Gap fills, simultaneous entry/exit, and session-close exits follow the same source-quality and predeclared ordering rules.
