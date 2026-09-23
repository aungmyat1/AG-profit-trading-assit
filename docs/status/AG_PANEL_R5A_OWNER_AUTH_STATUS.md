# Panel-R5A Owner Auth -- Status (2026-09-23)

R5A_BASE_SHA = `609e92f07ef2fac6333df3d14ee91648b4e3b8d1` (PANEL-R4 implementation,
independently audited PASS -- `docs/status/AG_PANEL_R4_INDEPENDENT_AUDIT_STATUS.md`,
audit artifact `00cc13283d15cca897b7b2b199c386d35aa5add2`, local branches
`panel-r4-http-confirmation` and `audit/panel-r4`).

This work package implements the prerequisite the R4 independent audit named before any
R5B+ (durable idempotency / broker-side-effect) work: "R5 must add an authenticated
owner boundary before broker-side effects." It is the first of the bounded R5 packages
(R5A owner auth -> R5B durable idempotency -> R5C risk/execution gate -> R5D MT5 Demo
submission -> R6 broker reconciliation).

## What was added

- `require_owner_auth` (`src/api/app.py`) -- a FastAPI route dependency, applied only
  via `dependencies=[Depends(require_owner_auth)]` on
  `POST /api/canonical-proposals/{proposal_id}/owner-decision`. No other route is
  touched.
- Configuration: `AG_OWNER_API_KEY` environment variable (no default, no fallback
  value). The client must send it back in the `X-AG-Owner-Key` request header.
- `tests/test_api_owner_decision_auth.py` -- 7 focused tests.
- `tests/test_api_owner_decision.py` -- unchanged in intent; its `_client` helper now
  also overrides `require_owner_auth` (same `dependency_overrides` pattern already used
  for the two stores), since those 13 tests are about
  `owner_decision.bridge.evaluate_owner_decision()`'s semantics, not this boundary.

## Fail-closed design

- **Unset key means disabled, not open.** If `AG_OWNER_API_KEY` is not set in the
  process environment, every call to this route returns `503
  OWNER_AUTH_NOT_CONFIGURED` -- never silent pass-through. This matches AGENTS.md
  "Default safety": absence of explicit configuration must never be read as
  authorization.
- **Constant-time comparison.** The supplied header is compared with
  `hmac.compare_digest`, not `==`, so response timing cannot be used to recover the
  configured key byte-by-byte.
- **Missing/empty/wrong header -> `401 OWNER_AUTH_REJECTED`.** Same reason code for all
  three so a caller cannot distinguish "no header" from "wrong header" from response
  shape alone.
- **Scoped to exactly one route.** Every GET route audited in R4
  (`/api/canonical-proposals[/{id}]`, `/api/opportunity-analysis`) remains reachable
  with no header, whether or not `AG_OWNER_API_KEY` is configured --
  `test_get_routes_never_require_owner_auth`.
- **Rejected auth never reaches the bridge.** A 401/503 response happens before
  `evaluate_owner_decision()` is called, so no `OwnerDecision`/`ExecutionDecision` row
  is created or consumed for a rejected attempt --
  `test_auth_rejection_leaves_no_owner_decision_recorded` confirms this indirectly (a
  same-`decision_id` retry with the correct key still returns a fresh `AUTHORIZED`
  result, not a conflicting-reuse rejection).

## What was deliberately NOT added

- No session/cookie/token-issuance flow, no user database, no role model. This is a
  single shared local-owner key, matching the existing local-only deployment model
  (127.0.0.1 bind, narrow CORS allow-list) documented in R4's status doc and the module
  docstring -- appropriate for "one local owner", not a multi-user system.
- No change to `owner_decision.bridge.evaluate_owner_decision()` or any of its
  fail-closed rules (R3, frozen, untouched).
- No durable/cross-process idempotency. `OwnerDecisionStore` is still the R3/R4
  process-local, lock-protected, in-memory store -- unchanged. That gap is explicitly
  R5B's, not this package's; see "Next recommended package" below.
- No touch to the pre-existing, separate `POST /api/tickets/{approval_id}/authorize-demo`
  route (`api.execution_service.authorize_demo_execution`), which already resolves to
  `get_execution_handler()` / the real MT5 execution handler in production and today has
  no equivalent auth boundary either. That route predates the R2-R4 lineage this package
  is scoped to (R4's own audit noted it as a pre-existing, unmodified, separate pathway)
  and is out of scope here -- flagged below as a known gap for a future package rather
  than folded into R5A silently.

## Tests

Focused: `python -m pytest tests/test_api_owner_decision_auth.py tests/test_api_owner_decision.py -q`
-> 20 passed.

Regression: `python -m pytest tests/test_api_opportunity_analysis.py tests/test_api.py
tests/test_api_canonical_proposals.py tests/test_post_asian_observe_only_remediation.py
tests/test_post_asian_status_readonly_remediation.py tests/test_post_asian_pilot.py
tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_adapters.py
tests/test_assistant_canonical_proposal_adapter.py tests/test_owner_decision_bridge.py
tests/test_api_owner_decision.py tests/test_api_owner_decision_auth.py -q` -> 226 passed,
1 failed (the same pre-existing, out-of-scope
`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover` failure
already documented against the R3/R4 baseline; unrelated to this change and not
introduced by it).

## Static boundary sweep (P19/P6, re-run against this change)

`git grep -n "user_confirmed=True" -- src/api/app.py` -> no match.

`git grep -n "order_send\|mt5_gateway\|execution.executor" -- src/api/app.py` -> only
this change's own docstring text describing what it does NOT do.

## Isolation

`wp/v2-3c-asian-sweep-remediation` and its dirty `state/fx_schedule/slot_ledger.json`
were never referenced. This worktree was created fresh from
`609e92f07ef2fac6333df3d14ee91648b4e3b8d1`.

## Known gap (not fixed here, flagged for a future package)

`POST /api/tickets/{approval_id}/authorize-demo` has no owner-auth boundary today and
is closer to an actual broker call than the owner-decision route this package gates
(it depends on `get_execution_handler()`, the real MT5 execution handler in
production). It predates this R2-R4-R5A lineage and touching it was out of scope for
this bounded package; recommend gating it with the same `require_owner_auth`
dependency (or an equivalent) before or alongside R5D.

## Next recommended package

`PANEL_R5A_INDEPENDENT_AUDIT`, then `PANEL_R5B` (durable, cross-process idempotency for
`OwnerDecisionStore`/`decision_id`/`execution_id`/`command_id`/`broker_order_id`, so a
crash after MT5 accepts an order and before the HTTP response is returned cannot result
in a duplicate submission on retry). R5C (risk/execution gate) and R5D (MT5 Demo
submission) remain out of scope until R5B closes and an independent audit passes.
