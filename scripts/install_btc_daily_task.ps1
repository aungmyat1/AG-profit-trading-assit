param(
    [string]$TaskName = "AG Profit Trading - BTC Daily Decision",
    [string]$LocalTime = "06:37"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "run_btc_daily_report.py"
$python = (Get-Command python -ErrorAction Stop).Source

if ((Get-TimeZone).Id -ne "Myanmar Standard Time") {
    throw "This preset expects Windows timezone 'Myanmar Standard Time' (UTC+06:30)."
}

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument ('"{0}" --json' -f $runner) `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $LocalTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Read-only Bybit BTCUSDT daily decision at 00:07 UTC; execution disabled." `
    -Force | Out-Null

Write-Output "Installed '$TaskName' daily at $LocalTime local time (00:07 UTC)."
