<#
AG_V1_HOST_HARDENING_R1 T3 -- read-only Windows power/wake report.

  powershell -ExecutionPolicy Bypass -File scripts\host\report_power_settings.ps1

Runs exactly two read-only `powercfg` queries:
  powercfg /lastwake              -- what woke the machine last time it resumed
  powercfg /devicequery wake_armed -- every device currently allowed to wake the machine

Nothing is changed. No scheduled task, device setting, or power scheme is touched here --
see propose_power_hardening.ps1 (also report-only by default; it never applies anything
without an explicit, separate owner-approval gate -- see its own header).

Output is written to a timestamped file under the same host-wide, OUTSIDE-the-checkout
location this kit already uses for cross-checkout state (%ProgramData%\AG\reports, or
$env:AG_HOST_REPORT_DIR when set) and also printed to the console.
#>
$ErrorActionPreference = 'Stop'

$ReportDir = if ($env:AG_HOST_REPORT_DIR) { $env:AG_HOST_REPORT_DIR } else { Join-Path $env:ProgramData 'AG\reports' }
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutFile = Join-Path $ReportDir "power_report_$Stamp.txt"

function Write-Section($title, $scriptBlock) {
  "=== $title ===" | Tee-Object -FilePath $OutFile -Append | Write-Host
  try {
    $output = & $scriptBlock 2>&1
  } catch {
    $output = "ERROR: $_"
  }
  $output | Tee-Object -FilePath $OutFile -Append | Write-Host
}

"AG power report -- $Stamp UTC-local host time" | Tee-Object -FilePath $OutFile | Write-Host
Write-Section 'powercfg /lastwake' { powercfg /lastwake }
Write-Section 'powercfg /devicequery wake_armed' { powercfg /devicequery wake_armed }

Write-Host ""
Write-Host "RESULT: REPORT_WRITTEN $OutFile"
