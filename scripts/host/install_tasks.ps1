<#
Step 4 of scripts/host/GO_LIVE.md -- Windows Task Scheduler tasks for AG V1 (informational only).

  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1          # -WhatIf (default): prints the plan, changes nothing
  powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1 -Apply   # installs / replaces the four tasks

Tasks. All run the repo venv: .venv\Scripts\python.exe scripts\host\live_candles_smoke.py --mode <m>
  AG-V1-FX-Cycles     every 15 min, daily. The runner acts only inside the frozen ST_ASIAN_SWEEP_5R_V1
                      trade sessions in UTC, plus 30 min grace:
                        ASIAN_LONDON   07:00-11:00 GMT (08:00-12:00 Europe/London in BST)
                        LONDON_NEWYORK 12:00-15:00 GMT (13:00-16:00 Europe/London in BST)
                      Gating in UTC inside Python makes the schedule DST-safe and independent of the
                      host's time zone.
  AG-V1-Crypto-Daily  every 5 min, daily. The runner acts only inside the active crypto ticket config
                      windows (V3: weekdays 09:00-12:00 America/New_York + Sat/Sun 21:00-23:00 UTC;
                      V2: weekdays only; V1: 06:30-06:45 UTC).
  AG-V1-LSMC-Watch    every 5 min, Mon-Fri. ST_LARGE_SMC_V1@1.1.0 watch; alerts are ARCHIVE_ONLY.
  AG-V1-LSMC-Crypto-Weekend
                      every 5 min, Sat+Sun 20:45-23:15 UTC (first start 20:48 at the +3 offset).
                      BTCUSD/ETHUSD only, VT Markets MT5 data (never the public feed). The UTC window
                      is converted to this host's local days/times at install time; the runner also
                      self-gates in UTC.

Every task:
- runs single-instance (MultipleInstances IgnoreNew, plus a Python lock file in logs\);
- starts at a staggered minute offset (fx +1, crypto +2, lsmc +3) so no two tasks start together,
  and all MT5 access is serialized on one cross-process lock (logs\mt5_access.lock);
- has a 4-minute time limit (the runner itself self-exits after 120 s with TIMEOUT);
- runs at normal priority 4 (the Task Scheduler default 7 is below-normal CPU and low I/O
  priority, which stretched a 35 s run to ~250 s);
- logs to logs\ag_v1_<mode>.log;
- runs as the current user, only while logged on, because the MT5 terminal must run in the same session.
Re-running -Apply replaces the same four tasks. No task places, checks or modifies orders or positions.
#>
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
$Runner = Join-Path $Repo 'scripts\host\live_candles_smoke.py'

$Plan = @(
  @{ Name = 'AG-V1-FX-Cycles';           Mode = 'fx';           Minutes = 15; Offset = 1; Days = 'DAILY' },
  @{ Name = 'AG-V1-Crypto-Daily';        Mode = 'crypto';       Minutes = 5;  Offset = 2; Days = 'DAILY' },
  @{ Name = 'AG-V1-LSMC-Watch';          Mode = 'lsmc';         Minutes = 5;  Offset = 3; Days = 'WEEKDAYS' },
  @{ Name = 'AG-V1-LSMC-Crypto-Weekend'; Mode = 'lsmc-weekend'; Minutes = 5;  Offset = 3; Days = 'WEEKEND_UTC';
     UtcStart = '20:45'; UtcEnd = '23:15' }
)

function Get-WeekendUtcLocal($t) {
  # First +Offset slot at/after UtcStart, last slot before UtcEnd, for the coming Sat and Sun (UTC),
  # converted to this host's local day of week and time.
  $now = [datetime]::UtcNow
  $sat = $now.Date.AddDays((([int][DayOfWeek]::Saturday) - [int]$now.DayOfWeek + 7) % 7)
  $s = [timespan]$t.UtcStart; $e = [timespan]$t.UtcEnd
  $first = [math]::Ceiling(($s.TotalMinutes - $t.Offset) / $t.Minutes) * $t.Minutes + $t.Offset
  $span = [math]::Floor(($e.TotalMinutes - 1 - $first) / $t.Minutes) * $t.Minutes
  $days = @(); $at = $null
  foreach ($d in 0, 1) {
    $startUtc = [datetime]::SpecifyKind($sat.AddDays($d).AddMinutes($first), 'Utc')
    $local = $startUtc.ToLocalTime()
    if ($local.Date -ne $local.AddMinutes($span).Date) { throw "$($t.Name): local window crosses midnight; not supported" }
    $days += $local.DayOfWeek
    if ($null -eq $at) { $at = $local }
  }
  return @{ Days = $days; At = $at; Duration = (New-TimeSpan -Minutes ($span + 1)); FirstUtc = $first }
}

if (-not (Test-Path $Python)) {
  Write-Host "MISSING venv python: $Python  (py -3.11 -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
  if ($Apply) { exit 1 }
}

foreach ($t in $Plan) {
  $when = switch ($t.Days) { 'DAILY' { 'daily' } 'WEEKDAYS' { 'Mon-Fri' } 'WEEKEND_UTC' {
      $w = Get-WeekendUtcLocal $t
      'Sat+Sun {0}-{1} UTC (local: {2} {3:HH:mm} for {4:hh\:mm})' -f $t.UtcStart, $t.UtcEnd, ($w.Days -join '+'), $w.At, $w.Duration } }
  Write-Host ("{0}: every {1} min at +{6} min {2} -> `"{3}`" `"{4}`" --mode {5}" -f $t.Name, $t.Minutes, $when, $Python, $Runner, $t.Mode, $t.Offset)
}
if (-not $Apply) { Write-Host 'WhatIf: no changes made. Re-run with -Apply to install.'; exit 0 }

New-Item -ItemType Directory -Force -Path (Join-Path $Repo 'logs') | Out-Null
foreach ($t in $Plan) {
  $action = New-ScheduledTaskAction -Execute $Python -Argument ("`"{0}`" --mode {1}" -f $Runner, $t.Mode) -WorkingDirectory $Repo
  if ($t.Days -eq 'WEEKEND_UTC') {
    $w = Get-WeekendUtcLocal $t
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $w.Days -At $w.At
    $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $w.At -RepetitionInterval (New-TimeSpan -Minutes $t.Minutes) -RepetitionDuration $w.Duration).Repetition
  } else {
    $at = '00:{0:D2}' -f $t.Offset
    $repeat = (New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes $t.Minutes) -RepetitionDuration (New-TimeSpan -Hours 24)).Repetition
    if ($t.Days -eq 'WEEKDAYS') { $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $at }
    else                        { $trigger = New-ScheduledTaskTrigger -Daily -At $at }
    $trigger.Repetition = $repeat
  }
  $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -Priority 4
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false }
  Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'AG V1 informational (ARCHIVE_ONLY). No orders.' | Out-Null
  Write-Host "INSTALLED $($t.Name)"
}
Get-ScheduledTask -TaskName 'AG-V1-*' | Select-Object TaskName, State | Format-Table -AutoSize
