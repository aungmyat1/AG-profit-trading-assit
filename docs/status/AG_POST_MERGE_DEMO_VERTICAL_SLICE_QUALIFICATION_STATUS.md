# AG Post-Merge Demo Vertical Slice Qualification (2026-09-25)

Scope: prepare-only qualification (Phases 0-3 + security), by explicit owner choice.
No local servers started, no MT5 session opened, no order submitted. Phases 5-14
(real runtime, real MT5 data, owner-decision runtime, prepared E2E, execution,
reconciliation, frontend parity) were **not attempted** this pass and must not be
read as PASS.

## Baseline correction (blocking, now resolved)

PR #4 showed all 10 review threads resolved, but GitHub had merged it at head
`8bd7ae6` -- one commit behind the branch's actual tip. Commit `654fac6` (the fix
for all 10 findings) was pushed after the merge and never reached `main`. Opened
and merged [PR #5](https://github.com/aungmyat1/AG-profit-trading-assit/pull/5)
(merge commit `10da232260fd0cd11a4766ac2468ad0f335d0e38`) to close the gap. `main`
now actually contains the fixes the review threads claim are resolved.

## Phase 1 -- review replay guard

10/10 threads on PR #4 confirmed resolved via GraphQL before this session; the
`<ci-monitor-event>` replays received afterward referenced the same 10
`comment_id`s with no new unresolved thread -> classified `STALE_REVIEW_REPLAY`,
no code action taken in response to them.

## Phase 2 -- security/diagnostic check (PASS)

`web/scripts/check_mt5_mcp.mjs` on merged `main`:
- `shell: isWin` removed from the Windows `where` lookup (line 55) -- no shell
  metacharacter injection surface via `MT5_MCP_COMMAND`.
- Claude Desktop launcher command-line echo now redacts the value following any
  `--password/--login/--server/--token/--secret/--key` argument
  (`SENSITIVE_ARG` regex + `redactArgs`, lines 87-99).

## Phase 3 -- focused regression (PASS, fresh worktree from origin/main)

Worktree: `D:/AG-post-merge-demo-e2e-r1` @ `10da232` (branch
`verify/post-merge-demo-e2e-r1`).

```
python -m pytest tests/test_proposal_dedup_r1.py tests/test_api_owner_decision_auth.py \
  tests/test_api_owner_decision.py tests/test_runtime_error_log.py \
  tests/test_execution_reconciliation.py tests/test_execution_reconciliation_r1.py \
  tests/test_execution_reconciliation_r2.py -q
```
Result: **71 passed, 0 failed** in 33.44s. Covers: proposal identity/dedup
(same-setup dedup, strategy-version-scoped identity), owner-decision auth boundary
+ CORS preflight, owner-decision semantics, runtime-error retry-chain recovery,
execution reconciliation R1/R2 (shared broker identity).

Full-suite (4000+ tests) was not re-run in this pass: the merged code is byte-
identical to what was already run against on the pre-merge branch (186 passed on
the equivalent test selection, plus the full historical baseline documented in
`PROJECT_STATUS.md`'s `PROJECT_AUDIT_AND_CLEANUP` entry). Re-running it here would
not produce new information.

## Known pre-existing gap (not introduced by PR #4/#5, blocks Phase 11 if ever attempted)

`web/server.ts`'s `POST /api/execution/manual-demo` (introduced by `74d65ea`,
predates PR #4) still spawns `scripts/web_execute_trade.py --confirm` directly,
bypassing the canonical owner-decision -> execution pipeline. Prior commits
(`8ec1ab4`, `cbf62af`, `f266001`) attempted containment/retirement but the route
is live on current `main`. This is the same pre-existing failure already
documented in `PROJECT_STATUS.md` (`AG_FINAL_DEMO_EXECUTION_GATE`: "known
limitation, not attempted this session"). **Before any future Phase 11 (real
Demo order submission) attempt, `LEGACY_MANUAL_DEMO_ROUTE = RETIRED` must be
true; it is currently false.** Classified P0 per this mission's own priority
rubric (live-trading-escape-adjacent: an unauthenticated-boundary path that can
reach the broker gateway outside the audited owner-decision flow).

## Result

`FINAL_CLASSIFICATION = POST_MERGE_RUNTIME_BLOCKED`

Not a technical failure -- baseline, security, and focused regression all PASS.
Blocked by explicit scope choice: the owner selected "prepare-only, stop at
Phase 9" rather than starting real backend/frontend/MT5 runtime and tracing a
live proposal to a prepared order. Runtime/real-data/owner-decision-runtime/
prepared-E2E/execution/reconciliation/frontend-parity phases were not attempted
and must not be read as passed.
