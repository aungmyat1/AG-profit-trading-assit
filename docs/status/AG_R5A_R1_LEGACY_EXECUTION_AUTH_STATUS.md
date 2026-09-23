# AG R5A-R1 Legacy Execution Auth -- Status (2026-09-23)

R5A_R1_BASE_SHA = `083399df0644ebe7a38c1a2d9b0174da6dcb18ac` (PANEL-R5A implementation,
independently audited `PANEL_R5A_INDEPENDENT_AUDIT_PASS`, audit artifact
`fea11af1551fc158bfb0cfcfe7134bd499efdb71`, branch `panel-r5a-owner-auth`).

Mission: secure the existing, separate, broker-reachable
`POST /api/tickets/{approval_id}/authorize-demo` route with the same canonical
`require_owner_auth` dependency R5A added for `owner-decision`, without introducing new
execution behavior, a second auth implementation, or any change to MT5/`user_confirmed`
semantics.

## P1 -- Trace (recorded before any modification)

`authorize_demo` (`src/api/app.py`) -> `api.execution_service.authorize_demo_execution()`
-> (on every guard passing) the injected `execution_handler` -> production default
`authorization.mt5_execution_handler.mt5_execution_handler` -> `execution.executor.execute()`
with `user_confirmed=True`.

Existing, unmodified semantics traced:
- **Request schema**: `AuthorizeDemoRequest{action: str = "EXECUTE_DEMO"}`. `action` is
  the route's own explicit confirmation field; a non-`"EXECUTE_DEMO"` value is a
  `400 UNSUPPORTED_ACTION` before anything else runs.
- **Confirmation semantics**: reaching the execution handler already required (per
  `mt5_execution_handler`'s own docstring) an explicit Web/Telegram "Execute (Demo)"
  action this turn, an atomic one-time `ExecutionApprovalStore.claim()`, and every
  `authorize_demo_execution()` guard passing. `user_confirmed=True` is set only inside
  `mt5_execution_handler`, on the strength of that whole chain -- never by this route
  directly.
- **Demo checks**: `check_strategy_demo_authorized(proposal.strategy_id)` and
  `approval.environment == ENVIRONMENT_DEMO`.
- **Execution authority checks**: atomic claim (`APPROVAL_ALREADY_PROCESSED` on replay),
  proposal-integrity hash verification, strategy Demo authority, Demo-only environment.
- **Error semantics**: normalized `AuthorizationExecutionResult(success, state,
  reason_code)`, never an exception for an expected/blocked outcome; HTTP 200 with
  `success: false` for a blocked-but-well-formed request, 400 only for `UNSUPPORTED_ACTION`.
- **Broker reachability**: exactly one path, gated behind every check above --
  confirmed by `tests/test_api.py`'s existing `test_duplicate_authorize_demo_request_calls_gateway_exactly_once`
  (unmodified assertion, still passes) and this package's own new handler-call-counting
  tests.

None of the above was changed.

## P2 -- Auth reused, not duplicated

`POST /api/tickets/{approval_id}/authorize-demo` now carries
`dependencies=[Depends(require_owner_auth)]` -- the exact same function object R5A
defined for `owner-decision`, imported from nowhere new, with no second
key/header/compare implementation:

```
AG_OWNER_API_KEY -> X-AG-Owner-Key -> require_owner_auth -> authorize-demo route
```

`git grep -n "OWNER_API_KEY_ENV\|OWNER_AUTH_HEADER" -- src/` shows exactly one
definition each (both in `src/api/app.py`, from R5A), referenced by both routes.

## P3 -- Fail closed (verified by test)

| Condition | Result | Handler called | Broker reachable |
|---|---|---|---|
| `AG_OWNER_API_KEY` unset | `503 OWNER_AUTH_NOT_CONFIGURED` | No | No |
| Header missing | `401 OWNER_AUTH_REJECTED` | No | No |
| Header incorrect | `401 OWNER_AUTH_REJECTED` | No | No |
| Header correct | existing `authorize_demo_execution()` semantics continue unchanged | Only if every pre-existing guard also passes | Only then |

Auth success does not itself mean `user_confirmed=True`, execution authorized, risk
approved, or MT5 order allowed -- see P4.

## P4 -- Existing confirmation preserved

`test_valid_auth_alone_does_not_bypass_user_confirmation`: a correct owner-auth header
with `action != "EXECUTE_DEMO"` is still `400 UNSUPPORTED_ACTION`, handler never called.
`test_valid_auth_alone_does_not_bypass_demo_authority_guard`: a correct header against
the real, current `strategies/registry.yaml` (where `ST_ASIAN_SWEEP_5R_V1` is
`demo_authorized: false`) still returns `success: false,
reason_code: BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED`, handler never called. The chain is:

```
authenticated owner -> explicit action=="EXECUTE_DEMO" -> existing authorization checks -> existing execution handler
```

not `authenticated owner -> automatic execution`.

## P5 -- GET safety

No GET route was touched. `test_get_routes_remain_unauthenticated` reconfirms
`GET /api/tickets` stays reachable with no header, `AG_OWNER_API_KEY` configured or
not.

## P6 -- Tests added

`tests/test_api_authorize_demo_auth.py` -- 9 focused tests (P6's 10 required
assertions map onto 9 tests; #5 and #6, zero handler calls / zero broker
reachability on auth failure, are the same observable point in this codebase --
`execution_handler` is the only path to a broker call this module has -- and are
combined into one test plus reconfirmed individually in the missing/wrong-header
tests). All use a mocked `execution_handler`; no test submits or can submit a real
MT5 order.

`tests/test_api.py`'s shared `_client()` helper now also overrides
`require_owner_auth` (same pattern as the three pre-existing dependency overrides) --
those tests are about `authorize_demo_execution()`'s own semantics, not this new
boundary, and remain otherwise unmodified.

## P7 -- Static/dependency check

`git grep -n "user_confirmed=True" -- src/api/app.py` -> no match.
`git grep -n "order_send\|mt5_gateway\|execution.executor" -- src/api/app.py` -> only
this and R5A's own docstring text describing what the HTTP layer does NOT do.
No hardcoded secret: `AG_OWNER_API_KEY` is read via `os.environ.get`, no literal
default value. No new Live-authority code path. No new automatic-confirmation code
path -- `action == "EXECUTE_DEMO"` remains a caller-supplied field.

## P8 -- Regression

`python -m pytest tests/test_api_authorize_demo_auth.py tests/test_api_owner_decision_auth.py
tests/test_api_owner_decision.py tests/test_api.py tests/test_api_canonical_proposals.py
tests/test_api_opportunity_analysis.py tests/test_owner_decision_bridge.py
tests/test_proposal_envelope_execution_boundary.py -q` -> **91 passed, 0 failed**.

Known pre-existing failure reproduced separately, in isolation, to confirm it is
unrelated to this change:
`python -m pytest tests/test_proposal_envelope_adapters.py tests/test_assistant_canonical_proposal_adapter.py -q`
-> 38 passed, 1 failed
(`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`, the
same assertion already documented against the R3/R4/R5A baselines; this package's diff
touches neither file it's defined or exercised in).

## Isolation

Diff scope is exactly `src/api/app.py`, `tests/test_api.py` (modified), plus one new
file `tests/test_api_authorize_demo_auth.py` and this status document. No frontend
file, no `wp/v2-3c-asian-sweep-remediation` state, no other worktree's content was
referenced.

## Next recommended package

`R5A_R1_INDEPENDENT_AUDIT` -- independent verification of this SHA. R5B (durable,
cross-process idempotency) remains the next architectural package after that audit
passes; this package does not implement it.
