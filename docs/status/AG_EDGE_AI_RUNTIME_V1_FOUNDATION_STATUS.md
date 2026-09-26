# AG Edge + AI Runtime V1 Foundation Status

Date: 2026-09-26
Owner decision: `MIGRATION_BASELINE_SELECTED`
Classification: `FOUNDATION_PASS`

## P0 frozen migration baseline

```text
MIGRATION_BASE_SHA = 1a8e7c5d922ba48423dca1b7858f8895afe0d66f
MIGRATION_BASE_TREE = 53b54053283f58fe7f34a898808212275c725768
BASELINE_REASON = owner-selected merged origin/main route-containment baseline
GATE2_R3_CANDIDATE = 19fd8fa320e6f93ed15ec32cd442941e1fc337b2
GATE2_R3_STATUS = SEPARATE_LINEAGE_NOT_ACCEPTED_AS_FOUNDATION_BASELINE
BRANCH = arch/edge-ai-runtime-v1-foundation
INITIAL_HEAD = 847924439d7b2d2f5e886c9f047cbb76d8e4a7ab
INITIAL_TREE = bb801045d7d4f8c871e9ca5f35e17591621591eb
INITIAL_ORIGIN_MAIN = 1a8e7c5d922ba48423dca1b7858f8895afe0d66f
INITIAL_WORKTREE = CLEAN
```

Baseline evidence available before this mission: the merged containment record reports
the focused canonical owner-decision/execution/reconciliation backend matrix at 71/71
and the frontend containment suite at 59/59. The Gate-1 containment matrix reported
zero process spawns and zero broker orders. These are recorded baseline evidence, not
tests rerun by this foundation mission. The baseline record does not claim full-suite
green status.

Baseline environment limitations: prior broad Linux backend run recorded 4,051 passed,
46–47 failed (one nondeterministic), and 3 errors, classified in the project audit as
offline replay/live-MT5 coupling, CRLF-bound data hashes, mutable-state/directory-diff
expectations, Windows-only paths, and three known failures. This historical broad-suite
result is not represented as reproduced on this branch.

## Frozen authorities

```text
STRATEGY_DEMO_AUTHORIZATION = SESSION_TRADE_V1 only among listed strategies
STRATEGY_LIVE_AUTHORIZATION = none
CONFIG_ORDER_CHECK_DEFAULT = false
CONFIG_ORDER_SEND_DEFAULT = false
CONFIG_ALLOW_LIVE_TRADING = false
OWNER_DECISION_ROUTE = POST /api/canonical-proposals/{id}/owner-decision
OWNER_DECISION_FUNCTION = owner_decision.bridge.evaluate_owner_decision
NEW_ORDER_ENTRYPOINT = assistant.commands.execute_command(user_confirmed=True)
NEW_ORDER_GATEWAY = src/execution/mt5_gateway.py
MANAGEMENT_GATEWAY = src/mt5/management_gateway.py
PRODUCTION_ORDER_CHECK_ORDER_SEND_FILES = 2
LEGACY_MANUAL_DEMO_ROUTE = RETIRED (HTTP 410; no web_execute_trade.py spawn)
```

See [the foundation ADR](../architecture/AG_EDGE_AI_RUNTIME_V1_FOUNDATION_ADR.md) and
the merged [route containment evidence](AG_MANUAL_DEMO_ROUTE_CONTAINMENT_FINAL_STATUS.md).

## Mission results

```text
CLASSIFICATION = FOUNDATION_PASS
MIGRATION_BASE_SHA = 1a8e7c5d922ba48423dca1b7858f8895afe0d66f
MIGRATION_BASE_TREE = 53b54053283f58fe7f34a898808212275c725768
BRANCH = arch/edge-ai-runtime-v1-foundation
HEAD = this status document's containing commit (see final handoff / git log)
WORKTREE = CLEAN after local commit

P0_ARCH_BASELINE_FROZEN = PASS
P1_CONTRACTS_V1_FROZEN = PASS
P2_NEW_ARCH_SHELL_READY = PASS
OLD_RUNTIME_UNCHANGED = PASS

BROKER_CALL_DELTA = 0 (same five call sites in the same two gateway files)
STRATEGY_SEMANTIC_DELTA = 0
RISK_POLICY_DELTA = 0
AUTHORIZATION_DELTA = 0
DEMO_AUTHORIZATION_EXPANSION = NO
LIVE_AUTHORIZATION_EXPANSION = NO
```

## Validation

| Gate | Exact command | Observed result |
|---|---|---|
| New contracts and architecture boundaries | `python -m pytest -q tests/test_edge_ai_contracts_v1.py tests/test_edge_ai_architecture_boundaries.py` | PASS, 33 passed in 5.31s |
| Focused owner-decision/execution regression | `python -m pytest -q tests/test_proposal_dedup_r1.py tests/test_api_owner_decision_auth.py tests/test_api_owner_decision.py tests/test_execution_reconciliation.py tests/test_execution_reconciliation_r1.py tests/test_execution_reconciliation_r2.py` | PASS, 58 passed in 64.81s |
| Broader owner-decision/execution regression | `$files = rg --files tests | Where-Object { $_ -match 'test_(owner_decision|execution|api_owner_decision)' }; python -m pytest -q $files` | PASS, 247 passed in 136.60s |
| Protected runtime diff | `git diff --name-only 1a8e7c5 -- src scripts web strategies config scheduler` | PASS, no paths |
| Whitespace validation | `git diff --check` | PASS; only Git's LF-to-CRLF working-copy notices for the two edited Markdown files |

The two existing gateways still contain five production `order_check`/`order_send`
calls total: three in `src/execution/mt5_gateway.py` and two in
`src/mt5/management_gateway.py`. The boundary test compares their exact source lines to
the frozen baseline. The new Python contract package has no broker or MT5 imports.

`FULL_BACKEND = NOT_RUN`: the complete backend suite is several thousand tests and the
repository's recorded baseline contains known broad-suite failures; the new changes are
additive and the focused plus 247-test affected regression sets passed. No live MT5
checks were run and no broker orders were requested or sent.

`FAILURE_CLASSIFICATION = NONE`. The existing regressions emitted one upstream
Starlette/httpx deprecation warning; no test failure or runtime blocker was observed.

## Handoff

```text
FILES_CHANGED = PROJECT_STATUS.md; docs/README.md;
  docs/architecture/AG_EDGE_AI_RUNTIME_V1_FOUNDATION_ADR.md;
  docs/status/AG_EDGE_AI_RUNTIME_V1_FOUNDATION_STATUS.md;
  packages/**; apps/**; mt5/**; research/**;
  tests/test_edge_ai_contracts_v1.py; tests/test_edge_ai_architecture_boundaries.py
COMMITS = one local foundation commit (see final handoff / git log)
PUSHED = NO
NEXT_GATE = INDEPENDENT_FOUNDATION_AUDIT
```

P3 MT5 MarketState implementation is outside this handoff and must not start before the
independent foundation audit passes.
