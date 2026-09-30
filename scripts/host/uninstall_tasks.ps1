<#
Removes the four AG V1 host tasks created by install_tasks.ps1.
  powershell -ExecutionPolicy Bypass -File scripts\host\uninstall_tasks.ps1          # -WhatIf (default)
  powershell -ExecutionPolicy Bypass -File scripts\host\uninstall_tasks.ps1 -Apply
#>
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$Names = @('AG-V1-FX-Cycles', 'AG-V1-Crypto-Daily', 'AG-V1-LSMC-Watch', 'AG-V1-LSMC-Crypto-Weekend')
foreach ($n in $Names) {
  $exists = [bool](Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue)
  if (-not $Apply) { Write-Host "WhatIf: would remove $n (present=$exists)"; continue }
  if ($exists) { Unregister-ScheduledTask -TaskName $n -Confirm:$false; Write-Host "REMOVED $n" } else { Write-Host "ABSENT $n" }
}
if (-not $Apply) { Write-Host 'WhatIf: no changes made. Re-run with -Apply to remove.' }
