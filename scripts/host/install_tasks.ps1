<#
Step 4 of scripts/host/GO_LIVE.md -- Windows Task Scheduler tasks for AG V1 (informational only).

  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1          # -WhatIf (default): prints the plan, changes nothing
  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1 -Apply   # installs / replaces the three tasks

Tasks. All run the repo venv windowless: .venv\Scripts\pythonw.exe scripts\host\live_candles_smoke.py --mode <m>
(the objective preflight still runs .venv\Scripts\python.exe so its output is visible)
  AG-V1-FX-Cycles     adds --canonical to the scheduled FX mode. It retains run_manual_jobs,
                      then uses the canonical daily evaluator and TICKET_STORE_V1; the legacy
                      run_fx path remains available for unscheduled/manual invocations only.
                      It acts only inside the frozen ST_ASIAN_SWEEP_5R_V1
                      trade sessions in UTC, plus 30 min grace:
                        ASIAN_LONDON   07:00-11:00 GMT (08:00-12:00 Europe/London in BST)
                        LONDON_NEWYORK 12:00-15:00 GMT (13:00-16:00 Europe/London in BST)
                      Gating in UTC inside Python makes the schedule DST-safe and independent of the
                      host's time zone.
  AG-V1-Crypto-Daily  every 5 min, daily. The runner acts only inside the active crypto ticket config
                      windows (V3: weekdays 09:00-12:00 America/New_York + Sat/Sun 21:00-23:00 UTC;
                      V2: weekdays only; V1: 06:30-06:45 UTC).
  AG-V1-LSMC-Watch    every 5 min, daily. ST_LARGE_SMC_V1@1.1.0 watches the complete six-
                      instrument universe. FX evaluates to MARKET_CLOSED during its weekend;
                      BTCUSDT/ETHUSDT remain watched. Alerts are ARCHIVE_ONLY by default.

Before any task is changed, verify_objective.py must pass the complete symbol/cycle/config
contract. After registration, verify_tasks.ps1 checks all three exact actions and task bindings.

Every task:
- runs single-instance (MultipleInstances IgnoreNew, plus a Python lock file in logs\);
- starts at a staggered offset after each M5 close (fx +1:00, crypto +2:30, lsmc +4:15; see START
  STAGGER RULE below) so runs rarely overlap, and all MT5 access is serialized on one host-wide cross-process lock
  (%ProgramData%\AG\locks\mt5_access.lock, shared by every checkout);
- has a 4-minute time limit (the runner itself self-exits after 120 s with TIMEOUT);
- runs at normal priority 4 (the Task Scheduler default 7 is below-normal CPU and low I/O
  priority, which stretched a 35 s run to ~250 s);
- logs to logs\ag_v1_<mode>.log;
- runs as the current user, only while logged on, because the MT5 terminal must run in the same session.
Re-running -Apply replaces the same three tasks and removes the superseded narrow weekend-only
watch task. No task places, checks or modifies orders or positions.
#>
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
$PythonW = Join-Path $Repo '.venv\Scripts\pythonw.exe'
$Runner = Join-Path $Repo 'scripts\host\live_candles_smoke.py'
$Preflight = Join-Path $Repo 'scripts\host\verify_objective.py'
$VerifyTasks = Join-Path $Repo 'scripts\host\verify_tasks.ps1'

$Plan = @(
  @{ Name = 'AG-V1-FX-Cycles';    Mode = 'fx';     Minutes = 15; Canonical = $true;  StartAt = '00:01:00' },
  @{ Name = 'AG-V1-Crypto-Daily'; Mode = 'crypto'; Minutes = 5;  Canonical = $false; StartAt = '00:02:30' },
  @{ Name = 'AG-V1-LSMC-Watch';   Mode = 'lsmc';   Minutes = 5;  Canonical = $false; StartAt = '00:04:15' }
)

# ---------------------------------------------------------------------------------------------
# HOST TASK DECLARATIONS -- always-on target (SCHED-R1-B, 2026-10-08).
# Registered = what `schtasks /query /tn <name> /xml` showed on 2026-10-08, sanitized: no SIDs, user
# names, author, machine name or password; every task runs as the current interactive user
# (LogonType InteractiveToken, only while logged on). Target = the always-on host.
# -Apply acts only on Managed INSTALLER/RETIRE rows ($Plan + AG-V1-LSMC-Crypto-Weekend); every other
# target is reached by a separate owner-run change. WhatIf prints a read-only registered-vs-target diff.
# Trigger times are host local time (MMT). MMT has no DST, so UTC = MMT - 06:30 all year.
# AG-HOST-TIMEZONE: Id=Myanmar Standard Time; Abbrev=MMT; UtcOffset=+06:30; DST=false
# AG-HOST-POWER-POLICY: AC_STANDBY_TIMEOUT_MIN=0; AC_HIBERNATE_TIMEOUT_MIN=0; MODE=ALWAYS_ON
#   Declaration only: this script never changes power settings (tests/test_host_go_live_kit.py checks
#   that it never calls powercfg). Owner-applied 2026-10-08 (SCHED-R1-A2).
$HostTimeZone = @{ Id = 'Myanmar Standard Time'; Abbrev = 'MMT'; UtcOffset = '+06:30'; Dst = $false }
$HostPowerPolicy = @{ AcStandbyTimeoutMin = 0; AcHibernateTimeoutMin = 0; Mode = 'ALWAYS_ON' }
# Roots as observed on the host. PROD = deployed checkout, DEV = owner's working checkout,
# TELEMETRY = separate main checkout for the local heartbeat (absent on 2026-10-08).
$HostRoots = @{ PROD = 'D:\wp3-main-integ'; DEV = 'D:\ddev\AG profit trading'; TELEMETRY = 'D:\ag-telemetry\repo'
                USERPROFILE = $env:USERPROFILE }
# START STAGGER RULE (runner logs 2026-10-01..08, duration = last log line - scheduled start):
#   every M5 close (UTC :00/:05 = MMT :00/:05) opens a 300 s cycle. Runners start in priority order
#   fx -> crypto -> lsmc: the first 60 s after the close, each next one at the previous start plus the
#   previous runner's p95 duration, rounded up to 15 s. fx +1:00 (p95 78 s), crypto +2:30 (p95 103 s),
#   lsmc +4:15 (p95 62 s, ends ~+0:17 of the next cycle). The hourly heartbeat takes the idle head of
#   a cycle at +0:20. MT5 access stays serialized on the host-wide mt5_access.lock.
# Status: ACTIVE | NEW | RETIRED (superseded, target ABSENT) | REMOVE (target ABSENT) |
#         DISABLED (target DISABLED, DeleteAfter) | DISABLE_AFTER_PARITY (ENABLED until parity, then DISABLED).
# Target.State: ENABLED | DISABLED | ABSENT. Target.Days: DAILY | ONCE | Mon,Tue,... list.
$Declared = @(
  @{ Name = 'AG-V1-FX-Cycles'; Path = '\'; Managed = 'INSTALLER'; Status = 'ACTIVE'
     Registered = 'ENABLED; pythonw; daily 00:01 every 15 min'
     Target = @{ State = 'ENABLED'; Exe = '{PROD}\.venv\Scripts\pythonw.exe'; Args = '"{PROD}\scripts\host\live_candles_smoke.py" --mode fx'
                 Days = 'DAILY'; Start = '00:01:00'; EveryMin = 15 }
     Note = 'FX windows are fixed UTC inside the runner; cadence = the M15 trigger timeframe' },
  @{ Name = 'AG-V1-Crypto-Daily'; Path = '\'; Managed = 'INSTALLER'; Status = 'ACTIVE'
     Registered = 'ENABLED; pythonw; daily 00:02 every 15 min'
     Target = @{ State = 'ENABLED'; Exe = '{PROD}\.venv\Scripts\pythonw.exe'; Args = '"{PROD}\scripts\host\live_candles_smoke.py" --mode crypto'
                 Days = 'DAILY'; Start = '00:02:30'; EveryMin = 5 }
     Note = 'cadence = ST_LIQUIDITY_SWEEP_RETEST_V1 M5 entry timeframe; windows gated in the runner (zoneinfo)' },
  @{ Name = 'AG-V1-LSMC-Watch'; Path = '\'; Managed = 'INSTALLER'; Status = 'ACTIVE'
     Registered = 'ENABLED; pythonw; Mon-Fri 00:03 every 5 min'
     Target = @{ State = 'ENABLED'; Exe = '{PROD}\.venv\Scripts\pythonw.exe'; Args = '"{PROD}\scripts\host\live_candles_smoke.py" --mode lsmc'
                 Days = 'DAILY'; Start = '00:04:15'; EveryMin = 5 }
     Note = 'daily: the runner reports FX MARKET_CLOSED in the FX weekend and keeps watching BTC/ETH' },
  @{ Name = 'AG-V1-LSMC-Crypto-Weekend'; Path = '\'; Managed = 'RETIRE'; Status = 'RETIRED'
     Registered = 'ENABLED; pythonw; Sun,Mon 03:18 every 5 min for 2 h 26 min'
     Target = @{ State = 'ABSENT' }; Note = 'superseded by the daily AG-V1-LSMC-Watch' },
  @{ Name = 'AG-Wake-MT5'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'RETIRED'
     Registered = 'ENABLED; WakeToRun; Mon-Fri 12:25; starts the MT5 terminal'
     Target = @{ State = 'ABSENT' }; Note = 'always-on host' },
  @{ Name = 'AG-Wake-Weekend-Crypto'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'RETIRED'
     Registered = 'ENABLED; WakeToRun; Sun,Mon 03:10; starts the MT5 terminal'
     Target = @{ State = 'ABSENT' }; Note = 'always-on host' },
  @{ Name = 'AG-Sleep-Night'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'RETIRED'
     Registered = 'ENABLED; daily 00:45; rundll32 powrprof.dll,SetSuspendState 0,1,0'
     Target = @{ State = 'ABSENT' }; Note = 'always-on host; the sleep lasted only 3-11 s each night' },
  @{ Name = 'AG-Sleep-Weekend-Crypto'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'RETIRED'
     Registered = 'ENABLED; Sun,Mon 05:45; rundll32 powrprof.dll,SetSuspendState 0,1,0'
     Target = @{ State = 'ABSENT' }; Note = 'always-on host' },
  @{ Name = 'AG Profit Trading - BTC Daily Decision'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'DISABLE_AFTER_PARITY'
     Registered = 'ENABLED; daily 13:05 (06:35Z); system Python 3.14; DEV checkout'
     Target = @{ State = 'ENABLED'; Exe = 'C:\Python314\python.exe'; Args = '"{DEV}\scripts\run_btc_daily_report.py" --json'
                 Days = 'DAILY'; Start = '13:05:00'; EveryMin = 0 }
     Note = 'disable once the VT MT5 crypto ticket has shown parity with this Bybit report' },
  @{ Name = 'AGX-HealthExport'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'ACTIVE'
     Registered = 'ENABLED; one-time 2026-10-01 19:50:23, every 30 min indefinitely; script outside the repo'
     Target = @{ State = 'ENABLED'; Exe = 'powershell.exe'; Args = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{USERPROFILE}\Scripts\export-ag-health.ps1"'
                 Days = 'ONCE'; Start = '19:50:23'; EveryMin = 30 }
     Note = 'script content is not in the repository' },
  @{ Name = 'AG_FX_ASIAN_LONDON_SHADOW'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'REMOVE'
     Registered = 'DISABLED; Mon-Fri 13:30:20-17:30:20 (17 triggers); DEV run_asian_london_once.bat'
     Target = @{ State = 'ABSENT' }; Note = 'superseded by AG-V1-FX-Cycles' },
  @{ Name = 'AG_FX_LONDON_NEWYORK_SHADOW'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'REMOVE'
     Registered = 'DISABLED; Mon-Fri 18:30:20-21:30:20 (13 triggers); DEV run_london_newyork_once.bat'
     Target = @{ State = 'ABSENT' }; Note = 'superseded by AG-V1-FX-Cycles' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowA_AsianRef'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Status = 'DISABLED'
     Registered = 'DISABLED_2026-10-08; Mon-Fri 12:00 (05:30Z); DEV venv'; DeleteAfter = '2026-10-15'
     Target = @{ State = 'DISABLED' }; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowB_PreLondon'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Status = 'DISABLED'
     Registered = 'DISABLED_2026-10-08; Mon-Fri 13:20 (06:50Z); DEV venv'; DeleteAfter = '2026-10-15'
     Target = @{ State = 'DISABLED' }; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowC_London'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Status = 'DISABLED'
     Registered = 'DISABLED_2026-10-08; Mon-Fri 15:30 (09:00Z); DEV venv'; DeleteAfter = '2026-10-15'
     Target = @{ State = 'DISABLED' }; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowD_LondonNY'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Status = 'DISABLED'
     Registered = 'DISABLED_2026-10-08; Mon-Fri 19:00 (12:30Z); DEV venv'; DeleteAfter = '2026-10-15'
     Target = @{ State = 'DISABLED' }; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection' },
  @{ Name = 'AG-Heartbeat-Local'; Path = '\'; Managed = 'HOST_ONLY'; Status = 'NEW'
     Registered = 'ABSENT'
     Target = @{ State = 'ENABLED'; Exe = '{TELEMETRY}\.venv\Scripts\pythonw.exe'
                 Args = '"{TELEMETRY}\scripts\host\heartbeat.py" --host-repo "{PROD}" --out "D:\ag-telemetry\heartbeat.json"'
                 Days = 'DAILY'; Start = '00:00:20'; EveryMin = 60 }
     Note = 'local output only (heartbeat.json; nothing is sent). Needs the TELEMETRY checkout + venv first' }
)

function Expand-HostRoot([string]$s) {
  foreach ($k in $HostRoots.Keys) { $s = $s.Replace("{$k}", [string]$HostRoots[$k]) }
  $s
}

function Get-RegisteredTaskFacts($d) {
  # Read-only: Get-ScheduledTask only. Summarizes the first trigger and first action.
  $t = Get-ScheduledTask -TaskPath $d.Path -TaskName $d.Name -ErrorAction SilentlyContinue
  if ($null -eq $t) { return @{ State = 'ABSENT' } }
  $tr = @($t.Triggers)[0]; $a = @($t.Actions)[0]
  $days = switch ($tr.CimClass.CimClassName) {
    'MSFT_TaskDailyTrigger' { 'DAILY' }
    'MSFT_TaskTimeTrigger' { 'ONCE' }
    'MSFT_TaskWeeklyTrigger' {
      $names = 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'
      (0..6 | Where-Object { $tr.DaysOfWeek -band (1 -shl $_) } | ForEach-Object { $names[$_] }) -join ','
    }
    default { $tr.CimClass.CimClassName }
  }
  $every = 0
  if ($tr.Repetition.Interval -match '^PT(?:(\d+)H)?(?:(\d+)M)?$') { $every = 60 * [int]$Matches[1] + [int]$Matches[2] }
  @{ State = $(if ($t.State -eq 'Disabled') { 'DISABLED' } else { 'ENABLED' })
     Exe = $a.Execute; Args = $a.Arguments; Days = $days; EveryMin = $every
     Start = $(if ($tr.StartBoundary -match 'T(\d\d:\d\d:\d\d)') { $Matches[1] } else { '' }) }
}

function Get-TaskDiff($d) {
  # Fields that differ between the registered task and its declared target ('' when none differ).
  $r = Get-RegisteredTaskFacts $d
  $diff = @()
  if ($r.State -ne $d.Target.State) { $diff += "State: $($r.State) -> $($d.Target.State)" }
  if ($r.State -ne 'ABSENT' -and $d.Target.State -eq 'ENABLED') {
    foreach ($f in 'Exe', 'Args', 'Days', 'Start', 'EveryMin') {
      $want = if ($f -in 'Exe', 'Args') { Expand-HostRoot $d.Target[$f] } else { [string]$d.Target[$f] }
      if ([string]$r[$f] -ne $want) { $diff += "${f}: $($r[$f]) -> $want" }
    }
  }
  $diff -join '; '
}

if (-not (Test-Path $Python)) {
  Write-Host "MISSING venv python: $Python  (py -3.11 -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
  if ($Apply) { exit 1 }
}
if ($Apply) {
  Write-Host '=== OBJECTIVE PREFLIGHT ==='
  & $Python $Preflight
  if ($LASTEXITCODE -ne 0) {
    Write-Host 'REFUSED: repository objective preflight failed; no scheduled task was changed.'
    exit 1
  }
}

foreach ($t in $Plan) {
  $ModeSuffix = if ($t.Canonical) { ' --canonical' } else { '' }
  $Arguments = ("`"{0}`" --mode {1}{2}" -f $Runner, $t.Mode, $ModeSuffix)
  Write-Host ("{0}: every {1} min from {5} daily -> `"{2}`" `"{3}`" --mode {4}{6}" -f `
    $t.Name, $t.Minutes, $PythonW, $Runner, $t.Mode, $t.StartAt, $ModeSuffix)
}
Write-Host ("=== HOST TASK DECLARATIONS vs REGISTERED ({0}, UTC{1}; {2} declared; -Apply acts only on INSTALLER/RETIRE) ===" -f `
  $HostTimeZone.Abbrev, $HostTimeZone.UtcOffset, $Declared.Count)
foreach ($d in $Declared) {
  $diff = Get-TaskDiff $d
  Write-Host ("{0}{1} [{2}/{3}] {4}" -f $d.Path, $d.Name, $d.Managed, $d.Status, $(if ($diff) { "CHANGE $diff" } else { 'MATCHES TARGET' }))
}
if (-not $Apply) { Write-Host 'WhatIf: no changes made. Re-run with -Apply to install.'; exit 0 }

New-Item -ItemType Directory -Force -Path (Join-Path $Repo 'logs') | Out-Null
# Retire the superseded narrow weekend-only watch. The daily six-instrument watch now
# covers BTCUSDT/ETHUSDT throughout weekends and fails FX closed while its market is shut.
$LegacyWeekendTask = 'AG-V1-LSMC-Crypto-Weekend'
if (Get-ScheduledTask -TaskName $LegacyWeekendTask -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $LegacyWeekendTask -Confirm:$false
  Write-Host "REMOVED SUPERSEDED $LegacyWeekendTask"
}
foreach ($t in $Plan) {
  $ModeSuffix = if ($t.Canonical) { ' --canonical' } else { '' }
  $Arguments = ("`"{0}`" --mode {1}{2}" -f $Runner, $t.Mode, $ModeSuffix)
  $action = New-ScheduledTaskAction -Execute $PythonW -Argument $Arguments -WorkingDirectory $Repo
  $at = $t.StartAt
  $repeat = (New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes $t.Minutes) -RepetitionDuration (New-TimeSpan -Hours 24)).Repetition
  $trigger = New-ScheduledTaskTrigger -Daily -At $at
  $trigger.Repetition = $repeat
  $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -Priority 4
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false }
  Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'AG V1 informational (ARCHIVE_ONLY). No orders.' | Out-Null
  Write-Host "INSTALLED $($t.Name)"
}
Write-Host '=== INSTALLED TASK VERIFICATION ==='
& $VerifyTasks
if ($LASTEXITCODE -ne 0) { exit 1 }
