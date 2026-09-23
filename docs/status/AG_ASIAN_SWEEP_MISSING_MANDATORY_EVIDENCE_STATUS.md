# AG Asian Sweep -- MISSING_MANDATORY_EVIDENCE Investigation + Continuation Gate (2026-09-23)

Dated evidence record per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Campaign:
`AG_V1_0_3_FX_SHADOW_SERIES_002` (`ST_ASIAN_SWEEP_5R_V1` v1.1.1, FX proposal-only shadow
qualification toward 20 VALID days). Track A (validation platform) only -- no strategy,
registry, execution, MT5, R5C or trading-config file was touched. No historical record
was rerun, reconstructed, backfilled or reclassified.

## Classification

**`EVIDENCE_PIPELINE_REMEDIATED_CONTINUE_VALIDATION`**

## Target observation (unchanged)

```text
2026-09-23  INVALID_DAY  MISSING_MANDATORY_EVIDENCE:ASIAN_LONDON:EURUSD;
                         MISSING_MANDATORY_EVIDENCE:ASIAN_LONDON:GBPUSD
CLASSIFICATION_BEFORE = INVALID   CLASSIFICATION_AFTER = INVALID
```

## Stage A -- exact evidence gap

Classifier rule: `src/post_asian_pilot/shadow_day_classifier.py::classify_day` -- any
unit with no in-window archive record (`NO_IN_WINDOW_EVIDENCE`) while another unit has
evidence => `INVALID_DAY` / `MISSING_MANDATORY_EVIDENCE:<cycle>:<symbol>`.

```text
EXPECTED_EVIDENCE = 4 per-unit ticket archive records, in-window evaluation_time_utc:
                    journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/
                    {EURUSD,GBPUSD}/{ASIAN_LONDON,LONDON_NEWYORK}/2026/2026-09-23[.correction-NNN].json
ACTUAL_EVIDENCE   = LONDON_NEWYORK EURUSD (base + 7 corrections), LONDON_NEWYORK GBPUSD (base + 7)
MISSING_EVIDENCE  = ASIAN_LONDON EURUSD and ASIAN_LONDON GBPUSD -- no file of any kind for the date
```

Scope: session-wide (whole ASIAN_LONDON cycle, both symbols), not single-symbol.

## Stage B -- pipeline trace

```text
Task Scheduler AG_FX_ASIAN_LONDON_SHADOW -> scripts/scheduled/run_asian_london_once.bat
  -> scripts/run_fx_cycle_once.py (gates: weekday/window/friction/slot) -> pilot cycle
  -> ticket archive (producer) -> classify_day (consumer)
```

| Stage | 2026-09-23 ASIAN_LONDON | Evidence |
|---|---|---|
| Scheduler launched runner | **NO** | `%TEMP%\ag_shadow_asian_london.log` last written 2026-09-22 17:30 local; zero 09-23 entries (a gate refusal would also have been logged) |
| Slot claimed | NO | `state/fx_schedule/slot_ledger.json`: 0 ASIAN_LONDON keys for 09-23 (LONDON_NEWYORK: 9) |
| Producer ran / succeeded | NO / NO | nothing to produce |
| Evidence generated / persisted | NO / NO | no archive file |
| Report / classifier received | NO / NO | classifier correctly failed closed |

## Root cause (temporal trace)

The ASIAN_LONDON task had ONE weekly Mon-Fri trigger at 13:30:20 MMT (07:00:20 UTC) with
PT15M/PT4H repetition, `StartWhenAvailable=False`, `WakeToRun=False` (installed by
`scripts/install_fx_scheduler.ps1`). All 16 later slots are repetitions of that single
trigger instance. When the host is asleep at the first slot, Windows Task Scheduler
launched none of the day's repetitions, even after the host woke up. Task Scheduler
operational history is disabled on this host, so the mechanism is shown by the three
days below (System event log sleep/resume/boot records), not by task-history events:

```text
2026-09-21  awake at 07:00:20Z -> base fired; host slept 09:03-10:10Z; repetitions
            RESUMED at 10:12Z (repetitions survive a mid-window sleep once the base fired)
2026-09-22  asleep 06:10:51Z -> 07:17:28Z across the base trigger; awake 07:17-09:29Z
            with ZERO launches; unrelated OS reboot 10:08Z re-armed the trigger;
            launches resumed 10:15Z (4 slots) -> archive evidence exists -> VALID_DAY
2026-09-23  asleep 06:29:32Z -> 07:03:37Z across the base trigger; awake 07:04-09:24Z
            and 10:17-11:00Z (~12 slots available) with ZERO launches; no reboot inside
            the window (reboot at 14:43Z, after it) -> no evidence -> INVALID_DAY
```

`LastRunTime 2026-09-23 17:51:21 MMT (11:21Z)`, `LastTaskResult 0x800710E0`
(ERROR_REQUEST_REFUSED) is a Task-Scheduler-level launch refusal after the window closed.
The runner never executed (no log line), so this is not the runner's fail-closed exit 2.
The deployment checkpoint doc called it "a fail-closed refusal code". That doc is left as
historical, and this note records the correction.

```text
ROOT_CAUSE_CLASS      = SCHEDULER_TIMING_FAILURE
ROOT_CAUSE_CONFIDENCE = HIGH (three-day natural comparison; mechanism inferred, task history disabled)
RECURRENCE_RISK       = REPEATABLE_DEFECT (2 of the last 2 trading days; host idles to sleep
                        around 13:00 MMT, just before the 13:30:20 first slot; same exposure
                        on LONDON_NEWYORK at 18:30:20 MMT)
OCCURRED_BEFORE_PROVENANCE_DEPLOYMENT (8f8f5b5, deployed ~14:14-14:30Z) = YES
STRUCTURED_RUNTIME_ERROR_PRESENT = NO (not applicable -- pipeline never launched; none fabricated)
RECOVERED_ERROR_PRESENT = NO   UNRESOLVED_ERROR_PRESENT = NO
```

## Current campaign state (re-derived, `classify_series` 2026-09-05 -> 2026-09-23)

```text
CURRENT_VALID = 8     (09-09, 09-11, 09-14, 09-15, 09-16, 09-17, 09-21, 09-22)
CURRENT_INVALID = 4   (09-08 anomaly; 09-10, 09-18, 09-23 missing mandatory evidence)
CURRENT_PENDING = 1   (09-07 PRE_ARCHIVE_ONLY_ACTIVATION -- unrelated to this root cause)
CURRENT_EXCLUDED = 6  (weekends)
VALID_REMAINING = 12
```

The `fx_adapter` frozen counters add 2026-09-04 (INVALID, series Day 1) on top of these
counts. This record shows 1 PENDING, not the 2 quoted in the mission prompt.

Related prior INVALID days (read-only triage, not reclassified):
- 2026-09-18 (`LONDON_NEWYORK:*` missing): host asleep 11:50Z -> 19:41Z, covering the
  whole 12:00-15:00Z window. This is `OPERATIONAL_INTERRUPTION`; per-slot triggers
  would not have recovered it.
  Note: the uncommitted PROJECT_STATUS section "RUNTIME_ERROR_PROVENANCE_RECONCILIATION"
  lists 09-18 as reclassified VALID_DAY. The classifier returns INVALID_DAY for it
  (missing unit evidence, a separate matter from runtime_errors). The owner must resolve
  this before that section is committed.
- 2026-09-10 (`ASIAN_LONDON:*` missing): no sleep event in window; predates the
  2026-09-20 trigger hardening. Cause `NOT_EVALUATED`.

## Continuation gate

```text
VALIDATION_PIPELINE_HEALTH before fix = BLOCKED_BY_REPEATABLE_DEFECT (evidence suppression,
    fail-closed -- no false VALID possible; prior VALID days remain trustworthy)
FUTURE_VALIDATION_INTEGRITY_AT_RISK = YES (repeatable suppression of whole cycles)
REMEDIATION_SCOPE_IS_INFRASTRUCTURE_ONLY = YES
CAMPAIGN_RESET_REQUIRED = NO
```

## Remediation (prospective, scheduler infrastructure only)

`scripts/install_fx_scheduler.ps1`: replaced the single repetition-anchored trigger with
one independent weekly Mon-Fri trigger per M15-close slot (ASIAN_LONDON 17 from 13:30:20
MMT, LONDON_NEWYORK 13 from 18:30:20 MMT). A slot missed while the host sleeps is now only
that slot. `StartWhenAvailable` stays False, so missed slots are still never caught up. The
runner's gates, window, friction check, slot idempotency, actions and settings are
unchanged. Also: the installer's XML backup now uses a timestamped name instead of
overwriting an existing `.before.again.json` evidence file.

Tests (`tests/test_fx_scheduler_once.py`, 2 added):
- `test_installer_registers_one_independent_trigger_per_slot` -- FAILED on the pre-fix
  installer (defect reproduced statically), PASSES after.
- `test_installer_slot_counts_match_the_canonical_schedule` -- installer slot count and
  first slot equal `scheduling.fx_schedule.m15_close_slots` (17 / 13).

```text
.venv/Scripts/python.exe -m pytest tests/test_fx_scheduler_once.py -q
  => 29 passed, 2 skipped, 1 failed
  failed: test_runner_refuses_friction_window_collision -- PRE-EXISTING, fails identically
  with this change stashed (stale 2026-09-21 date literal); not candidate-attributable.
```

Deployment (both windows closed, 16:57Z; no cycle process running; nothing to drain):
- The installer was run and both prior task XMLs were backed up to
  `logs/scheduler/*.before.20260923T2334*.json`.
- Live verification: AG_FX_ASIAN_LONDON_SHADOW has 17 triggers (13:30:20-17:30:20 MMT,
  Mon-Fri, no repetition). AG_FX_LONDON_NEWYORK_SHADOW has 13 triggers
  (18:30:20-21:30:20 MMT).
- Both tasks remain enabled, and each keeps its original action. Next run: 2026-09-24
  07:00:20Z and 12:00:20Z.
- SHA-256 of `slot_ledger.json` and `proposal_ledger.json` was identical before and after.
- Natural-cycle verification: AWAITING the 2026-09-24 ASIAN_LONDON window.

Residual limitation (owner option, not implemented): slots during which the host is
asleep are still missed (`WakeToRun=False`). If the host sleeps through an entire window,
the day fails closed as INVALID. Enabling wake timers or changing the power plan would
change host hardware behavior, so that is the owner's decision.

## Protected scope and side effects

```text
STRATEGY_CHANGED = NO  STRATEGY_VERSION_CHANGED = NO  REGISTRY_CHANGED = NO  R5C_CHANGED = NO
EXECUTION_CHANGED = NO  MT5_CHANGED = NO  TRADING_CONFIG_CHANGED = NO  DATA_ERROR_CONTRACT_CHANGED = NO
HISTORICAL_CLASSIFICATION_MUTATED = NO  CAMPAIGN_RESET_PERFORMED = NO
REAL_ORDER_CHECK_CALLS = 0  REAL_ORDER_SEND_CALLS = 0  DEMO_ORDERS_SENT = 0  LIVE_ORDERS_SENT = 0
ROOT_CAUSE_COMMIT = n/a (scheduler trigger shape from AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1)
REMEDIATION_COMMIT = see git log for this document
```

Next action: `CONTINUE_FORWARD_SHADOW_ACCUMULATION_TO_20_VALID`. On 2026-09-24, confirm
that ASIAN_LONDON slots are claimed after any sleep that spans 07:00:20Z.
