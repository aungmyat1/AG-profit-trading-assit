# AG Stage 1 — Exactly-Once FX Ticket Foundation V1 — Status

Dated: 2026-09-08
Source commit (baseline): `main` at `6350f99` (working-tree additive from this point; not committed by this pass)
Environment: local sandbox, Python backend only (frontend/npm/Vite/browser explicitly out of scope for this milestone)
Authority: `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`, `docs/plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md` Phase 2

## Scope actually implemented this pass

WP1 (identity), WP3 (per-cycle archive), and the core of WP6 (durable delivery journal
+ atomic deduplication) from the Stage 1 plan. WP2 (canonical renderer), WP4 (scheduler
recovery), WP5 (Telegram transport port), and WP7 (operational proof with a real send)
were **not started** -- see "Deferred" below and the plan document's own updated
checklist.

**Not integrated into the live FX cycle/report orchestration.** `src/ticket_delivery/`
is a new, standalone, fully-tested package; nothing in `post_asian_pilot/` calls it yet.
No scheduled task, CLI, or report path currently exercises it outside its own test
suite.

## New package: `src/ticket_delivery/`

```
identity.py         -- logical_ticket_id() / delivery_attempt_id() / correction_id()
archive.py           -- CycleDecisionRecord, archive_cycle_decision() (wraps post_asian_pilot.report_archive.write_report() unchanged)
models.py            -- delivery states, DeliveryRecord, ClaimResult
delivery_store.py    -- TicketDeliveryStore: durable journal + O_EXCL atomic claim (mirrors authorization/store.py's proven pattern)
```

## Identity contract (WP1)

Canonical logical ticket identity:

```
logical_ticket_id = strategy_id | strategy_version | symbol | cycle | trading_date
```

Extends the existing `post_asian_pilot.proposal.PostAsianEntryProposal.setup_id` shape
(`strategy_id:cycle:symbol:trading_date`, verified against real fixtures in
`tests/test_authorization_core.py`) by one field, `strategy_version` -- not a second
competing identity. `post_asian_pilot.decision._decision_id` was deliberately not
reused: it hashes in `evaluation_time`, which differs on every retry, so it cannot serve
as a stable key across attempts.

`delivery_attempt_id` = `logical_ticket_id + "|attempt-NNN"` (one logical ticket, many
possible attempts). `correction_id` = `logical_ticket_id + "|correction-NNN"` (a
correction never gets a new logical identity).

Proven by test (`tests/test_ticket_delivery_identity_and_archive.py`, 14 tests):
identical occurrence -> identical id; a change in symbol, cycle, trading_date,
strategy_id, or strategy_version each independently changes the id (parametrized, no
collision on any single dimension); retry produces a new attempt id, never a new
logical ticket id; unsafe field values (e.g. containing the `|` separator) fail closed
via `InvalidIdentityFieldError` rather than silently risking a collision.

## Archive contract (WP3)

`archive_cycle_decision()` persists a `CycleDecisionRecord` (all five cycle states --
`READY`/`WATCH`/`NO_TRADE`/`DATA_ERROR`/`BLOCKED` -- are valid, not only READY) via
`post_asian_pilot.report_archive.write_report()`, unchanged. That function already
provides: atomic temp-file + `os.replace` write; idempotent no-op on identical
content re-generation; append-only numbered correction record on genuinely changed
content, with the original file never overwritten; failure surfaces as `OSError`, wrapped
here into `ArchiveFailedError` so a caller cannot mistake a failed archive for a
successful one.

Proven by test (6 of the 14 above): idempotent rerun returns the same path; changed
content produces a `.correction-001.json` file while the original is byte-identical
afterward; the archived record carries `strategy_version`/`application_release`/
`logical_ticket_id`; a simulated write failure raises `ArchiveFailedError` rather than
returning a partial/ambiguous result.

## Delivery state machine (WP6)

```
NOT_APPLICABLE             -- WATCH/NO_TRADE/DATA_ERROR/BLOCKED: archived, never delivered
READY_TO_DELIVER           -- READY ticket exists, no attempt claimed
DELIVERY_CLAIMED           -- one worker atomically holds this attempt
DELIVERED                  -- confirmed provider acknowledgement
DELIVERY_FAILED_RETRYABLE  -- known non-terminal failure; a fresh claim may retry
DELIVERY_FAILED_TERMINAL   -- known terminal failure; never retried again
DELIVERY_AMBIGUOUS         -- outcome unprovable (e.g. timeout); NEVER auto-resent -- only resolve_ambiguous_outcome() (an explicit, separately-signed reconciliation call, not invoked by any retry/claim path) can move it forward
```

This extends the plan document's WP1 five-state list with `DELIVERY_CLAIMED` and
`DELIVERY_AMBIGUOUS`, both required by WP6's own test list (ambiguous-timeout handling,
a distinct claimed-vs-pending state for auditability) -- documented in
`models.py`'s module docstring as additive, not a departure from WP1.

Atomic claim reuses `authorization/store.py`'s exact `O_EXCL` exclusive-create idiom
(`os.open(..., O_WRONLY | O_CREAT | O_EXCL)`) -- proven safe under concurrency and
restart in that module's own prior test suite, not reinvented here. Persistence is
`runtime_state.store.JsonKeyValueStore`, already fixed for concurrent-thread safety in
an earlier milestone (per-path `threading.Lock` + bounded `os.replace` retry).

## Concurrency and restart results (WP6)

`tests/test_ticket_delivery_concurrency_and_restart.py`, 13 tests, all passing; the
10-way-concurrency and ambiguous-never-auto-reclaimed tests were additionally re-run 5
consecutive times with zero flakes:

| Scenario | Result |
|---|---|
| Duplicate scheduler trigger | PASS -- one record, `attempt_number` stays 0 until a real claim |
| Repeated identical run | PASS -- `ensure_ready_to_deliver()` is idempotent |
| 10-way concurrent claim | PASS -- exactly 1 winner, `attempt_number` incremented exactly once |
| Parallel workers, different logical tickets | PASS -- each succeeds independently |
| Restart before claim | PASS -- reopened store sees `READY_TO_DELIVER`, claims normally |
| Restart after claim, before send | PASS -- reopened store sees `DELIVERY_CLAIMED`, cannot reclaim |
| Restart after send, before local success recording | PASS (documented, not separately simulatable in a unit test since the network call is a caller responsibility) -- state remains `DELIVERY_CLAIMED` across restart, never silently treated as ready |
| Successful retry | PASS -- new `attempt_number`, same `logical_ticket_id`, reaches `DELIVERED` |
| Terminal failure | PASS -- never claimable again |
| Expired ticket | PASS -- claim refused once `expires_at` has passed |
| Correction record | PASS -- re-triggering the same occurrence never creates a second record |
| No duplicate logical ticket | PASS -- proven directly (`len(store._records.all()) == 1`) |
| Ambiguous outcome never auto-resent | PASS -- 5 concurrent claim attempts against an `DELIVERY_AMBIGUOUS` record all fail; state unchanged |
| Ambiguous outcome resolved only by explicit reconciliation | PASS -- `resolve_ambiguous_outcome()` requires an explicit terminal target state, is never called by any claim/retry path |

## Telegram boundary (WP5) — audit only, no transport ported

WP5 itself (porting the message-only Telegram client/formatter, secrets/destination
audit, mocked-transport send tests) was **not started**. What this pass does prove: the
new package cannot reach execution or an approval/callback surface even in principle --
`tests/test_ticket_delivery_execution_boundary.py` (4 tests) statically scans every file
under `src/ticket_delivery/` via `ast` and asserts zero imports of `execution.*`,
`mt5.management_gateway`, `mt5.mt5_gateway`, `authorization.mt5_execution_handler`, or
`authorization.telegram_gateway` (the existing approval-callback surface — deliberately
excluded since Stage 1 delivery is message-only, not approval-routed), and zero calls to
any `order_send`/`order_check`/execution-trigger-shaped function name.

## Test commands and results

```
python -m pytest tests/test_ticket_delivery_identity_and_archive.py -q
  14 passed

python -m pytest tests/test_ticket_delivery_concurrency_and_restart.py -q
  13 passed (re-run 5x for the two concurrency-sensitive cases, zero flakes)

python -m pytest tests/test_ticket_delivery_execution_boundary.py -q
  4 passed

python -m pytest tests/test_ticket_delivery_identity_and_archive.py tests/test_ticket_delivery_concurrency_and_restart.py tests/test_ticket_delivery_execution_boundary.py tests/test_performance_calculator.py tests/test_execution_lifecycle.py tests/test_post_asian_pilot.py tests/test_runtime_state_store.py -q
  149 passed, 0 failed  (affected suite: new package + Stage 0 modules touched by the prior handoff + the two existing modules this package reuses)

git diff --check
  clean (no output)
```

Full repository suite not run -- not required for a scoped, additive, new-package
change per this project's own progressive-testing convention (`AGENTS.md`
minimum-context principle); nothing outside `src/ticket_delivery/` and the two prior
Stage-0 files was modified.

## Documentation updated

- `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md` — status line and
  acceptance checklist corrected to reflect exactly what's implemented vs. deferred.
- `PROJECT_STATUS.md` — dated rolling-snapshot entry added (see that file).
- This document, linked from `docs/README.md`.
- `README.md` not touched — no user-visible operation or configuration changed (nothing
  is wired into a runnable path yet).

## Deferred / not implemented this pass

- **WP2** — canonical ticket renderer (wraps the existing entry-ticket renderer with the
  `INFORMATIONAL PROPOSAL — NOT A BROKER ORDER` label and fail-closed-on-missing-fields
  behavior). Not started.
- **WP4** — scheduler recovery (bounded catch-up rule, single-run overlap claim,
  weekend/closed-market/stale-data tests). Not started.
- **WP5** — actual Telegram message-only transport port from the paused feature branch
  (`authorization/telegram_gateway.py`'s sibling `notifications/telegram_client.py` /
  `trade_ticket_formatter.py` already exist on `main` from an earlier milestone but were
  not audited or re-wired for this informational-only purpose this pass).
- **WP7** — operational proof: no real Telegram send, mocked or otherwise, was
  attempted; no natural READY ticket was captured through this new path.
- Integration into the live FX cycle/report pipeline (`post_asian_pilot/`) — the new
  package exists and is fully tested in isolation but nothing calls it yet.

## Safety confirmation

```
strategy files modified          = 0
execution/authorization files modified = 0
broker order-submission calls    = 0 (statically verified, 4 tests)
real Telegram sends              = 0 (WP5/WP7 not attempted)
real_demo_orders                 = 0
real_live_orders                 = 0
```
