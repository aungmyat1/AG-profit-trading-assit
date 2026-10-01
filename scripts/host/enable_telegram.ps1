<#
Step 6 (optional) of scripts/host/GO_LIVE.md -- enable message-only Telegram delivery on THIS host.

  # Set these in the session (or as persistent user variables, see below):
  $env:TELEGRAM_BOT_TOKEN = '<token>'; $env:TELEGRAM_CHAT_ID = '<chat id>'
  powershell -ExecutionPolicy Bypass -File scripts\host\enable_telegram.ps1

1. Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment. They are never passed as
   arguments, printed, written to disk or committed.
2. Sends ONE clearly-labelled SIMULATED proposal through the same formatter and Telegram send
   path used by scheduled READY tickets (plain text, no buttons, never archived).
3. Only if the proposal test succeeds, writes the host-local, gitignored config\local\delivery_override.yaml
   (mode MESSAGE_DELIVERY; scopes TICKET_READY and LSMC_OPPORTUNITY).
   - WATCH/INFO alerts and NO_TRADE/DATA_ERROR tickets stay archive-only.
   - The repo default, config\ticket_delivery.yaml (ARCHIVE_ONLY), is not changed.

Disable: delete config\local\delivery_override.yaml.
Scheduled tasks see the two variables only if they are set as persistent USER environment variables:
[Environment]::SetEnvironmentVariable('TELEGRAM_BOT_TOKEN', '<token>', 'User')
#>
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not $env:TELEGRAM_BOT_TOKEN -or -not $env:TELEGRAM_CHAT_ID) {
  Write-Host 'MISSING TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID in the environment. Nothing changed.'
  exit 1
}
$env:PYTHONPATH = (Join-Path $Repo 'src')
& $Python -m host_delivery.telegram_message --test-proposal
if ($LASTEXITCODE -ne 0) { Write-Host 'Proposal validation message failed. Delivery stays ARCHIVE_ONLY.'; exit 1 }
$dir = Join-Path $Repo 'config\local'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
@"
# Host-local override written by scripts/host/enable_telegram.ps1 -- gitignored, never commit.
mode: MESSAGE_DELIVERY
scopes: [TICKET_READY, LSMC_OPPORTUNITY]
"@ | Set-Content -Encoding UTF8 -Path (Join-Path $dir 'delivery_override.yaml')
Write-Host 'Telegram MESSAGE_DELIVERY enabled on this host for READY tickets + Large-SMC OPPORTUNITY alerts only.'
