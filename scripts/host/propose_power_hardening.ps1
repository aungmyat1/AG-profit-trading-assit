<#
AG_V1_HOST_HARDENING_R1 T3 -- PROPOSED host power hardening. Prints a plan; changes NOTHING
by default, and refuses to change anything even with -Apply unless a second, independent
owner-approval gate is also set. This mission's instruction was explicit: "propose (do not
apply without owner OK)" -- stronger than this kit's usual -WhatIf/-Apply convention, so this
script adds the extra gate on top of it rather than reusing -Apply alone.

  powershell -ExecutionPolicy Bypass -File scripts\host\propose_power_hardening.ps1
      -> prints the current wake-armed devices, the current AC standby timeout, and the
         exact commands that WOULD be run. No change is made.

  # Only after the owner has read the printed plan and explicitly agrees:
  $env:AG_OWNER_APPROVED_POWER_HARDENING = 'YES'
  powershell -ExecutionPolicy Bypass -File scripts\host\propose_power_hardening.ps1 -Apply

Plan (both parts are proposals; neither is scoped/implemented beyond what is printed here
until a human runs -Apply with the approval variable set):

  1. Disable mouse wake. `powercfg /devicequery wake_armed` is queried; any device whose
     PnP class is Mouse/HIDClass is proposed for `powercfg /devicedisablewake "<Device Name>"`.
     Keyboards and anything else currently wake-armed are left untouched and only reported --
     they are not touched without the device appearing literally in the printed mouse list.

  2. AC sleep = never during session windows. The trading session windows this kit already
     schedules around (install_tasks.ps1): FX 07:00-15:00 GMT (ASIAN_LONDON + LONDON_NEWYORK,
     covering the gap between them), plus the crypto/LSMC watch windows, which together span
     most of the UTC day on weekdays. Rather than proposing several start/stop pairs (one per
     narrow window), this proposes the simplest safe version: two scheduled tasks,
     "AG-V1-Sleep-Never-Start" at 06:55 UTC (`powercfg /change standby-timeout-ac 0`) and
     "AG-V1-Sleep-Never-Restore" at 23:30 UTC (`powercfg /change standby-timeout-ac <captured
     original value>`), covering the full FX+crypto+LSMC active window with margin. A owner who
     wants a tighter, multi-window schedule instead should treat this as a starting point, not
     a final design -- it is not applied either way without the approval gate below.

No order, position, or account-mutation call exists in this file.
#>
param([switch]$Apply)
$ErrorActionPreference = 'Stop'

Write-Host '=== CURRENT: powercfg /devicequery wake_armed ==='
$wakeArmed = (powercfg /devicequery wake_armed) -join "`n"
Write-Host $wakeArmed

Write-Host ''
Write-Host '=== CURRENT: AC standby timeout (active power scheme) ==='
$acQuery = powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>&1
Write-Host ($acQuery -join "`n")
$currentAcSeconds = $null
foreach ($line in $acQuery) {
  if ($line -match 'Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)') { $currentAcSeconds = [Convert]::ToInt64($Matches[1], 16) }
}
if ($null -eq $currentAcSeconds) { Write-Host 'WARNING: could not parse current AC standby timeout; -Apply will refuse the restore step.' }

$mouseDevices = @()
try {
  $mouseDevices = Get-PnpDevice -PresentOnly | Where-Object {
    ($_.Class -eq 'Mouse' -or $_.Class -eq 'HIDClass') -and ($wakeArmed -match [Regex]::Escape($_.FriendlyName))
  } | Select-Object -ExpandProperty FriendlyName -Unique
} catch {
  Write-Host "WARNING: Get-PnpDevice unavailable to cross-reference wake-armed devices ($_)."
}

Write-Host ''
Write-Host '=== PROPOSED PLAN (nothing applied yet) ==='
if ($mouseDevices.Count -eq 0) {
  Write-Host 'Mouse wake: no currently wake-armed device matched a Mouse/HIDClass PnP entry. Nothing proposed.'
} else {
  foreach ($d in $mouseDevices) { Write-Host "  powercfg /devicedisablewake `"$d`"" }
}
Write-Host "  powercfg /change standby-timeout-ac 0   # at 06:55 UTC daily (AG-V1-Sleep-Never-Start)"
if ($null -ne $currentAcSeconds) {
  $restoreMinutes = [Math]::Round($currentAcSeconds / 60)
  Write-Host "  powercfg /change standby-timeout-ac $restoreMinutes   # at 23:30 UTC daily (AG-V1-Sleep-Never-Restore; restores the CURRENT value captured above)"
} else {
  Write-Host '  (restore command withheld -- current AC standby timeout could not be parsed; -Apply will refuse)'
}

if (-not $Apply) {
  Write-Host ''
  Write-Host 'WhatIf: no changes made. This is a PROPOSAL ONLY per AG_V1_HOST_HARDENING_R1 T3.'
  exit 0
}

if ($env:AG_OWNER_APPROVED_POWER_HARDENING -ne 'YES') {
  Write-Host ''
  Write-Host 'REFUSED: -Apply was given but AG_OWNER_APPROVED_POWER_HARDENING is not set to YES.'
  Write-Host 'Review the plan above. If the owner approves it, set that variable and re-run -Apply.'
  exit 1
}
if ($null -eq $currentAcSeconds) {
  Write-Host 'REFUSED: cannot safely apply -- the current AC standby timeout could not be captured for the restore task.'
  exit 1
}

foreach ($d in $mouseDevices) {
  powercfg /devicedisablewake "$d"
  Write-Host "APPLIED: disabled wake for `"$d`""
}
$restoreMinutes = [Math]::Round($currentAcSeconds / 60)
$startAction = New-ScheduledTaskAction -Execute 'powercfg.exe' -Argument '/change standby-timeout-ac 0'
$restoreAction = New-ScheduledTaskAction -Execute 'powercfg.exe' -Argument "/change standby-timeout-ac $restoreMinutes"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
foreach ($pair in @(
  @{ Name = 'AG-V1-Sleep-Never-Start';   At = '06:55'; Action = $startAction },
  @{ Name = 'AG-V1-Sleep-Never-Restore'; At = '23:30'; Action = $restoreAction }
)) {
  $trigger = New-ScheduledTaskTrigger -Daily -At $pair.At
  if (Get-ScheduledTask -TaskName $pair.Name -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $pair.Name -Confirm:$false }
  Register-ScheduledTask -TaskName $pair.Name -Action $pair.Action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description 'AG_V1_HOST_HARDENING_R1 T3: AC sleep=never during the FX/crypto/LSMC session window.' | Out-Null
  Write-Host "APPLIED: registered scheduled task $($pair.Name)"
}
Write-Host 'RESULT: APPLIED (owner-approved).'
