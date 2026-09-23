# AG_PANEL_R5C_PROPOSAL_DECISION_UNIQUENESS_V2 — Status

STATUS_EVIDENCE. Current as of 2026-09-23. Branch
`feat/r5c-proposal-owner-decision-uniqueness`, worktree
`D:/AG-r5c-proposal-owner-decision-uniqueness`.

- Baseline SHA: `061d3e09765c88950ae1b074aff5a02a74f41ade` (the independently-audited,
  frozen `AG_FRONTEND_OWNER_DECISION_REWIRE` commit; audit evidence `8b871b7`,
  classification `FRONTEND_OWNER_DECISION_REWIRE_REAUDIT_PASS`).
- R5C implementation SHA: recorded at commit time (see `git log -1`), one bounded
  commit on top of baseline.
- Scope: backend-only. `src/owner_decision/bridge.py` extended; one new test file
  added. No other file under `src/`, `web/`, `strategies/`, `mt5/`, or `execution/`
  changed.

## Mission

Implement `ONE CANONICAL PROPOSAL → AT MOST ONE AUTHORITATIVE OWNER DECISION` as a
backend safety invariant layered on top of the already-independently-verified,
decision_id-keyed idempotency ledger (`owner_decision.bridge.OwnerDecisionStore`),
without reopening the frozen frontend, without touching strategy/registry/execution/
MT5/scheduler code, and without enabling Demo execution or authorizing any strategy.

## Pre-fix gap reproduced (P1)

Reproduced directly against baseline `061d3e0` (before any R5C code changes), using
`evaluate_owner_decision()` with a shared `OwnerDecisionStore()` instance, exactly the
existing test harness pattern from `tests/test_owner_decision_bridge.py`:

| Case | Sequence | Pre-fix result |
|---|---|---|
| 1 | `P1/A/APPROVE` then `P1/B/REJECT` | `A -> AUTHORIZED`, `B -> REJECTED (OWNER_REJECTED)` — **contradictory authority for the same proposal** |
| 2 | `P2/A/REJECT` then `P2/B/APPROVE` | `A -> REJECTED`, `B -> AUTHORIZED` — **contradictory authority** |
| 3 | `P3/A/APPROVE` then `P3/B/APPROVE` | Both `AUTHORIZED`, two independent decision_ids/records — **duplicate authority** |
| 4 | `P4/A/REJECT` then `P4/B/REJECT` | Both `REJECTED`, two independent records — **duplicate (harmless but still non-unique) authority** |

Confirms the gap named in the mission brief: `decision_id` idempotency alone does not
give proposal-level at-most-one-authority; each new `decision_id` for the same proposal
was evaluated completely independently.

## Invariant implemented

`ONE proposal_envelope_id → ZERO or ONE authoritative terminal owner decision.`
`decision_id` remains the request/idempotency identity, unchanged and untouched in its
own existing semantics (same-ID replay, same-ID opposite-action-preserves-original).
`proposal_envelope_id` becomes a second, higher-level authority key enforced on top.

## Which rejection paths participate in proposal-level authority (the "must verify" finding)

Read the entirety of `evaluate_owner_decision()` before designing this. Findings:

- **One early-return path never persists anything at all**: missing
  `decision_id`/`proposal_envelope_id` (`REASON_MALFORMED_DECISION`) returns directly,
  bypassing `store.put_if_absent`/`store.commit_terminal_decision` entirely. Unchanged
  by R5C — out of scope, correctly never establishes any authority.
- **Every other REJECTED outcome except one is a validation/gating failure, not a
  completed owner action**, and each of these already called `store.put_if_absent`
  pre-R5C (so each is durably recorded under its own `decision_id` for idempotent
  replay of that exact request) but **must never participate in proposal-level
  authority**: unknown action, `NON_DEMO_ENVIRONMENT_REJECTED`, envelope not
  found/`PROPOSAL_NOT_READY`, envelope-identity mismatch, `SYMBOL_MISMATCH`,
  `DEMO_NOT_AUTHORIZED`, `BROKER_MUTATION_BLOCKED`, `PROPOSAL_STALE`,
  `PROPOSAL_MALFORMED`. These remain wired to the unchanged `store.put_if_absent` and
  are excluded from the proposal index by construction
  (`OwnerDecisionStore._is_terminal_owner_outcome`). A dedicated test
  (`test_validation_failure_rejection_does_not_establish_proposal_authority`) proves a
  validation failure on one `decision_id` never blocks a later, correctly-formed
  request for the same proposal from getting a real evaluation.
- **Exactly two paths are genuine, terminal, completed owner actions**: the explicit
  `REJECT` action (`REASON_OWNER_REJECTED`) and a fully-validated `APPROVE_DEMO` that
  reaches `AUTHORIZED`. Only these two now route through the new atomic gate,
  `OwnerDecisionStore.commit_terminal_decision`, instead of `put_if_absent`.

This resolves the ambiguity the mission flagged directly from the code structure, not
from assumption.

## Storage / index design

No new persisted file. `OwnerDecisionStore` gains one new in-memory field,
`_proposal_index: Dict[proposal_envelope_id, decision_id]`, pointing at the one
authoritative terminal decision per proposal. It is 100% reconstructed from the
existing `_decisions` dict (itself loaded from the existing
`state/owner_decisions/owner_decisions.json`) on every `_load_from_disk()` call — fully
backward-compatible with pre-R5C persisted ledgers, no migration needed.

The atomic primitive is `OwnerDecisionStore.commit_terminal_decision()`, which extends
(does not duplicate) the same `self._lock` that already made `put_if_absent`'s
decision_id uniqueness atomic. Under one lock acquisition it:

1. Re-checks decision_id idempotency (matches `put_if_absent`'s own first check —
   needed because two racing requests for two *different* decision_ids on the *same*
   decision_id-that-turns-out-identical edge case, and general belt-and-suspenders,
   though the outer `evaluate_owner_decision` idempotency-first check already handles
   the common case before this is ever reached).
2. If the proposal has no recorded authority yet: the candidate outcome becomes that
   authority, recorded under its own `decision_id`, atomically with the index update.
3. If the proposal already has authority with the **same** semantic action (both
   `AUTHORIZED`, or both `OWNER_REJECTED`): the candidate is discarded and the
   **existing** authoritative outcome is returned verbatim (its original `decision_id`,
   not the caller's new one) — no second record is created.
4. If the proposal already has authority with the **opposite** semantic action: fail
   closed. A new `REJECTED` record with `reason_code = PROPOSAL_ALREADY_DECIDED` is
   durably recorded under the caller's own `decision_id` (so *that* decision_id's own
   replay stays idempotent), but the original authority is never mutated.

## Same-ID semantics (unchanged, independently-verified, reconfirmed)

`P1/A/APPROVE` then `P1/A/REJECT` (same decision_id, opposite action second time):
handled entirely by the pre-existing idempotency-first check at the top of
`evaluate_owner_decision` (`store.get(decision.decision_id)`), which returns the prior
outcome before the action is even inspected a second time. R5C changes nothing here.
Reconfirmed by `test_same_id_approve_then_reject_preserves_original` and
`test_same_id_reject_then_approve_preserves_original`.

## Different-ID / same-action semantics

`P1/A/APPROVE` then `P1/B/APPROVE` (or `REJECT`/`REJECT`): `B` never becomes a durable
record (`store.get("dec-B") is None`); the response for `B` is the SAME
`ExecutionDecision` object/values as `A`'s original result, including `A`'s own
`decision_id` — callers must not assume the response's `decision_id` echoes the
request's `decision_id` in this specific replay-collapse case. In production this
scenario is expected to be rare: the frozen frontend derives `decision_id`
deterministically from `proposal_id` (`OWNER_DECISION:<proposal_id>`), so the same
proposal from the same client already produces the same `decision_id` on its own; this
path is a backend safety net for any other caller (retry tooling, a second client,
manual API use), not a change the frozen frontend needs to accommodate.

## Different-ID / opposite-action semantics

`P1/A/APPROVE` then `P1/B/REJECT` (or the reverse): `B` fails closed with
`status=REJECTED`, `reason_code=PROPOSAL_ALREADY_DECIDED`, `trade_command=None`, and
its own `decision_id="dec-B"` echoed back (this one **is** durably recorded under its
own id, unlike the same-action case, since it represents a genuinely distinct rejected
request). `A`'s original authority is provably untouched
(`store.get("dec-A") == approve`, `store.proposal_authority(...) == approve`).

## Concurrency proof (P5)

`tests/test_owner_decision_proposal_uniqueness_r5c.py::_race` runs three races
(`APPROVE`/`REJECT`, `APPROVE`/`APPROVE`, `REJECT`/`REJECT`) using real
`threading.Thread` + `threading.Barrier(2)` so both submissions genuinely overlap, 25
iterations each with a fresh store/path/proposal per iteration. After every iteration:
exactly one authoritative outcome exists for the proposal (verified via a **third**,
fresh `OwnerDecisionStore` instance re-reading the same path, i.e. proven from durable
state, not just in-memory agreement of the two racing threads). 75 total race
iterations passed with zero flakes in this run.

## Restart durability proof (P4)

`test_restart_preserves_approve_authority_and_blocks_conflicting_and_dupes` and
`test_restart_preserves_reject_authority`: authority established by one
`OwnerDecisionStore(path=...)` instance is read correctly by two subsequent, entirely
separate instances over the same path (simulating process restart), including a
post-restart same-action dedup (no new record) and a post-restart opposite-action fail
closed — both against `_proposal_index` rebuilt fresh from disk on each new instance's
`_load_from_disk()`.

## Corruption fail-closed proof (P7)

New exception `OwnerDecisionProposalAuthorityConflict(OwnerDecisionStoreUnavailable)`.
`_load_from_disk()` now also reconstructs `_proposal_index` deterministically from
`_decisions` and, on encountering two different `decision_id`s for the same
`proposal_envelope_id` whose terminal outcomes **disagree** (one `AUTHORIZED`, one
`OWNER_REJECTED` — only reachable via pre-R5C data or direct file tampering, since
`commit_terminal_decision` never lets this occur going forward), raises immediately at
store construction — the whole store becomes unavailable, matching the existing
`StateStoreCorrupted -> OwnerDecisionStoreUnavailable` fail-closed convention exactly
(subclassed so existing callers catching that family already fail closed here with no
code change). Proven by
`test_corrupt_conflicting_proposal_authority_fails_closed` with a hand-planted
conflicting ledger file.

Two terminal records that **agree** (both `AUTHORIZED`, or both `OWNER_REJECTED`) for
the same proposal are not a contradiction — P7's own wording specifically concerns
"conflicting ... with different outcomes" — so reconstruction deterministically keeps
whichever is encountered first (`raw.items()` order, itself alphabetical by
`decision_id` because `JsonKeyValueStore` persists with `sort_keys=True`) rather than
failing closed; proven by
`test_corrupt_agreeing_duplicate_proposal_authority_does_not_fail_closed`.

Pre-existing store-unavailable behavior (malformed JSON file entirely) is unchanged and
reconfirmed by `test_unavailable_store_fails_closed_on_construction` and the existing
`tests/test_owner_decision_store_persistence.py::test_corrupt_on_disk_ledger_fails_closed_not_empty`.

## Authentication (P8)

Zero changes to `src/api/app.py` or `require_owner_auth`/`X-AG-Owner-Key`/
`AG_OWNER_API_KEY` — confirmed by `git diff --stat` against baseline: only
`src/owner_decision/bridge.py` and the new test file changed. R5C's logic lives
entirely inside `OwnerDecisionStore`/`evaluate_owner_decision`, below the FastAPI auth
dependency, which already runs before the route body (and therefore before this
module) on every request. `tests/test_api_owner_decision_auth.py` (unchanged, rerun)
still passes. Structural confirmation also in
`test_no_alternate_auth_free_path_to_proposal_authority`.

## Regression evidence

Exact commands run in this worktree, 2026-09-23:

- **Tier 1 — R5C focused** (new file):
  `python -m pytest tests/test_owner_decision_proposal_uniqueness_r5c.py -q`
  → **20 passed**.
- **Tier 2 — owner-decision/R5 family**:
  `python -m pytest tests/test_owner_decision_bridge.py tests/test_api_owner_decision.py tests/test_api_owner_decision_auth.py tests/test_owner_decision_store_persistence.py -q`
  → **41 passed**.
- **Tier 3 — bounded backend regression** (canonical proposals API, proposal envelope/
  adapters/models/ledger/lifecycle, execution durable idempotency + lifecycle, proposal
  dedup):
  `python -m pytest tests/test_api_canonical_proposals.py tests/test_assistant_canonical_proposal_adapter.py tests/test_execution_durable_idempotency.py tests/test_execution_durable_idempotency_lifecycle.py tests/test_proposal_dedup_r1.py tests/test_proposal_envelope_adapters.py tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_models.py tests/test_proposal_ledger.py tests/test_proposal_lifecycle.py -q`
  → **124 passed**.

No candidate-attributable regression found in any tier.

## Scope evidence (P15)

`git diff --stat 061d3e09765c88950ae1b074aff5a02a74f41ade`:

```
src/owner_decision/bridge.py | 161 +++++++++++++++++++++++++++++++++++++++++--
1 file changed, 157 insertions(+), 4 deletions(-)
```

plus one new untracked test file, `tests/test_owner_decision_proposal_uniqueness_r5c.py`.

- `FRONTEND_PRODUCTION_CHANGED` = NO (nothing under `web/` touched)
- `SRC_UNRELATED_CHANGED` = NO (only `src/owner_decision/bridge.py`)
- `STRATEGIES_CHANGED` = NO
- `STRATEGY_REGISTRY_CHANGED` = NO
- `MT5_CHANGED` = NO
- `BROKER_EXECUTION_CHANGED` = NO (`execution/`, `mt5/` untouched)
- `SCHEDULER_CHANGED` = NO

## Side-effect firewall (P14)

`evaluate_owner_decision` never imports `execution.executor`/`execution.mt5_gateway`
(unchanged, structurally reconfirmed by the existing structural tests in
`tests/test_owner_decision_bridge.py`, which still pass). All new R5C tests use only
in-memory/temp-file `OwnerDecisionStore` instances and the existing
`assistant.commands`/`execution.executor.ProposalStore` test-isolation fixture —
`REAL_ORDER_CHECK_CALLS = 0`, `REAL_ORDER_SEND_CALLS = 0`, `BROKER_ORDERS_SENT = 0`,
`DEMO_ORDERS_SENT = 0`, `LIVE_ORDERS_SENT = 0` throughout implementation and testing.

## WP0A (pre-existing, untouched)

Not rerun. `web/` was never touched by this package (confirmed by `git diff --stat`
above), so the pre-existing, independently-classified
`PRE_EXISTING/NON_ATTRIBUTABLE` WP0A gap in `web/server.ts` is unaffected and out of
scope, per the mission brief.

## Remaining authorization gates (unchanged by this package)

This package changes only decision-authority bookkeeping inside the OwnerDecision
bridge. It does not authorize any strategy for Demo or Live, does not enable Demo
execution, does not change `strategies/registry.yaml`, and does not open a new path to
MT5. `AUTHORIZED` still only means a PREPARED, UNCONFIRMED `TradeCommand` template
exists; reaching an actual broker order still requires the separate, explicitly
user-confirmed `assistant.commands.execute_command(..., user_confirmed=True)` call this
module never makes (AGENTS.md Authority order point 3).
