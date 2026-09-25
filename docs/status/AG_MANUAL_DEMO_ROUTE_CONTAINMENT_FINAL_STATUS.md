# AG Manual-Demo Route Containment (Gate 1) -- Final Status (2026-09-25)

## Baseline

```
BASE_SHA    = 5501420bb6f4666f6ae5bd6084cf585c307d2c5d (origin/main, matched expected)
WORKTREE    = D:/AG-manual-demo-containment
BRANCH      = fix/manual-demo-route-containment-final
WORKTREE_CLEAN (pre-fix) = YES
```

## Architecture (derived from source, not assumed)

```
LEGACY_ROUTE                   = POST /api/execution/manual-demo (web/server.ts)
CANONICAL_OWNER_DECISION_ROUTE = POST /api/canonical-proposals/{id}/owner-decision
                                  (src/api/app.py, gated by require_owner_auth /
                                  X-AG-Owner-Key)
CANONICAL_EXECUTION_ENTRYPOINT = owner_decision.bridge.evaluate_owner_decision ->
                                  execution.executor / durable_idempotency ->
                                  execution.mt5_gateway.order_check/order_send
BROKER_MUTATION_BOUNDARY       = src/execution/mt5_gateway.py (order open) and
                                  src/mt5/management_gateway.py (existing position);
                                  both config-gated (allow_order_check/allow_order_send)
                                  and account-guarded (mt5.account_guard)
```

## Defect reproduction

```
BASELINE_BYPASS_REPRODUCED = NO
REASON = Reproducing would require spawning `python scripts/web_execute_trade.py
  --confirm` against a real/attempted MT5 session before any in-process sentinel
  in this codebase could intercept it -- there is no existing instrumentation
  hook in server.ts or the Python CLI to safely stop it mid-flight. Unsafe given
  this mission's zero-order-send invariant. Substituted with direct source/call-
  path evidence instead: the pre-fix handler (read at web/server.ts:1325-1371
  before edit) called `spawn(pythonExe, [...,'scripts/web_execute_trade.py',
  ...,'--confirm'], ...)` unconditionally once `VITE_AG_API_MODE=real` and
  `user_confirmed=true`, with no owner-decision-store involvement -- a genuine,
  code-verified bypass, corroborated by PROJECT_STATUS.md's own prior
  "AG_FINAL_DEMO_EXECUTION_GATE" entry documenting it as a known limitation.
```

## Sentinel positive control

```
SENTINEL_POSITIVE_CONTROL = PASS
POSITIVE_CONTROL_SPAWNS   = 1
```
Standalone `node -e` script monkeypatched `child_process.spawn`, invoked a
harmless child process through it, and confirmed the interceptor counted
exactly 1 spawn -- proving the detection method itself works before trusting
any zero-spawn result below.

For the retired route itself, the stronger proof used is elimination, not
runtime interception: the handler was rewritten to return 410 unconditionally,
before any body parsing, with the `spawn(...)` call and every reference to the
literal string `'web_execute_trade.py'` removed from `web/server.ts` entirely
(verified by the pre-existing source-scan test, see below) -- there is no
remaining code path in this route that could invoke `spawn` at all.

## Containment implementation

`web/server.ts`'s `POST /api/execution/manual-demo` handler replaced: removed
the `child_process.spawn(...)` invocation of `scripts/web_execute_trade.py
--confirm` and all upstream validation/mode-gating that preceded it (previously
mode-gated: only actually spawned when `VITE_AG_API_MODE=real`). Now
unconditionally:
```
HTTP 410 { success: false, error: 'EXECUTION_ROUTE_RETIRED',
  message: 'Direct manual Demo execution has been retired. Use the canonical
  owner-authorized execution workflow (...)' }
```
Reuses the exact `EXECUTION_ROUTE_RETIRED` contract already established by the
prior retirement of `/api/execution/manage` and `/api/execution/claim` in the
same file -- no new response shape introduced. `web/src/App.tsx`'s
`handleExecuteTrade` (the only frontend caller) already treats any
`!res.ok`/`!data.success` response as a generic execution-failure toast; no
frontend change needed or made.

## HTTP containment matrix (`web/tests/wp0a_execution_route_containment.test.ts`, new WP0C block)

Run: `npx tsx --test --test-concurrency=1 tests/wp0a_execution_route_containment.test.ts`

| # | Case | Result |
|---|---|---|
| 1 | valid legacy payload | 410, `EXECUTION_ROUTE_RETIRED` |
| 2 | `{}` | 410 |
| 3 | `null` JSON | body-parser rejects (>=400), no execution evidence |
| 4 | malformed/truncated JSON (`{"symbol":`, `{not valid json}`, `''`) | never 200, no execution evidence |
| 5 | missing required legacy fields | 410 |
| 6 | arbitrary extra / bypass-looking fields (`bypass`,`force`,`admin`,`mode`) | 410 |
| 7 | no auth header | 410 (every other case already covers this) |
| 8 | arbitrary auth header (`X-AG-Owner-Key`, fake `Authorization`) | 410 |
| 9 | alternate content-type (`application/json;charset=utf-8`) | 410 |
| 10 | query parameters (`?confirm=true&force=1`) | 410 |
| 11 | repeated requests (x3) | 410 each, independently |
| 12 | source scan | `'web_execute_trade.py'` absent from `web/server.ts` |

```
HTTP_MATRIX_TOTAL           = 13 assertions across 12 test cases (+3 malformed-JSON sub-cases)
HTTP_MATRIX_410              = 10 of 12 direct-410 cases
HTTP_MATRIX_PARSER_REJECTED  = 2 (null body, malformed/truncated JSON -- express.json()
                                  strict-mode rejection, surfaced as a pre-existing
                                  500 from Express's default error handler since this
                                  app has no app-level JSON-parse error middleware;
                                  not weakened to force a specific code, per mission
                                  instruction not to alter framework parsing)
HTTP_MATRIX_FAILED           = 0
PROCESS_SPAWN_ATTEMPTS        = 0 (no code path to spawn remains)
```

Full file result: **19/19 passed** (includes the 7 pre-existing WP0A/WP0B tests,
unaffected). Full `npm test` (5 files, typecheck + 59 tests): **59/59 passed**,
zero collateral regressions.

## Alternate execution-bypass audit

Searched for actual call sites (not docstring/comment mentions) of
`order_send(`, `order_check(`, `subprocess.(run|Popen|call)(`,
`child_process` across `web/server.ts`, `src/`, `web/src/`, `scripts/`.

| File | Symbol/Route | Mutation reachable | Authority | Classification | Evidence |
|---|---|---|---|---|---|
| `src/execution/mt5_gateway.py` | `order_check`/`order_send` (open) | Yes | `owner_decision.bridge` -> `execution.executor`, config-gated (`allow_order_check`/`allow_order_send`), account-guarded | CANONICAL_AUTHORIZED | lines 112-197 |
| `src/mt5/management_gateway.py` | `order_check`/`order_send` (existing position) | Yes | canonical Python CLI (`scripts/manage_trade.py`) under `config/trading.yaml` | CANONICAL_AUTHORIZED | lines 128-140 |
| `web/server.ts` `/api/execution/execute` | -- | No (retired, pre-existing) | -- | RETIRED | prior WP0A test, unchanged |
| `web/server.ts` `/api/execution/manage`, `/claim` | -- | No (retired, pre-existing) | -- | RETIRED | prior WP0B tests, unchanged |
| `web/server.ts` `/api/execution/manual-demo` | -- | No (retired, this change) | -- | RETIRED | this gate |
| `web/server.ts` `/api/execution/positions` (GET) | `spawn` -> `scripts/web_mt5_positions.py` | No (read-only position query, no order_check/order_send) | -- | READ_ONLY | script reads `mt5.account.positions`/`load_claims` only |
| `scripts/web_execute_trade.py` (CLI) | canonical CLI entrypoint | Yes, by design | direct terminal/file-system operator invocation, requires `--confirm` and config gates | CANONICAL_AUTHORIZED | not reachable from any web route after this fix |

```
PRODUCTION_MUTATION_SURFACES  = 2 (mt5_gateway.py, management_gateway.py -- both
                                   pre-existing, config-gated, account-guarded,
                                   unchanged by this gate)
ALTERNATE_UNSAFE_BYPASS_FOUND = NO
UNSAFE_BYPASS_COUNT           = 0
```

## Canonical pipeline preservation

Zero files under `src/` changed by this gate. The 71 focused backend tests
already validated in the prior qualification pass (`test_proposal_dedup_r1`,
`test_api_owner_decision_auth`, `test_api_owner_decision`,
`test_runtime_error_log`, `test_execution_reconciliation{,_r1,_r2}`) exercise
exactly this pipeline and are unaffected by a `web/server.ts`-only change.

```
OWNER_AUTH_PRESERVED             = YES (unchanged, src/api/app.py untouched)
OWNER_DECISION_DURABILITY        = YES (unchanged)
PROPOSAL_IDENTITY_PRESERVED      = YES (unchanged)
EXECUTION_IDEMPOTENCY_PRESERVED  = YES (unchanged)
RECONCILIATION_PRESERVED         = YES (unchanged)
CANONICAL_DEMO_PATH_PRESERVED    = YES (owner-decision route untouched)
LIVE_EXECUTION_UNAUTHORIZED      = YES (no config/registry/authorization file touched)
```

## Safety counters (this session, throughout)

```
REAL_ORDER_CHECK_CALLS = 0
REAL_ORDER_SEND_CALLS  = 0
DEMO_ORDERS_SENT        = 0
LIVE_ORDERS_SENT        = 0
```
No MT5 terminal was started; no broker connection was made.

## Unresolved limitations (out of this gate's scope)

- The `EXECUTION_ROUTE_RETIRED` message references the canonical owner-decision
  route by path rather than a fully worked frontend flow for manual (non-
  proposal-driven) Demo entry -- if that capability is still wanted, it needs a
  deliberate design through the canonical pipeline, not a restoration of this
  route.
- `web/src/App.tsx`'s `handleExecuteTrade` (manual entry form) will now always
  show a generic "Execution failed" toast for manual Demo submissions; a
  friendlier retired-route message is UI polish, not a containment requirement,
  and was left unchanged per scope discipline.

## Commit discipline

Local commit only, not pushed -- no publication authorization given for this
Gate. Changed files: `web/server.ts`, `web/tests/wp0a_execution_route_containment.test.ts`.
