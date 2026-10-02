<#
Copy the MetaTrader 5 app MCP tokens from src\.env into persistent USER environment variables.

Claude Code expands ${MT5_APP_MCP_TOKEN} / ${METATRADER_MARKETDATA_MCP_TOKEN} in .mcp.json (and
Codex reads bearer_token_env_var) from the process environment only -- never from src\.env.

  powershell -ExecutionPolicy Bypass -File scripts\host\set_mt5_app_mcp_env.ps1

Then fully restart Claude Code / Codex (new terminal). Values are never printed. Afterwards it
reports whether the local MT5 app MCP ports (22345 MetaEditor, 22346 Terminal) accept connections.
#>
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$EnvFile = @((Join-Path $Repo 'src\.env'), (Join-Path $Repo '.env')) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $EnvFile) { Write-Host 'No src\.env or .env found. Nothing changed.'; exit 1 }

$Values = @{}
foreach ($Line in Get-Content -LiteralPath $EnvFile) {
  $Trimmed = $Line.Trim()
  if (-not $Trimmed -or $Trimmed.StartsWith('#')) { continue }
  $Index = $Trimmed.IndexOf('=')
  if ($Index -lt 1) { continue }
  $Value = $Trimmed.Substring($Index + 1).Trim()
  if ($Value.Length -ge 2 -and (($Value.StartsWith('"') -and $Value.EndsWith('"')) -or ($Value.StartsWith("'") -and $Value.EndsWith("'")))) {
    $Value = $Value.Substring(1, $Value.Length - 2)
  }
  $Values[$Trimmed.Substring(0, $Index).Trim()] = $Value
}

$Missing = 0
foreach ($Key in 'MT5_APP_MCP_TOKEN', 'METATRADER_MARKETDATA_MCP_TOKEN') {
  $Value = $Values[$Key]
  if ($Value -and $Value.StartsWith('Bearer ')) { $Value = $Value.Substring(7) }  # .mcp.json adds "Bearer "
  if (-not $Value) { Write-Host "MISSING $Key in $EnvFile"; $Missing++; continue }
  [Environment]::SetEnvironmentVariable($Key, $Value, 'User')
  Write-Host "SET     $Key (user environment, $($Value.Length) chars)"
}

foreach ($Port in 22345, 22346) {
  $Client = New-Object System.Net.Sockets.TcpClient
  try {
    $Open = $Client.ConnectAsync('127.0.0.1', $Port).Wait(2000)
  } catch { $Open = $false } finally { $Client.Dispose() }
  if ($Open) { Write-Host "PORT    127.0.0.1:$Port accepting connections" }
  else { Write-Host "PORT    127.0.0.1:$Port not listening -- open MT5 and enable its MCP servers" }
}
if ($Missing) { exit 1 }
Write-Host 'Done. Restart Claude Code / Codex so the new variables are loaded.'
