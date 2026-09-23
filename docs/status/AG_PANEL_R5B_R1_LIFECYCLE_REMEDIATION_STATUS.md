# AG Panel R5B-R1 Execution Lifecycle Remediation -- Status (2026-09-23)

R5B_R1_BASE_SHA = `2ff13af2cc0fe3f46ce81c49d88dbb575f9442ba` (PANEL_R5B implementation,
independently audited `PANEL_R5B_INDEPENDENT_AUDIT_FAIL`).

Blocking finding: `DurableExecutionStore.transition()` validated only that the
requested target state was a member of `ALL_STATES`, never that the record's ACTUAL
current state legally permitted reaching it. The auditor demonstrated
`BROKER_ACCEPTED -> PREPARED` was silently accepted and persisted.

## P1 -- Derived canonical lifecycle (before coding)

No repository consumer of `DurableExecutionState`/`transition()`/`is_retry_safe()`
exists outside this module and its own tests (R5B is not yet wired into any HTTP route
or into `owner_decision.bridge`), so production semantics reduce to this module's own
prior comments plus the mission's canonical path. Derived graph:

```
PREPARED           -> {AUTHORIZED, REJECTED}
AUTHORIZED         -> {SUBMISSION_PENDING, REJECTED}
SUBMISSION_PENDING -> {SUBMISSION_UNKNOWN, BROKER_ACCEPTED, REJECTED}
SUBMISSION_UNKNOWN -> {BROKER_ACCEPTED, REJECTED}
BROKER_ACCEPTED    -> {RECONCILED}
REJECTED           -> {}   (terminal)
RECONCILED         -> {}   (terminal)
```

Rationale for each edge is in `ALLOWED_TRANSITIONS`'s own comment in
`src/execution/durable_idempotency.py`. `REJECTED` and `RECONCILED` are both terminal
exactly as the mission's own `ALLOWED_TRANSITIONS` skeleton showed
(`REJECTED: set()`, `RECONCILED: set()`). No transition was invented merely to make a
test convenient -- see the "test sequence fixes" note below for the one place this cut
the other way.

## P2 -- Transition policy

`ALLOWED_TRANSITIONS: Dict[str, frozenset]` -- an immutable mapping, current-state ->
allowed-target-states, checked in `transition()` before any mutation.
`InvalidStateTransition(RuntimeError)` -- a specific domain exception, added alongside
this module's existing `FingerprintConflict`/`IdempotencyStateUnavailable` convention,
not a generic `ValueError` (which remains reserved for the two pre-existing, unrelated
checks: unknown state name, and broker-id-attached-on-an-ineligible-state).

## P3 -- No rewinds (verified by test)

All eight mission-listed rewinds rejected with `InvalidStateTransition`:
`BROKER_ACCEPTED->PREPARED`, `BROKER_ACCEPTED->AUTHORIZED`,
`SUBMISSION_UNKNOWN->PREPARED`, `SUBMISSION_UNKNOWN->AUTHORIZED`,
`REJECTED->PREPARED`, `REJECTED->AUTHORIZED`, `RECONCILED->PREPARED`,
`RECONCILED->SUBMISSION_PENDING` -- `test_execution_durable_idempotency_lifecycle.py::test_rewind_rejected`
(parametrized, 8 cases).

## P4 -- Valid forward transitions (verified by test)

The full canonical path (`PREPARED->AUTHORIZED->SUBMISSION_PENDING->BROKER_ACCEPTED->RECONCILED`),
the uncertainty branch (`SUBMISSION_PENDING->SUBMISSION_UNKNOWN`), and every valid
rejection edge (`PREPARED|AUTHORIZED|SUBMISSION_PENDING|SUBMISSION_UNKNOWN -> REJECTED`)
each exercised as an individual test.

## P5 -- Same-state transitions

Decision: `STATE -> SAME_STATE` is an idempotent no-op, checked BEFORE consulting
`ALLOWED_TRANSITIONS` (`state != record.state and state not in
ALLOWED_TRANSITIONS[record.state]` -- the graph is never even looked up when the two
match). This is not a lifecycle rewind (the state does not change), so a terminal
state's empty transition set does not forbid re-affirming it --
`test_same_state_transition_is_idempotent_not_a_rewind` reaffirms `RECONCILED ->
RECONCILED` and confirms `execution_id`/`fingerprint`/`broker_order_id` are unchanged.
This also preserves the original R5B test's own expectation
(`test_broker_ids_attached_only_per_state_rules`'s "re-affirming the SAME
broker_order_id is not an error") without weakening it.

## P6 -- Atomic validate + write (no TOCTOU)

`runtime_state.store.JsonKeyValueStore`'s per-absolute-path `threading.Lock` (the
existing R5B locking primitive) wraps only a single `get()`/`put()` call, not a
read-validate-write SEQUENCE -- exactly the TOCTOU shape that store's own docstring
already names as the bug class it fixed for load-modify-save, recurring here one level
up. Fixed by mirroring that exact design (not inventing a different one): a new
per-`(state_dir, decision_id)` `threading.Lock`, held for the ENTIRE
read-validate-write sequence inside `transition()`. `create_or_get()`'s existing
O_EXCL claim-lock for first-writer-wins creation is untouched.

## P7 -- Conflict preservation (verified by test)

`test_invalid_transition_leaves_durable_record_unchanged`: captures the record before
an illegal `BROKER_ACCEPTED -> PREPARED` attempt, attempts it (raises
`InvalidStateTransition`), reloads the record, and asserts full equality (state,
fingerprint, `broker_order_id`, `broker_position_id`, `execution_id`, `command_id`,
`created_at`/`updated_at`) -- no partial mutation, because the validation happens
strictly before `self._put()` is ever reached.

## P8 -- Uncertain-state safety (reconfirmed)

`is_retry_safe(SUBMISSION_PENDING) == False`, `is_retry_safe(SUBMISSION_UNKNOWN) ==
False`, `is_retry_safe(BROKER_ACCEPTED) == False` -- unchanged by this remediation
(`RETRY_FORBIDDEN_STATES` was not touched).
`test_retry_safety_states_unchanged_by_remediation` reconfirms all three.

## P9 -- Broker-ID semantics (re-run, unchanged)

The original R5B broker-ID conflict test
(`test_broker_ids_attached_only_per_state_rules`) still passes verbatim in its
assertions (only its transition SEQUENCE was corrected -- see below) --
same-value re-affirmation is a no-op, a different value is rejected with
`ValueError`, and broker identity may only be attached while transitioning into a
`BROKER_ID_ELIGIBLE_STATES` member. The new lifecycle-legality check cannot be
bypassed by attaching a broker ID: the eligibility check and the transition-graph
check both run, in that order, before any write.

## P10 -- Restart safety (verified by test)

`test_illegal_rewind_remains_rejected_after_restart`: instance #1 advances a record to
`BROKER_ACCEPTED` and is discarded; instance #2, freshly opened against the same
`state_dir`, both preserves the advanced state AND rejects
`BROKER_ACCEPTED -> PREPARED` exactly as instance #1 would have -- the transition
graph applies equally to a record recovered from disk, since `ALLOWED_TRANSITIONS` is
a pure function of the persisted `state` field, not of any in-memory session state.

## P11 -- Concurrency (adversarial test)

`test_incompatible_concurrent_transitions_serialize_safely`: from `AUTHORIZED`, two
real threads race for `SUBMISSION_PENDING` (writer A) and `REJECTED` (writer B) --
both individually legal from `AUTHORIZED`. The per-decision_id lock (P6) serializes
them; whichever commits second is validated against the state the first one actually
left behind. Because `REJECTED` is also reachable from `SUBMISSION_PENDING`, both
orderings converge on the same final persisted state, `REJECTED` -- either directly
(B first), or via `AUTHORIZED->SUBMISSION_PENDING->REJECTED` (A first, B still legal
from `SUBMISSION_PENDING`) -- proving one coherent, legal serialized history results
regardless of scheduling, with no lost update and no corruption. No cross-machine
guarantee is claimed (this is a same-process, multi-thread test only, matching
`JsonKeyValueStore`'s own documented scope).

## P12 -- Durability claims corrected

The module and class docstrings now explicitly state: **atomic file replacement**
(inherited from `JsonKeyValueStore`'s temp-file + `os.replace`) and **restart
persistence under an ordinary process restart** are guaranteed; **power-loss
durability is NOT guaranteed**, because neither this module nor
`JsonKeyValueStore` calls `fsync` anywhere. Concurrency is explicitly scoped to
multiple threads within one process, not cross-process or cross-machine. No new
storage engine was introduced -- `JsonKeyValueStore` remains the sole persistence
backend.

## P13 -- No broker/HTTP changes (static sweep)

`git diff 2ff13af -- src/api/` -> empty (0 lines). AST/text sweep of the diff for
`order_send`, `mt5_gateway`, `execution.executor`, `user_confirmed=True` -> no
occurrence anywhere in the changed files (only in this module's own docstrings
describing what it does NOT do, unchanged from R5B). `ORDER_SEND_ADDED = NO`,
`MT5_SUBMISSION_ADDED = NO`, `HTTP route changes = NO`, `auth changes = NO`,
`Live authority changes = NO`, `auto execution changes = NO`.

## P14 -- Tests

`tests/test_execution_durable_idempotency_lifecycle.py` -- 21 focused tests covering
all 14 required points (valid transitions 1-5, rewind rejections 6-9 as one
parametrized test with 8 cases, conflict preservation 10, restart 11, concurrency 12,
retry-safety 13, broker-ID 14) plus two additional P5/graph-shape sanity checks.

**Test-sequence correction to the original R5B suite** (P1's own instruction: derive
the graph from production semantics, "do not invent transitions merely to make tests
convenient" -- applied here to the TESTS, not the graph): two original R5B tests
(`test_restart_preserves_identity_and_state`,
`test_broker_ids_attached_only_per_state_rules`) transitioned a freshly-created
(`PREPARED`) record directly to `SUBMISSION_PENDING`, which the ORIGINAL, unvalidated
`transition()` silently allowed. That direct edge is not part of the canonical graph
(the mission's own valid path requires `AUTHORIZED` first); both tests were corrected
to insert the legal `PREPARED -> AUTHORIZED` step, with every other assertion in both
tests left exactly as originally written. This is the one and only change to the
original R5B test file; no assertion's intent changed, only the lifecycle sequence
each test drives through.

## P15 -- Regression

`python -m pytest tests/test_execution_durable_idempotency.py
tests/test_execution_durable_idempotency_lifecycle.py -q` -> **34 passed**.

`python -m pytest tests/test_api_owner_decision_auth.py
tests/test_api_authorize_demo_auth.py tests/test_api_owner_decision.py
tests/test_api.py -q` (R5A/R5A-R1 auth boundaries) -> **58 passed**.

`python -m pytest tests/test_owner_decision_bridge.py
tests/test_proposal_envelope_execution_boundary.py -q` -> **23 passed**.

Known pre-existing failure recorded separately, not repaired here: `python -m pytest
tests/test_proposal_envelope_adapters.py -k dedup -q` -> 1 failed
(`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`), same
assertion already documented against every prior baseline (R3/R4/R5A/R5A-R1/R5B);
unrelated to and untouched by this diff.

## Isolation

Diff scope is exactly `src/execution/durable_idempotency.py` (modified),
`tests/test_execution_durable_idempotency.py` (two test sequences corrected, no
assertion intent changed), one new file
`tests/test_execution_durable_idempotency_lifecycle.py`, this status document, and the
`PROJECT_STATUS.md` rolling-summary addition. `src/api/app.py` and every other
previously-audited file are untouched.

## Next recommended package

`PANEL_R5B_R1_INDEPENDENT_REAUDIT`. R5C and R5D remain explicitly out of scope until
that reaudit passes.
