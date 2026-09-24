# AG Profit Trading — Manual Demo Route Containment Independent Runtime Audit R2

## Classification

`MANUAL_DEMO_ROUTE_CONTAINMENT_AUDIT_BLOCKED`

R2 did not discover a production-code defect. It remains blocked by dependency restoration: a fresh detached worktree at the exact candidate SHA was created, but `web/npm ci` did not complete within the bounded runtime window and did not produce an installed `tsx` runtime. Therefore the required baseline runtime reproduction, sentinel positive control, candidate HTTP matrix, and regression gates were not executed.

## Frozen references and preservation

- BASE_SHA: `595ca08b9cc9c6f7b54b017f9748285ad7d44a87`
- AUDITED_SHA: `f26600186c0a328dab42490952eabd87b580a408`
- ORIGIN_MAIN: `87e2da798f827caf95e8c6e58916b394641c98fb`
- Candidate exists and remains the requested commit, with parent `595ca08` and subject `fix(execution): retire legacy manual-demo execution route`.
- Candidate production files were not modified.
- R1 remains historical and was not overwritten.

## Isolated environment

- AUDIT_WORKTREE: `D:\audit_manual_demo_r2_20260924`
- Worktree state at creation: clean detached `HEAD f266001`.
- Platform: Windows
- Node: `v24.14.0`
- npm: `11.9.0`
- Python: runtime version collection was not completed before the dependency gate blocked progress.
- Package manager: npm, selected from `web/package-lock.json` and `web/package.json`.
- Restore method: `npm ci` in `D:\audit_manual_demo_r2_20260924\web`.
- Restore result: incomplete/blocked; no usable `web/node_modules/tsx` installation was available.

## Runtime safety and evidence status

The committed R1 suite contains the spawn sentinel and blocks the configured Python execution command. However, because the test runner could not be restored, the sentinel positive control was not executed and the MT5 `order_check`/`order_send` interception counters were not established.

- R1 gaps resolved: No; dependency restoration prevented runtime execution.
- Baseline bypass runtime reproduced: `NOT EXECUTED`.
- Sentinel positive control: `NOT EXECUTED`.
- Manual-demo route retirement matrix: `NOT EXECUTED`.
- Process spawn from retired route: `NOT ESTABLISHED`.
- Real order_check calls: `0 observed`; no broker/runtime process was started.
- Real order_send calls: `0 observed`; no broker/runtime process was started.
- Demo orders sent: `0`.
- Live orders sent: `0`.
- Side-effect containment: `NOT EXECUTED`.

## Source-level scope observations

The candidate diff remains bounded to the documented route retirement, package test wiring, status documentation, and the R1 test/sentinel files. It contains no strategy or strategy-authorization changes. Source inspection shows `/api/execution/manual-demo` returns `410 EXECUTION_ROUTE_RETIRED` unconditionally, but this is not runtime proof.

The independent sink inventory, actual HTTP call-chain trace, canonical owner/R5C/idempotency regression checks, and required focused/regression suites were not completed. Their statuses are `NOT EVALUATED`, not PASS.

## Failure attribution

`ENVIRONMENTAL` / `TEST_INFRASTRUCTURE`: deterministic dependency restoration in the fresh candidate worktree did not complete within the bounded audit run, leaving the required Node test runner unavailable. No candidate-caused failure was identified. This blocker prevents a PASS classification.

## Separate workstreams

- `56bbdd7`: remains a separate documentation-only integration decision; not used as runtime evidence.
- Scheduler status: `SCHEDULER_NATURAL_CYCLE_NOT_OBSERVED`.
- No integration or push performed.

## Next action

Resolve the isolated npm dependency-restore issue without changing `f266001`, then rerun R2 from the exact candidate SHA. The next run must execute the baseline sentinel reproduction, positive control, candidate matrix, side-effect comparison, sink inventory, canonical-path tests, and regression gates before any integration recommendation.

---

## R2 recovery and final adjudication — 2026-09-24

### Final classification

`MANUAL_DEMO_ROUTE_CONTAINMENT_INDEPENDENT_AUDIT_PASS`

The initial R2 blocked result above is preserved as historical evidence. Recovery established that npm was not failing on network access: the first `npm ci` had completed with exit 0, but the earlier status probe raced package extraction. A deterministic offline `npm ci --offline --ignore-scripts --no-audit --no-fund` then completed from cache. The registry endpoint also returned HTTP 200. The lockfile and package manifest remained unchanged.

### Frozen target and environment

- BASE_SHA: `595ca08b9cc9c6f7b54b017f9748285ad7d44a87`
- AUDITED_SHA: `f26600186c0a328dab42490952eabd87b580a408`
- ORIGIN_MAIN observed: `87e2da798f827caf95e8c6e58916b394641c98fb`
- Lineage: valid; `f266001` has parent `595ca08`.
- Candidate audit worktree: `D:\audit_manual_demo_r2_20260924`, detached at `f266001`, clean tracked tree.
- Baseline worktree: `D:\audit_manual_demo_r2_baseline_20260924`, detached at `595ca08`; dependency junction points to the restored candidate `web/node_modules`.
- Platform: Windows 10 (`Windows_NT 10.0.19045`).
- Node: `v24.14.0`; npm: `11.9.0`; Python: `3.14.0`.
- Package manager/lock: npm, `web/package-lock.json`, lockfileVersion 3. `tsx` is a declared development dependency, lock-resolved at `4.23.13`; verified local binary `web/node_modules/tsx/dist/cli.cjs`.
- `web/package.json` SHA-256: `11549b2b7c1e7bdb9c1d7b2741a90488d164c8de2ab1cc949bd690849198b0bd`.
- `web/package-lock.json` SHA-256: `7100e0b7558255d217cf716b39d422ce8572a30390a52619b9133fc8f552a484`.
- Dependency restore: PASS; `npm ci --offline --ignore-scripts --no-audit --no-fund`, exit 0.
- Candidate content changed: No. No tracked source or dependency metadata changes were made in either audit worktree.

### Sentinel and baseline runtime proof

The committed spawn sentinel positive control passed in the candidate suite: the sentinel observed the configured Python command for the read-only positions route, proving that a spawn is recorded. The intercepted child is an inert fake process. No MT5 function was loaded or called.

On the separate baseline worktree, a valid real-mode DEMO-shaped request to `POST /api/execution/manual-demo` returned HTTP 502 because the sentinel emitted its deliberate blocked-child error. The sentinel log captured this attempted invocation:

```text
ag-python-spawn-sentinel D:\audit_manual_demo_r2_baseline_20260924\scripts\web_execute_trade.py --symbol EURUSD --side BUY --volume 0.31 --sl 1.083 --strategy-id FRONTEND_MANUAL --confirm
```

This independently reproduces the legacy process-spawn bypass while preventing Python execution. Baseline bypass runtime reproduced: YES. `order_check=0`, `order_send=0`.

### Candidate containment and side effects

The focused committed suite command was:

```text
node .\node_modules\tsx\dist\cli.cjs --test --test-concurrency=1 tests/manual_demo_route_containment_r1.test.ts
```

Result: 9 passed, 0 failed, 0 skipped; 159,977 ms. It verified the sentinel positive control, real/mock modes, owner-key header, FX/crypto, malformed input handling, repeated valid requests, no execution-script spawn, unchanged `state/` hashes and `/api/logs`, plus WP0A retirement.

An additional audit-only matrix against the built candidate sent 19 requests: valid confirmed, false confirmation, empty object/body, null JSON, unexpected fields, wrong content type, malformed JSON, crypto symbol, and ten repeated valid-shaped requests. The 17 parseable requests that reached the route returned HTTP 410 `EXECUTION_ROUTE_RETIRED`. Null and malformed JSON were rejected by body parsing before route dispatch and surfaced as HTTP 500 through the generic error handler; neither reached execution. Candidate request-triggered spawn log was empty (0). The separate positive control was observed independently.

Side-effect containment: PASS. The committed suite compared execution-relevant `state/` files and API log content before and after requests and found no differences. The audit sent no orders.

### HTTP execution-sink inventory

| HTTP surface | Controls / behavior | Classification |
|---|---|---|
| `POST /api/execution/manual-demo` (Node) | Unconditional 410; runtime matrix; 0 request-triggered spawn | RETIRED |
| `POST /api/execution/execute` (Node) | Unconditional 410; candidate suite WP0A check passed | RETIRED |
| `POST /api/execution/manage` and `/claim` (Node) | Retired in server route code; broad WP0A/management tests hit startup timeouts, so not separately runtime-confirmed in this recovery | RETIRED (source classified; runtime regression blocked) |
| `GET /api/execution/positions` (Node) | Python read-only positions bridge; observed only as sentinel positive control, never an order sink | READ_ONLY |
| `POST /api/canonical-proposals/{proposal_id}/owner-decision` (Python API) | `require_owner_auth`; proposal identity comes from URL; creates/replays owner decision only and does not call execution handler | OWNER_AUTHORIZED_CANONICAL_DEMO (decision stage only) |
| `POST /api/tickets/{approval_id}/authorize-demo` (Python API) | `require_owner_auth`, explicit `EXECUTE_DEMO`, canonical approval/proposal checks, Demo authorization and execution handler | OWNER_AUTHORIZED_CANONICAL_DEMO |
| Read-only proposal, ticket, execution detail, broker-status/history, and market-data GET routes | Return stored/read-only information; no order submission path | READ_ONLY |
| Telegram test/trade/position notifications | Notification actions; no order submission call chain | SIMULATION/NOTIFICATION ONLY |

No alternate unauthenticated broker-capable HTTP path was found in the audited web server and Python API route scope. The two canonical owner-controlled write surfaces remain the only identified owner-decision/authorize-demo chain. Alternate HTTP execution bypass found: NO.

### Canonical controls and authorization diff

The production diff is limited to `web/server.ts` route retirement. The remaining changed files are status/readme documentation, package test wiring, and the new containment test/sentinel. Diff checks show no changes to `src/api`, `src/execution`, `src/owner_decision`, `config/trading.yaml`, or strategy files between base and candidate.

Runtime-backed regression evidence:

- Owner authentication / owner decision / R5C / idempotency / durable store / reconciliation: `54 passed` across `test_api_owner_decision_auth.py`, `test_api_owner_decision.py`, `test_owner_decision_proposal_uniqueness_r5c.py`, `test_owner_decision_store_persistence.py`, `test_execution_reconciliation_r1.py`, and `test_execution_reconciliation_no_submit.py`.
- Dedicated authorize-demo auth, owner-decision auth, and R5C rerun: `36 passed` across `test_api_authorize_demo_auth.py`, `test_api_owner_decision_auth.py`, and `test_owner_decision_proposal_uniqueness_r5c.py`.
- Candidate focused route test: 9/9 passed.
- TypeScript `tsc --noEmit`: passed as the first stage of `npm test` (the suite proceeded to Node tests without type errors).
- Frontend/server build: `npm run build` passed; Vite transformed 2,478 modules. Vite emitted its existing large-chunk advisory; esbuild completed successfully.
- Authorization broadened: NO. Live authorization broadened: NO. Strategy changed: NO.

### Broader web regression and attribution

Command: `npm test` in `web/`. Result: 58 tests total, 37 passed, 21 failed, 0 skipped; command duration 340,340 ms. Failures were server-start readiness timeouts in existing `vantage_mt5_crypto_venue`, `wp0a_execution_route_containment`, and `wp0b_management_route_mock_mode` tests. The dedicated candidate suite passed in the same command. Standalone candidate and baseline probes started successfully after longer cold starts; the existing suites use 10–20 second readiness limits. Attribution: ENVIRONMENTAL/TEST_INFRASTRUCTURE startup-limit failures, supported by those explicit timeout traces and successful standalone starts. No candidate-caused failure was demonstrated. These timeout failures remain regression caveats, not passing results.

No repository secret-scan gate was found in the inspected `.github/`, `scripts/`, or `pyproject.toml`; secret gate: NOT CONFIGURED / NOT RUN.

### Orders, scheduler, docs candidate, and integration

- REAL_ORDER_CHECK_CALLS: `0`
- REAL_ORDER_SEND_CALLS: `0`
- DEMO_ORDERS_SENT: `0`
- LIVE_ORDERS_SENT: `0`
- Scheduler: `SCHEDULER_NATURAL_CYCLE_NOT_OBSERVED`; scheduler work was not evaluated or changed.
- `56bbdd7`: ACCURATE as a separate documentation correction for the local-only `0461152` publication claim when compared with its inspected diff and observed `origin/main=87e2da7`; it does not supply technical containment evidence. Keep the integration decision separate.
- R1 gaps: the baseline spawn was independently reproduced, the sentinel was positively exercised, candidate matrix and side-effect checks ran, alternate HTTP routes were inventoried, canonical auth/R5C/idempotency tests passed, and focused runtime evidence is now available. The broader web suite still has host startup timeouts documented above.
- Integration eligibility: YES for `f266001` containment scope based on the PASS evidence and absence of a candidate-caused blocker. Do not integrate as part of this audit. After integration, rerun the publication gate from the exact integrated SHA. `56bbdd7` remains a separate decision.
- Pushed: NO.
