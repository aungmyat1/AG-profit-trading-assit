# AG Stage 1 — Exactly-Once FX Ticket Delivery V1

Status: **WP1/WP3/WP6 CORE IMPLEMENTED AND TESTED (2026-09-08); WP2/WP4/WP5/WP7 NOT
STARTED.** Not yet integrated into the live FX cycle/report orchestration -- see
`docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`.

## Outcome

Turn existing EURUSD/GBPUSD decisions for `ASIAN_LONDON` and `LONDON_NEWYORK` into
durable, externally delivered informational tickets without changing strategy rules or
opening an execution path.

## In scope

- current `ST_ASIAN_SWEEP_5R_V1` decision/proposal output;
- proposal identity as the logical ticket identity;
- immediate per-cycle archive;
- installed Windows scheduler tasks;
- restart, overlap, and missed-run recovery;
- message-only Telegram transport reused from the paused feature branch after review;
- delivery journal, retry, deduplication, and operational failure notification.

## Explicitly out of scope

- signal, entry, stop, target, risk, or session-rule changes;
- USDJPY/XAUUSD, BTC/ETH, or Large-SMC implementation;
- Telegram approval/execution buttons and callbacks;
- MT5 order checks or sends;
- profitability claims or strategy promotion.

## Work packages

### WP1 — Freeze identity and state transitions

Define the canonical key as strategy id/version + cycle + symbol + trading date +
proposal occurrence. Specify `NOT_APPLICABLE`, `READY_TO_DELIVER`, `DELIVERY_PENDING`,
`DELIVERED`, and `DELIVERY_FAILED_RETRYABLE`. A correction keeps the original logical
identity and receives a correction identity.

Tests: two processes produce one logical ticket for the same occurrence; another cycle
or date cannot collide; retry cannot create a new ticket.

### WP2 — Canonical ticket rendering

Wrap the existing renderer without re-deriving strategy fields. Add the informational
label, reason codes, evaluation time, venue/freshness, expiry, and source identities
where already present. Missing required strategy fields fail closed.

Tests: exact provenance, READY-only rendering, no execution imports, stable
serialization and hash.

### WP3 — Per-cycle durable archive

Archive after each completed cycle and before delivery. Preserve append-only correction
behavior. Record WATCH/NO_TRADE/failure outcomes even when no ticket exists.

Tests: idempotent rerun, correction without overwrite, crash after archive and before
delivery, and corrupted-store failure.

### WP4 — Scheduler recovery

Keep the installed tasks; add a bounded catch-up rule and a single-run claim for
overlap. Confirm timezone and closed-candle gates before evaluation.

Tests: duplicate trigger, restart during run, missed checkpoint, weekend/closed market,
premature run, stale data, and successful next-run recovery.

### WP5 — Message-only transport extraction

Audit the Telegram client/formatter for token, chat/user source, payload privacy, log
redaction, timeout behavior, and dependencies. Port the smallest message-only subset.
Do not port approval stores, execution buttons, callback execution, or broker handlers.

Tests: no hardcoded secrets; authorized destination only; mocked success, timeout,
rate limit, malformed response, redacted logs; static execution-boundary scan.

### WP6 — Delivery journal and retry

Persist the ticket before the first network attempt. Give each attempt its own id while
retaining the logical ticket id. On ambiguous timeout, retry the same ticket. Use
bounded backoff and preserve terminal failure evidence.

Tests: timeout-after-send ambiguity, restart, repeated scheduler run, parallel workers,
successful retry, non-retryable failure, and no duplicate logical ticket.

### WP7 — Operational proof

Run focused tests, the affected suite, one non-trading real Telegram test with a
synthetic operational message, then one natural strategy-generated informational
ticket when READY occurs. Do not manufacture a READY strategy result.

Capture source commit, strategy version, scheduler state, archive path, ticket id,
attempt id, Telegram response identity, and proof that execution was unreachable.

## Acceptance checklist

- [x] Strategy output remains unchanged before ticket wrapping. (no strategy file touched; `src/ticket_delivery/` has no strategy-evaluation code)
- [x] One logical ticket exists per natural READY occurrence. (`identity.logical_ticket_id()`, deterministic, tested against collision on every dimension)
- [x] Every cycle decision is archived before delivery. (`archive.archive_cycle_decision()`, all 5 cycle states, reuses `report_archive.write_report()`'s existing idempotent/correction/atomic-write guarantees; archive-before-send enforced by design -- delivery journal has no path that doesn't require an existing archived record's identity)
- [x] Duplicate and overlapping runs are idempotent. (`ensure_ready_to_deliver()` idempotent creation; 10-way concurrent claim proven exactly-one-winner; parallel-different-tickets proven independent)
- [ ] Missed checkpoints recover under a signed catch-up rule. (WP4 -- not started this pass)
- [x] Telegram retries reuse the logical ticket. (`claim_for_delivery()` retry path proven: same `logical_ticket_id`, new `attempt_number`/`delivery_attempt_id`)
- [ ] Secrets/destinations are configuration-only and redacted. (WP5 -- transport not yet ported/audited this pass)
- [x] No path enters execution or MT5 order submission. (static AST guard, `tests/test_ticket_delivery_execution_boundary.py`, 4 tests passing)
- [ ] Real message-only delivery is evidenced. (WP7 -- no live send attempted or claimed)
- [x] No execution authority or lifecycle field changes. (verified: no `strategies/`, `execution/`, `authorization/telegram_gateway.py` file modified this pass)

## Implementation order

```text
WP1 identity
 -> WP2 renderer
 -> WP3 archive
 -> WP4 recovery
 -> WP5 transport audit/port
 -> WP6 delivery journal/retry
 -> WP7 operational proof
```

Stop when the checklist passes. Expansion and validation begin as separate milestones.
