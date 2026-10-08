---
class: status
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---

# Host schedule authority and always-on target — SCHED-R1 (2026-10-08)

Mission: resolve the review findings on PRs #77, #78 and #81 (Workstream A of
`AGP-PR-BACKLOG-CLOSURE-R1`) on a single reconciliation branch, without running
`install_tasks.ps1 -Apply` and without touching a host scheduled task or power setting.

## Safety statement

- `install_tasks.ps1 -Apply` was **not** executed.
- No scheduled task was registered, changed, disabled or removed.
- No power setting was changed; `powercfg` / `SetSuspendState` are never called by the installer
  (enforced by `tests/test_host_go_live_kit.py`).
- No broker order was sent. `BROKER_MUTATIONS = 0`.
- No strategy registration, threshold or authorization changed. `STRATEGY_ADMISSIONS = 0`.

## What changed

### 1. Schedule authority is now unambiguous (PR #77)

`scripts/docs/collect_facts.py` derives the schedule from `scripts/host/install_tasks.ps1` instead of
`config/ag_scheduler_v2.yaml`. The generated `status/facts.json`, the Cog block in
`PROJECT_STATUS.md` and `docs/agents/CONTEXT_PACK.md` now carry **four explicitly separate layers**:

| Layer | Meaning | Source |
|---|---|---|
| `REPO_DECLARED` | what `-Apply` would install | `$Plan` |
| `REGISTERED` | what Task Scheduler actually held on 2026-10-08 | `$Declared[].Registered` |
| `OBSERVED` | runtime execution evidence | `heartbeat.py` output — **NOT_PUBLISHED** |
| `TARGET` | the proposed always-on end state | `$Declared[].Target` |

A repository declaration is not a registration, a registration is not an observed run, and a target is
not a fact. The `OBSERVED` layer stays `NOT_PUBLISHED` rather than being inferred from the
declaration, so observed cadence and weekday/weekend coverage are never stated from this repository
alone.

A `drift` list is computed only for fields the declaration states in machine-comparable form
(state / days / start / every-minute). Anything the declaration does not state comparably is left as
the verbatim `Registered` string instead of being guessed.

### 2. Host checkout roots redacted at capture time (PR #78 review P1)

`$HostRoots` previously committed the owner's private checkout roots
(`D:\wp3-main-integ`, `D:\ddev\AG profit trading`, `D:\ag-telemetry\repo`). Per the AGENTS.md
host-evidence rule, host-specific paths are now `<HOST_SCRATCHPAD>\...` placeholders that preserve
each root's *role* and the task's identity, never the private path. `Get-TaskDiff` reports the
executable and argument fields as `REDACTED (host path not committed)` instead of inventing a path
comparison it cannot make honestly; `State`, `Days`, `Start` and `EveryMin` are still compared.

Task identity (name, path, managed class, status, trigger, cadence, enabled state) is preserved
exactly.

### 3. Scheduler gaps recorded in the rolling status (PR #78 review P1; Crypto-Daily target updated by FIX-84)

`PROJECT_STATUS.md` now records, as observed 2026-10-08 and deliberately **not corrected**:

- `AG-V1-Crypto-Daily`: the 2026-10-08 capture showed registered every 15 min vs the then-declared
  every 5 min. FIX-84 changes the repository plan and target to every 15 min; five-minute cadence is
  deferred until the crypto runner checks its active window before MT5 attach. The registered value
  remains a historical capture, not a claim about current host state.
- `AG-V1-LSMC-Watch`: registered Mon–Fri only vs declared daily.
- `scripts/host/GO_LIVE.md` describes the daily LSMC watch as providing weekend crypto coverage; on
  the host as observed it does not, and the retired `AG-V1-LSMC-Crypto-Weekend` task is still the only
  weekend coverage.

### 4. Heartbeat staleness is power-mode aware (PR #81 review P1)

`scripts/host/heartbeat.py` previously hard-coded the wake/sleep windows
(`AWAKE_DAILY` 12:25→00:45 MMT, `WEEKEND_CRYPTO` Sun/Mon 03:10→05:45). Once the always-on target
retires those tasks, runner silence between 00:45 and 12:25 MMT would have been reported
`INACTIVE_EXPECTED` instead of `STALE`, hiding a dead runner for almost twelve hours.

- New `--host-power-mode {wake_sleep,always_on}`, default `wake_sleep` (the observed host state), so
  behaviour is unchanged until the owner applies the target.
- `always_on` resolves every runner to a full-day window: overnight silence can only be `OK` or
  `STALE`, never `INACTIVE_EXPECTED`.
- An unrecognised mode **fails closed** to the `always_on` rule rather than inventing a sleep span.
- The output records `host_power_mode`, `host_power_mode_source`, the resolved `source_windows` and a
  mode-aware `reader_rule`, so a reader can always see which rule produced a status.
- The module docstring's reader-side rule now states the exemption only for `wake_sleep`.

## Verification

| Command | Result |
|---|---|
| `pytest tests/test_host_heartbeat.py -q` | 21 passed (4 new: overnight `wake_sleep`, overnight `always_on`, unknown-mode fail-closed, `build` records mode + applied windows) |
| `pytest tests/test_host_go_live_kit.py -q` | 73 passed, 1 skipped |
| `pytest tests/test_context_pack.py tests/test_docs_live.py -q` | 24 passed, 1 skipped |
| `pytest -q` (full suite) | 1366 passed, 2 skipped |
| `cog --check PROJECT_STATUS.md` | PASS |
| `python scripts/docs/check_drift.py` | 0 errors (5 pre-existing missing-route advisories) |
| `python scripts/docs/collect_facts.py --check` | FACTS_FRESH |

Environment: Linux (Python 3.11), not the Windows MT5 host. No Task Scheduler, PowerShell or live-host
verification was performed; `verify_tasks.ps1` / `Get-TaskDiff` / `-WhatIf` remain unexecuted.

## Deferred live checks

- `install_tasks.ps1 -WhatIf` on the host (prints the registered-vs-target diff).
- `install_tasks.ps1 -Apply` — **owner decision**, after the cadence and weekday/weekend drift above
  is resolved.
- `verify_tasks.ps1` after any apply.
- `heartbeat.py --host-power-mode always_on` once the wake/sleep tasks are retired.
- Publishing `heartbeat.json` so the `OBSERVED` layer can stop being `NOT_PUBLISHED`.

## Remaining approval decisions

1. Owner: resolve the `AG-V1-LSMC-Watch` weekday-only coverage vs the daily declared target and the
   weekend-coverage claim in `scripts/host/GO_LIVE.md`.
2. Owner: apply the always-on target (retire the wake/sleep tasks, apply the power policy) and only
   then switch the scheduled heartbeat to `--host-power-mode always_on`.
