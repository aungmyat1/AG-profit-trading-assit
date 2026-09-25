# AG FX Runtime-Error Provenance Deployment Checkpoint (2026-09-23)

Deployment of the independently audited structured runtime-error provenance
implementation into the live worktree/branch used by the active FX forward-shadow
qualification scheduler. Deployment + integration only -- no strategy logic,
configuration, threshold, execution authority, or historical decision was changed.

## Source and audit

```text
SOURCE_AUDITED_SHA = ff06877f3cc1d551e15b1b56b9a94e42804ae9df
  (fix(fx-reporting): persist runtime error provenance; branch
  feat/fx-runtime-error-structured-provenance, worktree D:/AG-fx-runtime-error-provenance)
AUDIT_EVIDENCE_SHA  = 84b78ce668b606707a7d226384cd9da40ee70e9a
  (docs-only, 1 file changed: AG_FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_INDEPENDENT_AUDIT_STATUS.md;
  branch audit/fx-runtime-error-structured-provenance-independent, worktree
  D:/AG-audit-ff06877-independent-recovery -- never merged/cherry-picked as production code)
AUDIT_RESULT        = FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_INDEPENDENT_AUDIT_PASS
```

## Active runtime identified (P0)

```text
ACTIVE_WORKTREE  = D:/ddev/AG profit trading
ACTIVE_BRANCH    = feat/demo-execution-bridge
ACTIVE_HEAD_BEFORE = e7e9583749bebade5b89c4c53c9af97739d5f20f
Scheduled tasks (Windows Task Scheduler, confirmed via schtasks /query):
  \AG_FX_ASIAN_LONDON_SHADOW    -> scripts\scheduled\run_asian_london_once.bat
  \AG_FX_LONDON_NEWYORK_SHADOW  -> scripts\scheduled\run_london_newyork_once.bat
  both invoke "D:\ddev\AG profit trading\.venv\Scripts\python.exe" scripts\run_fx_cycle_once.py
  from this exact worktree -- confirms this is the correct integration target.
```

## Scheduler drain (P1)

A LONDON_NEWYORK cycle (PID 9640 -> 5628 -> run_post_asian_pilot.py subprocesses
17904/14528, started 14:19:57 local) was actively running at the moment deployment
began. Both scheduled tasks were disabled immediately (`schtasks /change ... /disable`)
to prevent a new tick, and the in-flight cycle was allowed to finish naturally --
untouched -- before any worktree mutation. Drain confirmed complete
(`DRAINED: no matching python process remains at 2026-09-23T20:44:44+06:30`,
i.e. 2026-09-23T14:14:44Z) before P2 began.

## Pre-deployment state (P2/P3)

`git status --short` at quiesce showed only pre-existing state, classified as follows
(matches the mission's own pre-briefed context; none required a STOP):

- `M PROJECT_STATUS.md` -- PRE_EXISTING_AGENT_OR_OWNER_WORK
- `M state/fx_schedule/slot_ledger.json`, `M state/proposal_ledger/proposal_ledger.json`
  -- RUNTIME_GENERATED_STATE (the live scheduler's own writes)
- 8 untracked `artifacts/validation/ST_LARGE_SMC_V1/.../friction_campaign_wp3a1/sessions/*`
  files -- RUNTIME_GENERATED_STATE (separate, pre-existing Large-SMC WP3A.1 friction
  campaign, running independently via its own scheduled tasks)
- 2 untracked `docs/status/AG_*RECONCILIATION_STATUS.md` -- PRE_EXISTING_AGENT_OR_OWNER_WORK

An out-of-tree recovery snapshot was created before any mutation:

```text
RUNTIME_SNAPSHOT_PATH = D:/AG-deployment-snapshots/20260923T141933Z
MANIFEST              = D:/AG-deployment-snapshots/MANIFEST_20260923T141933Z.txt (84 files, SHA-256 + size each)
Contents: state/fx_schedule/slot_ledger.json, state/proposal_ledger/proposal_ledger.json,
  journal/post_asian_pilot/, journal/post_london_newyork_pilot/, journal/reports/fx/,
  PROJECT_STATUS.md, both untracked status docs, all 8 friction-campaign session files.
```

Campaign state was derived read-only via `src.post_asian_pilot.shadow_day_classifier
.classify_series` (not from the stale 2026-09-23-morning status doc, since the mission
required rediscovery from current runtime evidence):

```text
CAMPAIGN_ID_BEFORE     = AG_V1_0_3_FX_SHADOW_SERIES_002 (ST_ASIAN_SWEEP_5R_V1 v1.1.1)
VALID_BEFORE_DEPLOYMENT    = 8
INVALID_BEFORE_DEPLOYMENT  = 4
PENDING_BEFORE_DEPLOYMENT  = 2   (excluded_days = 6, non-counting)
```

## Preflight and integration (P4-P9)

`git cat-file -t` confirmed both SHAs are commits in this repo's shared object store.
`git show --stat 84b78ce` confirmed audit-evidence-only scope (1 doc file). `git show
--stat ff06877` confirmed expected candidate scope: `src/post_asian_pilot/{pipeline.py,
report.py,store.py,runtime_error_log.py}`, `tests/test_runtime_error_log.py`, and a new
remediation status doc -- 650 insertions, 0 deletions, no file outside that scope.

`git merge-base HEAD ff06877` == `HEAD` == `e7e9583`, and
`git merge-base --is-ancestor HEAD ff06877` succeeded: ff06877's sole parent is the
active HEAD. This is the simplest possible integration case (a direct child commit) --
`git diff --check` reported no whitespace conflicts and no stash was required (none of
the candidate's paths overlapped the pre-existing dirty/untracked files).

```
git cherry-pick ff06877f3cc1d551e15b1b56b9a94e42804ae9df
[feat/demo-execution-bridge 8f8f5b5] fix(fx-reporting): persist runtime error provenance
 6 files changed, 650 insertions(+)
```

```text
INTEGRATION_METHOD = CHERRY_PICK (clean, zero conflicts)
DEPLOYED_SHA        = 8f8f5b59069d15ac980594456078d0f9f027cf1d
ACTIVE_HEAD_AFTER    = 8f8f5b59069d15ac980594456078d0f9f027cf1d
```

Byte-identical content proof (`git diff <sha>:<path> HEAD:<path>`, empty diff = identical):

```text
src/post_asian_pilot/pipeline.py           IDENTICAL
src/post_asian_pilot/report.py             IDENTICAL
src/post_asian_pilot/store.py              IDENTICAL
src/post_asian_pilot/runtime_error_log.py  IDENTICAL
AUDITED_CONTENT_IDENTITY = PASS
```

No stash was used (P6/P8 not applicable); `RUNTIME_STATE_LOST = NO`,
`RUNTIME_STATE_RESET = NO`.

## Protected-scope assertion (P10)

```text
git diff ff06877^..HEAD -- strategies/ execution/ mt5/ src/owner_decision/ config/trading.yaml
  => 0 lines (no change)
strategies/registry.yaml: ST_ASIAN_SWEEP_5R_V1.demo_authorized = false (unchanged)
STRATEGY_CHANGED = NO   REGISTRY_CHANGED = NO   R5C_CHANGED = NO
EXECUTION_CHANGED = NO   MT5_CHANGED = NO   TRADING_CONFIG_CHANGED = NO
```

## Runtime integrity re-verification (P11)

Re-running `classify_series` immediately after cherry-pick (scheduler still stopped)
returned identical counts (VALID=8, INVALID=4, PENDING=2). SHA-256 of
`state/fx_schedule/slot_ledger.json` and `state/proposal_ledger/proposal_ledger.json`
matched the P3 snapshot exactly (byte-for-byte unchanged). `HISTORICAL_BACKFILL_CREATED
= NO`.

## Import smoke and targeted tests (P12/P13)

```text
PYTHONPATH=src .venv/Scripts/python.exe -c "from post_asian_pilot import pipeline, store, report, runtime_error_log"
  => IMPORT_SMOKE = PASS

.venv/Scripts/python.exe -m pytest tests/test_runtime_error_log.py -q
  => 12 passed

.venv/Scripts/python.exe -m pytest tests/test_daily_fx_report.py tests/test_post_asian_pilot.py -q
  => 86 passed

POST_DEPLOYMENT_TESTS = PASS (98/98; all fixtures use tmp_path / isolated state, not
  live journal/state paths -- confirmed by inspection before running)
```

## Scheduler restart (P14/P15)

Both tasks re-enabled (`schtasks /change ... /enable`); `Scheduled Task State: Enabled`
confirmed on both, pointing at the unmodified `.bat` -> `run_fx_cycle_once.py` command,
same worktree, same campaign/state paths, same strategy version -- no new task created,
no parameters changed.

Immediate post-restart load checks (read-only): proposal ledger loads (107 top-level
keys), slot ledger loads, `RuntimeErrorLog.default()` initializes against
`journal/post_asian_pilot/runtime_error_log.json` without creating the file merely by
instantiation/read (`events_for_date` returned `[]`, file still absent before and after).
`FALSE_RUNTIME_ERROR_CREATED = NO`.

## Prospective natural cycle (P16-P19)

The LONDON_NEWYORK task's next tick (14:30 UTC) was imminent at restart time (within
the 12:00-15:00 UTC window) and was observed rather than declared AWAITING:

```text
CYCLE_STARTED = 14:30:44Z   CYCLE_ENDED = 14:31:08Z  (run_fx_cycle_once.py --cycle LONDON_NEWYORK)
PROSPECTIVE_CYCLE_OBSERVED = YES
```

Cycle completed normally: both EURUSD and GBPUSD reached ordinary `READY` decisions via
`LOWER_SWEEP_STRICT_PENETRATION` (unchanged strategy behavior, not the error path);
`result: PASS`; `execution.automatic_execution: DISABLED`, `execution_authorized: false`
on every produced ticket. `record_recovery()` is a documented no-op absent a preceding
unresolved failure (verified by reading `runtime_error_log.py:100-121`), so an ordinary
successful cycle correctly created zero structured events --
`runtime_error_log.json` still does not exist on disk.

Re-running `scripts/run_fx_daily_report.py --date 2026-09-23 --json` (read-only, its own
docstring: "read-only orchestration; PROPOSAL_ONLY, no execution") confirmed the new
schema fields are present and correctly all-zero for a clean day:

```json
"operations": {
  "mt5_disconnect_events": 0, "recovered_errors": 0, "restart_recovery_events": 0,
  "runtime_error_events": [], "runtime_errors": 0, "unresolved_errors": 0
}
```

```text
STRUCTURED_PROVENANCE_ACTIVE = YES
REPORT_FIELDS_AVAILABLE = YES (runtime_error_events, recovered_errors, unresolved_errors)
```

## Post-restart campaign state (P18)

Re-running `classify_series` after the natural cycle: VALID=8, INVALID=4, PENDING=2
(unchanged -- 2026-09-23 was already `INVALID_DAY` before this cycle, for a pre-existing,
unrelated reason: `MISSING_MANDATORY_EVIDENCE:ASIAN_LONDON:*` -- the ASIAN_LONDON task's
last run today returned a fail-closed refusal code before this deployment began and was
not re-run or manipulated). No count was manually changed.

## Side-effect firewall (P20)

```text
REAL_ORDER_CHECK_CALLS = 0   REAL_ORDER_SEND_CALLS = 0
DEMO_ORDERS_SENT = 0         LIVE_ORDERS_SENT = 0
```
Confirmed via the cycle's own JSON log (`order_check_calls: 0`, `order_send_calls: 0`
on both cycle safety blocks) and the daily report's `safety` block for both cycles.

## Classification

**`FX_RUNTIME_ERROR_PROVENANCE_DEPLOYMENT_PASS`**

Deployment complete, byte-identical to the audited candidate, zero protected-scope
changes, zero broker-side-effects, campaign state preserved and continuing normally,
and one full prospective natural cycle observed end-to-end with the new structured
provenance path present but correctly silent on a clean run.
