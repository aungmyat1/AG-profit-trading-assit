<#
    setup_mbt.ps1 — one MT5 MCP, cleanly installed.

    WHAT IT DOES
      Part 1 (needs Administrator)
        - moves MBT out of C:\Windows\System32 into your profile
        - quarantines the MQL5 files the installer scattered into BOTH terminals
          (this project has no MQL5 indicator, so SignalLogger.mqh and the
           MBT_IndicatorHost EA are not needed — and an EA sitting in \Experts is
           one toggle away from being able to trade)
      Part 2 (normal user, NOT admin)
        - writes MBT config.yaml pointing at the terminal you actually trade
        - rewrites claude_desktop_config.json to hold exactly ONE MT5 server: mbt
        - removes the dead "metatrader" server that has been returning Not connected

    NOTHING IS DELETED. Removed files move to a dated _quarantine folder and the
    Claude config is backed up before it is touched.

    RUN
        # 1. right-click PowerShell -> Run as Administrator
        powershell -ExecutionPolicy Bypass -File .\setup_mbt.ps1 -Part 1

        # 2. close that window. open a NORMAL PowerShell
        powershell -ExecutionPolicy Bypass -File .\setup_mbt.ps1 -Part 2
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('1', '2')] [string] $Part,
    [string] $Dest      = "$env:USERPROFILE\MBT",
    [string] $Source    = "C:\Windows\System32\MBT",
    [string] $TerminalId = ""          # leave blank to auto-detect
)

$ErrorActionPreference = 'Stop'
$MQ    = "$env:APPDATA\MetaQuotes\Terminal"
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Say  ($m) { Write-Host "  $m" }
function Head ($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Warn ($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Good ($m) { Write-Host "  + $m" -ForegroundColor Green }

function Get-Terminals {
    <#  Identifies each terminal by READING ITS LOGS, not by guessing from file
        timestamps.  MT5 writes the account and server into the journal on every
        login, so the right terminal names itself.

        This matters: the old 'metatrader' MCP was attached to the WRONG terminal
        the whole time — it answered "Symbol 'EURUSD' not found" while a chart
        titled "EURUSD, M15" sat open in the other one.  A wrong-terminal
        connection returns real-looking data from an account you are not trading. #>
    Get-ChildItem $MQ -Directory -EA SilentlyContinue |
        Where-Object { $_.Name -match '^[0-9A-F]{32}$' } |
        ForEach-Object {
            $log = Join-Path $_.FullName 'logs'
            $last = $null; $acct = $null; $server = $null; $symbols = 0
            if (Test-Path $log) {
                $newest = Get-ChildItem $log -Filter *.log -EA SilentlyContinue |
                          Sort-Object LastWriteTime -Desc | Select-Object -First 3
                if ($newest) { $last = $newest[0].LastWriteTime }
                foreach ($f in $newest) {
                    foreach ($line in (Get-Content $f.FullName -Tail 4000 -EA SilentlyContinue)) {
                        # e.g.  "'1144985': authorized on VTMarkets-Demo"
                        if (-not $acct -and $line -match "'(\d{5,})'.*authorized on ([^\s]+)") {
                            $acct = $Matches[1]; $server = $Matches[2]
                        }
                    }
                    if ($acct) { break }
                }
            }
            # a terminal with no symbol cache has nothing the API can find
            $bases = Join-Path $_.FullName 'bases'
            if (Test-Path $bases) {
                $symbols = (Get-ChildItem $bases -Recurse -Filter *.sel -EA SilentlyContinue |
                            Measure-Object).Count
            }
            [pscustomobject]@{
                Id = $_.Name; Path = $_.FullName; LastLog = $last
                Account = $acct; Server = $server; SymbolFiles = $symbols
            }
        } | Sort-Object LastLog -Descending
}

# ────────────────────────────────────────────────────────────── PART 1 ──
if ($Part -eq '1') {
    $admin = ([Security.Principal.WindowsPrincipal] `
              [Security.Principal.WindowsIdentity]::GetCurrent()
             ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { Warn "Part 1 must run as Administrator (it touches System32). Stopping."; exit 1 }

    Head "Move MBT out of System32"
    if (Test-Path $Source) {
        if (Test-Path $Dest) { Warn "$Dest already exists — leaving both, merge by hand." }
        else { Move-Item $Source $Dest; Good "moved -> $Dest" }
    } elseif (Test-Path $Dest) { Say "already at $Dest — nothing to move" }
    else { Warn "MBT found in neither location." }

    Head "Quarantine the MQL5 files the installer copied"
    $q = "$env:USERPROFILE\_MBT_quarantine_$Stamp"
    $targets = @('MQL5\Include\SignalLogger.mqh',
                 'MQL5\Experts\MBT_IndicatorHost.mq5',
                 'MQL5\Experts\MBT_IndicatorHost.ex5')
    $moved = 0
    foreach ($t in Get-Terminals) {
        foreach ($rel in $targets) {
            $f = Join-Path $t.Path $rel
            if (Test-Path $f) {
                $to = Join-Path $q "$($t.Id)\$(Split-Path $rel -Parent)"
                New-Item $to -ItemType Directory -Force | Out-Null
                Move-Item $f $to -Force; $moved++
                Say "$($t.Id.Substring(0,8))…  $rel"
            }
        }
    }
    if ($moved) { Good "$moved file(s) -> $q  (restore from there if ever needed)" }
    else        { Say  "nothing to quarantine" }

    Write-Host "`nPart 1 done. Close this window and run Part 2 in a NORMAL PowerShell.`n" -ForegroundColor Green
    exit 0
}

# ────────────────────────────────────────────────────────────── PART 2 ──
Head "Terminals found — identified from their own logs"
$terms = Get-Terminals
if (-not $terms) { Warn "No MT5 terminal data folders under $MQ"; exit 1 }
foreach ($t in $terms) {
    $who = if ($t.Account) { "account $($t.Account) on $($t.Server)" } else { "NO LOGIN FOUND" }
    Say ("{0}   {1}" -f $t.Id, $who)
    Say ("{0}   last log {1} · {2} symbol file(s)" -f (' ' * 32),
         $(if ($t.LastLog) { $t.LastLog.ToString('yyyy-MM-dd HH:mm') } else { 'never' }),
         $t.SymbolFiles)
}
if (-not $TerminalId) {
    # prefer a terminal that has actually logged in AND has a symbol cache
    $best = $terms | Where-Object { $_.Account -and $_.SymbolFiles -gt 0 } | Select-Object -First 1
    if (-not $best) { $best = $terms | Where-Object Account | Select-Object -First 1 }
    if (-not $best) {
        Warn "No terminal shows a completed login. Open MT5, log in, then re-run."
        Warn "Override manually with -TerminalId <ID> if you are sure."
        exit 1
    }
    $TerminalId = $best.Id
}
$term = $terms | Where-Object Id -eq $TerminalId
if (-not $term) { Warn "TerminalId $TerminalId not found."; exit 1 }
if (-not $term.Account)      { Warn "selected terminal shows no login — data calls will fail" }
if ($term.SymbolFiles -eq 0) { Warn "selected terminal has an empty symbol cache — 'Symbol not found' errors will follow" }
Good "using $TerminalId  ($($term.Account) on $($term.Server))"

Head "MBT config.yaml"
if (-not (Test-Path $Dest)) { Warn "MBT not at $Dest — run Part 1 first."; exit 1 }
$mt5exe = @("$env:ProgramFiles\MetaTrader 5\terminal64.exe",
            "${env:ProgramFiles(x86)}\MetaTrader 5\terminal64.exe") |
          Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $mt5exe) { Warn "terminal64.exe not found in Program Files — set mt5_path by hand." }

$cfg = Join-Path $Dest 'config.yaml'
$sig = Join-Path $term.Path 'MQL5\Files\mbt_signals.csv'
@"
# written by setup_mbt.ps1 on $(Get-Date -Format 'yyyy-MM-dd HH:mm')
mt5_path: "$($mt5exe -replace '\\','\\')"
signal_file: "$($sig -replace '\\','\\')"
default_symbol: EURUSD
default_timeframe: M15
"@ | Set-Content $cfg -Encoding UTF8
Good "wrote $cfg"

Head "Claude Desktop config — exactly one MT5 server"
$cc = "$env:APPDATA\Claude\claude_desktop_config.json"
if (-not (Test-Path $cc)) { Warn "$cc not found."; exit 1 }
Copy-Item $cc "$cc.bak-$Stamp"; Good "backup -> $cc.bak-$Stamp"

$j = Get-Content $cc -Raw | ConvertFrom-Json
if (-not $j.mcpServers) { $j | Add-Member mcpServers ([pscustomobject]@{}) -Force }

foreach ($dead in @('metatrader', 'mtx', 'MTX')) {
    if ($j.mcpServers.PSObject.Properties.Name -contains $dead) {
        $j.mcpServers.PSObject.Properties.Remove($dead); Good "removed '$dead'"
    }
}
$j.mcpServers | Add-Member mbt ([pscustomobject]@{
    command = 'python'
    args    = @((Join-Path $Dest 'mcp_server.py'))
}) -Force
$j | ConvertTo-Json -Depth 100 | Set-Content $cc -Encoding UTF8
Good "mcpServers now: $($j.mcpServers.PSObject.Properties.Name -join ', ')"

Head "Live verification — prove the connection BEFORE trusting it"
$py = @"
import sys
try:
    import MetaTrader5 as mt5
except ImportError:
    print('SKIP  MetaTrader5 package not installed for this interpreter'); sys.exit(0)
if not mt5.initialize():
    print('FAIL  initialize():', mt5.last_error()); sys.exit(1)
i = mt5.account_info()
print(f'OK    attached to {i.login} on {i.server}  ({i.currency} {i.balance:.2f})' if i
      else 'FAIL  no account_info - terminal not logged in')
n = len(mt5.symbols_get() or [])
print(f'OK    {n} symbols visible' if n else 'FAIL  0 symbols - nothing the API can read')
for s in ('EURUSD','XAUUSD','XAUUSD.crp'):
    if mt5.symbol_info(s): print(f'OK    symbol {s} resolves')
r = mt5.copy_rates_from_pos('EURUSD', mt5.TIMEFRAME_M15, 0, 1)
if r is None or not len(r):
    print('WARN  no EURUSD M15 bars - check Market Watch (right-click -> Show All)')
else:
    import datetime as dt
    t = dt.datetime.utcfromtimestamp(int(r[0]['time']))
    age = (dt.datetime.utcnow() - t).total_seconds()/3600
    print(f'OK    newest EURUSD M15 bar {t} (server clock), {age:+.1f}h from UTC now')
    print('      a large offset here is the broker timezone, not an error')
mt5.shutdown()
"@
$tmp = Join-Path $env:TEMP "mbt_verify_$Stamp.py"
$py | Set-Content $tmp -Encoding UTF8
try { python $tmp } catch { Warn "python not on PATH - skipped live check" }
Remove-Item $tmp -EA SilentlyContinue

Head "Next"
Say "1. Fully quit Claude Desktop (tray icon -> Quit), then reopen it."
Say "2. Start a NEW conversation. MCP servers load per session - an app"
Say "   restart alone will not expose 'mbt' to an existing chat."
Say "3. Ask: 'the last 10 M15 candles for EURUSD'"
Say "4. Leave 'Allow algorithmic trading' OFF in MT5. MBT does not need it."
Say "5. Keep MT5 open and logged in. Neither server can start it for you."
Say ""
Say "Not installed, deliberately: MTX (the trade executor). This desk is analysis-only."
Write-Host ""
