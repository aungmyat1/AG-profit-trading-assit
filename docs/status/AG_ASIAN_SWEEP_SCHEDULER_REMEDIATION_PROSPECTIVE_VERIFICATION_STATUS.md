# AG Asian Sweep -- Scheduler Remediation Prospective Verification + Evidence Reconciliation (2026-09-24)

Dated evidence record per `docs/status/LIVE_STATUS_MAINTENANCE.md`. It verifies scheduler
remediation `3208e78` (one independent weekday trigger per slot) against the first natural
ASIAN_LONDON cycle after deployment. It also reconciles the contradictory 2026-09-18
documentation. Track A (validation platform) only: no strategy, registry, owner-decision,
R5C, execution, MT5 or trading-config change, and no order of any kind.

## Classification

**`SCHEDULER_REMEDIATION_WAITING_FOR_NATURAL_CYCLE`** (updated below once the cycle is observed)

## P0/P1 -- repository and live task configuration (read at 2026-09-23T17:33Z)

```text
3208e78_PRESENT = YES (ancestor of feat/demo-execution-bridge HEAD 9f9ae7d)
SCHEDULER_REMEDIATION_INSTALLED = YES -- no reinstall performed
AG_FX_ASIAN_LONDON_SHADOW    Ready, enabled, 17 triggers, all enabled, no repetition,
                             first 13:30:20 MMT = 07:00:20Z, last 17:30:20 MMT = 11:00:20Z, Mon-Fri
AG_FX_LONDON_NEWYORK_SHADOW  Ready, enabled, 13 triggers, all enabled, no repetition,
                             first 18:30:20 MMT = 12:00:20Z, last 21:30:20 MMT = 15:00:20Z, Mon-Fri
actions unchanged: scripts\scheduled\run_asian_london_once.bat / run_london_newyork_once.bat
```

## P2 -- pre-cycle snapshot (2026-09-23T17:4xZ, read-only)

```text
state/fx_schedule/slot_ledger.json         sha256 7f2acf917c359d7db9d08fd1daf1e94bd1d4e482e040912b338939a3d49ee6de, 0 keys for 2026-09-24
state/proposal_ledger/proposal_ledger.json sha256 34e6b1672d4c8d3ede0dcbc76921e423027562e66073c2fe2931a92d23081fb8
archive .../{EURUSD,GBPUSD}/ASIAN_LONDON/2026/2026-09-24*  absent
%TEMP%\ag_shadow_asian_london.log          1919229 bytes, last write 2026-09-22 17:30 MMT
journal/post_asian_pilot/runtime_error_log.json  absent (created on first event; none since provenance deployment)
```

## P3-P6 -- natural prospective observation

PENDING -- first natural trigger due 2026-09-24T07:00:20Z. No manual execution, forced
invocation, slot clearing or fault injection.

## P7 -- missed-slot semantics

The claim `3208e78` preserves is that an individual missed slot does not suppress later
independent triggers. It is not tested by deliberately sleeping the host. Known limitation,
not closed by `3208e78`: if the host sleeps across the entire window, no evidence is
produced and the day may fail closed as INVALID. `WAKE_MACHINE_ENABLED = NO`.

## P8/P9 -- 2026-09-18 reconciliation (canonical classifier + archive)

| Unit | Expected | In-window evidence present | Classifier | Reason |
|---|---|---|---|---|
| ASIAN_LONDON / EURUSD | yes | YES (last 10:45:10Z) | PASS | TERMINAL_STATE:WATCH |
| ASIAN_LONDON / GBPUSD | yes | YES (last 10:45:10Z) | PASS | TERMINAL_STATE:WATCH |
| LONDON_NEWYORK / EURUSD | yes | **NO** (records at <=11:45:05Z, then 19:47:05Z post-wake BLOCKED) | NO_EVIDENCE | NO_IN_WINDOW_EVIDENCE |
| LONDON_NEWYORK / GBPUSD | yes | **NO** | NO_EVIDENCE | NO_IN_WINDOW_EVIDENCE |

**2026-09-18 = INVALID_DAY** (`MISSING_MANDATORY_EVIDENCE:LONDON_NEWYORK:*`). The host was
asleep from 11:50Z to 19:41Z, covering the whole 12:00-15:00Z window, which is an
operational interruption. The earlier runtime-error provenance reconciliation promoted 09-18
to VALID_DAY because its `runtime_errors` count was a recovered retry. That mixed two
independent questions. **A recovered runtime error does not imply VALID_DAY when mandatory
in-window session evidence is absent.**

Documentation corrected with explicit addenda (original text preserved as history):
- `docs/status/AG_ASIAN_SWEEP_RUNTIME_ERROR_PROVENANCE_RECONCILIATION_STATUS.md`
- `docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_BACKLOG_RECONCILIATION_STATUS.md`
- `PROJECT_STATUS.md`: a correction note on the provenance-reconciliation section. Its
  "8/20" total is numerically right, but its date list is wrong: the classifier counts
  09-17 as VALID and 09-18 as INVALID.

No archive, slot ledger, decision record, classifier rule or campaign history was changed.

## P10/P13 -- other dates (state only)

```text
2026-09-07  PENDING_RECONCILIATION  NO_PERSISTED_EVIDENCE_FOR_DATE:PRE_ARCHIVE_ONLY_ACTIVATION  (preserved)
2026-09-10  INVALID_DAY  MISSING_MANDATORY_EVIDENCE:ASIAN_LONDON:{EURUSD,GBPUSD}; ROOT_CAUSE = NOT_INVESTIGATED
2026-09-23  INVALID_DAY  MISSING_MANDATORY_EVIDENCE:ASIAN_LONDON:{EURUSD,GBPUSD}  (unchanged)
```

## P11/P12 -- count authority (as of 2026-09-23)

```text
CANONICAL_CLASSIFIER  classify_series 2026-09-05..2026-09-23:  VALID=8  INVALID=4  PENDING=1  EXCLUDED=6
FX_ADAPTER_FROZEN_COUNTERS  (_SHADOW_* literals, fx_adapter.py):  VALID=0  INVALID=1  PENDING=0  EXCLUDED=0
FX_ADAPTER_TOTAL  (frozen + classifier, as SHADOW_SERIES_COMPLETION reports):  VALID=8  INVALID=5  PENDING=1  EXCLUDED=6
```

The difference is a **series-boundary / classifier-scope difference, not an
inconsistency**. The frozen counters hold one hand-authored, signed record: 2026-09-04,
series 002 Day 1, INVALID_DAY. The classifier deliberately starts at 2026-09-05
(`_CLASSIFIER_SERIES_START_DATE`), so 09-04 is counted exactly once. If the classifier
were applied to 09-04, it would return PENDING_RECONCILIATION (pre-archive-activation),
because it cannot see the evidence the signed Day-1 record was based on. The frozen record
remains the authority for that date. Series 001 Day 1 (2026-09-02, EXCLUDED) belongs to a
separate predecessor series and is in neither counter. Neither counter was changed.

## P14 -- scheduler regression tests

```text
.venv/Scripts/python.exe -m pytest tests/test_fx_scheduler_once.py -q -rfs
  => 29 passed, 2 skipped, 1 failed
  FAILED test_runner_refuses_friction_window_collision
```

Attribution (refined): the runner's own dry run at the test's `--now
2026-09-21T12:30:20Z` reports the WP3A.1 friction campaign `active=false, complete_days=5,
minimum_days=5, reason=CAMPAIGN_MINIMUM_DAYS_MET`. So the runner correctly passes instead
of refusing. The two sibling Window-D tests skip in this state ("campaign no longer
collecting"), but this test lacks that guard. It is a test-only staleness issue and is not
attributable to `3208e78`. Proposed separate test-only package: add the same
`campaign no longer collecting` skip guard. It is not included here.

## Protected scope and side effects

```text
STRATEGY_CHANGED = NO  STRATEGY_VERSION_CHANGED = NO  REGISTRY_CHANGED = NO  OWNER_DECISION_CHANGED = NO
R5C_CHANGED = NO  EXECUTION_CHANGED = NO  MT5_CHANGED = NO  TRADING_CONFIG_CHANGED = NO
CAMPAIGN_RESET = NO  HISTORICAL_EVIDENCE_MUTATED = NO
REAL_ORDER_CHECK_CALLS = 0  REAL_ORDER_SEND_CALLS = 0  DEMO_ORDERS_SENT = 0  LIVE_ORDERS_SENT = 0
```
