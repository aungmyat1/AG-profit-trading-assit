# AG Stage 1 WP7 — Message-Delivery Preflight and Authorization Packet V1

Dated 2026-09-08. **This document does not authorize `MESSAGE_DELIVERY`, a real or
synthetic Telegram send, or any broker/execution action.** It exists so a separately
authorized WP7 task can execute without rediscovering the architecture. Written by
`AG_STAGE1_GOVERNANCE_RECONCILIATION_AND_WP7_PREFLIGHT_V1`, which performed the
verification but implemented none of the activation described here.

## WP7 objective

Prove Stage 1's exactly-once FX ticket-delivery infrastructure can deliver one real,
explicitly-authorized informational message to Telegram — first a synthetic
operational test message, then (separately, later) one naturally-occurring READY
ticket — without ever becoming reachable from broker execution.

## Current state (verified, not assumed)

```text
config/ticket_delivery.yaml: mode = ARCHIVE_ONLY (owner-authorized 2026-09-08)
MESSAGE_DELIVERY: inert (deliver=None unconditionally, structural)
Signed policy: fx_max_catch_up_age_minutes=60, delivery_max_attempts=3,
               delivery_retry_base_delay_seconds=30, delivery_retry_max_delay_seconds=300
RetryPolicy: instantiated from signed config, NOT YET CONSUMED anywhere (dead config)
CatchUpPolicy: instantiated AND wired into fx_cycle_integration.process_pair_result()
Execution boundary: zero broker/execution imports anywhere in src/ticket_delivery/
                     (AST-verified, tests/test_ticket_delivery_execution_boundary.py)
```

## Open architecture question WP7 must resolve first

**Where will retries actually be scheduled?** `RetryPolicy` is validated and
constructed from the signed config but is never consumed by any runtime code path.
`telegram_adapter.deliver_informational_ticket()` makes exactly one send attempt per
call; a `RETRYABLE` classification only flips persisted state
(`mark_failed_retryable()`, releasing the claim lock) — nothing re-invokes delivery
afterward. The only existing re-trigger mechanism is the next scheduled FX cycle tick
(~15 minutes), which does not match the signed 30s/60s retry cadence.

WP7 must explicitly choose one of:

- **(A) In-process wait-and-retry loop** inside a single scheduled invocation: after a
  retryable failure, sleep the policy's `next_delay()` seconds and re-attempt, up to
  `delivery_max_attempts`. A full 3-attempt cycle (30s + 60s waits) adds at most ~90
  seconds to one `--once` invocation — well inside the 15-minute scheduler window and
  `MultipleInstances: IgnoreNew` overlap guard. This matches the signed policy exactly
  as approved.
- **(B) Coarser scheduler-tick-driven retry**: treat "the next scheduled tick's natural
  re-evaluation" as the retry mechanism. Simpler to implement (no in-process sleep),
  but the effective retry cadence becomes "up to 15 minutes," not 30s/60s — this is a
  real deviation from the approved contract and would need its own explicit
  re-approval or documented exception before activation, not a silent substitution.

This packet does not choose between them — that decision belongs to the WP7 task
itself, made explicit and recorded, not inferred.

## Exact destination identity and credential source

- Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — the existing repository
  convention (already used by `src/authorization/config.py::TelegramGatewayConfig.from_env()`
  for the separate, forbidden-import approval-gateway path). Reuse the same names for
  consistency; do NOT reuse `TELEGRAM_ALLOWED_USER_IDS` (a different concept — Telegram
  user IDs allowed to approve a trade, not a destination allow-list).
- `ticket_delivery.telegram_adapter.TelegramDestinationConfig` has NO `from_env()`
  today — WP7 must add a small, additive wrapper (or read the env vars directly in
  `scheduler_integration.py` before constructing the config). No defaults; missing or
  unauthorized values must fail closed exactly as `from_values()` already does.
- The destination allow-list (`authorized_chat_ids`) must be explicitly configured
  (e.g., a new `authorized_chat_ids` field under `config/ticket_delivery.yaml`'s
  `policy:` block or a sibling block) — never inferred from `TELEGRAM_CHAT_ID` alone
  (that would make the "authorization" check tautological).

## MESSAGE_DELIVERY config change required

`config/ticket_delivery.yaml`: `mode: ARCHIVE_ONLY` → `mode: MESSAGE_DELIVERY`, plus
wiring `scheduler_integration.process_cycle_result()` to actually construct a `deliver`
closure over `telegram_adapter.deliver_informational_ticket()` when (and only when)
`mode == MODE_MESSAGE_DELIVERY` — today both archiving modes deliberately share
`deliver=None`; WP7 must split that branch, not remove the `ARCHIVE_ONLY` guarantee.

## Rollback change

Unchanged from today: `mode: DISABLED` (or reverting to `mode: ARCHIVE_ONLY`) remains
a one-line, unconditional rollback. WP7 must not weaken this — the `policy:` block
must remain unread/unrequired whenever `mode: DISABLED`.

## Synthetic ticket identity and message contract

```text
Ticket: SYNTHETIC-WP7-001
Environment: TEST
Trading authority: NONE
Broker execution: DISABLED

AG DELIVERY SYSTEM TEST

Environment: TEST
Ticket: SYNTHETIC-WP7-001
Trading authority: NONE
Broker execution: DISABLED

This message verifies Stage-1 external
ticket-delivery infrastructure.
```

This message must be sendable through the SAME `deliver_informational_ticket()` /
`TicketDeliveryStore` path a real ticket uses (no parallel, untested send path), with a
`logical_ticket_id` that is obviously synthetic and cannot collide with any real
`ST_ASIAN_SWEEP_5R_V1|...` identity (the literal `SYNTHETIC-WP7-001` string is not
`|`-separated in the real identity shape and would fail `identity.py`'s validation if
run through the real constructor — WP7 should either bypass `logical_ticket_id()` for
this one synthetic case with an explicit, clearly-labeled literal, or mint a fake but
correctly-shaped identity, e.g. `SYNTHETIC_TEST|1.0.0|TESTPAIR|SYNTHETIC_CYCLE|2026-09-08`).

## Expected provider response fields

Telegram's `sendMessage` response (already parsed by
`notifications.telegram_client.TelegramClient.send_message()`): `ok: true`,
`result.message_id` (persisted verbatim as `DeliveryRecord.provider_response_id`,
already proven by existing tests against a mocked session).

## Retry behavior (once Question above is resolved)

Per the signed contract: attempt 1 (initial) → on retryable failure, 30s delay →
attempt 2 → on retryable failure, 60s delay → attempt 3 → exhausted
(`DELIVERY_EXHAUSTED`/`RETRY_MAX_ATTEMPTS_EXHAUSTED`), no attempt 4. Terminal and
ambiguous classifications are never retried regardless of remaining attempts (existing,
unchanged `RetryPolicy` behavior).

## Failure behavior

- `DELIVERY_FAILED_TERMINAL` — a non-retryable provider rejection (e.g. destination
  blocked the bot). Never retried, never auto-resolved.
- `DELIVERY_AMBIGUOUS` — a timeout/connection failure/malformed response, where
  whether Telegram actually received the message cannot be determined. Never
  auto-resent (existing, tested guarantee) — requires explicit
  `resolve_ambiguous_outcome()` reconciliation.
- `CATCH_UP_REJECTED` — the freshness gate rejected this READY occurrence before
  delivery was ever attempted (Addendum 5's real evidence). Not a delivery failure.

## Restart behavior

Already proven at the primitive layer (no new WP7-specific logic required): a fresh
`TicketDeliveryStore` against the same `state_dir` after a restart sees exactly the
persisted state; a `DELIVERY_CLAIMED` record from a crashed process cannot be
reclaimed while its lock file exists (deterministic reconciliation path already
exists — see Addendum 1/2's restart tests).

## Evidence files WP7 should produce

- One evidence export via `scripts/ticket_delivery_evidence.py export` capturing the
  synthetic ticket's archive + delivery-journal state, immediately before and after
  the synthetic send.
- A dated status document (or an addendum to this one) recording: exact synthetic
  message sent, provider `message_id`, `logical_ticket_id`, final `DeliveryRecord`
  state, and the retry-scheduling design choice actually implemented (A or B above).

## Zero-broker-execution proof required

`tests/test_ticket_delivery_execution_boundary.py` must still pass after WP7's changes
(directory-wide AST scan of `src/ticket_delivery/`, zero forbidden imports/calls) —
this is a regression gate, not new tooling to build.

## Commands to execute (once separately authorized)

```bash
# 1. Set the signed MESSAGE_DELIVERY config and destination allow-list.
# 2. Run the focused ticket_delivery + Telegram-adapter test suites.
# 3. Send exactly one synthetic message via the real deliver_informational_ticket() path
#    with a synthetic, non-colliding logical_ticket_id.
# 4. Export evidence: python scripts/ticket_delivery_evidence.py export
# 5. Verify: python scripts/ticket_delivery_evidence.py verify-restore <export_dir>
```

## Commands explicitly prohibited (this packet, and until WP7 is separately authorized)

```text
Any change to config/ticket_delivery.yaml's mode away from ARCHIVE_ONLY/DISABLED.
Any real send to a Telegram chat/bot outside this packet's own explicit synthetic proof.
Any MT5 order_check/order_send, Bybit/Binance/MEXC order endpoint call.
Any change to strategy YAML, strategy registry, or Demo/live authorization.
```

## Success criteria (from the roadmap's own WP7 acceptance list)

```text
1. one explicitly authorized synthetic operational message
2. provider accepts it
3. provider response/message identity persisted
4. one logical delivery record reaches DELIVERED
5. duplicate invocation does not create a duplicate logical delivery
6. retry path operates using the signed policy (30s/60s/300s cap, 3 total attempts)
7. restart recovery operates correctly
8. DISABLED rollback remains immediate
9. broker execution remains unreachable
10. secrets do not appear in repository/log/evidence
```

Only after that synthetic proof succeeds may a separate, later step observe one
natural READY occurrence (age ≤ 60 minutes at delivery time) reach exactly one
completed delivery with zero broker execution. Only then may Stage 1 be considered for
closure — not by this packet, and not by the synthetic proof alone.

## Rollback criteria

Revert `mode` to `ARCHIVE_ONLY` (or `DISABLED`) immediately if: any delivery attempt
reaches a broker/execution path (should be structurally impossible — treat as a
stop-the-line defect), any secret appears in a log/evidence file, or the retry design
chosen (A or B) produces unexpected duplicate sends.
