# AG Missing Platform Packages Integration (2026-09-24)

Dated evidence record per `docs/status/LIVE_STATUS_MAINTENANCE.md`. It covers
integrating two independently audited platform packages into the authoritative platform
branch (`feat/demo-execution-bridge`) before `main` is published. **Nothing here is
operational authorization.** No strategy, registry, Demo or Live authorization changed,
and no broker order call was made.

## Starting state

```text
START_BRANCH       = feat/demo-execution-bridge
START_HEAD         = 3208e78
REMOTE_START_HEAD  = origin/main 570e755 (local 20 ahead / 0 behind, not diverged)
CONCURRENT_SOURCE_WRITER = NO (3 peer Claude sessions idle; HEAD and dirty set stable)
```

Before integration, a preservation checkpoint `8f6f408` committed the already-classified
durable files:
- the `PROJECT_STATUS.md` sections;
- `AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_BACKLOG_RECONCILIATION_STATUS.md`;
- `AG_ASIAN_SWEEP_RUNTIME_ERROR_PROVENANCE_RECONCILIATION_STATUS.md`;
- the four completed 2026-09-23 WP3A.1 friction windows, 8 files at 120/120 samples each.

`main` already versions completed friction days at 8 files per day, so these follow
precedent. `state/fx_schedule/slot_ledger.json` and
`state/proposal_ledger/proposal_ledger.json` are live runtime state. They were not staged,
reset, stashed or deleted.

## Integration

| Package | Source (audited) | Integrated as | Method |
|---|---|---|---|
| Frontend owner-decision rewire | `061d3e0` | `f08aa35` | `git cherry-pick -x` |
| R5C proposal-level owner-decision uniqueness | `cffe626` (parent `061d3e0`) | `00c6819` | `git cherry-pick -x` |
| Frontend rewire R1 re-audit record (doc only) | `8b871b7` | `19747cf` | `git cherry-pick -x` |
| R5C independent audit record (doc only) | `230a6fd` | `9f9ae7d` | `git cherry-pick -x` |

No audit branch was merged wholesale. The audit commits each add exactly one
`docs/status/` file.

**Conflicts:** `PROJECT_STATUS.md` only, in both implementation picks. Both were purely
additive, with new top sections on each side. Resolution kept every section verbatim:
current-lineage sections first, then R5C, then the frontend rewire. `docs/README.md` and
all code files applied cleanly.

## Current-tip semantic review

The audits of both packages were performed against baseline `e7e9583`. Between
`e7e9583` and `3208e78`, the only non-doc changes are:

```text
scripts/install_fx_scheduler.ps1
src/post_asian_pilot/{pipeline,report,runtime_error_log,store}.py
tests/test_fx_scheduler_once.py, tests/test_runtime_error_log.py
```

`git diff e7e9583 3208e78 -- src/owner_decision src/api src/execution src/assistant
src/proposal_envelope web config strategies` is **empty**. The integrated tree differs
from the audited R5C tip `230a6fd` only in those 7 files. So every code surface the
audits examined is byte-identical at the integrated tip.

**R5C consumer trace (`src/`):**
- `POST /api/canonical-proposals/{proposal_id}/owner-decision` is guarded by
  `dependencies=[Depends(require_owner_auth)]`. `require_owner_auth` checks the
  `X-AG-Owner-Key` header against `AG_OWNER_API_KEY`: it returns 503 when the key is
  unset and 401 when the header is missing or wrong.
- The route calls `owner_decision.bridge.evaluate_owner_decision()`, which calls
  `OwnerDecisionStore.commit_terminal_decision()`. That is the only terminal-authority
  write.
- There is a single store instance (`src/api/app.py` `_default_owner_decision_store`).
  No other `src/` module calls `evaluate_owner_decision` or `commit_terminal_decision`.
- `src/execution/durable_idempotency.py` references the bridge only in a comment.
- Validation and gating rejections stay outside proposal authority, as covered by R5C
  tests.

**Frontend contract trace:**
- `agApiClient.ts` uses `/api/canonical-proposals`, `/api/canonical-proposals/{id}`,
  `/api/opportunity-analysis` and `POST /api/canonical-proposals/{id}/owner-decision`.
  All exist in the current `src/api/app.py`.
- The panel's only write call is `submitOwnerDecision`.
- The decision ID is `OWNER_DECISION:<proposal_id>`.
- `AUTH_NOT_CONFIGURED`, `SERVER_UNAVAILABLE`, `CLIENT_OUTCOME_UNKNOWN` and
  `SUBMISSION_UNKNOWN` stay distinct in `ownerDecisionLogic.ts`, and the panel logic
  tests cover this.
- The owner key never touches `localStorage`, `sessionStorage` or IndexedDB.
- There is no browser-to-MT5 or browser-to-order path in the Owner Analysis panel or API
  client.

## Tests (integrated tip `9f9ae7d` + this record; local, 2026-09-23/24, Windows, `.venv`)

```text
OWNER_DECISION_R5C   61 passed   test_owner_decision_bridge, _proposal_uniqueness_r5c,
                                 _store_persistence, test_api_owner_decision, _auth
EXECUTION            95 passed   test_execution_durable_idempotency(+_lifecycle),
                                 test_execution_reconciliation(+_no_submit, _r1),
                                 test_api_authorize_demo_auth, test_api
PROPOSAL_PIPELINE   110 passed   opportunity_proposal_bridge, assistant_canonical_proposal_adapter,
                                 proposal_dedup_r1, api_opportunity_analysis, post_asian status/
                                 observe-only remediation, ticket_delivery_wiring,
                                 runtime_error_log, daily_fx_report
SCHEDULER            29 passed, 1 failed, 2 skipped   test_fx_scheduler_once (see below)
FRONTEND typecheck   PASS (tsc --noEmit)
FRONTEND tests       48/49 (see below)
FRONTEND build       PASS (vite build + esbuild server.ts)
```

Command form: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <files>`,
`npm test`, `npm run build` (in `web/`). R5C race, restart and corruption coverage is the
package's own suite: 3 race shapes x 25 iterations, simulated restart, and a
conflicting-ledger fail-closed check. It was run here unchanged against the integrated
tip.

### Scheduler failure attribution: `LIVE_STATE_DEPENDENCE` (proven)

`test_runner_refuses_friction_window_collision` spawns `scripts/run_fx_cycle_once.py`,
which reads the **live** WP3A.1 campaign directory. `load_friction_campaign()` sets
`active = complete_days < minimum_trading_days`. With the 2026-09-23 sessions the
campaign has 5/5 complete days (`CAMPAIGN_MINIMUM_DAYS_MET`), so
`friction_window_conflict()` correctly returns `None`. That is the documented behaviour
("nothing to protect once the manifest's own minimum day count is met").

Controlled proof, loading the same summaries from a scratch copy:

```text
WITHOUT_2026-09-23  active=True  complete=4/5 CAMPAIGN_COLLECTING      conflict=WINDOW_D_LONDON_NEWYORK
CURRENT_REPO        active=False complete=5/5 CAMPAIGN_MINIMUM_DAYS_MET conflict=None
```

Neither the runner nor `src/scheduling/` changes in the outgoing lineage, and the
production behaviour is correct. The test needs a controlled campaign fixture instead of
live evidence. That is a separate follow-up, like `bcee106`. The test was not changed
here.

### Frontend failure attribution

- **Cold-start timeouts (ENVIRONMENTAL):** a full `npm test` run first failed 21 tests
  across the three server-spawning suites with `server did not become ready in time`.
  Spawned exactly as those suites do, `server.ts` became ready after about 14.6s, close to
  the 20s `waitForServer` budget, and Vite was re-optimizing dependencies. Run
  individually, the suites give wp0b 2/2, vantage 10/10 and wp0a 8/9. The
  non-server suites passed 28/28 in the full run, owner-decision panel logic included.
  The prior frontend audit recorded the same cold-start behaviour.
- **Containment failure (PRE_EXISTING_REMOTE_BASELINE, safety-relevant):**
  `wp0a` "server.ts source contains no real-mode spawn of a broker-mutating script". The
  cause is `web/server.ts` `POST /api/execution/manual-demo`, which spawns
  `scripts/web_execute_trade.py --confirm` (`74d65ea`, 2026-09-22). Both `web/server.ts`
  and the test are **identical on `origin/main`**, so this publication neither
  introduces nor changes it. The route is gated by:
  - `user_confirmed === true`;
  - a DEMO account;
  - `VITE_AG_API_MODE=real` (it returns 409 in the default mock mode);
  - the Python side's `config/trading.yaml` (`mode: ANALYSIS`,
    `allow_order_check: false`, `allow_order_send: false`).

  It has **no owner-key authentication and bypasses the R5C owner-decision boundary**.
  It stays a separate remediation item.

## Secret gate

Scanned all 25 outgoing commits (`origin/main..9f9ae7d`, about 12,000 added lines) plus
this record:
- no private-key, AWS, GitHub, Anthropic/OpenAI, Slack, Telegram-bot or JWT token
  patterns;
- no sensitive filenames added;
- 18 name-equals-literal matches, all status or reason-code constants, the env-var and
  header *names* (`AG_OWNER_API_KEY`, `X-AG-Owner-Key`), or dummy test header values.

`SECRET_GATE = PASS`, `SECRET_FINDINGS = 0`.

## Safety state (repository truth, unchanged by this work)

```text
config/trading.yaml   mode: ANALYSIS; execution.allow_order_check/allow_order_send: false;
                      account.allow_live_trading: false; execution mode DRY_RUN
strategies/registry.yaml  no live_authorized: true anywhere; one pre-existing
                      demo_authorized: true (ASIAN_LONDON cycle only, per its contract) --
                      already on origin/main, not modified, not a Live authorization
AUTOMATIC_EXECUTION = DISABLED     LIVE_EXECUTION = DISABLED
OWNER_AUTH_REQUIRED = YES (owner-decision + legacy authorize-demo routes)
EXECUTION_FAIL_CLOSED = YES (config gates) -- see manual-demo gap above
REAL_ORDER_CHECK_CALLS = 0  REAL_ORDER_SEND_CALLS = 0  DEMO_ORDERS_SENT = 0  LIVE_ORDERS_SENT = 0
```

## FX shadow campaign snapshot (documentation reconciliation)

`PROJECT_STATUS.md` holds three dated 2026-09-23 snapshots with differing counts. They
were kept as historical evidence. The latest one (`AG_ASIAN_SWEEP_MISSING_MANDATORY_EVIDENCE`)
is authoritative. Canonical `classify_series` was re-run read-only for 2026-09-05..09-23:
`valid 8, invalid 4, excluded 6, unresolved 1`, identical to that snapshot. The
earlier provenance-reconciliation section's claim that 2026-09-18 is `VALID_DAY`
conflicts with the classifier (`INVALID_DAY`) and remains an open owner item. It was
annotated, not rewritten.
