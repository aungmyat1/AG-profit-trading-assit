<#
Step 4 of scripts/host/GO_LIVE.md -- Windows Task Scheduler tasks for AG V1 (informational only).

  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1          # -WhatIf (default): prints the plan, changes nothing
  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1 -Apply   # installs / replaces the three tasks

Tasks. All run the repo venv: .venv\Scripts\python.exe scripts\host\live_candles_smoke.py --mode <m>
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
- starts at a staggered minute offset (fx +1, crypto +2, lsmc +3) so no two tasks start together,
  and all MT5 access is serialized on one host-wide cross-process lock
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
$Runner = Join-Path $Repo 'scripts\host\live_candles_smoke.py'
$Preflight = Join-Path $Repo 'scripts\host\verify_objective.py'
$VerifyTasks = Join-Path $Repo 'scripts\host\verify_tasks.ps1'

$Plan = @(
  @{ Name = 'AG-V1-FX-Cycles';    Mode = 'fx';     Minutes = 15; Canonical = $true;  Offset = 1 },
  @{ Name = 'AG-V1-Crypto-Daily'; Mode = 'crypto'; Minutes = 5;  Canonical = $false; Offset = 2 },
  @{ Name = 'AG-V1-LSMC-Watch';   Mode = 'lsmc';   Minutes = 5;  Canonical = $false; Offset = 3 }
)

# ---------------------------------------------------------------------------------------------
# HOST TASK DECLARATIONS (declaration only -- -Apply never registers, changes or removes these).
# Every AG* task registered on the host, exported via `schtasks /query /tn <name> /xml` on
# 2026-10-08 and sanitized: no SIDs, user names, author, machine name or password. All tasks run
# as the current interactive user (LogonType InteractiveToken, only while logged on).
# Trigger times are host local time; UTC equivalents are given because the host has no DST.
# AG-HOST-TIMEZONE: Id=Myanmar Standard Time; Abbrev=MMT; UtcOffset=+06:30; DST=false
$HostTimeZone = @{ Id = 'Myanmar Standard Time'; Abbrev = 'MMT'; UtcOffset = '+06:30'; Dst = $false }
# Roots as observed on the host. PROD = deployed checkout, DEV = owner's working checkout.
$HostRoots = @{ PROD = 'D:\wp3-main-integ'; DEV = 'D:\ddev\AG profit trading'; USERPROFILE = '%USERPROFILE%' }
# Managed: INSTALLER = registered by -Apply from $Plan; RETIRE = -Apply unregisters it;
#          HOST_ONLY = registered by hand / another tool, not touched by -Apply.
# Drift: registered state differs from what -Apply would install (recorded, not corrected here).
$Declared = @(
  @{ Name = 'AG-V1-FX-Cycles'; Path = '\'; Managed = 'INSTALLER'; Enabled = $true
     Trigger = 'daily 00:01 MMT, every 15 min for 24 h'; Limit = 'PT4M'; Priority = 4
     Action = '{PROD}\.venv\Scripts\pythonw.exe "{PROD}\scripts\host\live_candles_smoke.py" --mode fx'; WorkDir = '{PROD}'
     Drift = 'registered runs pythonw.exe; installer writes python.exe' },
  @{ Name = 'AG-V1-Crypto-Daily'; Path = '\'; Managed = 'INSTALLER'; Enabled = $true
     Trigger = 'daily 00:02 MMT, every 15 min for 24 h'; Limit = 'PT4M'; Priority = 4
     Action = '{PROD}\.venv\Scripts\pythonw.exe "{PROD}\scripts\host\live_candles_smoke.py" --mode crypto'; WorkDir = '{PROD}'
     Drift = 'registered interval 15 min; installer writes 5 min; pythonw.exe vs python.exe' },
  @{ Name = 'AG-V1-LSMC-Watch'; Path = '\'; Managed = 'INSTALLER'; Enabled = $true
     Trigger = 'Mon-Fri 00:03 MMT, every 5 min for 24 h'; Limit = 'PT4M'; Priority = 4
     Action = '{PROD}\.venv\Scripts\pythonw.exe "{PROD}\scripts\host\live_candles_smoke.py" --mode lsmc'; WorkDir = '{PROD}'
     Drift = 'registered weekdays only; installer writes daily; pythonw.exe vs python.exe' },
  @{ Name = 'AG-V1-LSMC-Crypto-Weekend'; Path = '\'; Managed = 'RETIRE'; Enabled = $true
     Trigger = 'Sun,Mon 03:18 MMT (Sat,Sun 20:48Z), every 5 min for 2 h 26 min'; Limit = 'PT4M'; Priority = 4
     Action = '{PROD}\.venv\Scripts\pythonw.exe "{PROD}\scripts\host\live_candles_smoke.py" --mode lsmc-weekend'; WorkDir = '{PROD}'
     Drift = 'still registered although -Apply retires it as superseded' },
  @{ Name = 'AG-Wake-MT5'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $true; WakeToRun = $true
     Trigger = 'Mon-Fri 12:25 MMT (05:55Z)'; Limit = 'PT72H'
     Action = 'cmd.exe /c start "" "C:\Program Files\MetaTrader 5\terminal64.exe"'; WorkDir = '' },
  @{ Name = 'AG-Wake-Weekend-Crypto'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $true; WakeToRun = $true
     Trigger = 'Sun,Mon 03:10 MMT (Sat,Sun 20:40Z)'; Limit = 'PT72H'
     Action = 'cmd.exe /c start "" "C:\Program Files\MetaTrader 5\terminal64.exe"'; WorkDir = '' },
  @{ Name = 'AG-Sleep-Night'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $true
     Trigger = 'daily 00:45 MMT (18:15Z previous day)'; Limit = 'PT72H'
     Action = 'rundll32.exe powrprof.dll,SetSuspendState 0,1,0'; WorkDir = '' },
  @{ Name = 'AG-Sleep-Weekend-Crypto'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $true
     Trigger = 'Sun,Mon 05:45 MMT (Sat,Sun 23:15Z)'; Limit = 'PT72H'
     Action = 'rundll32.exe powrprof.dll,SetSuspendState 0,1,0'; WorkDir = '' },
  @{ Name = 'AG Profit Trading - BTC Daily Decision'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $true
     Trigger = 'daily 13:05 MMT (06:35Z)'; Limit = 'PT72H'
     Action = 'C:\Python314\python.exe "{DEV}\scripts\run_btc_daily_report.py" --json'; WorkDir = '{DEV}'
     Drift = 'system Python 3.14 and DEV checkout, not the PROD venv' },
  @{ Name = 'AGX-HealthExport'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $true
     Trigger = 'one-time 2026-10-01 19:50:23 MMT, every 30 min indefinitely'; Limit = 'PT72H'
     Action = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{USERPROFILE}\Scripts\export-ag-health.ps1"'; WorkDir = ''
     Drift = 'script lives outside the repository; its content is not declared here' },
  @{ Name = 'AG_FX_ASIAN_LONDON_SHADOW'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $false
     Trigger = 'Mon-Fri 13:30:20-17:30:20 MMT (07:00:20-11:00:20Z), 17 calendar triggers 15 min apart'; Limit = 'PT10M'
     Action = '"{DEV}\scripts\scheduled\run_asian_london_once.bat"'; WorkDir = '' },
  @{ Name = 'AG_FX_LONDON_NEWYORK_SHADOW'; Path = '\'; Managed = 'HOST_ONLY'; Enabled = $false
     Trigger = 'Mon-Fri 18:30:20-21:30:20 MMT (12:00:20-15:00:20Z), 13 calendar triggers 15 min apart'; Limit = 'PT10M'
     Action = '"{DEV}\scripts\scheduled\run_london_newyork_once.bat"'; WorkDir = '' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowA_AsianRef'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Enabled = $false; State = 'DISABLED_2026-10-08'; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection'
     Trigger = 'Mon-Fri 12:00 MMT (05:30Z)'; Limit = 'PT15M'
     Action = 'cmd.exe /c ""{DEV}\.venv\Scripts\python.exe" "{DEV}\scripts\run_eurusd_friction_campaign_window.py" --window-id WINDOW_A_ASIAN_REFERENCE >> "{DEV}\logs\friction_campaign_WINDOW_A_ASIAN_REFERENCE.log" 2>&1"'; WorkDir = '{DEV}' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowB_PreLondon'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Enabled = $false; State = 'DISABLED_2026-10-08'; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection'
     Trigger = 'Mon-Fri 13:20 MMT (06:50Z)'; Limit = 'PT15M'
     Action = 'cmd.exe /c ""{DEV}\.venv\Scripts\python.exe" "{DEV}\scripts\run_eurusd_friction_campaign_window.py" --window-id WINDOW_B_PRE_LONDON >> "{DEV}\logs\friction_campaign_WINDOW_B_PRE_LONDON.log" 2>&1"'; WorkDir = '{DEV}' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowC_London'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Enabled = $false; State = 'DISABLED_2026-10-08'; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection'
     Trigger = 'Mon-Fri 15:30 MMT (09:00Z)'; Limit = 'PT15M'
     Action = 'cmd.exe /c ""{DEV}\.venv\Scripts\python.exe" "{DEV}\scripts\run_eurusd_friction_campaign_window.py" --window-id WINDOW_C_LONDON >> "{DEV}\logs\friction_campaign_WINDOW_C_LONDON.log" 2>&1"'; WorkDir = '{DEV}' },
  @{ Name = 'AG_LSMC_EURUSD_Friction_WindowD_LondonNY'; Path = '\AG_LSMC_Friction_Campaign\'; Managed = 'HOST_ONLY'; Enabled = $false; State = 'DISABLED_2026-10-08'; Note = 'campaign ended 2026-09-30; delete after 2026-10-15 if no objection'
     Trigger = 'Mon-Fri 19:00 MMT (12:30Z)'; Limit = 'PT15M'
     Action = 'cmd.exe /c ""{DEV}\.venv\Scripts\python.exe" "{DEV}\scripts\run_eurusd_friction_campaign_window.py" --window-id WINDOW_D_LONDON_NEWYORK >> "{DEV}\logs\friction_campaign_WINDOW_D_LONDON_NEWYORK.log" 2>&1"'; WorkDir = '{DEV}' }
)

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
  Write-Host ("{0}: every {1} min at +{5} min daily -> `"{2}`" `"{3}`" --mode {4}{6}" -f `
    $t.Name, $t.Minutes, $Python, $Runner, $t.Mode, $t.Offset, $ModeSuffix)
}
Write-Host ("=== HOST TASK DECLARATIONS ({0}, UTC{1}; {2} tasks, -Apply manages only INSTALLER/RETIRE) ===" -f `
  $HostTimeZone.Abbrev, $HostTimeZone.UtcOffset, $Declared.Count)
foreach ($d in $Declared) {
  Write-Host ("{0}{1} [{2}{3}] {4}" -f $d.Path, $d.Name, $d.Managed, $(if ($d.Enabled) { '' } else { ', DISABLED' }), $d.Trigger)
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
  $action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Repo
  $at = '00:{0:D2}' -f $t.Offset
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
