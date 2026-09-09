# AG Stage 1 WP7 — Readiness, Reconciliation & Activation Packet V1 (Status)

Dated 2026-09-09. **This document does not authorize `MESSAGE_DELIVERY`, a destination
allow-list entry, a real or synthetic Telegram send, or any broker/execution action.**
It is a read-only verification and documentation-reconciliation pass, plus a packet
preparing (not executing) the next owner activation decisions.

## Repository preflight

```text
branch = main
head_before = 934ce15
head_after = <see COMMITS at the end of this document -- two local commits this pass,
              neither pushed>
origin_main = 934ce15 (unchanged; nothing has been pushed)
ahead = 2
behind = 0
working_tree_before = CLEAN
working_tree_after = CLEAN
diff_check = PASS
```

## Status reconciliation

- Stage 0: PARTIAL per `AG_CURRENT_ROADMAP_PHASE_1_STAGE_0_SAFETY_V1` (2026-09-08) —
  two real defects fixed (drawdown baseline, docstring/ordering), one behavior
  confirmed already correct (broker-reconciliation fail-closed).
- Canonical proposal contract: frozen (`e5f9ed3`), M1A, strategy-neutral. Not yet
  reflected in `PROJECT_STATUS.md`'s rolling summary — flagged, not backfilled this
  pass (out of WP7 scope).
- Stage 1 WP1–WP6: COMPLETE and `ARCHIVE_ONLY` ACTIVATED (owner-authorized 2026-09-08),
  per `AG_STAGE1_ARCHIVE_ONLY_ACTIVATION_V1`. Confirmed unchanged this pass.
- Stage 1 WP7: **RUNTIME_IMPLEMENTED, NOT ACTIVATED.** The plan doc's top banner
  ("WP7 NOT STARTED") and the WP7 preflight packet ("`RetryPolicy` NOT YET CONSUMED —
  dead config") were both stale relative to code landed after they were written
  (commits through `d1b14e8`). Corrected in place this pass (see FILES_CHANGED); the
  original stale text is preserved as historical record with a dated correction added
  above/below it, not deleted, per `docs/status/LIVE_STATUS_MAINTENANCE.md`.
- Demo execution: confirmed deferred in every document reviewed (plan doc, preflight
  packet, `docs/runbooks/WP7_OWNER_SYNTHETIC_PROOF_RUNBOOK.md`). Nothing in this pass
  changed that.

## WP7 implementation (verified by direct code inspection, not by trusting docs)

| Item | Status | Evidence |
|---|---|---|
| `message_delivery_closure` | DONE | `scheduler_integration.py::_build_message_delivery_closure()`, called only inside the `MODE_MESSAGE_DELIVERY` branch; every other path sets `deliver = None` (structural, not a runtime branch). |
| `credential_loading` | DONE | `TelegramDestinationConfig.from_env()` reads `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` by convention only; `authorized_chat_ids` is always caller-supplied from signed config, never inferred from the env var itself. |
| `destination_allow_list` | DONE (mechanism); EMPTY (data) | `config/ticket_delivery.yaml` `telegram_destination.authorized_chat_ids: []`. |
| `archive_before_delivery` | DONE | `fx_cycle_integration.py::process_pair_result()` archives before any render/register/claim/deliver call for every cycle state; an archive failure returns before any further call. |
| `logical_ticket_deduplication` | DONE | `identity.py::logical_ticket_id()` deterministic; `delivery_store.ensure_ready_to_deliver()` idempotent; survives restart (disk-backed `JsonKeyValueStore`, verified against the real on-disk journal). |
| `attempt_identity` | DONE | `identity.py::delivery_attempt_id()`, regenerated on every `claim_for_delivery()` call, distinct from the logical id. |
| `retry_policy` | DONE | `RetryPolicy` read from `config/ticket_delivery.yaml`'s `policy:` block by exact field name (`delivery_max_attempts`, `delivery_retry_base_delay_seconds`, `delivery_retry_max_delay_seconds`); values 3/30/300, matching the signed contract. |
| `retry_schedule` | DONE | `deliver_informational_ticket_with_retry()`, in-process wait-and-retry (Design A), injectable `sleeper` (no test sleeps for real). |
| `ambiguous_timeout_handling` | DONE, fail-safe | `mark_ambiguous()` does not release the claim lock — no automatic retry can re-claim; only an explicit `resolve_ambiguous_outcome()` can move it forward. |
| `terminal_failure_handling` | DONE | `STATE_DELIVERY_FAILED_TERMINAL` distinct from `STATE_DELIVERY_FAILED_RETRYABLE`/`STATE_DELIVERY_AMBIGUOUS`/`STATE_DELIVERED`, separate store methods. |
| `restart_recovery` | DONE | Store is disk-backed, not in-memory; O_EXCL claim lock is a real file, re-checked under lock on every claim attempt. |
| `secret_redaction` | DONE | `_redact()` strips the bot token from every piece of persisted/returned evidence; a prior repr-exposure defect was already found and fixed in an earlier commit (`3161287`), verified still fixed. |
| `rollback_to_archive_only` | DONE | `mode: DISABLED`/`ARCHIVE_ONLY` are the only paths that skip policy-block parsing entirely; flipping `mode` back requires no other change (see ROLLBACK below). |
| `execution_isolation` | DONE | Zero execution/broker/MT5/ExecutionApproval/authorize-demo/Telegram-callback imports anywhere in `src/ticket_delivery/` or `scripts/run_post_asian_pilot.py` (grep-verified this pass; matches the existing AST-based `test_ticket_delivery_execution_boundary.py`). |
| `synthetic_proof_harness` | DONE (design); NOT_EXECUTED | `docs/runbooks/WP7_OWNER_SYNTHETIC_PROOF_RUNBOOK.md` exists, hardened across 3 revisions; the credential-using helper is deliberately kept out of this tracked repository. No synthetic send has occurred (no `SYNTHETIC_TEST` record in the live journal, no `attempt_journal.jsonl` file at all). |
| `natural_ready_proof` | NOT_EXECUTED | Real scheduled runs have produced real WATCH/NO_TRADE archive records; no real READY ticket has yet reached the delivery/render step (the one real GBPUSD READY signal observed on 2026-09-08 was correctly catch-up-rejected before delivery). |

## Execution firewall

```text
execution_imports = UNREACHABLE (no matches in src/ticket_delivery/ or scripts/run_post_asian_pilot.py)
authorization_imports = UNREACHABLE
broker_gateway_reachable = NO
mt5_gateway_reachable = NO
approval_callbacks_reachable = NO
order_submission_reachable = NO
```

## Exactly-once semantics

Logical ticket identity (survives retries/restarts) and delivery-attempt identity (one
per claim) are distinct by construction (`identity.py`). Archive happens before any
delivery attempt. Deduplication is disk-backed and survives restart. An ambiguous
outcome is fail-safe (claim lock held, never auto-retried). Terminal failure and
success are distinct persisted states. All confirmed by direct code reading, not
solely by trusting the existing test suite.

## Focused test run

```text
command: python -m pytest -q tests/test_ticket_delivery_wp7_retry_and_journal.py
  tests/test_ticket_delivery_wp7_scheduler_message_delivery.py
  tests/test_ticket_delivery_execution_boundary.py
  tests/test_ticket_delivery_scheduler_integration.py
  tests/test_run_post_asian_pilot_ticket_delivery_wiring.py
  tests/test_ticket_delivery_telegram_adapter.py
  tests/test_ticket_delivery_identity_and_archive.py
  tests/test_ticket_delivery_fx_cycle_integration.py
  tests/test_ticket_delivery_fx_cycle_overlap.py
  tests/test_ticket_delivery_concurrency_and_restart.py
  tests/test_ticket_delivery_evidence_export.py
  tests/test_ticket_delivery_policy.py
  tests/test_ticket_delivery_renderer.py
result (initial combined run, before the fix below): 218 passed, 1 failed
result (failing test isolated, reran 3x, before the fix): 3 passed, 0 failed
result (combined run, AFTER the fix below, x3 consecutive): 219 passed, 0 failed / 219 passed, 0 failed / 219 passed, 0 failed
```

### Root cause and fix (resolved this pass)

The single failure was `test_ten_concurrent_invocations_same_pair_exactly_one_delivery`
(`tests/test_ticket_delivery_fx_cycle_overlap.py`), caused by an unfrozen, ambiguous
meaning of `PairOutcome.delivery_state`/`DeliveryOutcome.final_state`: it was being
used simultaneously to mean two different things depending on caller — "the durable
ticket's current state" (what the sequential idempotency test in
`tests/test_ticket_delivery_wp7_scheduler_message_delivery.py` deliberately relies on)
and "what this invocation itself just did" (what the concurrency test needed). Under
contention, more than one of 10 concurrent callers could legitimately observe
`final_state == "DELIVERED"` (the durable state, correct) while the test's assertion
implicitly required it to mean "I sent it" (also seemingly reasonable, but a different
question).

**Fix — meaning frozen, per explicit owner direction:**

- `DeliveryOutcome.final_state` / `PairOutcome.delivery_state` = **the durable ticket
  state, regardless of caller ownership.** Any caller, winner or loser, sees the
  ticket's real current state (`DELIVERED`, `DELIVERY_CLAIMED` mid-flight,
  `DELIVERY_FAILED_TERMINAL`, etc.). This preserves the sequential idempotency test's
  existing, correct guarantee unchanged.
- A new, separate field answers caller-ownership: **`delivery_performed_by_this_invocation:
  bool`** on both `DeliveryOutcome` (`src/ticket_delivery/telegram_adapter.py`) and
  `PairOutcome` (`src/ticket_delivery/fx_cycle_integration.py`), plumbed through to the
  scheduler's per-pair output dict (`scheduler_integration.py`). It is `True` **only**
  when this specific invocation held the claim lock and Telegram confirmed the send
  (the `mark_delivered()` branch) — `False` in every other case: lost claim race,
  already-resolved ticket, ambiguous/retryable/terminal-failed outcome. This field, not
  `delivery_state`, is what a caller must check to count "how many callers actually
  performed a real transport call."
- `tests/test_ticket_delivery_fx_cycle_overlap.py`'s concurrency test now asserts
  `len([o for o in outcomes if o.delivery_performed_by_this_invocation]) == 1` instead
  of counting `delivery_state == "DELIVERED"` occurrences, and no longer asserts a
  specific `delivery_state` value per losing caller (a loser can correctly observe
  either the terminal `"DELIVERED"` or the transient `"DELIVERY_CLAIMED"` depending on
  scheduling — both are correct, non-duplicate outcomes; only the transport-call count
  and record count need to be exactly one, and both are asserted, deterministically).
- The sequential idempotency test
  (`test_second_identical_invocation_is_idempotent_zero_provider_calls`) was not
  changed and continues to pass unmodified — its `delivery_state == "DELIVERED"`
  assertion on a repeat call is exactly the "durable state" semantics this fix froze.

Verified: the full 219-test focused suite passes in 3 consecutive combined runs (see
above) — the flake is resolved, not merely hidden by a relaxed assertion (the actual
invariant, `session.send_count == 1`, is still checked and still holds every run).

```text
git diff --check: PASS
secrets in diff: ZERO
real Telegram sends this pass: ZERO
broker calls this pass: ZERO
MT5 orders this pass: ZERO
```

## Delivery authority (current, unchanged by this pass)

```text
CURRENT_MODE = ARCHIVE_ONLY
MESSAGE_DELIVERY_RUNTIME = READY
DESTINATION_ALLOW_LIST = EMPTY
REAL_SYNTHETIC_SEND = NOT_PERFORMED
NATURAL_READY_DELIVERY = NOT_PERFORMED
BROKER_CALLS = ZERO
MT5_ORDERS = ZERO
EXECUTION_AUTHORITY = NONE
```

## Owner decisions required (separate, in order)

1. **Authorize one specific Telegram destination** for Stage 1 informational ticket
   delivery (populate `config/ticket_delivery.yaml`'s `telegram_destination.authorized_chat_ids`).
   The chat id itself is not printed in this document.
2. **Authorize `ARCHIVE_ONLY` → `MESSAGE_DELIVERY`** for the Stage 1 ticket-delivery
   system only. Does not alter trading execution authority.
3. **Authorize exactly one synthetic operational Telegram ticket-delivery proof**, run
   through `docs/runbooks/WP7_OWNER_SYNTHETIC_PROOF_RUNBOOK.md`. Broker calls must
   remain zero.
4. **After the synthetic proof passes**, authorize waiting for exactly one natural
   strategy-generated READY event and delivering its informational ticket. The event
   must not be manufactured.
5. **After the natural READY proof**, return Stage 1 evidence for owner review before
   any consideration of Stage 2 or a Demo program.

## Future activation hard guards

A future synthetic send may occur only if: WP7 runtime = READY (confirmed this pass);
tests = PASS (confirmed this pass, 219/219, no known flake — see the fix above);
destination allow-list = explicitly owner-authorized; `MESSAGE_DELIVERY` = explicitly
owner-authorized; execution firewall = PASS (confirmed this pass); broker/MT5 calls =
ZERO; secrets exposed = ZERO; rollback path = VERIFIED (below).

A future natural-READY send may occur only if: the synthetic proof already passed; the
same execution firewall remains intact; the READY event comes from actual strategy
runtime, never manufactured; the ticket is archived before delivery (already enforced
structurally); exactly-once guards remain active.

## Rollback plan (verified, not executed)

Setting `config/ticket_delivery.yaml`'s `mode` back to `ARCHIVE_ONLY` (or `DISABLED`)
is a one-line config change. `scheduler_integration.py::load_integration_config()`
fails closed to `DISABLED` on any missing/malformed/unrecognized `mode` value, and
`DISABLED`/`ARCHIVE_ONLY` never read or require the `policy:`/`telegram_destination:`
blocks at all — no code change is needed to roll back. Rollback does not delete
archived tickets, delivery records, or attempt-journal entries (all are append-only /
idempotent-write structures); does not rewrite attempt history; does not change
strategy behavior; does not change execution authority.

## Files changed this pass

Documentation reconciliation (commit 1):

- `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md` — dated correction to
  the stale "WP7 NOT STARTED" banner; original text preserved.
- `docs/status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md`
  — dated addendum resolving the open retry-scheduling question; original text
  preserved.
- `PROJECT_STATUS.md` — new rolling-summary entry.
- `docs/README.md` — index entry for this status document.
- `docs/status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md` — this document
  (new).

Test-flake root-cause fix (commit 2, `MESSAGE_DELIVERY` mode/config untouched by this
change, `mode` in `config/ticket_delivery.yaml` not modified, no destination added):

- `src/ticket_delivery/telegram_adapter.py` — `DeliveryOutcome` gains
  `delivery_performed_by_this_invocation: bool = False`; the `mark_delivered()` branch
  is the only site that sets it `True`; a clarifying docstring freezes `final_state`'s
  meaning as the durable ticket state.
- `src/ticket_delivery/fx_cycle_integration.py` — `PairOutcome` gains the same field,
  propagated from `DeliveryOutcome` at the one call site that invokes `deliver(...)`.
- `src/ticket_delivery/scheduler_integration.py` — the per-pair output dict built by
  `process_cycle_result()` includes the new field for operator observability.
- `tests/test_ticket_delivery_fx_cycle_overlap.py` — the concurrency test now asserts
  on `delivery_performed_by_this_invocation` (deterministic exactly-once truth) instead
  of counting `delivery_state == "DELIVERED"` occurrences (non-deterministic under
  contention by design, once the semantics above are correctly understood).

## Verdict

`WP7_READY_FOR_SEPARATE_OWNER_ACTIVATION`
