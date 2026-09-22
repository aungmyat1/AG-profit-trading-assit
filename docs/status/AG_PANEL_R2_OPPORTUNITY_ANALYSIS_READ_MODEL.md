# Panel-R2 Opportunity Analysis Read Model

`GET /api/opportunity-analysis` is an observation-only projection of the existing
Post-Asian evaluation. It calls `run_pilot_cycle(..., observe_only=True)` directly;
it does not invoke CLI scripts or preflight.

`READY` is a strategy decision and optional in-memory proposal preview. It is not
PREPARE, owner confirmation, demo authorization, or execution authorization.
The response always reports `execution_authority: NONE`. GET requests do not claim
opportunity capacity, persist native or canonical proposals, deliver tickets, or
execute broker orders.
