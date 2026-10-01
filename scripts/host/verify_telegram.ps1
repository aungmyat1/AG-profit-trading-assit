<#
Validate Telegram proposal reporting on the Windows MT5 host.
Read-only except for sending one clearly-labelled SIMULATED validation proposal.
No token or chat ID is printed or written to disk.

  powershell -ExecutionPolicy Bypass -File scripts\host\verify_telegram.ps1
#>
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
  Write-Host "MISSING venv python: $Python"
  exit 1
}
if (-not $env:TELEGRAM_BOT_TOKEN -or -not $env:TELEGRAM_CHAT_ID) {
  Write-Host 'TELEGRAM_STATUS: NOT_READY credentials=MISSING. No message sent.'
  exit 1
}
$env:PYTHONPATH = (Join-Path $Repo 'src')
Push-Location $Repo
try {
  & $Python -m host_delivery.telegram_message --status
  if ($LASTEXITCODE -ne 0) {
    Write-Host 'Telegram host-local delivery override is not enabled. Run enable_telegram.ps1 first.'
    exit 1
  }
  & $Python -m host_delivery.telegram_message --test-proposal
  if ($LASTEXITCODE -ne 0) { exit 1 }
  Write-Host 'RESULT: PASS -- simulated proposal rendered and accepted by Telegram.'
} finally {
  Pop-Location
}
