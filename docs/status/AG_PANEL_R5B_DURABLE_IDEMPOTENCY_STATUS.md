# AG Panel R5B Durable Execution Idempotency -- Status (2026-09-23)

R5B_BASE_SHA = `c94beb8e38928de25f105a086806f98ab7485c59` (PANEL-R5A-R1 implementation,
independently audited `R5A_R1_INDEPENDENT_AUDIT_PASS`, audit artifact
`7c68de5e457a32e0d57510c23ec195353492d263`, branch `panel-r5a-r1-legacy-execution-auth`).

Mission: establish durable execution identity and restart-safe idempotency as the
transactional foundation R5C (risk/execution gate), R5D (MT5 Demo submission), and R6
(broker reconciliation) will consume. This package submits no MT5 order, wires into no
HTTP route, and modifies no strategy or execution behavior.

## P1 -- Existing execution identity (discovery, before designing anything new)

```
proposal_id            == proposal_envelope.models.CanonicalProposal.proposal_envelope_id
    -> decision_id      == owner_decision.models.OwnerDecision.decision_id
                           ("the caller-supplied idempotency key" -- that module's own
                           docstring; already the canonical idempotency key for this
                           chain)
    -> execution/approval identity
         - owner_decision path:  owner_decision.models.ExecutionDecision (process-local
           only -- OwnerDecisionStore, R3/R4/R5A, frozen)
         - ticket path:          authorization.models.ExecutionApproval / approval_id
           (already durable -- authorization.store.ExecutionApprovalStore)
    -> command_id       == execution.models.TradeCommand.command_id
                           (owner_decision.bridge sets this to
                           f"OWNER_DECISION:{decision_id}" on the AUTHORIZED path)
    -> broker_order_id / broker_position_id -- NOT YET PRODUCED anywhere in this
                           repository; execution.models.OrderSendResult and
                           execution.adapter carry a raw MT5 ticket/result_reference,
                           but no existing contract names a durable, nullable
                           "broker_order_id" field on a pre-submission record.
```

No duplicate concept was introduced for anything that already exists above.
`execution_id` is the one genuinely new identifier this package mints, and it is
minted deterministically FROM `decision_id` (`execution_id_for()`), never randomly, so
re-deriving it after a restart reproduces the same value.

## P2 -- Existing persistence (discovery)

- `runtime_state.store.JsonKeyValueStore` -- one JSON file, atomic temp-file +
  `os.replace` write, per-absolute-path `threading.Lock` for same-process
  read/modify/write serialization, fails loudly (`StateStoreCorrupted`) on a corrupt or
  unreadable file rather than silently resetting to empty. Already the backing store
  for `authorization.store.ExecutionApprovalStore`'s own durable approval ledger.
- The O_EXCL exclusive-create claim-lock idiom, used identically in two places already:
  `authorization.store.ExecutionApprovalStore._try_acquire_lock` and
  `execution.journal.claim_command`. Proven cross-thread/cross-process-restart safe;
  claims are lock files that are never removed, so a restart never re-opens a claim.
- No SQLite, no database server, no new persistence mechanism exists anywhere in this
  repository's runtime path. Introducing one for this package alone would be a second,
  divergent persistence convention -- not done.

**Choice**: reuse `JsonKeyValueStore` for the mutable per-`decision_id` record, plus the
same O_EXCL lock-file idiom for atomic first-writer-wins creation. This is the smallest
durable mechanism consistent with the existing architecture -- literally the same two
primitives `ExecutionApprovalStore` already combines for the same kind of problem
(durable record + atomic one-time claim).

Atomicity/restart behavior inherited from `JsonKeyValueStore`: a write is atomic
(temp-file + `os.replace`, with bounded retry against transient Windows
`PermissionError`s); a restart simply re-opens the same on-disk file; a corrupt file
raises rather than silently resetting.

## P3/P4 -- Durable record and fingerprint

`execution.durable_idempotency.DurableExecutionRecord`: `execution_id`, `proposal_id`,
`decision_id`, `command_id` (nullable), `fingerprint`, `state`, `created_at`,
`updated_at`, `broker_order_id` (nullable), `broker_position_id` (nullable),
`failure_reason` (nullable) -- exactly P3's field list, using existing repository
identifiers wherever one exists.

`compute_execution_fingerprint()`: SHA-256 over `decision_id`, `proposal_envelope_id`,
`action`, `symbol`, `environment`, plus `execution.models.TradeCommand`'s own
execution-critical field vocabulary (`side`, `order_type`, `volume`, `entry`, `sl`,
`tp`, `risk_percent`) -- the same canonicalization convention
`authorization.integrity.compute_proposal_hash` already established
(`json.dumps(sort_keys=True, separators=(",", ":"))` + `hashlib.sha256`), not an
invented scheme. Deliberately excludes timestamps/actor/request-source (volatile,
would make an identical retry look different). Never uses Python's built-in `hash()`
(process-local, not durable/cross-restart) -- proven by
`test_fingerprint_never_uses_python_hash` (64 hex chars, deterministic across calls).

## P5 -- Durable uniqueness

`DurableExecutionStore.create_or_get()`: same `decision_id` + same fingerprint ->
returns the existing record unchanged. Same `decision_id` + a DIFFERENT fingerprint ->
raises `FingerprintConflict`, fail closed -- the original record is left untouched
(`test_conflicting_fingerprint_fails_closed`). This durable behavior is strictly an
upgrade over the current process-local `OwnerDecisionStore.put_if_absent()` (R3), which
has no fingerprint concept at all and would silently treat any two same-`decision_id`
calls as the same request regardless of content.

## P6/P7 -- State machine and crash-safety invariant

States: `PREPARED`, `AUTHORIZED`, `SUBMISSION_PENDING`, `SUBMISSION_UNKNOWN`,
`BROKER_ACCEPTED`, `REJECTED`, `RECONCILED` -- exactly the mission's own names; none
already existed as a canonical vocabulary elsewhere in the repository (checked
`authorization.models` state constants, `execution.lifecycle`, `execution.executor` --
all define a DIFFERENT, ticket/approval-scoped state machine, not this one).

R5B activates only `PREPARED` (create_or_get's default initial state) plus whatever a
test exercises via `transition()` (`AUTHORIZED`, `SUBMISSION_PENDING`,
`SUBMISSION_UNKNOWN`, `BROKER_ACCEPTED` are all reachable via `transition()`, proving
the contract, but no caller anywhere in this repository invokes them yet).

`is_retry_safe()` is the single authoritative answer to the crash-safety invariant:
`SUBMISSION_PENDING`, `SUBMISSION_UNKNOWN`, and `BROKER_ACCEPTED` are NEVER retry-safe.
This function only reports that answer -- it never itself submits, resubmits, or
contacts a broker; a later package (R5D) must consult it before ever resubmitting.

## P8/P9 -- Atomic create/claim and restart parity

`test_concurrent_duplicate_creation_produces_one_record`: 8 real threads racing
`create_or_get()` for the identical `decision_id` produce exactly one persisted record
(verified both via the returned `execution_id` set and by reading the raw on-disk JSON
file's key list). The O_EXCL lock ensures exactly one winner creates the record; every
loser polls (bounded, 200 attempts x 5ms) until the winner's write becomes visible,
then returns that same record -- never a second, independent one.

`test_restart_preserves_identity_and_state`: instance #1 creates a record and
transitions it to `SUBMISSION_PENDING`, then is discarded (simulating process exit);
instance #2, freshly constructed against the same `state_dir`, reads back the identical
`execution_id`, fingerprint, and state, and a subsequent `create_or_get()` with the same
fingerprint returns that same record rather than resetting or duplicating it.

## P10 -- Corruption / unavailability

Both fail closed as `IdempotencyStateUnavailable` (mapped internally from
`runtime_state.store.StateStoreCorrupted` for unreadable/malformed JSON content, and
from a raw `OSError` for a write-side failure such as a path component that is
actually a file rather than a directory) -- never interpreted as "no previous execution
exists". Covered by `test_persistence_unavailable_fails_closed` (blocked directory) and
`test_corrupted_persistence_fails_closed` (truncated JSON file), both on `get()` and on
`create_or_get()`.

## P11 -- Auth boundary regression

Both protected routes re-verified unchanged: `python -m pytest
tests/test_api_owner_decision_auth.py tests/test_api_authorize_demo_auth.py
tests/test_api_owner_decision.py tests/test_api.py -q` -> 58 passed. This package
touches neither `src/api/app.py` nor `require_owner_auth`.

## P12 -- No broker side effect

`execution.durable_idempotency` imports only `dataclasses`, `hashlib`, `json`, `os`,
`time`, `datetime`, `typing`, and `runtime_state.store` -- confirmed by AST walk (no
`execution.executor`, `execution.mt5_gateway`, `authorization.mt5_execution_handler`,
or `authorization.telegram_gateway` anywhere in the import graph). No occurrence of
`order_send`, `mt5_gateway`, `execution.executor`, or `user_confirmed=True` in the
module's executable code (only in its own docstring describing what it does NOT do).
No hardcoded secret. `BROKER_ORDER_SUBMITTED = NO`.

## P13 -- Tests

`tests/test_execution_durable_idempotency.py` -- 13 focused tests, covering all 12
required points (points 5 and 6 of the mission's own list -- "zero handler calls" /
"zero MT5 calls" on auth failure -- are P11's territory, already covered by the
existing R5A/R5A-R1 auth test files re-run above; this file's own 12-point coverage is
points 1-4 and 6-10 of the mission's P13 list plus the two additional determinism
checks below):

1. first execution identity persists
2. identical retry returns same record
3. same ID + conflicting fingerprint fails closed
4. restart preserves identity (combined with 5 in one test, same setup)
5. restart preserves state
6. concurrent duplicate creation produces one record (8 real threads)
7. persistence unavailable fails closed
8. corrupted persistence fails closed
9. SUBMISSION_UNKNOWN (and SUBMISSION_PENDING/BROKER_ACCEPTED) cannot be treated as
   retry-safe
10. broker IDs can be attached only according to state rules (and never silently
    overwritten with a different value)
11. transition() refuses to act on a decision_id that was never created (fail closed,
    not a silent no-op)
12. fingerprint is deterministic SHA-256, never Python's `hash()`, and changes with
    every execution-critical field

All tests use `tmp_path`-backed `DurableExecutionStore` instances; none touches
`journal/` or any real runtime ledger.

## P14 -- Existing dedup defect (not repaired here, not laundered away)

`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`
(`tests/test_proposal_envelope_adapters.py`) reproduces in isolation exactly as
before this change (`3 <= 1` assertion failure) -- confirmed unrelated to and untouched
by this package's diff. This package's own idempotency (decision-level,
execution-identity-level) is a SEPARATE defense from proposal-layer deduplication
(candidate/observation-level, upstream of any owner decision); fixing one is not a
substitute for the other, and both remain required before final broker activation.
Recorded here, not silently deferred without mention.

## P15 -- Durability guarantees, precisely stated

**Guaranteed by this package:**
- Durable execution INTENT identity: the same `decision_id` + same fingerprint always
  resolves to the same `execution_id`/record, across a process restart, on this one
  machine's filesystem.
- Fail-closed handling of an unreadable/corrupt/unavailable persistence layer -- never
  silently treated as "no prior execution", which could otherwise cause a duplicate
  broker submission downstream.
- Fail-closed handling of a fingerprint mismatch on an already-used `decision_id` --
  never silently reused for a different trade.
- Concurrency safety for multiple threads within ONE process racing the same
  `decision_id` (matches this repository's actual deployment shape: one
  execution-runtime process owns the one MT5 terminal connection -- same documented
  scope boundary as `runtime_state.store.JsonKeyValueStore`'s own docstring).
- A reserved, never-auto-retried `SUBMISSION_UNKNOWN` state for later packages to use.

**NOT guaranteed, and not claimed, by this package:**
- Broker exactly-once execution. That requires actually calling MT5 and reconciling
  against its own order/position/history query surface -- R6's job, not implemented
  here.
- Cross-machine or multi-instance safety. Nothing in this repository runs this store
  from more than one process today; this is a documented scope boundary, matching
  `JsonKeyValueStore`'s own.
- Any statement about what R5C's risk gate or R5D's actual MT5 submission will do with
  this record -- this package defines the contract they will consume, not their
  behavior.

The correct summary phrase for this package is: **durable execution intent identity +
fail-closed uncertain-submission handling** -- not "exactly-once broker execution".

## Isolation

New files only: `src/execution/durable_idempotency.py`,
`tests/test_execution_durable_idempotency.py`, this status document, and the
`PROJECT_STATUS.md` rolling-summary addition. No existing file was modified. No
`wp/v2-3c-asian-sweep-remediation` state or other worktree's content was referenced.

## Tests (commands and results)

Focused: `python -m pytest tests/test_execution_durable_idempotency.py -q` ->
13 passed.

Auth-boundary regression (P11): `python -m pytest tests/test_api_owner_decision_auth.py
tests/test_api_authorize_demo_auth.py tests/test_api_owner_decision.py tests/test_api.py -q`
-> 58 passed.

Adjacent execution-boundary regression: `python -m pytest
tests/test_owner_decision_bridge.py tests/test_proposal_envelope_execution_boundary.py -q`
-> 36 passed (one apparent failure on a first combined run was a subprocess-timeout
artifact of concurrent test-suite load in this session, not a real regression --
`test_behavioral_whole_package_never_reaches_order_mutation_surface` passes cleanly in
isolation, 1 passed in 34s).

Known pre-existing failure reproduced separately: `python -m pytest
tests/test_proposal_envelope_adapters.py -k dedup -q` -> 1 failed
(`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`), same
assertion already documented against every prior R3/R4/R5A/R5A-R1 baseline.

## Next recommended package

`PANEL_R5B_INDEPENDENT_AUDIT`. R5C (risk/execution gate) and R5D (MT5 Demo submission)
remain explicitly out of scope until that audit passes.
