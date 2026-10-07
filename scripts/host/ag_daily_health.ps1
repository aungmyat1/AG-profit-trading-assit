<#
.SYNOPSIS
  AG V1 daily health snapshot (read-only). Writes one JSON per UTC day.

.DESCRIPTION
  Reads git state, AG-* scheduled task results, logs and journal file names. It never
  writes inside the repo/runtime tree, never touches MT5, Telegram or scheduled tasks.
  git is run with --no-optional-locks so not even the index is refreshed.

.PARAMETER RepoRoot   Runtime tree to inspect (default D:\wp3-main-integ).
.PARAMETER OutDir     Output directory (default %LOCALAPPDATA%\AG\health -- outside tracked files).
.PARAMETER Date       UTC date yyyy-MM-dd to report (default: today UTC).
#>
param(
    [string]$RepoRoot = "D:\wp3-main-integ",
    [string]$OutDir = (Join-Path $env:LOCALAPPDATA "AG\health"),
    [string]$Date = ((Get-Date).ToUniversalTime().ToString("yyyy-MM-dd"))
)
$ErrorActionPreference = "Stop"

$repoFull = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\') + '\'
$outFull = [IO.Path]::GetFullPath($OutDir).TrimEnd('\') + '\'
if ($outFull.StartsWith($repoFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutDir must be outside the runtime tree ($RepoRoot)"
}

function DayLines([string]$path) {
    # Log lines start with an ISO UTC timestamp; keep only the requested day.
    if (-not (Test-Path $path)) { return @() }
    return @(Get-Content -LiteralPath $path | Where-Object { $_.StartsWith($Date) })
}

$logs = Join-Path $RepoRoot "logs"
$journal = Join-Path $RepoRoot "journal"

# git
$head = (git -C $RepoRoot rev-parse HEAD).Trim()
$porcelain = @(git --no-optional-locks -C $RepoRoot status --porcelain)

# scheduled tasks
$tasks = @(Get-ScheduledTask -TaskName "AG-*" -ErrorAction SilentlyContinue | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    [ordered]@{ name = $_.TaskName; state = "$($_.State)"; last_run = $i.LastRunTime.ToUniversalTime().ToString("o");
                last_result = $i.LastTaskResult; next_run = if ($i.NextRunTime) { $i.NextRunTime.ToUniversalTime().ToString("o") } else { $null } }
})

# FX decisions (decision=<token>, never bare tokens)
$fx = [ordered]@{}
foreach ($l in (DayLines (Join-Path $logs "ag_v1_fx.log"))) {
    if ($l -match 'decision=(\S+)') { $k = $Matches[1]; if ($fx.Contains($k)) { $fx[$k]++ } else { $fx[$k] = 1 } }
}

# Large-SMC alerts actually sent, and delivery-layer duplicate suppressions
$tg = DayLines (Join-Path $logs "telegram.log")
$lsmcSent = @($tg | Where-Object { $_ -match 'TELEGRAM_SENT_OK LSMC=' }).Count
$lsmcSuppressed = @(DayLines (Join-Path $logs "ag_v1_lsmc.log") | Where-Object { $_ -match 'ALERT_SUPPRESSED_DUPLICATE_CONFIRMATION' }).Count

# archive / paper files for the day, grouped by anchor
$groups = [ordered]@{}
if (Test-Path $journal) {
    Get-ChildItem -LiteralPath $journal -Recurse -File | Where-Object { $_.Name -like "*$Date*" } | ForEach-Object {
        $parts = $_.FullName.Substring($journal.Length).TrimStart('\').Split('\')
        $idx = -1
        for ($n = 0; $n -lt $parts.Length; $n++) {
            if ($parts[$n] -ieq "fx_ticket_archive" -or $parts[$n] -ieq "paper_trades") { $idx = $n; break }
        }
        if ($idx -ge 0 -and $parts.Length -gt $idx + 3) { $key = ($parts[$idx..($idx + 2)] -join '/') }
        else { $key = ($parts[0..([Math]::Min(1, $parts.Length - 2))] -join '/') }
        if ($groups.Contains($key)) { $groups[$key]++ } else { $groups[$key] = 1 }
    }
}

# errors and order-path markers across all AG logs for the day
$errors = 0; $orders = 0
Get-ChildItem -LiteralPath $logs -Filter "*.log" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $day = DayLines $_.FullName
    $errors += @($day | Where-Object { $_ -match 'ERROR|Traceback' }).Count
    $orders += @($day | Where-Object { $_ -match 'order_send|ORDER_SENT' }).Count
}

$report = [ordered]@{
    schema = "AG_DAILY_HEALTH_V1"; date_utc = $Date; generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    head_sha = $head; git_clean = ($porcelain.Count -eq 0); git_dirty_entries = $porcelain.Count
    tasks = $tasks; fx_decisions = $fx; lsmc_alerts_sent = $lsmcSent
    lsmc_duplicates_suppressed = $lsmcSuppressed; archive_counts = $groups
    error_lines = $errors; order_send_lines = $orders
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$path = Join-Path $OutDir "ag_health_$Date.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $path -Encoding UTF8
Write-Output $path
