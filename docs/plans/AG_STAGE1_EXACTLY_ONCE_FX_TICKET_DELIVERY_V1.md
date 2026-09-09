# AG Stage 1 — Exactly-Once FX Ticket Delivery V1

Status (2026-09-08): **WP1/WP2/WP3/WP5 COMPLETE. WP4 (scheduler call-site integration)
IS WIRED INTO THE ACTUAL SCHEDULED ENTRY POINT AND `ARCHIVE_ONLY` IS NOW ACTIVE.**

Policy status: `FX_MAX_CATCH_UP_AGE`/`DELIVERY_MAX_ATTEMPTS`/
`DELIVERY_RETRY_BASE_DELAY`/`DELIVERY_RETRY_MAX_DELAY` are **OWNER_APPROVED
2026-09-08** (60 min / 3 / 30s / 300s -- see
`docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md`'s approval
addendum) and are now **WIRED**: `config/ticket_delivery.yaml`'s `policy:` block is
validated by `scheduler_integration.py::_parse_policy()` and constructs a real
`CatchUpPolicy`/`RetryPolicy` used by the scheduler call site. `RetryPolicy` is wired
but not yet exercised by any live code path (`MESSAGE_DELIVERY` remains inert).

Activation status: `config/ticket_delivery.yaml`'s shipped `mode` is now
**`ARCHIVE_ONLY` (ACTIVATED 2026-09-08, owner-authorized)** --
`scripts/run_post_asian_pilot.py::_run_once()` calls
`ticket_delivery.scheduler_integration.process_cycle_result()` after every `--once`
cycle (the same function the real `AG_FX_ASIAN_LONDON_SHADOW` /
`AG_FX_LONDON_NEWYORK_SHADOW` scheduled tasks invoke). Real scheduled evidence exists:
the live task fired at 2026-09-08T08:30:20Z, producing a genuine natural GBPUSD READY
decision (`ready_at` 07:15:00Z) that the newly-wired catch-up gate correctly declined to
register as a deliverable ticket (75 minutes late, past the signed 60-minute bound,
`reason_code=OUTSIDE_CATCH_UP_WINDOW`) while still archiving the decision -- see
`docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`'s Addendum 5 for
the full evidence trail. One-line rollback to `DISABLED` remains available and untested
by neither reading nor requiring the `policy:` block.

`MESSAGE_DELIVERY` mode remains **NOT AUTHORIZED** -- `config/ticket_delivery.yaml`'s
shipped `mode` is `ARCHIVE_ONLY` and the Telegram destination allow-list is empty; the
scheduler call site only constructs a real delivery closure inside the
`MODE_MESSAGE_DELIVERY` branch (`scheduler_integration.py::_build_message_delivery_closure()`),
so no owner action in config alone can reach a network call.

**Correction (2026-09-09, WP7 readiness/reconciliation pass):** the line below
("WP7 NOT STARTED") is **STALE** and superseded by this correction; it is left in
place unmodified as the historical record of that 2026-09-08 pass. WP7 runtime is now
**RUNTIME_IMPLEMENTED, NOT ACTIVATED**: `deliver_informational_ticket_with_retry()`
(in-process wait-and-retry, Design A per the WP7 preflight packet's open question,
30s/60s backoff matching the signed 3-attempt/30s/300s policy), the append-only
`AttemptJournal`, and the conditional `MESSAGE_DELIVERY` closure construction are all
implemented and covered by the focused WP7 test suite (`tests/test_ticket_delivery_wp7_*`
and related `tests/test_ticket_delivery_*` files; 218/219 passing as of this pass, one
pre-existing load-dependent concurrency-outcome-reporting flake unrelated to the
execution boundary, mode gating, or dedup guarantees -- see
`docs/status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md`). No real or
synthetic Telegram send has ever been performed for Stage 1 ticket delivery; a hardened
owner runbook for the future synthetic proof exists at
`docs/runbooks/WP7_OWNER_SYNTHETIC_PROOF_RUNBOOK.md`. Activation to `MESSAGE_DELIVERY`,
population of the destination allow-list, and the synthetic/natural proof sends all
remain separate, explicit owner decisions -- none of them occurred during this pass.

**WP7 NOT STARTED** -- a real GBPUSD READY signal was observed live this pass (see
above), but it was correctly catch-up-rejected before reaching any delivery/render
step, so this is NOT the "natural READY ticket delivered" evidence WP7 requires; no
real Telegram send has ever been attempted. See
`docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`'s WP4/WP4-callsite/policy-activation addenda.

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
- [x] Every cycle decision is archived before delivery, AT THE ACTUAL SCHEDULED CALL SITE (not only the orchestration layer in isolation). `scripts/run_post_asian_pilot.py::_run_once()` now calls `ticket_delivery.scheduler_integration.process_cycle_result()`; proven idempotent under repeated and simultaneous CLI invocation via `tests/test_run_post_asian_pilot_ticket_delivery_wiring.py`. Shipped config is now `mode: ARCHIVE_ONLY` (owner-authorized, activated 2026-09-08), and real scheduled evidence (Addendum 5) confirms it archives live cycle output.
- [x] Missed checkpoints are gated by a signed catch-up rule at the actual scheduled call site. `ticket_delivery.policy.CatchUpPolicy` is now constructed from the OWNER_APPROVED `fx_max_catch_up_age_minutes: 60` value (`scheduler_integration.py::_parse_policy()`) and wired into `fx_cycle_integration.process_pair_result()`'s READY path (premature/exact-boundary/within-bound/outside-bound/missing-ready_at all covered by new tests). Proven with REAL data: a live scheduled run's genuine GBPUSD READY signal (75 minutes stale) was correctly rejected (`CATCH_UP_REJECTED`/`OUTSIDE_CATCH_UP_WINDOW`), archived but never registered as a ticket -- see Addendum 5. "Recovery" in the sense of an on-time re-evaluation succeeding is proven; a rejected-then-later-recovered catch-up scenario has not yet occurred naturally (would need a second READY within a later 60-minute window for the same occurrence, which this pass did not observe).
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
