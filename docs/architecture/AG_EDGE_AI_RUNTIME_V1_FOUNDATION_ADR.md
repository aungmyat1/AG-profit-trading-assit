# ADR: AG Edge + AI Runtime V1 foundation

Status: ACCEPTED FOUNDATION BASELINE / P0–P2 ONLY
Decision date: 2026-09-26

## Decision

Freeze `1a8e7c5d922ba48423dca1b7858f8895afe0d66f` as the migration baseline for
the additive Edge + AI Runtime V1 architecture work. Its tree is
`53b54053283f58fe7f34a898808212275c725768`. This is the merged `origin/main`
manual-demo route-containment baseline selected explicitly by the owner. Gate-2 R3
candidate `19fd8fa320e6f93ed15ec32cd442941e1fc337b2` is separate, awaiting independent
verification, and is not incorporated. A future accepted Gate-2 SHA requires a
separate compatibility and reconciliation decision.

The foundation creates versioned data contracts and empty package boundaries. Existing
runtime code, strategy semantics, risk policy, authorization, broker mutation behavior,
scheduler, owner-decision behavior, and frontend behavior remain the authorities during
this phase.

## Frozen baseline manifest

| Field | Frozen value |
|---|---|
| Baseline commit | `1a8e7c5d922ba48423dca1b7858f8895afe0d66f` |
| Baseline tree | `53b54053283f58fe7f34a898808212275c725768` |
| Owner selection | `MIGRATION_BASELINE_SELECTED` |
| Gate-2 R3 | `SEPARATE_LINEAGE_NOT_ACCEPTED_AS_FOUNDATION_BASELINE` |
| Planning branch | `plan/edge-ai-runtime-v1` |
| Foundation branch | `arch/edge-ai-runtime-v1-foundation` |
| Initial foundation HEAD | `847924439d7b2d2f5e886c9f047cbb76d8e4a7ab` |
| Initial foundation tree | `bb801045d7d4f8c871e9ca5f35e17591621591eb` |
| Initial worktree | clean |
| Initial origin/main | `1a8e7c5d922ba48423dca1b7858f8895afe0d66f` |

The initial foundation HEAD contains only the planning document and agent prompt above
the frozen baseline. The complete manifest, validation record, and final candidate SHA
are maintained in `docs/status/AG_EDGE_AI_RUNTIME_V1_FOUNDATION_STATUS.md`.

## Existing authorities and boundaries

- Canonical owner decision: `POST /api/canonical-proposals/{id}/owner-decision`,
  implemented in `src/api/app.py` and delegated to
  `owner_decision.bridge.evaluate_owner_decision()`.
- Canonical new-order route: `assistant.commands.execute_command()` with explicit
  same-turn `user_confirmed=True`, then `execution.executor` and
  `execution.mt5_gateway`.
- Existing-position management: `scripts/manage_trade.py` through
  `trade_management.manager` and `src/mt5/management_gateway.py` under its independent
  configuration gates.
- Production Python broker mutation call sites: `src/execution/mt5_gateway.py`
  (`order_check` and `order_send`, new orders) and
  `src/mt5/management_gateway.py` (`order_check` and `order_send`, existing positions).
- Legacy web route `POST /api/execution/manual-demo`: retired with HTTP 410;
  `web/server.ts` no longer spawns `scripts/web_execute_trade.py`.
- Strategy registry: demo authorization is true only for `SESSION_TRADE_V1` among the
  listed strategies; live authorization is false for all listed strategies.
- `config/trading.yaml`: order check, order send, and live trading default disabled;
  manual trade management is also disabled by default.

## Authority matrix

| Component | Facts | Strategy decision | Risk decision | Owner decision | Broker mutation |
|---|---:|---:|---:|---:|---:|
| MT5 indicators (future) | emit only | No | No | No | No |
| Owner Edge (future) | read/revalidate | no new decision | final guards only | consume/verify | gated, owner-confirmed only |
| Strategy Core (future) | consume | deterministic only | No | No | No |
| Risk Engine (future) | account/proposal | No | deterministic only | No | No |
| Control API / AI-facing tools (future) | authorized views | No | No | authenticated record/proxy only | No |
| Existing runtime (current authority) | as implemented | strategy engine | `execution/risk.py` | owner-decision boundary | existing gated gateways only |

AI has zero broker authority. No automatic execution or authorization expansion is
introduced by these contracts or shells.

## Rollback and recovery

The pre-foundation tree is recoverable from baseline commit
`1a8e7c5d922ba48423dca1b7858f8895afe0d66f`. Review the foundation candidate as a
reversible additive commit; revert that commit to remove P0–P2 additions while retaining
the planning documents. Do not reset a shared branch or rewrite historical evidence.

## Consequences

The contracts are standalone standard-library Python definitions. They cannot import
MT5, broker gateways, AI clients, or application runtime modules. Package shells state
dependency rules without moving existing code. Independent review is required before
P3 or any runtime migration begins.
