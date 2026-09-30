<#
Step 4 of scripts/host/GO_LIVE.md -- Windows Task Scheduler tasks for AG V1 (informational only).

  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1          # -WhatIf (default): prints the plan, changes nothing
  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1 -Apply   # installs / replaces the three tasks

Tasks. All run the repo venv: .venv\Scripts\python.exe scripts\host\live_candles_smoke.py --mode <m>
  AG-V1-FX-Cycles     every 15 min, daily. The runner acts only inside the frozen ST_ASIAN_SWEEP_5R_V1
                      trade sessions in UTC, plus 30 min grace:
                        ASIAN_LONDON   07:00-11:00 GMT (08:00-12:00 Europe/London in BST)
                        LONDON_NEWYORK 12:00-15:00 GMT (13:00-16:00 Europe/London in BST)
                      Gating in UTC inside Python makes the schedule DST-safe and independent of the
                      host's time zone.
  AG-V1-Crypto-Daily  every 5 min, daily. The runner acts only inside the active crypto ticket config
                      window (V2: weekdays 09:00-12:00 America/New_York; V1: 06:30-06:45 UTC).
  AG-V1-LSMC-Watch    every 5 min, Mon-Fri. ST_LARGE_SMC_V1@1.1.0 watch; alerts are ARCHIVE_ONLY.

Every task:
- runs single-instance (MultipleInstances IgnoreNew, plus a Python lock file in logs\);
- starts at a staggered minute offset (fx +1, crypto +2, lsmc +3) so no two tasks start together,
  and all MT5 access is serialized on one cross-process lock (logs\mt5_access.lock);
- has a 4-minute time limit (the runner itself self-exits after 120 s with TIMEOUT);
- logs to logs\ag_v1_<mode>.log;
- runs as the current user, only while logged on, because the MT5 terminal must run in the same session.
Re-running -Apply replaces the same three tasks. No task places, checks or modifies orders or positions.
#>
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
$Runner = Join-Path $Repo 'scripts\host\live_candles_smoke.py'

$Plan = @(
  @{ Name = 'AG-V1-FX-Cycles';    Mode = 'fx';     Minutes = 15; Offset = 1; Weekdays = $false },
  @{ Name = 'AG-V1-Crypto-Daily'; Mode = 'crypto'; Minutes = 5;  Offset = 2; Weekdays = $false },
  @{ Name = 'AG-V1-LSMC-Watch';   Mode = 'lsmc';   Minutes = 5;  Offset = 3; Weekdays = $true  }
)

if (-not (Test-Path $Python)) {
  Write-Host "MISSING venv python: $Python  (py -3.11 -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
  if ($Apply) { exit 1 }
}

foreach ($t in $Plan) {
  $when = if ($t.Weekdays) { 'Mon-Fri' } else { 'daily' }
  Write-Host ("{0}: every {1} min at +{6} min {2} -> `"{3}`" `"{4}`" --mode {5}" -f $t.Name, $t.Minutes, $when, $Python, $Runner, $t.Mode, $t.Offset)
}
if (-not $Apply) { Write-Host 'WhatIf: no changes made. Re-run with -Apply to install.'; exit 0 }

New-Item -ItemType Directory -Force -Path (Join-Path $Repo 'logs') | Out-Null
foreach ($t in $Plan) {
  $action = New-ScheduledTaskAction -Execute $Python -Argument ("`"{0}`" --mode {1}" -f $Runner, $t.Mode) -WorkingDirectory $Repo
  $at = '00:{0:D2}' -f $t.Offset
  $repeat = (New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes $t.Minutes) -RepetitionDuration (New-TimeSpan -Hours 24)).Repetition
  if ($t.Weekdays) { $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $at }
  else             { $trigger = New-ScheduledTaskTrigger -Daily -At $at }
  $trigger.Repetition = $repeat
  $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -Priority 4
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false }
  Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'AG V1 informational (ARCHIVE_ONLY). No orders.' | Out-Null
  Write-Host "INSTALLED $($t.Name)"
}
Get-ScheduledTask -TaskName 'AG-V1-*' | Select-Object TaskName, State | Format-Table -AutoSize
