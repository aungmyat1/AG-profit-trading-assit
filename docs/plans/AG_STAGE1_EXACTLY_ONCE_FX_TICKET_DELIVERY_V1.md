# AG Stage 1 — Exactly-Once FX Ticket Delivery V1

Status (2026-09-08): **WP1/WP2/WP3/WP5 COMPLETE. WP4 (scheduler call-site integration)
IS NOW WIRED INTO THE ACTUAL SCHEDULED ENTRY POINT** --
`scripts/run_post_asian_pilot.py::_run_once()` calls
`ticket_delivery.scheduler_integration.process_cycle_result()` after every `--once`
cycle (the same function the real `AG_FX_ASIAN_LONDON_SHADOW` /
`AG_FX_LONDON_NEWYORK_SHADOW` scheduled tasks invoke via
`scripts/scheduled/run_asian_london_once.bat` / `run_london_newyork_once.bat`), under an
explicit `DISABLED` / `ARCHIVE_ONLY` / `MESSAGE_DELIVERY` mode contract in
`config/ticket_delivery.yaml`. **The shipped repository default remains `DISABLED`** --
this task implemented and proved `ARCHIVE_ONLY` end-to-end through the real CLI
function (archive-before-send, repeated/simultaneous-invocation idempotency, archive
failure, zero network calls) but did NOT flip the shipped config to `ARCHIVE_ONLY`;
that activation remains an explicit, separate operator decision (edit one line in
`config/ticket_delivery.yaml`, instantly reversible). See
`docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md`.

`MESSAGE_DELIVERY` mode is currently identical to `ARCHIVE_ONLY` (both pass
`deliver=None`, a structural, not merely config-gated, zero-network guarantee) --
setting it in config has no additional effect this pass; real Telegram construction is
WP7, separately gated on signed catch-up/retry values.

**WP4.4 (missed-checkpoint catch-up) and the WP6 bounded-retry completion remain
MECHANISM-COMPLETE, OPERATIONALLY UNSIGNED** -- no production catch-up duration or
retry bound exists anywhere in this repository; see the decision packet above for the
proposed values awaiting owner sign-off. **WP7 NOT STARTED** (no real Telegram send, no
natural READY capture attempted). See
`docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`'s WP4 addenda.

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

**Call-site wiring (2026-09-08):** `src/ticket_delivery/scheduler_integration.py`
provides `process_cycle_result()`, the single call site
`scripts/run_post_asian_pilot.py::_process_ticket_delivery()` invokes from
`_run_once()` -- the exact function body the two live scheduled tasks execute every 15
minutes. Proven via `tests/test_run_post_asian_pilot_ticket_delivery_wiring.py` (loads
the real script module, no live MT5 needed) and
`tests/test_ticket_delivery_scheduler_integration.py`: disabled-by-default is silent
and touches no filesystem; `ARCHIVE_ONLY` archives every cycle state and makes zero
network calls; repeated and two-simultaneous invocations converge on exactly one
archive/logical-ticket; an archive failure surfaces as a nonzero scheduler exit code
without crashing the strategy report; any unexpected error in ticket-delivery
processing is caught and degrades to a no-op, never propagating into the cycle report
that already printed. Missed-checkpoint catch-up itself remains unsigned (see below) --
this pass proves the wiring and archive-only idempotency, not catch-up recovery.

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
- [x] Every cycle decision is archived before delivery, AT THE ORCHESTRATION LAYER (not only the primitive). `ticket_delivery.fx_cycle_integration.process_pair_result()` proven to archive-before-render-before-claim-before-transport for all 5 cycle states, with a simulated archive failure producing zero transport calls.
- [x] Every cycle decision is archived before delivery, AT THE ACTUAL SCHEDULED CALL SITE (not only the orchestration layer in isolation). `scripts/run_post_asian_pilot.py::_run_once()` now calls `ticket_delivery.scheduler_integration.process_cycle_result()`; proven idempotent under repeated and simultaneous CLI invocation via `tests/test_run_post_asian_pilot_ticket_delivery_wiring.py`. Shipped config remains `mode: DISABLED`; activating `ARCHIVE_ONLY` in the repository is a distinct, still-pending operator decision.
- [ ] Missed checkpoints recover under a signed catch-up rule. `ticket_delivery.policy.CatchUpPolicy` mechanism implemented and tested (premature/exact-boundary/within-bound/outside-bound/unconfigured all covered), but `max_catch_up_age` is UNSIGNED -- no production value exists, so operational catch-up remains disabled by construction (the unconfigured case fails closed).
- [x] Telegram retries reuse the logical ticket. (proven twice: at the store layer, and end-to-end in `test_successful_retry_after_retryable_failure_reuses_logical_ticket` against a mocked Telegram failure-then-success sequence)
- [x] Secrets/destinations are configuration-only and redacted. (`TelegramDestinationConfig.from_values` takes no defaults, requires an explicit authorized-chat-id allow-list; `_redact()` strips the bot token from every piece of persisted failure evidence -- proven by 2 tests reading the actual on-disk journal file)
- [x] No path enters execution or MT5 order submission. (static AST guard, `tests/test_ticket_delivery_execution_boundary.py`, now 4 tests covering renderer.py/telegram_adapter.py too, and excluding `notifications.trade_ticket_formatter` -- the approval/keyboard-coupled formatter -- as an additionally forbidden import)
- [ ] Real message-only delivery is evidenced. (WP7 -- no live send attempted or claimed; all Telegram tests use an injected fake HTTP session)
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
