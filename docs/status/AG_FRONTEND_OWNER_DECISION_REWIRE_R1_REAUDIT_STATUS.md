# AG Frontend Owner-Decision Rewire — R1 Independent Re-Audit Status

Date: 2026-09-23
Auditor role: independent audit worktree (`D:/AG-frontend-rewire-r1-audit`,
branch `audit/frontend-owner-decision-rewire-r1`), audit-only — no candidate
production code was modified.

```
BASELINE_SHA  = e7e9583749bebade5b89c4c53c9af97739d5f20f
CANDIDATE_SHA = 061d3e09765c88950ae1b074aff5a02a74f41ade
```

## Environment recovery

- Toolchain (this worktree): node v24.14.0, npm 11.9.0, npx 11.9.0,
  python 3.14.0 (resolves to the repo's existing `.venv` at
  `D:\ddev\AG profit trading\.venv`, already on PATH), pytest 8.3.5, git 2.50.1.
- Root cause of the prior isolated-environment BLOCKED result: `web/node_modules`
  was absent (fresh checkout) and no dedicated Python venv existed inside this
  audit worktree — but a working project venv was already available on this
  machine and importable from this directory (`pythonpath = ["src"]` in the
  repo's `pyproject.toml`), so no fresh Python install was needed.
- Recovery: `npm ci` inside `web/` (uses `web/package-lock.json` verbatim, no
  version changes). Python: reused the existing `.venv` on PATH, no install
  performed, no requirements/pyproject file touched.
- `web/package-lock.json` and all other tracked files were unchanged by `npm ci`
  (verified by `git diff --stat` before/after — no output either time).

## Frontend gates

- `npx tsc --noEmit` (web/): **PASS**, exit 0, no diagnostics.
- `npm run build` (web/): **PASS** — `vite build` (2478 modules) +
  `esbuild server.ts` both succeeded, `dist/server.cjs` produced.
- `npm run test` (`tsc --noEmit && tsx --test ...` over all 5 suite files,
  including `tests/owner_decision_panel_logic.test.ts`): **PASS on warm rerun**,
  48/49 individual test cases green. The one exception
  (`server.ts source contains no real-mode spawn of a broker-mutating script`,
  inside `tests/wp0a_execution_route_containment.test.ts`) is addressed below
  under WP0A — it is not part of the candidate's own new coverage.
- First cold-start run of `npm run test` produced 19 failures, all
  `"server at http://... did not become ready in time"` — an environment
  cold-start timing issue (first `tsx`/esbuild JIT compile of `server.ts` under
  test harness spawn), not a candidate defect: a second, warm run of the
  identical command produced only the one pre-existing WP0A finding below.
- `owner_decision_panel_logic.test.ts` coverage confirmed present and passing:
  deterministic `decision_id` derivation and stability, APPROVE/REJECT
  classification, identical-action replay, APPROVE→REJECT and REJECT→APPROVE
  client-side handling, DEMO_NOT_AUTHORIZED / SYMBOL_MISMATCH / PROPOSAL_STALE /
  PROPOSAL_MALFORMED / BROKER_MUTATION_BLOCKED distinct outcomes,
  CLIENT_OUTCOME_UNKNOWN for network/timeout errors, AUTH_FAILED (401) vs
  AUTH_NOT_CONFIGURED (503 w/ reason_code) vs SERVER_UNAVAILABLE (503 w/o
  matching reason_code) split, and a concurrent-submit guard.
- No broader frontend regression suite exists beyond the `package.json` "test"
  script (confirmed by inspection — nothing else under `web/` invokes a test
  runner).

## WP0A (`tests/wp0a_execution_route_containment.test.ts`)

One sub-test fails deterministically (reran 3x, same result every time — not a
timing flake): `server.ts source contains no real-mode spawn of a
broker-mutating script`. Root cause: `web/server.ts`'s **pre-existing**
`POST /api/execution/manual-demo` route (unrelated to the owner-decision
rewire; gated by `user_confirmed===true`, `DEMO`-only trade mode, and
`VITE_AG_API_MODE==='real'`) spawns `scripts/web_execute_trade.py` by design —
this is the project's separate, already-existing manual-demo execution bridge,
not something this candidate introduced.

Attribution proof: `git diff BASELINE..CANDIDATE -- web/server.ts` and
`git diff BASELINE..CANDIDATE -- web/tests/wp0a_execution_route_containment.test.ts`
are both **empty** — both files are byte-identical between baseline and
candidate. Confirmed independently by running the identical test against a
throwaway baseline worktree (`git worktree add ... e7e9583...`): **same
failure, same assertion, same line**. Classification: **PRE_EXISTING_NON_ATTRIBUTABLE**.

```
WP0A_CANDIDATE  = FAIL (1/9 sub-test; same failure reproduced 3x, not a flake)
WP0A_BASELINE   = FAIL (identical failure, identical assertion)
WP0A_CLASSIFICATION = PRE_EXISTING_NON_ATTRIBUTABLE
```

## Backend deterministic-decision_id replay (P8)

Reused the existing fixture pattern from `tests/test_owner_decision_bridge.py`
(`CanonicalProposal` + `OwnerDecision` + `OwnerDecisionStore()` in-memory, no
FastAPI/HTTP layer needed for this specific semantic — the HTTP-level
duplicate-confirmation case is already separately covered by
`tests/test_api_owner_decision.py::test_duplicate_http_confirmation_remains_idempotent`).
Ran via a temporary, untracked test file inside this worktree's `tests/`
directory (`tests/_audit_r1_replay_temp.py`), deleted immediately after the run
— never committed, confirmed via `git status --short` (clean before and after).

- **Test A** (APPROVE then identical APPROVE replay): PASS — second call
  returns the exact same `ExecutionDecision` object (`is` identity), status
  `AUTHORIZED`.
- **Test B** (REJECT then identical REJECT replay): PASS — second call returns
  the same object, status `REJECTED`, `reason_code=OWNER_REJECTED`.
- **Test C** (APPROVE then REJECT, same `decision_id`): PASS — idempotency-first
  check in `bridge.py` (~line 239) returns the original `AUTHORIZED` outcome
  unchanged; the REJECT request never overwrites it, `trade_command` unchanged.
- **Test D** (REJECT then APPROVE, same `decision_id`): PASS — original
  `REJECTED` outcome remains protected; the APPROVE request never silently
  authorizes, `trade_command is None` throughout.

All four exercised the in-memory `OwnerDecisionStore` (no `path=` argument, matching
every existing test in `test_owner_decision_bridge.py`) — durable/on-disk
persistence behavior is covered separately by
`tests/test_owner_decision_store_persistence.py` (Tier 1, passed).

```
PROPOSAL_LEVEL_OWNER_DECISION_UNIQUENESS = NOT_ENFORCED_BY_BACKEND
CROSS_CLIENT_AT_MOST_ONCE = NOT_GUARANTEED
```
(Unchanged, out-of-scope R5C limitation — not a defect of this candidate.)

## Backend regression

`git diff BASELINE..CANDIDATE -- src/` is empty — confirmed, so no backend
behavior change is attributable to this candidate in principle.

- Tier 1 (focused, required): `test_api_owner_decision.py`,
  `test_api_owner_decision_auth.py`, `test_owner_decision_bridge.py`,
  `test_owner_decision_store_persistence.py`, `test_api_opportunity_analysis.py`
  — **46 passed**, 0 failed.
- Tier 2 (broader owner_decision/proposal_envelope/execution-boundary-adjacent):
  `test_ag_scheduler_v2_p0_p1_and_lifecycle.py`, `test_api_canonical_proposals.py`,
  `test_assistant_canonical_proposal_adapter.py`,
  `test_execution_durable_idempotency_lifecycle.py`, `test_execution_lifecycle.py`,
  `test_proposal_dedup_r1.py`, `test_proposal_envelope_adapters.py`,
  `test_proposal_envelope_execution_boundary.py`, `test_proposal_envelope_models.py`,
  `test_proposal_lifecycle.py`, `test_td6_deterministic_dedup_targets.py` —
  **136 passed**, 0 failed.
- Tier 3 (full suite): not run — Tier 1+2 (182 tests, 0 failures) plus the
  proven-empty `src/` diff already give a clear, high-confidence signal for a
  frontend-only candidate; running the entire multi-hundred-test suite would
  not change the attribution conclusion and was judged not warranted for this
  scope.

## Side-effect firewall

No test in this audit connects to a real MT5 terminal or broker. The
project's `tests/conftest.py` MT5 stub raises `MT5StubOperationAttempted` on
any real operation call, so any accidental real order attempt would have
failed loudly, not silently. Zero such failures observed.

```
REAL_ORDER_CHECK_CALLS = 0
REAL_ORDER_SEND_CALLS  = 0
BROKER_ORDERS_SENT     = 0
DEMO_ORDERS_SENT       = 0
LIVE_ORDERS_SENT       = 0
```

## Immutability

`git rev-parse HEAD` = `061d3e09765c88950ae1b074aff5a02a74f41ade` before, during
(after `npm ci`), and after all test runs. `git status --short`, `git diff`,
`git diff --cached` were empty at every checkpoint except for the deliberately
created and then deleted temporary `tests/_audit_r1_replay_temp.py` (never
committed). No tracked candidate file was ever modified. This document itself
is added and committed to the audit branch only, per this repo's established
prior-audit convention (`D:/AG-final-demo-gate-audit`), not pushed.

## Conclusion

`FRONTEND_OWNER_DECISION_REWIRE_REAUDIT_PASS`
