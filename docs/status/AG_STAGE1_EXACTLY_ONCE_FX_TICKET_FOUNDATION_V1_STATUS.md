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
