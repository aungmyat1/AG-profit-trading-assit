# AG Panel R5C Reconciliation and Uncertain-Submission Recovery -- Status (2026-09-23)

R5C_BASE_SHA = `87e2da798f827caf95e8c6e58916b394641c98fb` (PANEL_R5B_R1, frozen,
independently reaudited).

Mission: the smallest safe reconciliation layer that recovers an execution decision's
durable state after restart or uncertain submission from broker-observation evidence,
without ever creating a duplicate broker submission. R5C is `OBSERVE -> MATCH ->
CLASSIFY -> RECONCILE`, never `OBSERVE -> NOT_FOUND -> RESUBMIT`.

## P1 -- Existing authority (discovery, before designing anything)

- `execution.crypto_reconciliation.reconcile()` -- the repository's own canonical
  reconciliation SHAPE: a pure function over caller-supplied evidence, returning typed,
  fail-closed outcomes (`STATE_CONFIRMED_OPEN`/`STATE_CONFIRMED_ABSENT`/
  `STATE_AMBIGUOUS`), never a bare `Optional` collapsing "found" and "lookup failed"
  into the same falsy shape. R5C's own outcome vocabulary mirrors this one-for-one
  (`STATE_MATCHED`==`CONFIRMED_OPEN`, `STATE_NOT_FOUND`==`CONFIRMED_ABSENT`,
  `STATE_AMBIGUOUS`==`AMBIGUOUS`), plus two outcomes that module's crypto-only shape
  never needed: `STATE_BROKER_UNAVAILABLE` (a lookup itself failed) and
  `STATE_CONFLICT` (a persisted broker ID disagrees with observed evidence).
- `execution.executor._reconcile_via_broker()` -- the FX/MT5-side precedent for this
  exact problem (crash-window reconciliation), already reusing `mt5.account.positions()`
  / `mt5.deals.deals_for_symbol()` and a broker-comment identity tag
  (`_comment_tag(command_id)` = `f"AGT:{command_id}"[:31]`). Lives inside
  `execution/executor.py`, which also contains `order_open`/`order_send`-adjacent code
  -- R5C must never import this module (P6).
- `execution.lifecycle.reconcile_open_positions()` -- the second precedent, and the one
  R5C's own injection pattern is modeled on: broker lookups are INJECTED callables
  (`positions_lookup`/`deals_lookup`), never imported directly, keeping the module
  itself free of any MT5/write-capable import. It also reads the same `AGT:` tag
  (`_COMMENT_TAG_PREFIX`/`_extract_command_id_from_comment`). This module is itself
  read-only (no `order_send`/`close_position`/`order_open` in its own source), but it
  is a caller of write-capable modules elsewhere, so R5C still does not import it --
  the tag convention was reproduced, not imported, for full import-graph isolation
  (P6's "isolate R5C behind a read-only adapter" applied maximally).
- `execution.durable_idempotency` (R5B-R1, frozen) -- `DurableExecutionRecord`
  (`decision_id`, `fingerprint`, `broker_order_id`, `state`, `command_id`),
  `DurableExecutionStore.transition()`, `ALLOWED_TRANSITIONS`, `is_retry_safe()`. No
  parallel execution-identity or state-machine concept was introduced; R5C only reads
  and, for one specific fail-closed case, calls the EXISTING `transition()`.
- `owner_decision.bridge` -- `command_id = f"OWNER_DECISION:{decision_id}"` on the
  `AUTHORIZED` path; this is the `command_id` R5C's comment-tag matching expects to
  find on `DurableExecutionRecord.command_id`.

No parallel execution architecture was created.

## P2/P3 -- Responsibility and contract

`execution.reconciliation.reconcile_decision(store, decision_id, *, symbol,
positions_lookup, deals_lookup) -> ReconciliationResult`. Outcomes: `STATE_MATCHED`,
`STATE_NOT_FOUND`, `STATE_AMBIGUOUS`, `STATE_BROKER_UNAVAILABLE`,
`STATE_EVIDENCE_INSUFFICIENT`, `STATE_CONFLICT`. `STATE_NOT_FOUND` is never collapsed
into "safe to retry" -- it is a terminal report for that call, never a trigger for
resubmission, and never mutates the durable record.

## P4 -- Identity matching

Matching requires an EXACT equality between the observed broker record's `comment`
field and `comment_tag_for(record.command_id)` (`"AGT:" + command_id`, truncated to
MT5's 31-character comment limit -- reproduced byte-for-byte from
`execution.executor._comment_tag`). This is STRICTER than executor.py's own `tag in
comment` substring check (a deliberate strengthening, not a weakening -- being more
conservative can only reduce false matches). If more than one DISTINCT broker record
(by ticket) matches the same tag, the outcome is `STATE_AMBIGUOUS`, never an arbitrary
pick (P8). Weak heuristics (symbol/volume/direction/timestamp proximity alone) are
never used as a substitute for tag identity.

**Inherited limitation, documented, not fixed** (out of this bounded package's scope --
fixing it means editing `execution.executor`/`execution.lifecycle`'s own tag
convention): a long `decision_id` (e.g. a UUID) embedded in `command_id =
f"OWNER_DECISION:{decision_id}"` may be truncated by the 31-character comment limit,
which could in principle let two different decision_ids collide on the same truncated
tag. R5C does not compound this risk (exact-equality matching, multi-match ->
`AMBIGUOUS`) but cannot retroactively eliminate it either.

## P5 -- State-aware reconciliation

`RECONCILIATION_APPLICABLE_STATES = {SUBMISSION_PENDING, SUBMISSION_UNKNOWN,
BROKER_ACCEPTED, RECONCILED}`. `PREPARED`/`AUTHORIZED` (nothing was ever submitted) and
`REJECTED` (terminal, never resurrected) are deliberately out of scope --
`STATE_EVIDENCE_INSUFFICIENT` with a `NOT_APPLICABLE_FROM_STATE:<state>` reason code, a
documented scope boundary, not an oversight.

- **`SUBMISSION_PENDING`**: a deterministic, non-conflicting `MATCHED` advances
  `SUBMISSION_PENDING -> BROKER_ACCEPTED` (attaching the observed ticket as
  `broker_order_id`) -- an edge R5B-R1's frozen `ALLOWED_TRANSITIONS` ALREADY permits;
  no lifecycle extension was needed. `NOT_FOUND`/`AMBIGUOUS`/`BROKER_UNAVAILABLE`/
  `EVIDENCE_INSUFFICIENT` never mutate the record -- it stays `SUBMISSION_PENDING`,
  never returns to `AUTHORIZED`, never triggers a resubmission (there is nothing in
  this module that could -- see P10).
- **`SUBMISSION_UNKNOWN`**: same `MATCHED` advance is legal too
  (`SUBMISSION_UNKNOWN -> BROKER_ACCEPTED` is already in R5B-R1's frozen graph) --
  **no architectural conflict was found; no lifecycle extension was required or made.**
  Every non-`MATCHED` outcome leaves it exactly at `SUBMISSION_UNKNOWN`
  (reconciliation-required, never auto-resolved by absence).
- **`BROKER_ACCEPTED`**: a consistent `MATCHED` (same or newly-confirmed ticket)
  advances `BROKER_ACCEPTED -> RECONCILED` (also an existing legal edge). A `CONFLICT`
  (a different ticket observed than the one already persisted) fails closed -- the
  record is left completely unchanged, never rewound, never overwritten.
- **`RECONCILED`**: re-reconciling with the same evidence reaffirms `RECONCILED ->
  RECONCILED`, R5B-R1's own documented same-state idempotent no-op -- not a second,
  divergent transition.

## P6 -- Broker observation boundary

`positions_lookup`/`deals_lookup` are injected callables, matching
`execution.lifecycle.reconcile_open_positions`'s own idiom exactly. `execution.
reconciliation`'s own import graph (verified by AST, see P10/tests) is exactly
`__future__`, `dataclasses`, `typing`, `execution.durable_idempotency` -- no `mt5.*`,
no `execution.executor`, no `execution.mt5_gateway`, no `execution.coordinator`, no
`authorization.mt5_execution_handler`. Production wiring (passing the real
`mt5.account.positions`/`mt5.deals.deals_for_symbol` as these callables) is documented
in this module's own docstring but not implemented -- no HTTP route, scheduler, or CLI
entry point was added in this package.

## P7 -- Recovery after restart (verified by test)

`test_restart_then_successful_reconciliation`: instance #1 prepares a decision through
`SUBMISSION_PENDING` and is discarded; instance #2, freshly opened, reconciles against
matching evidence and advances to `BROKER_ACCEPTED` with the observed ticket -- no
duplicate submission occurred (reconciliation has no submission path to duplicate
through). `test_restart_then_unresolved_reconciliation_preserves_uncertainty`: restart
+ no evidence -> `NOT_FOUND`, record unchanged, still `SUBMISSION_PENDING`, still
non-retry-safe. `test_broker_unavailable_never_treated_as_not_found`: a lookup
exception -> `BROKER_UNAVAILABLE`, record unchanged (restart + broker-unavailable
fails closed by the same mechanism).

## P8 -- Conflicting broker identity (verified by test)

`test_conflicting_broker_id_fails_closed`: an already-persisted `broker_order_id`
("111") observed against a different ticket ("222") under the identical tag -> outcome
`CONFLICT`, persisted value stays "111". `test_ambiguous_multiple_distinct_broker_records`:
two distinct tickets matching the same tag -> `AMBIGUOUS`, never an arbitrary pick.

## P9 -- Reconciliation idempotency (verified by test)

`test_repeated_reconciliation_is_idempotent`: three calls with unchanged evidence
converge `SUBMISSION_PENDING -> BROKER_ACCEPTED -> RECONCILED -> RECONCILED`
(the third call is a no-op reaffirmation) -- `execution_id`/`broker_order_id` identical
across all three; no duplicate lifecycle effect, no identity mutation.

## P10 -- No-submit proof

`tests/test_execution_reconciliation_no_submit.py`:
- Static AST sweep: the module's entire import graph is
  `{__future__, dataclasses, typing, execution.durable_idempotency}` -- no forbidden
  module (`execution.executor`, `execution.mt5_gateway`, `execution.coordinator`,
  `mt5.management_gateway`, `authorization.mt5_execution_handler`,
  `authorization.telegram_gateway`, `assistant.commands`) appears anywhere.
- Text sweep: no occurrence of `order_send(`, `order_check(`, `.submit(`,
  `place_order(`, `execute_order(`, or `user_confirmed=True`/`user_confirmed = True`.
- Signature proof: `reconcile_decision`'s own parameters are exactly `{store,
  decision_id, symbol, positions_lookup, deals_lookup}` -- there is no
  `execution_handler`-shaped parameter to plug a submission callable into, unlike e.g.
  `api.execution_service.authorize_demo_execution`.
- Dynamic proof: a full, real `MATCHED` reconciliation cycle runs with an unrelated
  `order_send`-named `MagicMock` in scope; `assert_not_called()` passes.

## P11 -- Proposal-dedup defect

Not repaired here. Reconciliation depends only on `decision_id` (already unique per
owner decision, assigned upstream of and independent from the proposal-candidate
dedup defect) and broker-observation evidence -- it has no dependency on proposal-layer
deduplication behavior. `CLASSIFICATION` is therefore NOT
`BLOCKED_PROPOSAL_DEDUP_DEPENDENCY`. The known failure
(`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`)
reproduces separately and unchanged (see Tests below), confirming no interaction.

## P12 -- Concurrency boundary

R5C claims nothing beyond what R5B-R1 already guarantees: same-process thread
serialization via `DurableExecutionStore.transition()`'s own per-decision_id lock (R5C
calls that existing method; it introduces no locking of its own). Not established, and
not claimed: cross-process locking, cross-machine locking, distributed exactly-once,
or broker exactly-once execution. `reconcile_decision()` itself performs no locking of
its own beyond what the underlying `store.get()`/`store.transition()` calls already do.

## P13 -- Tests

`tests/test_execution_reconciliation.py` -- 14 focused tests covering deterministic
match, missing evidence, ambiguous evidence, broker-unavailable, conflicting ID,
restart+success, restart+unresolved, repeated-reconciliation idempotency, illegal
rewind remains blocked, retry-unsafe states remain retry-unsafe, plus the
`SUBMISSION_UNKNOWN` recovery path, the deal-entry-code discipline, and the
out-of-scope-state/no-record edge cases.

`tests/test_execution_reconciliation_no_submit.py` -- 4 focused tests (P10, above).

Progressive run order and results:
1. `pytest tests/test_execution_reconciliation.py tests/test_execution_reconciliation_no_submit.py tests/test_execution_durable_idempotency.py tests/test_execution_durable_idempotency_lifecycle.py -q` -> **52 passed**.
2. `pytest tests/test_api_owner_decision_auth.py tests/test_api_authorize_demo_auth.py tests/test_api_owner_decision.py tests/test_api.py -q` -> **58 passed**.
3. `pytest tests/test_owner_decision_bridge.py tests/test_proposal_envelope_execution_boundary.py -q` -> **23 passed**.
4. `pytest tests/test_proposal_envelope_adapters.py -k dedup -q` -> 1 failed
   (`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`),
   same pre-existing assertion documented against every prior baseline
   (R3/R4/R5A/R5A-R1/R5B/R5B-R1); unrelated to and untouched by this diff.

## P14 -- Guarantees, precisely stated

```
broker exactly-once execution   = NOT CLAIMED (requires R6's full reconciliation loop
                                   against a live terminal; this package only defines
                                   and tests the fail-closed classification logic over
                                   caller-supplied evidence)
automatic resubmission          = DISABLED (no code path in this module can submit
                                   an order; see P10)
automatic execution             = DISABLED
Demo execution                  = NOT AUTHORIZED BY R5C
Live execution                  = DISABLED (account.allow_live_trading untouched;
                                   this package never reads or checks it, having no
                                   execution path that would need to)
cross-process/cross-machine     = NOT ESTABLISHED (same-process thread serialization
locking guarantee                 only, inherited unchanged from R5B-R1)
```

## Isolation

New files only: `src/execution/reconciliation.py`,
`tests/test_execution_reconciliation.py`,
`tests/test_execution_reconciliation_no_submit.py`, this status document, and the
`PROJECT_STATUS.md` rolling-summary addition. No existing file was modified --
`git diff` against the frozen R5B-R1 SHA for `src/api/`,
`src/execution/durable_idempotency.py`, and every previously-audited file is empty.

## Next recommended package

`R5C_INDEPENDENT_REAUDIT`. R5D (actual MT5 Demo submission) remains explicitly out of
scope until that reaudit passes.
