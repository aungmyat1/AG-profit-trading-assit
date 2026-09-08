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

## Safety confirmation (original pass)

```
strategy files modified          = 0
execution/authorization files modified = 0
broker order-submission calls    = 0 (statically verified, 4 tests)
real Telegram sends              = 0 (WP5/WP7 not attempted)
real_demo_orders                 = 0
real_live_orders                 = 0
```

---

## Addendum (2026-09-08, same date): WP2 renderer + WP5 message-only transport

Baseline for this addendum: HEAD `fecc32b` (the foundation above, committed). Continues
the same package; no prior file in this document's original section was modified.

### WP2 — `src/ticket_delivery/renderer.py`

`render_informational_ticket()` wraps the EXISTING `post_asian_pilot.report.render_entry_ticket()`-shaped
dict verbatim -- reads 14 mandatory dotted-path fields (identity/strategy/application/
market/entry/risk/timing/evidence), computes nothing itself. Only `decision_status ==
"READY"` renders; WATCH/NO_TRADE/DATA_ERROR/BLOCKED all return `status="BLOCKED"`,
`reason_code="DECISION_NOT_READY"`. Any missing mandatory field (individually tested,
all 14) blocks rendering with `reason_code="MISSING_MANDATORY_FIELDS"` and the exact
missing dotted paths -- never a fabricated or defaulted value. Output payload always
carries the literal label `INFORMATIONAL PROPOSAL -- NOT A BROKER ORDER` and an
`authorization: {strategy_authorized: false, execution_authorized: false}` block.
Canonical serialization is `json.dumps(..., sort_keys=True, separators=(",", ":"))`;
`payload_hash()` is its SHA-256 -- proven deterministic (same input -> same hash across
two independent calls) and content-sensitive (a single changed field changes the hash).
`format_message_text()` renders plain text only -- no inline keyboard, no
`callback_data` field anywhere in its output.

25 new tests, `tests/test_ticket_delivery_renderer.py`, all passing: complete READY
rendering; all 4 non-READY states rejected (parametrized); each of the 14 mandatory
fields individually missing (parametrized); stable hash across repeated calls; hash
changes on content change; strategy-version/release binding present; source proposal
dict never mutated; no inline-keyboard/callback shape in the message text; no
execution-module reference in the renderer source.

### WP5 — `src/ticket_delivery/telegram_adapter.py`

Reuses `notifications.telegram_client.TelegramClient.send_message()` ONLY -- no other
method on that class (`get_updates`, `answer_callback_query`, `edit_message_*`, or any
callback-parsing function) is ever called from this package. Deliberately does NOT
reuse `notifications.trade_ticket_formatter` (builds `ExecutionApproval`-coupled inline
keyboards) or `authorization.telegram_gateway` (the approval-callback surface) -- both
are now in the AST-based execution-boundary scan's forbidden-import list alongside
`execution.*`/`mt5.management_gateway`/`mt5.mt5_gateway`/`authorization.mt5_execution_handler`.

`TelegramDestinationConfig.from_values()` takes no defaults: missing bot token ->
`TELEGRAM_BOT_TOKEN_NOT_CONFIGURED`, missing chat_id -> `TELEGRAM_DESTINATION_NOT_CONFIGURED`,
a chat_id outside the caller-supplied `authorized_chat_ids` allow-list ->
`TELEGRAM_DESTINATION_NOT_AUTHORIZED` -- every case raises before `deliver_informational_ticket()`
is ever reached, so no network call is possible without explicit, authorized
configuration. `_redact()` strips the literal bot token from every string this module
ever persists as failure evidence, applied unconditionally (not only when a leak looks
likely) -- proven by two tests that construct a connection failure whose exception
message contains the real token embedded in a URL, then read back both the in-memory
record and the actual on-disk `delivery_records.json` file and assert the token string
is absent from both.

Outcome classification: `ok=true` -> `DELIVERED` (provider `message_id` persisted);
`ok=false, error_code=429` -> `DELIVERY_FAILED_RETRYABLE`; any other `ok=false` ->
`DELIVERY_FAILED_TERMINAL`; a transport-level exception (connection failure, timeout,
or an unparseable/malformed response -- all three currently share Telegram client's own
`SENDMESSAGE_REQUEST_FAILED` reason code, since none of them can distinguish "definitely
not sent" from "sent, response lost") -> `DELIVERY_AMBIGUOUS`, and `DELIVERY_AMBIGUOUS`
inherits the foundation's existing "never auto-reclaimed" guarantee unchanged (proven by
a repeat call after an ambiguous outcome: `claimed=False`, state unchanged). A retry
after `DELIVERY_FAILED_RETRYABLE` was proven end-to-end (mocked 429 then mocked success):
same `logical_ticket_id`, incremented `attempt_number`, final state `DELIVERED`.

20 new tests, `tests/test_ticket_delivery_telegram_adapter.py` (17) +
`tests/test_ticket_delivery_execution_boundary.py` (4, one pre-existing + `trade_ticket_formatter`
addition), all passing: missing token / missing destination / unauthorized destination
all fail closed pre-network; no hardcoded destination in the module source; successful
delivery with provider evidence persisted; rate-limit -> retryable; other `ok=false` ->
terminal; malformed response -> ambiguous; connection failure -> ambiguous; timeout ->
ambiguous; HTTP error -> ambiguous; ambiguous outcome never auto-reclaimed (a second
delivery attempt against the same store fails to claim); successful retry after a
retryable failure reuses the logical ticket and reaches DELIVERED; bot token absent from
both the returned failure evidence and the actual on-disk journal file; no
execution/broker import anywhere in the module (AST-verified).

### Combined test results

```
pytest tests/test_ticket_delivery_renderer.py -q            → 25 passed
pytest tests/test_ticket_delivery_telegram_adapter.py -q    → 17 passed
pytest tests/test_ticket_delivery_execution_boundary.py -q  → 4 passed
pytest tests/test_ticket_delivery_identity_and_archive.py tests/test_ticket_delivery_concurrency_and_restart.py tests/test_ticket_delivery_execution_boundary.py tests/test_ticket_delivery_renderer.py tests/test_ticket_delivery_telegram_adapter.py tests/test_telegram_client.py tests/test_telegram_gateway.py tests/test_authorization_core.py -q
  → 164 passed, 0 failed
git diff --check → clean (one CRLF line-ending warning only)
```

### Not implemented this addendum

- **WP4** — scheduler recovery (bounded catch-up rule, single-run overlap claim,
  weekend/closed-market/stale-data tests). Explicitly out of scope for this task.
- **WP7** — operational proof with a real Telegram send. Explicitly out of scope; no
  live send was attempted or claimed anywhere in this addendum.
- Integration into the live FX cycle/report pipeline -- `renderer.py` and
  `telegram_adapter.py` exist and are fully tested in isolation; nothing in
  `post_asian_pilot/` calls either yet.

### Safety confirmation (addendum)

```
strategy files modified          = 0
execution/authorization files modified = 0
scheduler files modified         = 0
broker order-submission calls    = 0 (statically verified)
real Telegram sends              = 0 (every test uses an injected fake HTTP session)
real_demo_orders                 = 0
real_live_orders                 = 0
```

---

## Addendum 2 (2026-09-08): WP4 scheduler/runtime integration + WP6 bounded retry

Baseline: HEAD `05ddd00` (the WP2/WP5 addendum above, committed). Continues the same
package.

### Gate 1 — scheduler entry-point reconciliation

Read-only inspection of `scripts/scheduled/run_asian_london_once.bat` and
`run_london_newyork_once.bat`: both invoke `python scripts\run_post_asian_pilot.py
--once --json`, the second with `--pilot-config config\pilot\AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml`.
Neither installed task was modified. `run_post_asian_pilot.py` calls
`post_asian_pilot.pipeline.run_pilot_cycle()`, which returns a `PilotCycleResult`
(`pairs: Tuple[PairResult, ...]`, each `PairResult(symbol, decision, portfolio_state,
portfolio_reason_code, proposal)`) -- this is the deterministic-cycle-completion
checkpoint the new orchestration consumes; nothing in `pipeline.py` was touched.
Live scheduler task state itself (Task Scheduler `Get-ScheduledTask`) was
**NOT_EVALUATED** this pass -- code-level integration was verified instead, per this
task's own explicit allowance not to treat that as a blocker.

### WP4.1/WP4.2 — `src/ticket_delivery/fx_cycle_integration.py`

`process_pair_result()` takes one already-computed `PairResult` and a caller-supplied
`cycle` label (the future scheduler wrapper's job, not derived here) and:

1. Maps `decision.status`/`portfolio_state` to the 5-state archive vocabulary via an
   exhaustive, fail-closed `_map_cycle_state()` (an unrecognized status raises, never
   silently defaults). A `READY` decision that never became actionable (governor/ledger
   blocked it) is correctly archived as `BLOCKED`, not `READY`.
2. Calls `archive_cycle_decision()` FIRST, unconditionally, for every cycle state --
   proven by construction: no render/register/claim/transport call exists on any code
   path that skips this step, and a simulated `ArchiveFailedError` returns immediately
   with zero further calls (`test_archive_failure_produces_zero_transport_calls`).
3. For non-READY states: `delivery_store.record_not_applicable()`, zero Telegram calls
   (parametrized across all 4 non-READY states).
4. For READY: calls a caller-injected `render_entry_ticket_dict` (keeps this module
   decoupled from `post_asian_pilot`'s fingerprint/ledger construction, matching WP2's
   own "wrap without re-deriving" boundary), renders via the existing WP2 renderer,
   registers via `ensure_ready_to_deliver()`, then calls a caller-injected `deliver`
   closure (typically `telegram_adapter.deliver_informational_ticket()`) -- absence of
   `deliver` fails closed AFTER the archive/registration already happened (config
   absence never discards the archived decision).

11 new tests, `tests/test_ticket_delivery_fx_cycle_integration.py`, all passing.

### WP4.3 — run-level overlap protection

No new locking mechanism -- proven by COMPOSITION of the already-atomic primitives
(`archive_cycle_decision`'s idempotent/correction write, `ensure_ready_to_deliver`'s
idempotent creation, `claim_for_delivery`'s O_EXCL atomic claim). 3 new tests,
`tests/test_ticket_delivery_fx_cycle_overlap.py`:

- 10 concurrent `process_pair_result()` calls for the identical pair -> exactly 1
  `DELIVERED` outcome, exactly 1 real HTTP call counted at the mocked transport
  boundary, all 10 outcomes share one `logical_ticket_id`, exactly 1 delivery record
  ever created.
- Two independent symbols processed concurrently both deliver independently (2 HTTP
  calls, 2 distinct logical tickets) -- proving unrelated occurrences don't block each
  other.
- A simulated restart (fresh `TicketDeliveryStore` instance against the same
  `state_dir`, after an archive+registration with no delivery attempted) resumes
  safely: same `logical_ticket_id`, same `archive_path` (idempotent), reaches
  `DELIVERED` with exactly 1 HTTP call total across both "processes".

### WP4.4 catch-up + WP6 retry policy — `src/ticket_delivery/policy.py`

**Resource-first check performed before writing this module:** searched
`docs/plans/`, `docs/contracts/`, `config/governance/` for any existing signed FX
ticket-delivery catch-up duration or retry/backoff bound. None exists. The only
related document (`docs/contracts/AG_BTC_CATCHUP_CONTRACT_AMENDMENT_V1_PROPOSED.md`) is
itself explicitly PROPOSED / not authorized, and scoped to a different domain (BTC
daily observation counting) that does not transfer by analogy without its own sign-off.

```
CATCH_UP_DURATION  = UNSIGNED
RETRY_MAX_ATTEMPTS = UNSIGNED
RETRY_BASE_DELAY   = UNSIGNED
RETRY_MAX_DELAY    = UNSIGNED
```

Both `CatchUpPolicy` and `RetryPolicy` are implemented as **mechanism-complete,
fail-closed interfaces**: zero-argument construction represents "not configured" and
refuses every evaluation (never applies an implicit default), while an explicit
injected value (e.g. in a test) exercises full, deterministic logic. `RetryPolicy`'s
backoff (`base * 2^(attempt-1)`, capped at `max_delay`) is a pure function of
`(attempt_number, policy)` -- no wall-clock read, no randomness, no real sleeping in
any test. Terminal and ambiguous classifications are refused unconditionally,
independent of whether numeric bounds are configured.

13 new tests, `tests/test_ticket_delivery_policy.py`, all passing: premature run,
exact-checkpoint boundary, valid configured catch-up, catch-up outside the bound,
missing catch-up configuration (fails closed), successful subsequent-cycle recovery
(framed as an ordinary in-bound catch-up, no separate mechanism needed);
deterministic backoff at 5 attempt numbers, successful bounded retry, max-attempts
exhaustion, terminal-never-retried, ambiguous-never-retried, missing retry
configuration (fails closed), `next_delay()` raises rather than guessing when
unconfigured.

**This is precisely the "mechanism complete, operational policy unsigned" distinction
the task instructions asked to classify precisely** -- WP4.4 and the WP6 retry
completion are NOT marked accepted/operational; they are proven-safe scaffolding
awaiting an owner-signed numeric value before any real catch-up or retry could ever
actually fire.

### WP4.5 — scheduler-facing CLI

`scripts/run_ticket_delivery_status.py`: read-only diagnostic over the existing
delivery journal (single-ticket lookup or full listing), JSON or pretty output,
nonzero exit on an actionable failure state (`DELIVERY_FAILED_TERMINAL` /
`DELIVERY_AMBIGUOUS` present). No execution/approval/broker flag exists. Documents the
two env var *names* (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) a real run would
eventually need, without reading or printing either. Does not archive, render, claim,
or deliver anything itself -- diagnostic only, smoke-tested against an empty state
directory this pass (`{"status": "OK", "count": 0, "records": []}`).

### Combined test results

```
pytest tests/test_ticket_delivery_fx_cycle_integration.py -q  → 11 passed
pytest tests/test_ticket_delivery_fx_cycle_overlap.py -q      → 3 passed
pytest tests/test_ticket_delivery_policy.py -q                → 13 passed
pytest tests/test_ticket_delivery_identity_and_archive.py tests/test_ticket_delivery_concurrency_and_restart.py tests/test_ticket_delivery_execution_boundary.py tests/test_ticket_delivery_renderer.py tests/test_ticket_delivery_telegram_adapter.py tests/test_ticket_delivery_fx_cycle_integration.py tests/test_ticket_delivery_fx_cycle_overlap.py tests/test_ticket_delivery_policy.py tests/test_telegram_client.py tests/test_telegram_gateway.py tests/test_authorization_core.py tests/test_post_asian_pilot.py -q
  → 271 passed, 0 failed
git diff --check → clean (1 CRLF line-ending warning only)
```

### Not implemented / not activated this addendum

- Installed scheduler tasks were NOT modified (read-only inspection only).
- Live Task Scheduler state was NOT_EVALUATED (code-level integration verified
  instead).
- `CatchUpPolicy`/`RetryPolicy` are NOT wired to any real config source and carry no
  signed operational value -- mechanism-complete, operationally inert.
- Nothing in `post_asian_pilot/run_post_asian_pilot.py` yet calls
  `process_pair_result()` -- the orchestration exists and is fully tested in isolation,
  but a real scheduled run still only produces the existing decision/proposal journals,
  not a ticket_delivery archive record, until a follow-up task wires the call site.
- **WP7** — no real Telegram send, mocked or otherwise beyond unit tests, was
  attempted; no natural READY ticket was captured through this path.

### Safety confirmation (addendum 2)

```
strategy files modified          = 0
execution/authorization files modified = 0
scheduler task files modified    = 0
broker order-submission calls    = 0 (statically verified, execution-boundary scan now covers fx_cycle_integration.py and policy.py too)
real Telegram sends              = 0 (every test uses an injected fake HTTP session)
real_demo_orders                 = 0
real_live_orders                 = 0
```

---

## Addendum 3 (2026-09-08): scheduler call-site wiring (final pre-operational slice)

Baseline: HEAD at the WP4 addendum 2 commit above. Continues the same package.

### Gate 1 — live scheduler re-inspection

`Get-ScheduledTask` confirmed both `AG_FX_ASIAN_LONDON_SHADOW` and
`AG_FX_LONDON_NEWYORK_SHADOW` are `State=Ready`, trigger every 15 minutes, with
`MultipleInstances: IgnoreNew` (OS-level overlap guard, independent of anything this
package does). Each invokes its own `.bat` wrapper, which calls `python
scripts\run_post_asian_pilot.py --once --json [--pilot-config ...]` -- confirming the
call-site target identified read-only in Addendum 2 is exactly where the real scheduled
process re-enters user code on every tick. Neither task, nor either `.bat` file, was
modified.

### New: `src/ticket_delivery/scheduler_integration.py`

The single call site. `load_integration_config()` reads `config/ticket_delivery.yaml`
and fails closed to `DISABLED` on any missing file, malformed YAML, or unrecognized
`mode` value. `process_cycle_result()` derives the `cycle` label from the
`--pilot-config` path already passed to the script (no pilot YAML modified), then loops
`process_pair_result()` (Addendum 2's orchestration, unmodified) over every pair in the
already-computed `PilotCycleResult`. `DISABLED` returns `[]` before touching any
filesystem. Both `ARCHIVE_ONLY` and (still-inert) `MESSAGE_DELIVERY` pass `deliver=None`
unconditionally -- a structural, not merely config-gated, zero-network guarantee,
proven by a static source-inspection test asserting the string `"deliver ="` appears
exactly once in `process_cycle_result()`'s source.

### New: `config/ticket_delivery.yaml`

Ships `mode: DISABLED` -- the real, committed repository default. Comments document
each mode and note that reverting to today's behavior is a one-line edit.

### Modified: `scripts/run_post_asian_pilot.py`

`_process_ticket_delivery()` is additive only: called from `_run_once()` AFTER the
existing `cycle_to_dict()` / `human_readable_report()` output has already printed (that
frozen schema is untouched), prints a separate `"ticket_delivery"` JSON block (or a
separate text block) only when `mode != DISABLED`, and never raises out of `_run_once()`
-- any unexpected exception inside it is caught and logged to stderr, degrading to a
no-op. The one exception: an `ARCHIVE_FAILED` outcome now produces a nonzero scheduler
exit code (`sys.exit(1)`) after the strategy report has already printed successfully --
a deliberate, narrow escalation for the one failure mode considered worth an operator
alert, not a silent one.

### Proof of archive-before-send, at the real call site (not only the orchestration layer)

`tests/test_ticket_delivery_scheduler_integration.py` (16 tests) and
`tests/test_run_post_asian_pilot_ticket_delivery_wiring.py` (7 tests, loading the real
script module via `importlib.util` so no live MT5 terminal is required -- `_execute_cycle`
is never invoked, only `_process_ticket_delivery()` directly against a fixture
`PilotCycleResult`) together prove, through the actual CLI function:

| Scenario | Result |
|---|---|
| Missing config file / malformed YAML / unrecognized mode | fails closed to `DISABLED` |
| Shipped `config/ticket_delivery.yaml` | is `DISABLED` (read directly, not a test fixture assumption) |
| `DISABLED` mode, real CLI call | zero new stdout output, zero new files |
| `ARCHIVE_ONLY`, real CLI call | archives, zero network calls, correct `mode`/`cycle_state` in output |
| Repeated identical CLI invocation | same `logical_ticket_id` both times |
| Two simultaneous CLI invocations (`ThreadPoolExecutor`) | exactly 1 persisted delivery record (verified by reading the store directly, not by parsing racing stdout -- `contextlib.redirect_stdout` is not thread-safe, see fix below) |
| Simulated archive failure | `archive_failed=True`, `"delivery_state": "ARCHIVE_FAILED"` in output, no crash |
| Unexpected exception anywhere in ticket-delivery processing | caught, logged to stderr, `_run_once()` still returns the already-printed strategy report normally |
| `MESSAGE_DELIVERY` config, real CLI call | zero network calls (no mock transport exists anywhere in this call chain; a real attempt would raise) |
| READY pair without ledger/fingerprint context | `RENDER_BLOCKED`, never fabricated |
| Zero-network in `ARCHIVE_ONLY`/`MESSAGE_DELIVERY` | proven structurally (single unconditional `deliver = None`), not just empirically |

10-concurrent-invocation scale beyond the 2-way `ThreadPoolExecutor` test was not
separately re-run at the CLI layer this pass -- the underlying 10-way concurrent claim
guarantee was already proven at the orchestration layer in Addendum 2
(`test_ticket_delivery_fx_cycle_overlap.py`), and this addendum's CLI-layer tests prove
the wiring reaches that same code path unchanged, not a new concurrency primitive.

### Bugs found and fixed by these tests

1. `load_integration_config(path: str = DEFAULT_CONFIG_PATH)` bound Python's default
   argument at function-definition time, so `monkeypatch.setattr(module,
   "DEFAULT_CONFIG_PATH", ...)` in tests had no effect on the already-bound default --
   fixed by changing the signature to `path: Optional[str] = None` and reading the
   module constant dynamically inside the function body.
2. The first version of the two-simultaneous-invocation test used
   `contextlib.redirect_stdout` from two threads via `ThreadPoolExecutor`, which is not
   thread-safe (it swaps the single process-global `sys.stdout`) and produced a flaky
   empty-buffer read on one thread -- a test-harness race, not a production defect. Fixed
   by inspecting `TicketDeliveryStore._records.all()` directly instead of parsing
   concurrently-captured stdout. Re-run 3 consecutive times after the fix, zero flakes.

### Owner decision packet

`docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md` proposes (does
not activate) values for `FX_MAX_CATCH_UP_AGE`, `DELIVERY_MAX_ATTEMPTS`,
`DELIVERY_RETRY_BASE_DELAY`, `DELIVERY_RETRY_MAX_DELAY`, each with a recommended
default, a conservative alternative, the unsigned fail-closed behavior already in
force, and confirmation that none of these values retroactively affects any
already-archived record's identity. `src/ticket_delivery/policy.py` was NOT modified
this addendum -- still zero production defaults, per Addendum 2.

### Combined test results

```
pytest tests/test_ticket_delivery_scheduler_integration.py -q                → 16 passed
pytest tests/test_run_post_asian_pilot_ticket_delivery_wiring.py -q          → 7 passed (re-run 3x after the redirect_stdout fix, zero flakes)
pytest tests/test_ticket_delivery_identity_and_archive.py tests/test_ticket_delivery_concurrency_and_restart.py tests/test_ticket_delivery_execution_boundary.py tests/test_ticket_delivery_renderer.py tests/test_ticket_delivery_telegram_adapter.py tests/test_ticket_delivery_fx_cycle_integration.py tests/test_ticket_delivery_fx_cycle_overlap.py tests/test_ticket_delivery_policy.py tests/test_ticket_delivery_scheduler_integration.py tests/test_run_post_asian_pilot_ticket_delivery_wiring.py tests/test_telegram_client.py tests/test_telegram_gateway.py tests/test_authorization_core.py tests/test_post_asian_pilot.py -q
  → 294 passed, 0 failed
git diff --check → clean
```

### Not implemented / not activated this addendum

- `config/ticket_delivery.yaml` was NOT flipped to `ARCHIVE_ONLY` -- ships `DISABLED`.
  Activating archive-only in the real repository remains a distinct, still-pending,
  one-line operator decision.
- `CatchUpPolicy`/`RetryPolicy` remain unwired to any config source and carry no signed
  value -- the decision packet proposes values; nothing here signs them.
- **WP7** — no real Telegram send, mocked or otherwise beyond unit tests, was
  attempted; no natural READY ticket was captured through this path.
- No strategy YAML, installed scheduler task, or execution/broker configuration file
  was modified.

### Safety confirmation (addendum 3)

```
strategy files modified                = 0
execution/authorization files modified = 0
scheduler task files modified          = 0 (.bat / Task Scheduler definitions untouched; read-only re-inspection only)
broker order-submission calls          = 0 (statically verified; execution-boundary scan unchanged, scheduler_integration.py has no execution import)
real Telegram sends                    = 0 (MESSAGE_DELIVERY remains structurally zero-network this pass; no mock transport exists in this call chain)
config/ticket_delivery.yaml shipped mode = DISABLED
real_demo_orders                       = 0
real_live_orders                       = 0
local commit made                      = yes (checkpoint only, not pushed)
```

---

## Addendum 4 (2026-09-08): exit-code propagation fix for unexpected ticket-delivery errors

Baseline: HEAD at the Addendum 3 commit (`c8b1fa8`). Continues the same package.

### Defect found and fixed

`_process_ticket_delivery()` caught every unexpected exception (a genuine bug in
ticket-delivery processing, distinct from the already-handled `ARCHIVE_FAILED`
outcome) and returned `False` -- meaning the scheduled run exited 0 even though
ticket-delivery processing had silently broken, with the only trace being an
unwatched stderr line. Fixed by returning `True` from that exception branch (still
never letting the exception propagate and crash the already-printed strategy report),
so `_run_once()` now raises `sys.exit(1)` for both an archive failure and an
unexpected operational error. `_run_once()`'s local variable was renamed from
`archive_failed` to `ticket_delivery_failed` to match the corrected, broader meaning.

### Proof

`tests/test_run_post_asian_pilot_ticket_delivery_wiring.py::test_ticket_delivery_error_never_crashes_but_signals_failure`
(updated) proves the helper itself now returns `True`. A new test,
`test_unexpected_ticket_delivery_error_propagates_as_nonzero_exit_from_run_once`,
proves the signal actually reaches `_run_once()` -- calling the real function
(`_execute_cycle`/`_entry_ticket_context` monkeypatched to avoid needing live MT5,
`cycle_to_dict` stubbed since report-rendering correctness is proven elsewhere) and
asserting both `SystemExit(1)` is raised AND the strategy report had already printed
successfully to stdout before that exit -- the never-crash-the-report guarantee still
holds; what changed is that the exit code no longer lies about the outcome.

Combined affected suite: **295 passed, 0 failed**; `git diff --check` clean.

### Not changed this addendum

- No activation: `config/ticket_delivery.yaml` remains `DISABLED`.
- No catch-up/retry policy signed.
- No strategy, scheduler task, or execution/broker file touched.

---

## Addendum 5 (2026-09-08): signed policy activation + real ARCHIVE_ONLY evidence

Baseline: HEAD at the Addendum 4 commit (`d7ab190`). Continues the same package, under
explicit owner authorization to record the approved policy values, wire them, and
activate `ARCHIVE_ONLY`.

### Owner authorization received this pass

```yaml
fx_max_catch_up_age_minutes: 60
delivery_max_attempts: 3
delivery_retry_base_delay_seconds: 30
delivery_retry_max_delay_seconds: 300
```

plus explicit authorization to change `config/ticket_delivery.yaml`'s `mode` from
`DISABLED` to `ARCHIVE_ONLY`. Recorded in
`docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md`'s new approval
addendum (the original alternatives table is preserved unchanged as historical
record).

### Gate 2 — signed values wired and validated

`src/ticket_delivery/scheduler_integration.py` gained `TicketDeliveryConfigError`, a
strict `_parse_policy()` validator, and two new `TicketDeliveryIntegrationConfig`
fields (`catch_up_policy: CatchUpPolicy`, `retry_policy: RetryPolicy`) constructed from
the signed `policy:` block. Validation fails closed (raises, never substitutes a
default) for: the whole block missing, any required field missing, non-numeric type,
a bool masquerading as numeric (Python's `bool` is an `int` subclass -- explicitly
excluded), zero/negative values, `base_delay > max_delay`, and any unrecognized extra
field. This validation applies ONLY when `mode != DISABLED` -- `DISABLED` remains the
unconditional one-line rollback, never reading or requiring the policy block, exactly
preserving the pre-existing structural fail-closed-to-DISABLED behavior for a missing
file, malformed top-level YAML, or an unrecognized `mode` value (deliberately
unchanged, documented in `load_integration_config()`'s own docstring as an explicit
interpretation choice, not a silent behavior change).

`scripts/run_post_asian_pilot.py::_process_ticket_delivery()` gained a specific
`except TicketDeliveryConfigError` branch (before the general exception handler) so a
broken signed policy under an active mode produces a normalized
`TICKET_DELIVERY_CONFIG_ERROR: <reason_code>: ...` stderr line and a nonzero scheduler
exit -- visible, never silently swallowed to `DISABLED`-style exit 0.

**Attempt-semantics interpretation confirmed, not changed:** `delivery_max_attempts=3`
is the total attempt count including the initial attempt (pre-existing
`RetryPolicy.should_retry()` behavior: `attempt_number >= max_attempts` refuses a
further retry) -- verified against the approved contract by a new "signed contract"
test section in `tests/test_ticket_delivery_policy.py`: attempt 1 (initial, 30s next
delay) -> attempt 2 (60s next delay) -> attempt 3 exhausts (`RETRY_MAX_ATTEMPTS_EXHAUSTED`),
delay capped at 300s, terminal/ambiguous never retried, expired ticket never claimable
(re-proven directly against the primitive store).

### Catch-up integration (previously unwired -- confirmed and closed this pass)

Confirmed `CatchUpPolicy`/`RetryPolicy` were NOT invoked anywhere in
`scheduler_integration.py` or `fx_cycle_integration.py` before this pass (`grep` came
back empty). Added the smallest integration point: `fx_cycle_integration.process_pair_result()`
gained an optional `catch_up_policy: Optional[CatchUpPolicy] = None` parameter,
evaluated ONLY for a READY pair, using `pair.decision.ready_at` (the real,
restart-frozen strategy-signal timestamp -- confirmed by reading `post_asian_pilot`'s
`decision_from_record()`/`map_trade_signal_to_decision()`: `ready_at` is the
authoritative bar-close/signal timestamp, never re-derived on a later poll) as the
checkpoint against an injectable `now` (real wall-clock in production, a fixed value in
every test). `None` (the default) skips the gate entirely, so every pre-existing test
and caller is unaffected. A rejected catch-up (`CATCH_UP_REJECTED`, reason code from
`CatchUpPolicy.evaluate()`) never creates a ticket -- the archive has already happened
unconditionally before this gate and is untouched. A READY decision with no `ready_at`
at all fails closed the same way (`READY_MISSING_READY_AT`), never assumed to be
"on time." `scheduler_integration.process_cycle_result()` gained an injectable `now`
parameter, forwarded through to the gate and to the delivery-journal timestamps it
already used.

This was NOT approximated: the checkpoint (`ready_at`) is real, authoritative evidence
already present on every `PostAsianDecision`, not an invented "expected 15-minute tick"
time (which Task Scheduler's actual trigger schedule is not passed into the Python
process at all, and which the pipeline itself never needs -- it evaluates directly
against live candle data, not against a scheduler-relative offset). Non-READY states
(`WATCH`/`NO_TRADE`/`DATA_ERROR`/`BLOCKED`) are current-state observations, not late
arrivals of a past event, so the catch-up gate structurally does not apply to them --
they return from the function before the READY-only branch is ever reached.

### Gate 3 — ARCHIVE_ONLY activated

`config/ticket_delivery.yaml`'s `mode` changed from `DISABLED` to `ARCHIVE_ONLY`, with
the signed `policy:` block added. Header comments rewritten to a status-history format
distinguishing "integration introduced" (2026-09-08) / "archive-only activated"
(2026-09-08) / "message delivery NOT authorized" (ongoing), replacing the earlier
single "activated 2026-09-08" phrase that had conflated introduction with activation.

### New tests

- `tests/test_ticket_delivery_scheduler_integration.py`: expanded to 35 tests (from
  16) -- policy validation (block missing, each required field missing x4, invalid
  type, bool-as-numeric, float-for-integer-field, zero/negative x3, base>max,
  base==max valid, unknown extra field, no-silent-default-on-repeat-call,
  MESSAGE_DELIVERY also requires policy), plus catch-up-through-`process_cycle_result`
  tests (on-time permitted, >60min rejected with no ticket registered), plus the real
  shipped config now asserting `ARCHIVE_ONLY` (renamed from the prior
  DISABLED-assuming test).
- `tests/test_ticket_delivery_fx_cycle_integration.py`: +9 tests -- catch-up gate
  behavior (no-policy-supplied skips gate / on-time passes / exact-60-minute-boundary
  permitted / 61-minutes rejected / premature-now rejected / missing-ready_at rejected
  / rejected catch-up still archives with no ticket created / identity preserved
  between an on-time and a late evaluation of the same occurrence / repeated on-time
  calls stay idempotent).
- `tests/test_ticket_delivery_policy.py`: +8 tests -- the signed-contract section
  (exact 3/30/60/300 values, not generic arbitrary values as before), plus a static
  no-real-sleep check.
- `tests/test_run_post_asian_pilot_ticket_delivery_wiring.py`: real-shipped-config-is-now-ARCHIVE_ONLY
  test (replacing the prior DISABLED-assuming test), an explicit DISABLED-rollback
  test (policy-block-optional, zero writes), missing-policy-under-active-mode nonzero
  exit + zero archive writes, invalid-policy-value-under-active-mode nonzero exit.

### Combined test results

```
pytest tests/test_ticket_delivery_scheduler_integration.py tests/test_ticket_delivery_fx_cycle_integration.py tests/test_ticket_delivery_policy.py tests/test_run_post_asian_pilot_ticket_delivery_wiring.py -q
  -> 87 passed

pytest tests/test_ticket_delivery_identity_and_archive.py tests/test_ticket_delivery_concurrency_and_restart.py tests/test_ticket_delivery_execution_boundary.py tests/test_ticket_delivery_renderer.py tests/test_ticket_delivery_telegram_adapter.py tests/test_ticket_delivery_fx_cycle_integration.py tests/test_ticket_delivery_fx_cycle_overlap.py tests/test_ticket_delivery_policy.py tests/test_ticket_delivery_scheduler_integration.py tests/test_run_post_asian_pilot_ticket_delivery_wiring.py tests/test_telegram_client.py tests/test_telegram_gateway.py tests/test_authorization_core.py tests/test_post_asian_pilot.py -q
  -> 334 passed, 0 failed

pytest tests/test_post_asian_pilot.py tests/test_runtime_state_store.py -q
  -> 87 passed

git diff --check -> clean (CRLF line-ending warnings only)
```

One pre-existing, non-reproducible concurrency-test flake
(`test_ten_concurrent_invocations_same_pair_exactly_one_delivery`, unrelated to this
pass's changes since `catch_up_policy` defaults to `None` there and the code path it
exercises is unchanged) was observed once under full-suite system load and did not
reproduce across 3 subsequent isolated and full-suite re-runs; noted for visibility,
not treated as a defect requiring a fix.

### Read-only scheduler re-inspection (live `Get-ScheduledTask`)

```
AG_FX_ASIAN_LONDON_SHADOW
  State: Ready
  Command: "D:\ddev\AG profit trading\scripts\scheduled\run_asian_london_once.bat"
  Trigger interval: 15 minutes (PT15M)
  MultipleInstances: IgnoreNew
  LastRunTime: 2026-09-08 15:00:30 (local, MMT/UTC+6:30) = 2026-09-08T08:30:00Z
  LastTaskResult: 0
  NextRunTime: 2026-09-08 15:15:45 (local)

AG_FX_LONDON_NEWYORK_SHADOW
  State: Ready
  Command: "D:\ddev\AG profit trading\scripts\scheduled\run_london_newyork_once.bat"
  Trigger interval: 15 minutes (PT15M)
  MultipleInstances: IgnoreNew
  LastRunTime: 2026-09-08 15:00:30 (local) = 2026-09-08T08:30:00Z
  LastTaskResult: 0
  NextRunTime: 2026-09-08 15:15:45 (local)
```

Neither task nor either `.bat` wrapper was modified. Both invoke exactly the call site
containing the new archive-only integration (`python scripts\run_post_asian_pilot.py
--once --json [--pilot-config ...]`).

### REAL_ARCHIVE_ONLY_EVIDENCE = VERIFIED

Two independent sources of real evidence, both from AFTER `ARCHIVE_ONLY` was activated
in this pass:

**1. A genuine, unprompted OS-scheduled trigger** (`LastTaskResult: 0` at
2026-09-08T08:30:00Z, confirmed against the real `%TEMP%\ag_shadow_asian_london.log`
and `ag_shadow_london_newyork.log` files the `.bat` wrappers append to) produced real
`ticket_delivery` output for both cycles:

```
ASIAN_LONDON: {"ticket_delivery": {"mode": "ARCHIVE_ONLY", "outcomes": [
  {"symbol": "EURUSD", "cycle_state": "DATA_ERROR", "delivery_state": "NOT_APPLICABLE", ...},
  {"symbol": "GBPUSD", "cycle_state": "READY", "delivery_state": "CATCH_UP_REJECTED",
   "reason_code": "OUTSIDE_CATCH_UP_WINDOW", "archived": true,
   "logical_ticket_id": "ST_ASIAN_SWEEP_5R_V1|1.1.1|GBPUSD|ASIAN_LONDON|2026-09-08"} ]}}
LONDON_NEWYORK: {"ticket_delivery": {"mode": "ARCHIVE_ONLY", "outcomes": [
  {"symbol": "EURUSD", "cycle_state": "WATCH", "delivery_state": "NOT_APPLICABLE", ...},
  {"symbol": "GBPUSD", "cycle_state": "WATCH", "delivery_state": "NOT_APPLICABLE", ...} ]}}
```

The GBPUSD `ASIAN_LONDON` decision was a real, naturally-occurring READY signal
(`ready_at: "2026-09-08T07:15:00+00:00"`, `LOWER_SWEEP_STRICT_PENETRATION`, real
rendered entry/stop/targets visible in the strategy report portion of the same log
line) -- not manufactured, not forced. By the time this scheduled run reached
`ticket_delivery` processing (evaluation_time `08:30:20Z`), the signal was 75 minutes
old, past the signed 60-minute catch-up bound -- so the catch-up gate correctly
rejected ticket registration while the decision itself was still archived. This is
real, live proof the newly-wired catch-up gate works correctly against genuine
production data, not just synthetic tests.

**2. One additional read-only, proposal-only manual invocation** (`python
scripts\run_post_asian_pilot.py --once --json`, run directly rather than waiting ~7
minutes for the next OS trigger, per this task's own allowance) at `08:39:04Z`
confirmed continued correct operation: `exit code 0`, GBPUSD had since rolled to a
fresh `WATCH` (a new M15 candle closed between the two runs, correctly superseding the
earlier stale READY -- ordinary strategy behavior, not a ticket_delivery concern), and
the archive for GBPUSD ASIAN_LONDON 2026-09-08 recorded a correction (append-only,
original preserved) rather than an overwrite.

**Archive path and decision state, verified directly from disk:**

```
journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/GBPUSD/ASIAN_LONDON/2026/2026-09-08.json
journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/GBPUSD/ASIAN_LONDON/2026/2026-09-08.correction-001.json
journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/EURUSD/ASIAN_LONDON/2026/2026-09-08.json
journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/EURUSD/ASIAN_LONDON/2026/2026-09-08.correction-001.json
journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/EURUSD/ASIAN_LONDON/2026/2026-09-08.correction-002.json
journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/{EURUSD,GBPUSD}/LONDON_NEWYORK/2026/2026-09-08.json
```

**Real delivery journal, read directly** (`journal/ticket_delivery/state/delivery_records.json`):
all four real logical tickets present, every one `"state": "NOT_APPLICABLE"` --
critically, GBPUSD `ASIAN_LONDON` shows NO `READY_TO_DELIVER` record anywhere,
confirming the catch-up-rejected READY never registered a deliverable ticket, exactly
per the approved contract ("do not create a ticket for a rejected catch-up attempt").

### IDEMPOTENCY_AND_CONCURRENCY (real data)

The correction-numbered files above are direct, real proof that archiving the same
`(symbol, cycle, trading_date)` occurrence multiple times across real scheduled/manual
runs converges correctly: identical content is a no-op, genuinely changed content
(a new decision snapshot/reason code on a later poll) produces a numbered correction
file while the original stays byte-identical -- this is the pre-existing
`report_archive.write_report()` guarantee (Addendum 1), now proven against real
production data rather than only synthetic tests.

### ZERO_NETWORK_PROOF (real run)

`deliver=None` unconditionally for both `ARCHIVE_ONLY` and `MESSAGE_DELIVERY` (static
source check, unchanged this pass) -- the real scheduled/manual runs above made zero
Telegram calls by construction, not merely by the absence of configured credentials.
No broker/MT5 order-submission call exists anywhere in `src/ticket_delivery/` (AST
scan, `tests/test_ticket_delivery_execution_boundary.py`, re-verified this pass to
still pass with the two files this task modified).

### Documentation updated this addendum

- `config/ticket_delivery.yaml` -- signed `policy:` block added, `mode: ARCHIVE_ONLY`,
  status-history header comments.
- `docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md` -- approval
  addendum (original alternatives table preserved unchanged).
- `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md` -- status header and
  acceptance checklist updated to reflect activation + real evidence; catch-up
  checklist item flipped from unchecked/unsigned to checked/wired-and-evidenced.
- `docs/plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md` -- Phase 2 status
  row updated.
- `PROJECT_STATUS.md` -- new dated entry (see below).
- This document (Addendum 5).

### Not implemented / not activated this addendum

- `MESSAGE_DELIVERY` remains inert and unauthorized -- no real Telegram transport
  constructed, no real send attempted.
- WP7 (real Telegram send, a natural READY ticket actually DELIVERED, not merely
  observed-and-correctly-rejected) not started.
- No strategy YAML, installed scheduler task, or execution/broker configuration file
  modified.
- No positions modified, no broker order sent, no push.

### Safety confirmation (addendum 5)

```
strategy files modified                = 0
execution/authorization files modified = 0
scheduler task files modified          = 0 (.bat / Task Scheduler definitions untouched; read-only re-inspection only)
broker order-submission calls          = 0 (statically verified; execution-boundary scan re-passed against the 2 files this task modified)
real Telegram sends                    = 0 (deliver=None unconditionally for every mode; zero mock/real transport in this call chain)
real MT5/broker calls from ticket_delivery = 0
config/ticket_delivery.yaml shipped mode = ARCHIVE_ONLY (owner-authorized 2026-09-08)
real_demo_orders                       = 0
real_live_orders                       = 0
positions modified                     = 0
local commit made                      = yes (checkpoint only, not pushed)
```

---

## Addendum 6 (2026-09-08): governance reconciliation + runtime evidence retention + WP7 preflight

Baseline: HEAD `6ed1cfb` (Addendum 5's commit, confirmed synchronized with `origin/main`
at task start). Scope: `AG_STAGE1_GOVERNANCE_RECONCILIATION_AND_WP7_PREFLIGHT_V1` --
governance cleanup and WP7 architecture preflight only. **Does not activate
MESSAGE_DELIVERY, does not send any Telegram message, does not close Stage 1.**

### M0A -- auto-commit/auto-push investigation

`git reflog show refs/remotes/origin/main` showed "update by push" for every commit in
this session's history, including two commits from the immediately prior task
(`5676e89`, `6ed1cfb`) that this session never explicitly invoked `git commit` or
`git push` to create. Investigated the smallest plausible repository-local sources
first, all negative:

- `git config core.hooksPath` -- unset (no custom hooks path).
- `.git/hooks/` -- contains only Git's own inert `*.sample` files, no active hook.
- `git config --show-origin --get-regexp '.*'` -- no `postCommitCommand`, no
  auto-sync/auto-push key anywhere in system/global/local git config.

Found the actual cause outside the repository, at the VS Code user-settings and
extension level (read-only inspection, `%APPDATA%\Code\User\settings.json`):

- `git.enableSmartCommit: true` -- VS Code's "Commit" action, if invoked with nothing
  staged, stages and commits ALL changes automatically. This explains a commit
  appearing without an explicit `git add` + `git commit` sequence, IF something
  invoked VS Code's commit action.
- `chat.tools.terminal.autoApprove: {"git push": true, "git reset": true, "git
  rev-parse": true, ...}` -- a GLOBAL setting that pre-approves `git push` (among
  others) for ANY chat/agent tool's terminal command, removing the human-confirmation
  step that would otherwise block an unintended push.
- Multiple OTHER agent-capable VS Code extensions are installed in this same profile
  and workspace (`alibaba-cloud.tongyi-lingma` -- whose own settings explicitly
  allowlist `git` in `Lingma.aI Chat.commandAllowlistInAgentMode` for its autonomous
  agent mode; plus `amazonwebservices.amazon-q-vscode`, `google.gemini-cli-vscode-ide-companion`,
  `openai.chatgpt`, `danielsanmedium.dscodegpt`, `vizards.deepseek-v4-for-copilot`),
  any of which could independently operate on this same repository checkout with its
  own terminal/git access, using the same local git identity (`user.name`/`user.email`
  are global, not per-extension, so a commit made by a different extension is
  indistinguishable by author from one made by this session).

**CAUSE_IDENTIFIED = YES** (environment-level, not repository-level): the combination
of (a) other installed, agent-capable extensions with independent terminal/git access
in this same workspace, and (b) a global VS Code setting that pre-approves `git push`
for chat/agent tool calls. Neither is a repository-local setting and neither can be
safely changed from within this task without touching the user's machine-wide
configuration or disabling extensions the owner installed deliberately -- per this
task's own instruction, that was NOT attempted.

**Corroborating evidence this session was never the source:** when this session's own
Bash tool attempted `git push` (to test the mitigation below), Claude Code's own
permission-classifier layer blocked it outright ("Permission for this action was denied
by the Claude Code auto mode classifier") -- an independent safety layer this session
cannot bypass, confirming this session has never had unmediated push capability.

**Mitigation implemented (repository-local, safe, reversible):** added
`scripts/git-hooks/pre-push` -- a hook that blocks every `git push` through this clone
unless the caller explicitly sets `AG_ALLOW_PUSH=1`, and set (repository-local, in
`.git/config`, not touching any global setting) `git config core.hooksPath
scripts/git-hooks`. This does not disable Smart Commit, does not touch the global
`chat.tools.terminal.autoApprove` setting, and does not disable any extension -- it
only adds a required, explicit opt-in for THIS repository's own push path, regardless
of which tool initiates it.

**Tested:** `git push` (no override) -> blocked, prints
`AG_PUSH_BLOCKED_BY_REPOSITORY_LOCAL_GUARD`, exit 1, nothing sent to origin (confirmed:
`git rev-parse HEAD origin/main` identical before and after the attempt). The explicit
override (`AG_ALLOW_PUSH=1 git push`) was NOT exercised end-to-end in this task (this
session's own push capability is separately blocked by the Claude Code classifier, as
above, and there was nothing new to push at that point in the task -- `HEAD ==
origin/main`); the hook's bypass logic is a single `if` on the environment variable and
was read-reviewed, not a complex path warranting a live-fire test that would itself
require pushing.

**AUTO_PUSH_CONTAINED = YES** (for this repository clone, going forward -- any push
through this checkout, from any tool, now requires the explicit opt-in). **The root
cause itself is NOT fixed** (it lives outside this repository) and is recorded as an
external governance blocker for the owner's awareness, not something a future agent
task can resolve by editing repository files.

**Caution for future agents:** during this investigation, a `grep` command
(unintentionally, scoped too broadly) echoed the real, live `TELEGRAM_BOT_TOKEN`/
`TELEGRAM_CHAT_ID` values from `src/.env` into this session's own tool output while
confirming the existing Telegram env-var naming convention. `src/.env` is confirmed
`.gitignore`d and was never tracked by git (`git ls-files src/.env` returns nothing),
so this did not leak into version control -- but it is a reminder to scope any future
`grep`/`cat` across the repository to explicitly exclude `.env`/`*.env` files. The
actual token/chat-id values are not reproduced anywhere in this document or any other
file this task touched.

### M0B -- roadmap reconciliation

`docs/plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md`'s "Current baseline"
section still described Stage 0 items (drawdown, timestamp ordering, fail-closed
reconciliation) as open blockers and FX scheduler overlap/restart/missed-run recovery
as unproven, even though the phase-by-phase table above it already correctly said
DONE/ARCHIVE-ONLY-ACTIVATED. Renamed the stale bullets to a new "Historical baseline
(superseded)" subsection, preserved verbatim as prior-state evidence (not deleted, not
rewritten), and replaced the "Current baseline" bullets with present-state prose that
matches the phase table and cites the specific evidence (real catch-up rejection,
signed policy, real scheduled-task confirmation). Added the exact
`STAGE_N = ...` classification block this task specified, with each line verified
against real repository evidence rather than pasted verbatim (e.g. `STAGE_3A_CHART_ASSISTANCE
= PARTIAL` was confirmed by grepping for `NO_REGISTERED_STRATEGY_MATCH` -- present only
in docs, not in any `.py` file, while the underlying analysis-chain advisory skills DO
exist; `STAGE_4_ECONOMIC_VALIDATION = FOUNDATION_PRESENT` was confirmed by the real
existence of `src/performance/{calculator,models}.py` and its adapters).

### M0C -- runtime journal evidence-retention policy

`journal/ticket_delivery/` is (correctly) `.gitignore`d -- Git is not the
evidence-retention layer for this mutable runtime state. Defined and implemented the
minimal retention architecture:

```
journal/ticket_delivery/ (local, mutable, gitignored, primary runtime state)
    |
    v  scripts/ticket_delivery_evidence.py export  (on demand / periodic, manual for now)
artifacts/ticket_delivery_evidence_exports/<UTC-timestamp>/  (immutable, one directory per export)
    |-- manifest.json  (SHA-256 + size per file, application_release, repository_head,
    |                    export_timestamp_utc, ticket_delivery mode + policy VALUES --
    |                    never a secret)
    `-- files/...       (byte-for-byte copies)
```

`artifacts/` already IS this repository's established convention for committed,
durable evidence (71 pre-existing tracked files under `artifacts/` -- backtests,
readiness snapshots, validation evidence) -- reused rather than inventing a parallel
subsystem. Committing a given export to git (or not) remains an operator decision per
export, same as the repository's existing `artifacts/` convention; this task does not
force every export into git automatically.

**Retention specification:**

| Aspect | Value |
|---|---|
| Primary runtime location | `journal/ticket_delivery/` (local, mutable, gitignored) |
| Backup/evidence destination | `artifacts/ticket_delivery_evidence_exports/<export_id>/` (local, immutable per export; may additionally be committed to git at operator discretion, matching existing `artifacts/` convention) |
| Backup frequency | Manual/on-demand this pass (`python scripts/ticket_delivery_evidence.py export`); a scheduled periodic export was NOT installed this task (no new scheduled task was added, per this task's scope boundary against modifying installed scheduler tasks) |
| Retention period | Not time-bounded by this tool -- each export is a separate, permanently immutable directory; pruning old exports is an explicit future operator decision, not automated here |
| Restore process | `python scripts/ticket_delivery_evidence.py verify-restore <export_dir>` -- restores into an isolated OS temp directory (never into `journal/ticket_delivery/`), recomputes every file's SHA-256, compares against the manifest, reports PASS/FAIL |
| File-integrity verification | SHA-256 + byte size, both recomputed and compared on restore |
| Corruption detection | Proven by test: a single-byte content change or a missing exported file is caught (`test_verify_restore_detects_a_corrupted_exported_file`, `test_verify_restore_detects_a_missing_exported_file`) |
| Access permissions | Inherits the local filesystem's existing permissions (same as the rest of the repository/journal) -- no new permission model introduced |
| Immutable evidence export | Enforced by construction: `export()` refuses to overwrite an existing export directory (`EvidenceExportError`), proven by a test that freezes the clock to force a name collision |
| Checksum generation | SHA-256 per file, `hashlib.sha256`, streamed in 1 MiB chunks |
| Evidence naming/versioning | `<UTC-timestamp-microsecond-precision>` directory names under the export root -- monotonically distinguishable, no two exports can collide except at exact microsecond-identical clock values (tested) |
| Off-machine/off-box backup | **DEFERRED, not built this pass** -- genuinely out of "smallest safe capability" scope; requires an owner infrastructure decision (cloud storage, network share, etc.) this task cannot make unilaterally. Recorded here as an explicit known gap, not silently omitted. |

### Evidence export and restore -- implementation and proof

New: `scripts/ticket_delivery_evidence.py` (`export()`/`verify_restore()`, CLI
`export`/`verify-restore` subcommands) and `tests/test_ticket_delivery_evidence_export.py`
(14 tests, all synthetic -- never touch the real `journal/ticket_delivery/` directory
except the one deliberate real-data export described below). Read-only relative to the
source; never sends a network request (statically verified: no `requests.`/`urllib.request`/
`socket.socket`/`http.client` reference anywhere in the module, test-enforced); never
reads or persists `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` or any other secret (verified
by test that the manifest text never contains those substrings).

Fail-closed behavior proven by test: missing source directory raises
`EvidenceExportError`; an empty source directory raises rather than producing a
misleadingly-empty manifest; a mid-copy `OSError` on any individual source file aborts
the WHOLE export and removes the partially-written directory (no partial export is
ever left on disk); a forced timestamp collision (clock frozen in test) raises rather
than silently overwriting a prior export.

**One real export was performed against the live `journal/ticket_delivery/` directory**
this pass (read-only; the source journal is unchanged, confirmed by content
comparison before/after):

```
export_dir: artifacts/ticket_delivery_evidence_exports/20260908T091756781644Z/
file_count: 20
application_release: AG_TRADE_ASSISTANT_V1_0_3
repository_head: 6ed1cfb...
ticket_delivery.mode: ARCHIVE_ONLY
```

**Restore-verification was run against that real export:** `passed: true`,
`file_count: 20`, zero checksum mismatches, zero missing files, restored into an
isolated OS temp directory that was cleaned up afterward.

### M1-preflight -- WP7 architecture review (verified from code, not inferred)

| Question | Answer (verified from code) |
|---|---|
| How will a logical ticket become a Telegram request? | `fx_cycle_integration.process_pair_result()`'s READY path: archive -> catch-up gate -> `render_informational_ticket()` -> `delivery_store.ensure_ready_to_deliver()` -> `format_message_text(render_result.payload)` -> caller-injected `deliver(ticket_id, message_text)`. Currently `deliver=None` unconditionally in `scheduler_integration.py` for every mode (structural zero-network guarantee) -- WP7 would supply a real closure over `telegram_adapter.deliver_informational_ticket()`. |
| Where is `RetryPolicy` instantiated? | `scheduler_integration.py::load_integration_config()`, from the signed `policy:` block, stored on `TicketDeliveryIntegrationConfig.retry_policy`. |
| Where will retries actually be scheduled? | **NOT YET RESOLVED -- the key open WP7 architecture question.** `RetryPolicy` is constructed but never consumed anywhere (`grep` for `retry_policy`/`.should_retry(` outside its own definition and the config dataclass returns nothing else). `telegram_adapter.deliver_informational_ticket()` makes exactly ONE send attempt per call; `mark_failed_retryable()` only flips persisted state and releases the claim lock -- nothing re-invokes delivery afterward. The only existing re-trigger mechanism is the next scheduled FX cycle tick (~15 minutes), which does not match the signed policy's 30s/60s retry cadence. WP7 must explicitly decide and implement one of: (a) an in-process wait-and-retry loop within a single scheduled invocation (extends that invocation's runtime by up to ~90s, still well inside the 15-minute window), or (b) explicitly redefine "retry" as "the next scheduled tick's natural re-evaluation" (coarser than the signed 30s/60s, would require a policy re-approval or an explicit documented deviation) -- see the WP7 authorization packet for this open question, not resolved by this task. |
| Where is delivery state persisted? | `TicketDeliveryStore` (`delivery_store.py`) over `runtime_state.store.JsonKeyValueStore`, on-disk JSON at `config.delivery_state_dir` (`journal/ticket_delivery/state/delivery_records.json` in production). |
| How is duplicate delivery prevented? | `claim_for_delivery()`'s atomic `O_EXCL` lock file plus a state-machine guard (only `READY_TO_DELIVER`/retryable states are claimable); `ensure_ready_to_deliver()`'s idempotent creation never produces a second record for the same `logical_ticket_id`. |
| How is a provider response stored? | `mark_delivered(logical_ticket_id, provider_response_id=...)` persists it on `DeliveryRecord.provider_response_id` (Telegram's `message_id`, proven by existing test reading the real on-disk record). |
| How will restart recovery work? | Already proven at the primitive layer (Addendum 1/2, unchanged): a fresh `TicketDeliveryStore` instance against the same `state_dir` after a restart sees the exact persisted state; a `DELIVERY_CLAIMED` record cannot be reclaimed while the lock file exists. No new WP7-specific recovery logic is required beyond wiring `deliver`. |
| How will a Telegram destination be authorized? | `TelegramDestinationConfig.from_values(bot_token, chat_id, authorized_chat_ids)` -- no defaults, explicit allow-list, rejects an unauthorized `chat_id` before any send is possible. **No `from_env()` convenience exists yet** for this class (unlike the separate, forbidden-import `authorization.config.TelegramGatewayConfig.from_env()`) -- WP7 will need a small, additive env-reading wrapper. The established env var NAMES already used elsewhere in this repo (`src/authorization/config.py`) are `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; `TELEGRAM_ALLOWED_USER_IDS` is a DIFFERENT, approval-gateway-specific concept (Telegram user IDs allowed to approve a trade) and must not be reused as the ticket_delivery destination allow-list. |
| What is the DISABLED rollback path? | `config/ticket_delivery.yaml`'s `mode: DISABLED` -- one-line, unconditional, never reads or requires the `policy:` block. Already tested. |
| Can any delivery path reach broker execution? | No -- re-verified this pass: `tests/test_ticket_delivery_execution_boundary.py` (4 tests, AST-based, directory-wide scan of `src/ticket_delivery/`) still passes with zero forbidden imports/calls. |

### Freshness gate ordering (re-confirmed, unchanged)

Verified the actual code ordering matches the required
`natural READY -> ready_at -> freshness check -> ticket registration -> delivery`
sequence, not the reverse: `fx_cycle_integration.process_pair_result()`'s catch-up gate
runs strictly BEFORE `render_informational_ticket()`/`ensure_ready_to_deliver()` (see
Addendum 5) -- there is no code path that registers a ticket or calls `deliver` before
the catch-up check for a READY pair. The real GBPUSD stale-signal evidence from
Addendum 5 remains correctly classified as a catch-up REJECTION, not a delivery --
this addendum does not reclassify it.

### Execution boundary (re-verified)

`tests/test_ticket_delivery_execution_boundary.py` -- 4 passed. No file created this
task references `execution.*`, `mt5.management_gateway`, `mt5.mt5_gateway`,
`authorization.mt5_execution_handler`, `authorization.telegram_gateway`, or any
`order_send`/`order_check`-shaped call.

### Test results (this addendum)

```
pytest tests/test_ticket_delivery_evidence_export.py -q          -> 14 passed
pytest tests/test_ticket_delivery_execution_boundary.py -q       -> 4 passed
git diff --check                                                  -> clean (CRLF warnings only)
```

Broader ticket-delivery/authorization/Telegram/FX-pilot regression not re-run in full
this addendum (no production `src/ticket_delivery/` behavior was changed this task --
only a new, additive, standalone evidence-export script and documentation were added);
Addendum 5's 334-passed baseline remains the last full confirmation of that surface.

### Not implemented / not activated this addendum

- `MESSAGE_DELIVERY` was NOT activated. No real, synthetic, or test-only Telegram
  message was sent. No `TelegramClient`/`TelegramDestinationConfig` was constructed
  against a real bot token this task.
- No broker/MT5/Bybit/Binance/MEXC order of any kind was placed or attempted.
- No strategy YAML, strategy registry, session/risk parameter, or Demo/live
  authorization was changed.
- No scheduled task (Task Scheduler) was installed, modified, or removed -- the
  periodic evidence-export capability exists as a manual CLI command only.
- The WP7 retry-scheduling architecture question above was identified and documented,
  not resolved or implemented.
- Off-machine/off-box backup destination was not implemented (deferred, owner
  infrastructure decision).

### Safety confirmation (addendum 6)

```
strategy files modified                = 0
execution/authorization files modified = 0
scheduler task files modified          = 0
broker order-submission calls          = 0 (statically verified, unchanged surface)
real Telegram sends                    = 0
synthetic Telegram sends               = 0
MESSAGE_DELIVERY activated             = NO
secrets committed to git               = 0 (src/.env confirmed gitignored/untracked;
                                             no secret value appears in any file this
                                             task created or modified)
positions modified                     = 0
push performed by this session         = 0 (blocked by Claude Code's own classifier;
                                             repository-local pre-push guard also now
                                             in place for any future attempt)
```
