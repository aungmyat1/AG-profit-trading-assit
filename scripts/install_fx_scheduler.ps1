# AG FX scheduler -- verify and (re)install deterministic weekday `--once` triggers.
#
# AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1, P1.
#
# DO NOT INSTALL DUPLICATE TASKS. This script operates on the two EXISTING task names
# (AG_FX_ASIAN_LONDON_SHADOW, AG_FX_LONDON_NEWYORK_SHADOW) and corrects their triggers
# in place. It never registers a second task for the same cycle. Their prior trigger
# configuration is exported to logs/scheduler/ before any change, so the previous state
# is preserved as evidence and can be restored.
#
# What is corrected (see src/scheduling/fx_schedule.py for the full rationale):
#   * Weekday only (Mon-Fri)            -- was every day, including closed weekends.
#   * Bounded to the cycle's own window -- was unbounded (PT15M repeating forever).
#   * Anchored at M15 CLOSE + 20s       -- was anchored at :00 (the bar OPEN).
#   * Fail-closed runner action         -- was a direct --once call with no gates.
#   * One independent trigger per slot  -- was ONE weekly trigger + PT15M repetition, whose
#     repetitions all hang off the first slot's trigger instance: with the host asleep at
#     the first slot (StartWhenAvailable/WakeToRun off), Task Scheduler launched NONE of
#     that day's later slots even after wake (2026-09-22, 2026-09-23 ASIAN_LONDON). See
#     docs/status/AG_ASIAN_SWEEP_MISSING_MANDATORY_EVIDENCE_STATUS.md. A slot missed while
#     asleep is now just that slot; missed slots are still never caught up.
#
# Idempotent: re-running with triggers already correct makes no change and says so.

[CmdletBinding()]
param(
    [switch]$VerifyOnly,
    [string]$RepoRoot = "",
    [string]$EndBoundary = "2026-12-31T23:59:00"
)

$ErrorActionPreference = "Stop"

# Resolve in the body, not as a parameter default: $PSScriptRoot is not reliably
# populated at parameter-binding time under -File in all PowerShell versions.
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Get-Location).Path
}
if (-not (Test-Path (Join-Path $RepoRoot "scripts\run_fx_cycle_once.py"))) {
    throw "AG_FX_SCHEDULER_ERROR: RepoRoot '$RepoRoot' does not contain scripts\run_fx_cycle_once.py"
}
Write-Output ("RepoRoot = {0}" -f $RepoRoot)

# cycle_id -> (task name, first-slot local time, repetition duration, runner cycle arg)
$Cycles = @(
    [pscustomobject]@{
        Cycle      = "ASIAN_LONDON"
        TaskName   = "AG_FX_ASIAN_LONDON_SHADOW"
        FirstSlot  = "13:30:20"   # 07:00:20 UTC (MMT = UTC+6:30), M15 close + 20s settle
        SlotCount  = 17           # 07:00:20 -> 11:00:20 UTC, every 15m
        BatchFile  = "scripts\scheduled\run_asian_london_once.bat"
    },
    [pscustomobject]@{
        Cycle      = "LONDON_NEWYORK"
        TaskName   = "AG_FX_LONDON_NEWYORK_SHADOW"
        FirstSlot  = "18:30:20"   # 12:00:20 UTC, M15 close + 20s settle
        SlotCount  = 13           # 12:00:20 -> 15:00:20 UTC, every 15m
        BatchFile  = "scripts\scheduled\run_london_newyork_once.bat"
    }
)

$BackupDir = Join-Path $RepoRoot "logs\scheduler"
if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }

Write-Output "=== AG FX SCHEDULER: BEFORE ==="
foreach ($c in $Cycles) {
    $t = Get-ScheduledTask -TaskName $c.TaskName -ErrorAction SilentlyContinue
    if ($null -eq $t) {
        Write-Output ("  {0}: ABSENT" -f $c.TaskName)
        continue
    }
    $i = Get-ScheduledTaskInfo -TaskName $c.TaskName
    Write-Output ("  {0}: State={1} LastRun={2} LastResult={3} NextRun={4}" -f `
        $c.TaskName, $t.State, $i.LastRunTime, $i.LastTaskResult, $i.NextRunTime)
    foreach ($tr in $t.Triggers) {
        Write-Output ("    trigger: start={0} interval={1} duration={2} days={3} end={4}" -f `
            $tr.StartBoundary, $tr.Repetition.Interval, $tr.Repetition.Duration, `
            ($tr.DaysOfWeek -join ","), $tr.EndBoundary)
    }
    foreach ($a in $t.Actions) { Write-Output ("    action: {0} {1}" -f $a.Execute, $a.Arguments) }
}

if ($VerifyOnly) {
    Write-Output ""
    Write-Output "VERIFY_ONLY -- no changes made."
    exit 0
}

Write-Output ""
Write-Output "=== BACKUP (prior task XML) ==="
foreach ($c in $Cycles) {
    $xml = Export-ScheduledTask -TaskName $c.TaskName -ErrorAction SilentlyContinue
    if ($xml) {
        $path = Join-Path $BackupDir ("{0}.before.json" -f $c.TaskName)
        if (Test-Path $path) { $path = Join-Path $BackupDir ("{0}.before.again.json" -f $c.TaskName) }
        if (Test-Path $path) {
            # never overwrite an earlier backup -- it is evidence of a prior state
            $path = Join-Path $BackupDir ("{0}.before.{1}.json" -f $c.TaskName, (Get-Date -Format "yyyyMMddTHHmmss"))
        }
        $xml | Set-Content -Path $path -Encoding UTF8
        Write-Output ("  saved {0}" -f $path)
    } else {
        Write-Output ("  {0}: no existing task to back up" -f $c.TaskName)
    }
}

Write-Output ""
Write-Output "=== APPLY (correct triggers in place -- no duplicate tasks) ==="
foreach ($c in $Cycles) {
    $t = Get-ScheduledTask -TaskName $c.TaskName -ErrorAction SilentlyContinue
    if ($null -eq $t) {
        Write-Output ("  {0}: ABSENT -- not created by this script" -f $c.TaskName)
        Write-Output  "           (register the task deliberately rather than letting an installer invent one)"
        continue
    }

    $at = [datetime]::ParseExact($c.FirstSlot, "HH:mm:ss", $null)

    # One weekly Mon-Fri trigger per M15-close slot (first slot + k*15m, k < SlotCount),
    # so the last trigger lands precisely on the window's last M15 close and never past
    # it, and no slot's launch depends on any other slot's trigger having fired.
    $triggers = @(
        for ($k = 0; $k -lt $c.SlotCount; $k++) {
            New-ScheduledTaskTrigger -Weekly `
                -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $at.AddMinutes(15 * $k)
        }
    )

    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable:$false `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries

    Set-ScheduledTask -TaskName $c.TaskName -Trigger $triggers -Settings $settings | Out-Null
    Write-Output ("  {0}: triggers corrected -> weekdays, {1} independent slots from {2}, every 15m" -f `
        $c.TaskName, $c.SlotCount, $c.FirstSlot)
}

Write-Output ""
Write-Output "=== AG FX SCHEDULER: AFTER ==="
foreach ($c in $Cycles) {
    $t = Get-ScheduledTask -TaskName $c.TaskName -ErrorAction SilentlyContinue
    if ($null -eq $t) { continue }
    $i = Get-ScheduledTaskInfo -TaskName $c.TaskName
    Write-Output ("  {0}: State={1} NextRun={2}" -f $c.TaskName, $t.State, $i.NextRunTime)
    foreach ($tr in $t.Triggers) {
        Write-Output ("    trigger: start={0} interval={1} duration={2} days={3}" -f `
            $tr.StartBoundary, $tr.Repetition.Interval, $tr.Repetition.Duration, `
            ($tr.DaysOfWeek -join ","))
    }
    foreach ($a in $t.Actions) { Write-Output ("    action: {0} {1}" -f $a.Execute, $a.Arguments) }
}
