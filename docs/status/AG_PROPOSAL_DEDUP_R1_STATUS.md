# AG Proposal Dedup R1 -- Root Cause + Bounded Remediation -- Status (2026-09-23)

Classification: `AG_PROPOSAL_DEDUP_R1_IMPLEMENTED`

R5C_R1_FROZEN_SHA = `1c5bbf578daa8c4773a7bf6e50c6ae5fd375595c`
Branch: `fix/proposal-dedup-r1`, created directly from `1c5bbf5` (worktree
`D:/ddev/AG-proposal-dedup-r1`). `1c5bbf5` is confirmed the ancestor commit; nothing
on that lineage (R5B-R1, R5A/R5A-R1, R4, R3, R5C, R5C-R1) was modified.

## P1 -- Reproduction before modification

Ran `tests/test_proposal_envelope_adapters.py::test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`
against the unmodified baseline before any production change:

```
FAILURE_REPRODUCED = YES
CURRENT_PROPOSAL_COUNT = 3
EXPECTED = <= 1
```

## P2 -- Duplicate lineage trace

The test drives `fx_adapter.to_canonical_proposal(decision, trade_proposal)` three
times with the SAME `strategy_id`, `symbol`, `reference_session`, `trading_date`, and
the SAME `trade_proposal` object (identical `setup_id`/geometry), varying only
`decision_id` (`f"DECISION-{symbol}-{i}"`) and `evaluation_time`/`ready_at` (by
microseconds, `i`). Tracing each of the three resulting `CanonicalProposal`s:

- source opportunity / strategy / symbol / session / trading date: identical across
  all three (`ST_ASIAN_SWEEP_5R_V1` / `EURUSD` / `ASIAN` / `2026-09-02`)
- setup identity (`trade_proposal.setup_id`): identical across all three (test
  constructs it once, reused for all three `_decision(...)` calls)
- **canonical proposal identity (`proposal_envelope_id`)**: DIFFERENT across all
  three -- `FX:DECISION-EURUSD-0`, `FX:DECISION-EURUSD-1`, `FX:DECISION-EURUSD-2`
- proposal-envelope identity: same as canonical proposal identity in this model (one
  field)
- execution command identity: none created (test never reaches
  `owner_decision`/`execution`)
- persistence key: `ProposalLedger` keys by `proposal_envelope_id` -- three distinct
  keys, hence three stored entries
- creation timestamp: three distinct `evaluation_time` values (by design, one per
  simulated scan cycle)
- producer/call path: `fx_adapter.to_canonical_proposal` -> `ProposalLedger.record_proposal`,
  called once per loop iteration, simulating three repeated scanner observations of the
  SAME still-open setup

**Case C** -- same economic setup with unstable technical IDs. Confirmed by direct
inspection, not assumed: `trade_proposal.setup_id` (the one field carrying genuine
economic identity in this call) was identical all three times; only the volatile
`decision.decision_id` differed, and that volatile value -- not the stable one -- was
what the adapter used to build the persistence key.

## P3 -- Authoritative dedup boundary

`rg -n "dedup|duplicate|proposal_id|opportunity_id|setup_id|command_id|canonical|fingerprint|trading_date|session" src tests`
plus direct inspection established:

- `proposal_envelope.ledger.ProposalLedger.record_proposal()` is the ONE authoritative
  uniqueness/admission boundary for canonical proposals -- keys strictly on
  `envelope.proposal_envelope_id`, and its own docstring already documents the intended
  idempotency contract ("recording the same proposal_envelope_id again with IDENTICAL
  geometry ... is a no-op that returns the ALREADY-persisted original unchanged").
  **This boundary was already correctly implemented** -- it does exactly what P6/P7
  require, keyed on whatever `proposal_envelope_id` it is given.
- The defect is entirely upstream, in the adapter that COMPUTES
  `proposal_envelope_id`: `proposal_envelope.adapters.fx_adapter.to_canonical_proposal()`.
  No second, independent dedup layer was introduced -- the existing single boundary was
  fixed by giving it a correct, stable key.

## P4 -- Economic proposal identity, explicitly defined

Two FX proposals are the SAME proposal iff they share:

```
strategy_id
pair_id (session pairing, e.g. ASIAN_LONDON)
symbol
trading_date (session date)
```

This is not invented for this package -- it is `strategy_engine.engine`'s own existing
`signal_id` contract (`src/strategy_engine/engine.py:56`:
`signal_id=f"{strategy.strategy_id}:{pair.pair_id}:{symbol}:{session_date.isoformat()}"`),
already flowing unchanged through `execution.intent_builder.build_intent()` ->
`TradeIntent.signal_id` -> `execution.adapter.TradeProposal.from_trade_intent()` ->
`TradeProposal.setup_id` (`src/execution/adapter.py:78`). `direction` is deliberately
NOT part of this identity (an existing, unmodified repository convention -- a given
strategy/symbol/session/date slot resolves to at most one direction by construction of
the strategy itself).

`created_at`, scan/evaluation timestamps, and `decision_id` (itself a hash that
includes `evaluation_time`) are explicitly EXCLUDED from the identity used for
dedup -- using them would make every repeated observation of the same setup look like
a new proposal, which is exactly the defect being fixed.

## P5 -- Deterministic identity

No new identity system was invented. `trade_proposal.setup_id` already IS the
required deterministic identity (same economic setup + same identity scope -> same
string, verified by construction: `strategy_engine.engine`'s f-string has no
volatile input). `fx_adapter.to_canonical_proposal()`'s READY branch now uses it
directly: `proposal_envelope_id=f"FX:{trade_proposal.setup_id}"` (previously
`f"FX:{source_record_id}"` where `source_record_id = decision.decision_id`).
`decision.decision_id` is preserved, unchanged, as `source_record_id` -- observation
provenance, a field that already existed for exactly this purpose and is never used
by `ProposalLedger` for identity.

## P6/P7 -- Idempotent admission / repeated producer invocation

`admit(P); admit(P); admit(P)` (three separate `fx_adapter.to_canonical_proposal()` +
`ProposalLedger.record_proposal()` calls, one per simulated scan cycle, varying only
`decision_id`/`evaluation_time` exactly as the original failing test does) now yields
ONE canonical admitted proposal -- proven by
`test_admit_same_setup_twice_yields_one_canonical_proposal` and
`test_admit_same_setup_three_times_yields_one_canonical_proposal`. Repeated admission
of the identical envelope is confirmed an idempotent no-op returning the existing
canonical record unchanged (`test_repeated_admission_returns_the_original_unchanged_not_a_mutation`)
-- compared on dedup-relevant fields (`proposal_envelope_id`, `version`,
`correction_of`, `direction`/`entry`/`stop`/`targets`) rather than full dataclass
equality, because `ProposalLedger`'s own JSON round-trip does not restore every nested
dataclass's tuple-typed field (e.g. `CostAssumptions.missing_fields` comes back as a
list, not a tuple) -- a pre-existing, unrelated serialization quirk, out of this
package's scope, noted here rather than silently worked around.

## P8 -- Distinct setup protection (negative controls)

All proven distinct and NOT merged, each via a dedicated test:

- same symbol, different trading date -> 2 proposals
- same trading date, different `strategy_id` -> 2 proposals
- same date/strategy/symbol, different `pair_id` (session pairing) -> 2 proposals
  (this dimension is part of `signal_id`/`setup_id` itself, so it was already handled
  correctly by the identity definition -- test proves it explicitly)
- different `symbol` (genuinely separate opportunity) -> 2 proposals

The fix narrows the identity to exactly the fields `strategy_engine`'s own contract
already uses; it does not add any additional collapsing beyond what that contract
defines, so it cannot turn dedup into over-broad suppression.

## P9 -- Restart persistence

`ProposalLedger` is backed by `runtime_state.store.JsonKeyValueStore` (durable,
file-based). `test_dedup_survives_restart` proves: produce proposal, persist, drop the
`ProposalLedger` instance (simulating process termination), construct a fresh
`ProposalLedger` over the SAME path, observe the same setup again (new `decision_id`,
same `trade_proposal.setup_id`) -- result: still exactly one canonical proposal. No
in-memory-only set is relied on; the proposal lifecycle already spans restarts via the
existing durable store, unchanged by this package.

## P10 -- Concurrency

`ProposalLedger.record_proposal()`'s read-decide-write sequence is NOT independently
atomic in this module -- its `_store.get()` / `_store.put()` pair does two separate
calls into `JsonKeyValueStore`. The concurrency guarantee this repository actually
provides is `JsonKeyValueStore`'s own PER-PATH lock (documented in `ledger.py`'s own
docstring: "JsonKeyValueStore's per-path lock already serializes concurrent writers
within one process"). `test_concurrent_admission_of_same_setup_yields_one_canonical_proposal`
adversarially races 8 threads, `threading.Barrier`-synchronized to maximize actual
overlap, all admitting the SAME economic setup through one shared `ProposalLedger`
instance -- result: exactly one canonical proposal survives. This proves the
same-process guarantee this architecture actually claims; it does NOT claim, and this
package does not add, cross-process or distributed uniqueness (per `ledger.py`'s own
documented scope, and per this mission's explicit "do not claim more than actually
implemented" instruction).

## P11 -- Execution identity interaction

Traced: neither the original failing test nor any new test in this package reaches
`owner_decision`, `execution.durable_idempotency`, or `execution.reconciliation` --
`fx_adapter`/`ProposalLedger` have no import of, or call into, any of those modules.
Because the fix operates entirely upstream of proposal admission (the dedup boundary
established in P3), a duplicate SCAN OBSERVATION can no longer even produce a second
canonical proposal in the first place -- there is structurally nothing left downstream
to fan out into multiple owner decisions or execution command IDs from a repeated
observation of the same setup. `execution/durable_idempotency.py` (R5B-R1, frozen) and
`execution/reconciliation.py` (R5C/R5C-R1) were not modified, imported, or touched by
this change -- confirmed by `git diff --stat` (scope limited to
`src/proposal_envelope/adapters/fx_adapter.py` and one new test file).

## P12 -- Owner-decision compatibility

`test_repeated_admission_after_owner_review_does_not_replace_the_reviewed_proposal`
proves: after a proposal has been admitted (standing in for "already reviewed
elsewhere," since `owner_decision` reads proposals by `proposal_envelope_id` from
whatever registry/ledger holds them), a later re-observation of the SAME still-open
setup (new `decision_id`, identical `trade_proposal` geometry) does not create a
second version, does not set `correction_of`, and does not alter direction/entry/
stop/targets -- `record_proposal()`'s existing idempotent-return contract (unchanged
by this package) already guarantees this end-to-end through the adapter, not just in
the ledger in isolation.

## P13 -- Exact known regression

`tests/test_proposal_envelope_adapters.py::test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`
passes UNCHANGED (not modified, not weakened) with the fix applied:
`current_proposal_count == 1` (its own assertion is `<= 1`; the fixture's three loop
iterations are definitively one economic setup per the identity contract in P4, so
the fix satisfies the tighter bound the test's own comment already implies, without
needing to edit the test to require it).

## P14 -- Additional regression matrix

`tests/test_proposal_dedup_r1.py`, 12 new focused tests: identity-derivation (2),
repeated-admission 2x/3x (2), idempotent no-mutation (1), negative controls for
different date/strategy/pair_id/symbol (4), restart persistence (1), concurrent
admission (1), owner-decision-compatible repeat (1).

## P15 -- Frozen execution regression

All run against the fixed code, unmodified:
- `test_execution_durable_idempotency.py` + `test_execution_durable_idempotency_lifecycle.py`
  (R5B/R5B-R1)
- `test_execution_reconciliation.py` + `test_execution_reconciliation_no_submit.py` +
  `test_execution_reconciliation_r1.py` (R5C/R5C-R1)
- `test_api_authorize_demo_auth.py` + `test_ticket_delivery_execution_boundary.py`
  (adjacent execution-boundary)
- `test_api_owner_decision.py` + `test_api_owner_decision_auth.py` (owner-decision /
  R5A / R5A-R1)

Combined: 70 + 20 = 90 passed (see exact command/counts in the final report below).
Zero failures, zero skips introduced by this change.

## P16 -- No broker side effects

`git diff -- src/` swept for `order_send`/`order_check`/`execute_order`/`place_order`:
no matches. `BROKER_ORDERS_SENT = 0`. No Demo or Live execution authority added or
changed.

## P17 -- Scope discipline

Root-cause fix applied at the identity-construction layer inside the adapter that
FEEDS the authoritative admission boundary (`ProposalLedger`), not at
presentation/API/report level. `git diff --stat`:

```
src/proposal_envelope/adapters/fx_adapter.py | 15 ++++++++++++++-
```

(14 net lines added: 1 code-line change plus ~13 lines of docstring/comment
explaining the identity-source rationale). Strategy rules
(`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`, `strategy_engine/*`) were not touched --
`signal_id`'s own existing convention was read, not modified. Duplicates no longer
exist in canonical proposal STATE itself (not merely hidden from a list/report).

## P18 -- Documentation

This document plus the `PROJECT_STATUS.md` rolling-summary entry record: root cause
(volatile `decision_id` used as a dedup key instead of the stable
`trade_proposal.setup_id`), the authoritative uniqueness boundary
(`ProposalLedger.record_proposal`, unchanged), the identity definition
(`strategy_id:pair_id:symbol:trading_date`, `strategy_engine`'s own existing
`signal_id` contract), persistence behavior (durable, `JsonKeyValueStore`-backed,
survives restart), concurrency guarantee (same-process only, via
`JsonKeyValueStore`'s per-path lock -- no cross-process claim), execution-identity
interaction (fix is entirely upstream of `owner_decision`/`execution.*`; those modules
untouched), and known limitations (the pre-existing, unrelated tuple/list
JSON-round-trip quirk on nested dataclass fields, noted in P6/P7 and left
unmodified/out of scope).

## Final status

- `SAFE_TO_START_R5D`: `NO`
- `SAFE_TO_START_BROKER_SIDE_EFFECTS`: `NO` -- this package removes ONE blocker
  (proposal fan-out) but does not itself authorize broker side effects; that remains a
  separate, later gate
- Next action: independent re-audit of this candidate (`fix/proposal-dedup-r1`), same
  process as prior R-series audits -- must specifically re-drive the original 3x-repeat
  scenario and the negative controls, not merely rerun builder tests
- Pushed: NO. Merged: NO.
