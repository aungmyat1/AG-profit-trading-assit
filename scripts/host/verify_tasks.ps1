<#
Verify the three Windows Task Scheduler bindings for the six-instrument AG V1 objective.
Read-only: this script never creates, starts, stops, or removes a task.

  powershell -ExecutionPolicy Bypass -File scripts\host\verify_tasks.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = (Join-Path $Repo '.venv\Scripts\python.exe')
$Runner = (Join-Path $Repo 'scripts\host\live_candles_smoke.py')
$Expected = @(
  @{ Name = 'AG-V1-FX-Cycles';    Mode = 'fx';     Canonical = $true },
  @{ Name = 'AG-V1-Crypto-Daily'; Mode = 'crypto'; Canonical = $false },
  @{ Name = 'AG-V1-LSMC-Watch';   Mode = 'lsmc';   Canonical = $false }
)
$Failures = 0
foreach ($e in $Expected) {
  $task = Get-ScheduledTask -TaskName $e.Name -ErrorAction SilentlyContinue
  if ($null -eq $task) {
    Write-Host "[FAIL] $($e.Name): ABSENT"
    $Failures += 1
    continue
  }
  $actions = @($task.Actions)
  $suffix = if ($e.Canonical) { ' --canonical' } else { '' }
  $expectedArg = "`"$Runner`" --mode $($e.Mode)$suffix"
  $actionOk = $actions.Count -eq 1 -and $actions[0].Execute -eq $Python -and `
              $actions[0].Arguments -eq $expectedArg -and $actions[0].WorkingDirectory -eq $Repo
  $triggerOk = @($task.Triggers).Count -ge 1
  $settingsOk = $task.Settings.MultipleInstances -eq 'IgnoreNew'
  $info = Get-ScheduledTaskInfo -TaskName $e.Name
  if (-not ($actionOk -and $triggerOk -and $settingsOk)) {
    Write-Host "[FAIL] $($e.Name): action=$actionOk trigger=$triggerOk single_instance=$settingsOk"
    $Failures += 1
  } else {
    Write-Host ("[PASS] {0}: State={1} LastResult={2} NextRun={3}" -f `
      $e.Name, $task.State, $info.LastTaskResult, $info.NextRunTime)
  }
}
$legacy = Get-ScheduledTask -TaskName 'AG-V1-LSMC-Crypto-Weekend' -ErrorAction SilentlyContinue
if ($null -ne $legacy) {
  Write-Host '[FAIL] AG-V1-LSMC-Crypto-Weekend: superseded duplicate task is still installed'
  $Failures += 1
}
if ($Failures -gt 0) {
  Write-Host "RESULT: FAIL ($Failures task binding(s) invalid)"
  exit 1
}
Write-Host 'RESULT: PASS (3/3 scheduled task bindings valid; no duplicate weekend watcher)'
