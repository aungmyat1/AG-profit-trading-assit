# AG PANEL R5C — Proposal-Level Owner-Decision Uniqueness — Independent Audit

Status: **R5C_PROPOSAL_DECISION_UNIQUENESS_INDEPENDENT_AUDIT_PASS**

Audited by an independent auditor agent, isolated in its own worktree
(`D:/AG-r5c-independent-audit`, branch `audit/r5c-proposal-owner-decision-uniqueness`),
with no access to the implementation worktree's transcript or self-report. All
evidence below was independently reproduced from source, tests, persistence
behavior, restart behavior, and concurrency behavior — the implementer's
`R5C_PROPOSAL_DECISION_UNIQUENESS_PASS` report was not trusted as proof of anything.

- BASELINE_SHA = `061d3e09765c88950ae1b074aff5a02a74f41ade`
- R5C_SHA = `cffe626221b3e867ceb5e1bf8fcda731d6ef183a`
- Lineage: `git merge-base --is-ancestor 061d3e0 cffe626` → true;
  `git log --oneline 061d3e0..cffe626` → exactly one commit,
  `cffe626 fix(owner-decision): enforce proposal-level uniqueness`.

## Diff scope (independently computed)

`git diff 061d3e0..cffe626 --stat`:

```
 PROJECT_STATUS.md                                                  |  33 ++
 docs/README.md                                                     |   5 +
 docs/status/PANEL_R5C_PROPOSAL_DECISION_UNIQUENESS_STATUS.md       | 258 +++++++++++++
 src/owner_decision/bridge.py                                      | 161 +++++++-
 tests/test_owner_decision_proposal_uniqueness_r5c.py               | 422 +++++++++++++++++++++
 5 files changed, 875 insertions(+), 4 deletions(-)
```

Production scope is bounded to `src/owner_decision/bridge.py` only. Independently
confirmed zero diff (`git diff 061d3e0..cffe626 -- <path> | wc -l` = 0) for:
`strategies/`, `strategies/registry.yaml`, `web/` (including `web/server.ts`),
`execution/`, `mt5/`, `src/api/app.py`.

## Storage model (read from source, `src/owner_decision/bridge.py`)

- `OwnerDecisionStore._proposal_index: Dict[proposal_envelope_id, decision_id]` is a
  pure in-memory index. No new persisted file — `JsonKeyValueStore` still only
  persists `_decisions` keyed by `decision_id`, byte-identical schema to baseline.
- On `_load_from_disk()`, `_proposal_index` is rebuilt from scratch by iterating
  `self._decisions.items()` and calling the private classifier
  `_is_terminal_owner_outcome()` on each record — fully deterministic reconstruction,
  no dependency on write order, browser state, or any external process.
- Both `put_if_absent` (unchanged call sites for validation failures) and the new
  `commit_terminal_decision` (genuine owner outcomes) execute entirely under the
  single existing `self._lock` — no second lock, no new synchronization primitive.

## P3 — authority-claiming semantics (critical gate)

`OwnerDecisionStore._is_terminal_owner_outcome(outcome)`:

```python
if outcome.status == EXECUTION_DECISION_AUTHORIZED:
    return True
return outcome.status == EXECUTION_DECISION_REJECTED and outcome.reason_code == REASON_OWNER_REJECTED
```

This is a structural **allowlist of exactly two conditions**, not a blocklist and not
string/message matching. Independently traced every `evaluate_owner_decision` return
path (11 call sites): the only two that route through `commit_terminal_decision` are
the genuine `OWNER_ACTION_REJECT` branch (line 409, `_reject(decision,
REASON_OWNER_REJECTED)`) and the terminal `AUTHORIZED` branch (line 475). Every other
branch — malformed decision, unknown action, non-DEMO environment, missing envelope,
identity/symbol mismatch, `PROPOSAL_NOT_READY`, `DEMO_NOT_AUTHORIZED`,
`BROKER_MUTATION_BLOCKED`, `PROPOSAL_STALE`, `PROPOSAL_MALFORMED` — routes through
`put_if_absent`, never `commit_terminal_decision`, and none of them uses
`REASON_OWNER_REJECTED` as their reason code. A future new reason code defaults to
**not** claiming authority unless it is literally `REASON_OWNER_REJECTED` on a
`REJECTED` status — the safe default direction for a new/unclassified code.

The new `PROPOSAL_ALREADY_DECIDED` conflict record itself is `status=REJECTED,
reason_code=PROPOSAL_ALREADY_DECIDED` (not `REASON_OWNER_REJECTED`), so it is correctly
excluded from claiming authority itself on any future reconstruction — verified this
does not recursively poison the index.

## Independent test evidence

A fresh auditor-written script (not the implementer's test file) exercised the store
and `evaluate_owner_decision` directly, covering P4–P14. All 18 independent checks
passed:

```
[PASS] VALIDATION_FAILURE_THEN_VALID_RETRY
[PASS] VALIDATION_FAILURE_RESTART_THEN_VALID_RETRY
[PASS] OWNER_REJECT_CLAIMS_AUTHORITY
[PASS] AUTHORIZED_CLAIMS_AUTHORITY
[PASS] DECISION_ID_IDEMPOTENCY_PRESERVED
[PASS] DIFFERENT_ID_SAME_APPROVE
[PASS] DIFFERENT_ID_SAME_REJECT
[PASS] DIFFERENT_ID_APPROVE_TO_REJECT
[PASS] DIFFERENT_ID_REJECT_TO_APPROVE
[PASS] RESTART_APPROVE_AUTHORITY
[PASS] RESTART_REJECT_AUTHORITY
[PASS] RESTART_VALIDATION_FAILURE_NON_AUTHORITY   <- most important test in the audit
[PASS] CONCURRENT_APPROVE_REJECT (30 iterations, real threading.Thread + Barrier)
[PASS] CONCURRENT_APPROVE_APPROVE (30 iterations)
[PASS] CONCURRENT_REJECT_REJECT (30 iterations)
[PASS] CORRUPT_CONFLICTING_AUTHORITY
[PASS] CORRUPT_DUPLICATE_SAME_ACTION_AUTHORITY
[PASS] STORE_UNAVAILABLE_FAIL_CLOSED
```

Notable details independently confirmed:

- Restart tests used genuinely fresh `OwnerDecisionStore(path)` instances pointed at
  the same durable file (old instance `del`eted first), not the same in-memory object.
- P8 (different-id/same-action) was verified by reading the raw persisted JSON file
  directly, not just HTTP/function return values: exactly one `AUTHORIZED` record and
  exactly one `OWNER_REJECTED` record existed per proposal after the "duplicate"
  request.
- P9 (different-id/opposite-action) was verified by snapshotting proposal A's durable
  record before and after B's conflicting request byte-for-byte (`dict` equality) —
  unchanged in both directions (APPROVE→REJECT and REJECT→APPROVE).
- P13 conflicting-authority corruption (`AUTHORIZED` + `OWNER_REJECTED` for the same
  proposal, both pre-existing on disk) raises
  `OwnerDecisionProposalAuthorityConflict` (subclass of `OwnerDecisionStoreUnavailable`)
  on store construction — fails closed as designed.
- P13 agreeing-duplicate corruption (two `AUTHORIZED` records for the same proposal,
  both pre-existing): confirmed **does not** fail closed — reconstruction picks
  whichever decision_id is encountered first while iterating `self._decisions.items()`.
  Read the code directly for this: `JsonKeyValueStore._save_all_unlocked` always
  writes with `json.dump(..., sort_keys=True)`, so on any reload the iteration order is
  **alphabetical by decision_id**, not `decided_at` or write order. This is an
  arbitrary (not causally-meaningful) tie-break. Audit assessment: this durable state
  is provably unreachable through any live R5C write path — `commit_terminal_decision`
  never durably records a second decision_id once a proposal already has
  same-status authority (it returns the existing record and skips the `persist.put`
  call entirely), so two agreeing `AUTHORIZED` records for one proposal can only exist
  via external file tampering or a pre-R5C ledger, exactly the class of state P13 says
  to construct by hand. Given that, and that the *semantic* authority outcome (approve
  vs. reject) is identical between the two tied records, the arbitrary tie-break does
  not create an approve/reject ambiguity — only a possible ambiguity in which
  `trade_command` payload is replayed if the two duplicate records' payloads somehow
  differ, which is a narrower and already out-of-band concern (hand-tampered file).
  Documented here as a design observation, not classified as a gate failure.
- Store-unavailable: malformed JSON on disk raises `OwnerDecisionStoreUnavailable`
  (via `StateStoreCorrupted`) on construction, unchanged from baseline pattern.

## P12 — crash/atomicity reasoning (code inspection, no new fault-injection framework)

`commit_terminal_decision` and (unchanged) `put_if_absent` both write to
`self._decisions[...]` in-memory *before* calling `self._persist.put(...)`. This
ordering is identical between the R5C-new method and the pre-existing baseline method
— R5C introduces no new crash-window risk beyond what the baseline already had for
decision_id uniqueness. `JsonKeyValueStore._save_all_unlocked` writes to a per-call
unique tmp file and does an `os.replace` (atomic on both POSIX and Windows), so a
mid-write crash never corrupts the on-disk file — the stale previous version (or
absence of the file) survives untouched. The independently-run restart tests (P10)
confirm that after a real reload, only durably-persisted records determine authority;
an in-memory-only record from a hypothetical persist failure would simply not survive
a restart, which is a fail-safe (not fail-open) direction consistent with the module's
documented "no power-loss guarantee, safe for concurrent threads, not cross-process."

## P15 — authentication regression

`src/api/app.py` is byte-identical to baseline (0 diff lines, confirmed above).
`tests/test_api_owner_decision_auth.py` run independently: 7/7 passed. Auth is
enforced at the route layer above `evaluate_owner_decision`/`OwnerDecisionStore`
(unchanged file), so an unauthenticated/incorrectly-authenticated request never
reaches the bridge layer at all — structurally unaffected by the R5C change.

## P16 — `PROPOSAL_ALREADY_DECIDED` reason code

- Defined once (`REASON_PROPOSAL_ALREADY_DECIDED = "PROPOSAL_ALREADY_DECIDED"`) and
  used in exactly one place: the opposite-action conflict branch of
  `commit_terminal_decision`.
- Message content (`reasons` tuple) embeds only `proposal_envelope_id`,
  `existing_decision_id`, `existing_outcome.status`, and `candidate.status` — no owner
  key, no auth token, no internal path or secret.
- Does not imply order submission (`status=REJECTED`, no `trade_command`).
- Independently confirmed (P7/P8 tests) that a same-action replay across different
  decision_ids does **not** produce `PROPOSAL_ALREADY_DECIDED` — it replays the
  original authoritative outcome's own status/reason_code verbatim. The two outcomes
  (clean replay vs. genuine conflict) are distinguishable in the response.

## Regression suites (independently run, not inherited)

| Tier | Command | Result |
|---|---|---|
| 1 — R5C focused | `pytest tests/test_owner_decision_proposal_uniqueness_r5c.py -q` | 20 passed |
| 2 — owner-decision regression | `pytest tests/test_owner_decision_bridge.py tests/test_api_owner_decision.py tests/test_api_owner_decision_auth.py tests/test_owner_decision_store_persistence.py -q` | 41 passed |
| 3 — broader backend regression | `pytest tests/test_api_canonical_proposals.py tests/test_assistant_canonical_proposal_adapter.py tests/test_execution_durable_idempotency.py tests/test_execution_durable_idempotency_lifecycle.py tests/test_proposal_dedup_r1.py tests/test_proposal_envelope_adapters.py tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_models.py tests/test_proposal_ledger.py tests/test_proposal_lifecycle.py -q` | 124 passed |

Total 185/185 — matches the implementer's reported counts, independently reproduced
rather than inherited.

A separate note (relayed to this audit, not self-generated) reported a repo-wide
`pytest -q` elsewhere showing 22 pre-existing failures in 8 unrelated test files
(`test_fx_occurrence_identity_promotion.py`,
`test_large_smc_eurusd_admission_wp2.py`,
`test_large_smc_eurusd_friction_campaign_wp3a1.py`,
`test_large_smc_eurusd_friction_evidence_wp3a.py`,
`test_proposal_occurrence_identity_v1.py`,
`test_ssc_svos_post_g2_authority_sync.py`,
`test_svos_context_authority.py`, `test_validation_framework.py`). Independently
verified via `git diff 061d3e0..cffe626 -- <file>` for each of the 8 files: all 8 are
byte-identical to baseline (0 diff lines). Structural conclusion, verified directly
rather than taken on faith: none of these failures can be attributable to R5C's single
changed file (`src/owner_decision/bridge.py`), consistent with a pre-existing/
unrelated-lineage issue.

## WP0A boundary

`web/server.ts` and all of `web/` are byte-identical between baseline and R5C
candidate (0 diff lines, independently confirmed). Per the established convention
from the prior frontend re-audit (`D:/AG-frontend-rewire-r1-audit`, commit `8b871b7`),
this alone is sufficient to classify `WP0A = PRE_EXISTING_NON_ATTRIBUTABLE` for this
audit; WP0A itself was not re-run here and is not claimed fixed.

## Side-effect firewall

No test, script, or code path exercised in this audit imports or calls
`execution.executor`, `execution.mt5_gateway`, `order_check`, or `order_send`. Grep of
`src/owner_decision/bridge.py` and the R5C test file confirms zero call sites (only
docstring/comment mentions of what it must never call).
`REAL_ORDER_CHECK_CALLS=0, REAL_ORDER_SEND_CALLS=0, BROKER_ORDERS_SENT=0,
DEMO_ORDERS_SENT=0, LIVE_ORDERS_SENT=0` throughout.

## Final classification

`R5C_PROPOSAL_DECISION_UNIQUENESS_INDEPENDENT_AUDIT_PASS`

`SAFE_TO_FREEZE_R5C = YES`, `SAFE_TO_START_STRATEGY_SELECTION = YES`.
`SAFE_TO_AUTHORIZE_STRATEGY = NO`, `SAFE_TO_RUN_DEMO_ORDER = NO`, `SAFE_FOR_LIVE = NO`
(strategy selection/authorization is explicitly out of scope for this audit).
