# Panel-R4 HTTP Confirmation -- Status (2026-09-22)

R4_BASE_SHA = `1b55a234d6f31ae6384825b11b5c0deb8d0fde4b` (PANEL-R3 implementation,
independently audited PASS -- `docs/status/AG_PANEL_R3_INDEPENDENT_AUDIT_STATUS.md`,
audit artifact `e7b8f450d2967d8c973b0858b9c9aeb19e18b912`, remote branches
`panel-r3-owner-decision-bridge` and `audit/panel-r3`).

This work package implements the "Next recommended package" named at the end of
`docs/status/AG_PANEL_R3_OWNER_DECISION_BRIDGE_STATUS.md`: an HTTP surface that lets an
explicit owner action reach `owner_decision.bridge.evaluate_owner_decision()`.

## What was added

- `POST /api/canonical-proposals/{proposal_id}/owner-decision` (`src/api/app.py`,
  `submit_owner_decision`) -- the route named in that doc's own recommendation.
  `proposal_id` is taken only from the URL path, never from the request body, so a
  client can never submit a decision against a proposal identity other than the one it
  POSTed to.
- `OwnerDecisionRequest` / `OwnerDecisionResponse` / `PreparedTradeCommandResponse`
  (`src/api/schemas.py`) -- thin, pure read/write projections of
  `owner_decision.models.OwnerDecision` / `ExecutionDecision` / the prepared
  `TradeCommand` template. No new approval, staleness, or governance field is
  introduced here; every value is copied verbatim from the R3 bridge's own outcome.
- `tests/test_api_owner_decision.py` -- 13 focused tests.

## What was deliberately NOT added

This route adds no new authorization logic of its own. Every fail-closed rule (REJECT
is terminal; `environment` must read exactly `"DEMO"`; `proposal_state` must be
`PROPOSAL_READY`; `demo_authorized` must be `True` and `broker_mutation_blocked` must be
`False`; staleness against `plan_expires_at`; symbol/identity cross-check; `decision_id`
idempotency) is `owner_decision.bridge.evaluate_owner_decision()`'s, reused unchanged --
see that module and `tests/test_owner_decision_bridge.py` (R3, frozen, untouched by this
change).

`AUTHORIZED` here means only that a PREPARED, UNCONFIRMED `execution.models.
TradeCommand` template now exists in the response body. Reaching an actual Demo broker
order still requires a SEPARATE, later, explicitly-confirmed call this route never
makes: `assistant.commands.execute_command(trade_command, user_confirmed=True)`, where
`user_confirmed` must be derived from an explicit user instruction that same turn
(AGENTS.md Authority order point 3). `submit_owner_decision` imports neither
`execution.executor` nor `execution.mt5_gateway`, and never sets `user_confirmed=True`
-- see `tests/test_api_owner_decision.py::test_http_layer_does_not_directly_call_mt5`
(AST-based import check) and the repo-wide `git grep` swept for this status (P6 below).

`GET /api/opportunity-analysis` (R2) and `GET /api/canonical-proposals[/{id}]` are
unmodified; both remain structurally incapable of importing `owner_decision` --
see `tests/test_api_owner_decision.py::test_get_routes_cannot_create_decisions`.

## Idempotency

Same `decision_id` posted twice returns the identical `ExecutionDecision` (same
`trade_command.command_id`), never a second independent authorization -- reuses
`owner_decision.bridge.OwnerDecisionStore`'s existing lock-protected,
process-local ledger unchanged; the route only adds a FastAPI dependency
(`get_owner_decision_store`) around the same singleton pattern already used for
`ExecutionApprovalStore` / `InMemoryProposalRegistry` / `ProposalLedger` in this module.

## Tests

Focused: `python -m pytest tests/test_api_owner_decision.py -q` -> 13 passed.

Regression: `python -m pytest tests/test_api_opportunity_analysis.py tests/test_api.py
tests/test_api_canonical_proposals.py tests/test_post_asian_observe_only_remediation.py
tests/test_post_asian_status_readonly_remediation.py tests/test_post_asian_pilot.py
tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_adapters.py
tests/test_assistant_canonical_proposal_adapter.py tests/test_owner_decision_bridge.py
tests/test_api_owner_decision.py -q` -> 219 passed, 1 failed (the same pre-existing,
out-of-scope `test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`
failure already documented against the R2/R3 baseline; unrelated to this change and not
introduced by it).

## Static boundary sweep (P19/P6)

`git grep -n "user_confirmed=True" -- src/` -- all matches are pre-existing (the
`execution_runtime.cycle` / `authorization.mt5_execution_handler` production call sites
this repo already gates separately) or docstring text in this change describing what it
does NOT do. No occurrence in `src/api/app.py`'s executable code.

`git grep -n "order_send\|mt5_gateway\|execution.executor" -- src/api src/owner_decision`
-- all matches are docstring/comment references (including this change's own docstrings
stating the boundary), except `src/api/execution_service.py`'s pre-existing, unmodified
reference to the SEPARATE `authorize-demo` execution pathway
(`authorization.store.ExecutionApprovalStore` / `POST /api/tickets/{id}/authorize-demo`)
this work package does not touch.

## Isolation

`wp/v2-3c-asian-sweep-remediation`, its dirty `state/fx_schedule/slot_ledger.json`, and
`web/src/components/OwnerAnalysis/OwnerAnalysisPanel.tsx` were never referenced,
imported, or cherry-picked into this worktree. This worktree was created fresh from
`1b55a234d6f31ae6384825b11b5c0deb8d0fde4b`.

## Next recommended package

`PANEL_R4_INDEPENDENT_AUDIT` -- independent verification of this SHA before any R5
(broker execution/reconciliation boundary) work begins. R5 is explicitly out of scope
for this package.
