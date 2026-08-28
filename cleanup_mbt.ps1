<#
    cleanup_mbt.ps1 — remove MBT, keep the working 'metatrader' MCP.

    DECISION (2026-08-17)
      The existing 'metatrader' MCP works. It returns account state and OHLC:
          account 1144985 · balance 987.82 USD
          EURUSD M15 2026-08-17 07:45  1.15866 / 1.15869 / 1.15861 / 1.15866
      Every failure earlier in the session was MetaTrader 5 being CLOSED, not a
      configuration fault. MBT was installed to solve a problem that did not exist,
      and its extra capability — EA compilation, Strategy Tester driving — is not
      used by this project.

    WHAT THIS DOES
      - quarantines C:\Windows\System32\MBT   (an installer landed it there because
        PowerShell was elevated; System32 is not a place for a user project)
      - quarantines SignalLogger.mqh and MBT_IndicatorHost.mq5/.ex5 from EVERY
        MT5 terminal profile.  The .mq5 is an Expert Advisor: an EA sitting in
        \Experts is one "Allow algorithmic trading" toggle away from being able
        to trade, and this desk is analysis-only.
      - leaves claude_desktop_config.json ALONE. 'metatrader' stays.
      - verifies the MT5 connection still works afterwards.

    NOTHING IS DELETED. Everything moves to a dated _MBT_quarantine folder.
    Delete that folder yourself once you are satisfied.

    RUN  (right-click PowerShell -> Run as Administrator)
        powershell -ExecutionPolicy Bypass -File .\cleanup_mbt.ps1
#>
[CmdletBinding()]
param(
    [switch] $WhatIfOnly,
    [string] $Source = "C:\Windows\System32\MBT"
)

$ErrorActionPreference = 'Stop'
$MQ    = "$env:APPDATA\MetaQuotes\Terminal"
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Q     = "$env:USERPROFILE\_MBT_quarantine_$Stamp"

function Say  ($m) { Write-Host "  $m" }
function Head ($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Warn ($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Good ($m) { Write-Host "  + $m" -ForegroundColor Green }

$admin = ([Security.Principal.WindowsPrincipal] `
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and (Test-Path $Source)) {
    Warn "MBT is in System32 — this must run as Administrator to move it. Stopping."
    exit 1
}
if ($WhatIfOnly) { Warn "DRY RUN — nothing will be moved." }

function Move-ToQuarantine ($path, $label) {
    if (-not (Test-Path $path)) { return $false }
    $to = Join-Path $Q $label
    if ($WhatIfOnly) { Say "would move  $path"; return $true }
    New-Item (Split-Path $to -Parent) -ItemType Directory -Force | Out-Null
    Move-Item $path $to -Force
    Say "moved  $path"
    return $true
}

Head "1. MBT install directory"
$n = 0
foreach ($p in @($Source, "$env:USERPROFILE\MBT")) {
    if (Move-ToQuarantine $p ("install\" + (Split-Path $p -Leaf) + "_" + ($p -replace '[:\\]','_'))) { $n++ }
}
if (-not $n) { Say "no MBT install directory found" }

Head "2. MQL5 artifacts, every terminal profile"
$targets = @('MQL5\Include\SignalLogger.mqh',
             'MQL5\Experts\MBT_IndicatorHost.mq5',
             'MQL5\Experts\MBT_IndicatorHost.ex5')
$m = 0
$terms = Get-ChildItem $MQ -Directory -EA SilentlyContinue |
         Where-Object { $_.Name -match '^[0-9A-F]{32}$' }
if (-not $terms) { Warn "no MT5 terminal folders under $MQ" }
foreach ($t in $terms) {
    foreach ($rel in $targets) {
        if (Move-ToQuarantine (Join-Path $t.FullName $rel) "$($t.Name)\$rel") { $m++ }
    }
}
Say "$m file(s) removed from $($terms.Count) terminal profile(s)"

Head "3. Claude config — untouched by design"
$cc = "$env:APPDATA\Claude\claude_desktop_config.json"
if (Test-Path $cc) {
    $names = (Get-Content $cc -Raw | ConvertFrom-Json).mcpServers.PSObject.Properties.Name
    Say "mcpServers: $($names -join ', ')"
    if ($names -contains 'mbt')  { Warn "'mbt' is registered but its files are now quarantined — remove that key by hand" }
    if ($names -contains 'mtx')  { Warn "'mtx' is an EXECUTION server and should not be here — remove that key by hand" }
    if ($names -contains 'metatrader') { Good "'metatrader' present — this is the one being kept" }
} else { Warn "$cc not found" }

Head "4. Verify the MT5 connection still works"
$py = @"
import sys, datetime as dt
try:
    import MetaTrader5 as mt5
except ImportError:
    print('SKIP  MetaTrader5 package not installed for this interpreter'); sys.exit(0)
if not mt5.initialize():
    print('FAIL  initialize():', mt5.last_error())
    print('      >>> Is MetaTrader 5 OPEN and logged in? That was the whole issue.')
    sys.exit(1)
i = mt5.account_info()
print(f'OK    {i.login} on {i.server}  {i.currency} {i.balance:.2f}' if i else 'FAIL  no account_info')
print(f'OK    {len(mt5.symbols_get() or [])} symbols visible')
r = mt5.copy_rates_from_pos('EURUSD', mt5.TIMEFRAME_M15, 0, 1)
if r is None or not len(r):
    print('WARN  no EURUSD M15 bars — check Market Watch (right-click -> Show All)')
else:
    t = dt.datetime.utcfromtimestamp(int(r[0]['time']))
    print(f'OK    newest EURUSD M15 bar {t} (server clock)')
mt5.shutdown()
"@
$tmp = Join-Path $env:TEMP "mt5_verify_$Stamp.py"
$py | Set-Content $tmp -Encoding UTF8
try { python $tmp } catch { Warn "python not on PATH — skipped" }
Remove-Item $tmp -EA SilentlyContinue

Head "Done"
if (-not $WhatIfOnly -and (Test-Path $Q)) { Say "quarantine: $Q" ; Say "delete it yourself once satisfied" }
Say ""
Say "KEPT     : metatrader MCP  (working)"
Say "REMOVED  : MBT install + its MQL5 include and host EA"
Say "NEVER    : MTX trade executor. This desk is analysis-only."
Say ""
Say "Keep MetaTrader 5 open and logged in whenever you want the MCP to answer."
Write-Host ""
