<#
AG_PROJECT_READINESS_IMPLEMENTATION_V2 -- readiness validation stage.

A single scriptable gate that runs the readiness checks this project otherwise
performs by hand, prints one result per check plus an overall verdict, and
writes a machine-readable snapshot to artifacts/readiness/latest.json.

SAFETY: this script performs NO trading action. It sends no order, calls no
order_send/order_check, mutates no broker state, and changes no strategy
parameter or authorization flag. It is read-only / build-only throughout.

RESULT STATES
  PASS                   check succeeded
  FAIL                   check failed and is NOT explained by a classified
                         environment gap -- this is what blocks readiness
  SKIP_ENVIRONMENT       check not applicable on this machine (e.g. no MT5)
  KNOWN_ENVIRONMENT_GAP  check failed for a specifically classified,
                         documented environment reason -- never a blanket
                         bucket; only explicitly enumerated checks may use it

Anything unclassified that fails is FAIL. There is no catch-all amnesty.

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_readiness.ps1 -Mode Fast
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_readiness.ps1 -Mode Full

  Fast : repo sanity, frontend deps/typecheck/build/safety-tests/config checks,
         backend pytest --collect-only, focused R0-R4 tests. The routine gate.
  Full : Fast + the complete backend suite + supported environment checks.
         Run once before signing off an R4 status change.
#>

[CmdletBinding()]
param(
    [ValidateSet("Fast", "Full")]
    [string]$Mode = "Fast"
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $RepoRoot "web"
$ReadinessDir = Join-Path $RepoRoot "artifacts/readiness"

$script:results = [System.Collections.Generic.List[object]]::new()
$script:backendStats = [ordered]@{}

function Add-Result {
    param(
        [string]$Name,
        [string]$Group,
        [string]$Status,
        [string]$Detail = ""
    )
    $script:results.Add([PSCustomObject]@{
        Check  = $Name
        Group  = $Group
        Status = $Status
        Detail = $Detail
    })
    $color = switch ($Status) {
        "PASS"                  { "Green" }
        "SKIP_ENVIRONMENT"      { "Yellow" }
        "KNOWN_ENVIRONMENT_GAP" { "Yellow" }
        default                 { "Red" }
    }
    Write-Host ("[{0}] {1}" -f $Status, $Name) -ForegroundColor $color
    if ($Detail) { Write-Host ("       {0}" -f $Detail) -ForegroundColor DarkGray }
}

# Runs a check and records its result. NEVER exits -- a failing check must not
# prevent the remaining checks from running or the summary from printing. This
# was the defect in the original draft of this script.
function Run-Check {
    param(
        [string]$Name,
        [string]$Group,
        [scriptblock]$Block
    )
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    try {
        $global:LASTEXITCODE = 0
        $output = & $Block 2>&1 | Out-String
        if ($output.Trim()) { Write-Host $output.Trim() }
        if ($LASTEXITCODE -ne 0) {
            Add-Result $Name $Group "FAIL" "exit code $LASTEXITCODE"
        } else {
            Add-Result $Name $Group "PASS"
        }
        return $output
    } catch {
        Add-Result $Name $Group "FAIL" ($_.Exception.Message)
        return ""
    }
}

Write-Host "AG READINESS VALIDATION -- mode: $Mode" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

# ---------------------------------------------------------------- repo sanity
Push-Location $RepoRoot

$commit = (& git rev-parse HEAD 2>$null)
if (-not $commit) { $commit = "UNKNOWN" }
$branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
if (-not $branch) { $branch = "UNKNOWN" }

Run-Check "Repo: git metadata resolvable" "repo" {
    if ($commit -eq "UNKNOWN") { throw "not a git checkout" }
    Write-Host "commit=$commit branch=$branch"
} | Out-Null

Run-Check "Repo: python toolchain present" "repo" {
    python --version
} | Out-Null

# --------------------------------------------------------------- frontend
Push-Location $WebDir

Run-Check "Frontend: dependencies installed" "frontend" {
    if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
    else { Write-Host "node_modules present" }
} | Out-Null

Run-Check "Frontend: typecheck (tsc --noEmit)" "frontend" {
    npx tsc --noEmit
} | Out-Null

Run-Check "Frontend: production build" "frontend" {
    npm run build
} | Out-Null

# Static execution-containment + proposal-authority tests. These are safety
# gates, not cosmetics: they prove the frontend cannot reach broker execution.
Run-Check "Frontend: safety tests (execution containment, proposal authority)" "frontend" {
    npm test
} | Out-Null

Run-Check "Frontend: API mode / base URL configuration" "frontend" {
    if (-not (Test-Path ".env.example")) { throw ".env.example missing" }
    $example = Get-Content ".env.example" -Raw
    foreach ($key in @("VITE_API_BASE_URL", "VITE_AG_API_MODE")) {
        if ($example -notmatch [regex]::Escape($key)) { throw "$key absent from .env.example" }
    }
    Write-Host "VITE_API_BASE_URL and VITE_AG_API_MODE documented in .env.example"
} | Out-Null

# The frontend is a renderer. It must never import an execution/broker surface.
Run-Check "Frontend: no direct MT5 / execution / Telegram imports in src" "frontend" {
    # Look for real CALL/IMPORT syntax, not bare identifiers. Legacy mock
    # components (BrokerConnectionModal.tsx) and src/types/trading.ts contain
    # `allow_order_send:` / `order_check_subsystem` as object keys and display
    # strings -- inert data in a mock panel, not an execution path. Matching bare
    # substrings would flag those forever and train the reader to ignore this gate.
    $files = Get-ChildItem -Path "src" -Recurse -Include *.ts, *.tsx -ErrorAction SilentlyContinue
    $hits = $files | Select-String -Pattern @(
        "order_send\s*\(",
        "order_check\s*\(",
        "from\s+['`"]MetaTrader5",
        "require\(\s*['`"]MetaTrader5",
        "execution\.executor"
    ) -ErrorAction SilentlyContinue
    if ($hits) {
        $hits | ForEach-Object { Write-Host ("{0}:{1}: {2}" -f $_.Filename, $_.LineNumber, $_.Line.Trim()) }
        throw "frontend source invokes an execution/broker surface directly"
    }
    Write-Host "no direct execution/broker invocation in web/src ($($files.Count) files scanned)"
} | Out-Null

Pop-Location

# ---------------------------------------------------------------- backend
Push-Location $RepoRoot

Run-Check "Backend: collection has zero errors" "backend" {
    $out = python -m pytest tests/ -q --collect-only 2>&1 | Out-String
    # Match pytest's explicit collection-error summary ONLY. A bare /error/ match
    # is wrong here: ~49 legitimate test NAMES contain the word "error"
    # (test_data_error_increments_error_days_not_valid, ...) and would produce a
    # permanent false FAIL.
    if ($out -match "errors? during collection" -or $out -match "^ERROR ") {
        Write-Host ($out -split "`n" | Select-Object -Last 15)
        throw "collection reported errors"
    }
    if ($out -match "(\d+) tests collected") {
        Write-Host "collected $($Matches[1]) tests, 0 errors"
    }
} | Out-Null

# Focused R0-R4 gate tests: the canonical pipeline, proposal identity, the
# execution boundary, and the fail-closed market-data guards.
$focused = @(
    "tests/test_proposal_envelope_execution_boundary.py",
    "tests/test_pipeline_canonical_wiring.py",
    "tests/test_bias_provenance_e2e.py",
    "tests/test_api.py",
    "tests/test_market_data_readiness_scanner.py"
) | Where-Object { Test-Path (Join-Path $RepoRoot $_) }

Run-Check "Backend: focused R0-R4 gate tests" "backend" {
    python -m pytest @focused -q
} | Out-Null

if ($Mode -eq "Full") {
    Write-Host ""
    Write-Host "== Backend: full suite (mode=Full) ==" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    $fullOut = python -m pytest tests/ -q 2>&1 | Out-String
    $fullExit = $LASTEXITCODE
    Write-Host ($fullOut -split "`n" | Select-Object -Last 25)

    foreach ($key in @("passed", "failed", "error", "skipped", "deselected")) {
        if ($fullOut -match "(\d+) $key") { $script:backendStats[$key] = [int]$Matches[1] }
        else { $script:backendStats[$key] = 0 }
    }
    if ($fullOut -match "in ([\d.]+)s") { $script:backendStats["duration_seconds"] = [double]$Matches[1] }

    if ($fullExit -eq 0) {
        Add-Result "Backend: full suite" "backend" "PASS" (
            "$($script:backendStats.passed) passed, $($script:backendStats.skipped) skipped")
    } else {
        Add-Result "Backend: full suite" "backend" "FAIL" (
            "$($script:backendStats.failed) failed, $($script:backendStats.error) error, " +
            "$($script:backendStats.passed) passed -- every failure must be explicitly " +
            "classified before R4 sign-off; unclassified failures are blockers")
    }
} else {
    Add-Result "Backend: full suite" "backend" "SKIP_ENVIRONMENT" "not run in Fast mode"
}

# ---------------------------------------------------------------- summary
Write-Host ""
Write-Host "===== READINESS VALIDATION SUMMARY ($Mode) =====" -ForegroundColor Cyan
$script:results | Format-Table Group, Status, Check -AutoSize

$failed = @($script:results | Where-Object { $_.Status -eq "FAIL" })
$overall = if ($failed.Count -eq 0) { "PASS" } else { "FAIL" }

# unexplained_failures: FAILs that no classification accounts for. The target
# for a baseline freeze is an empty list -- not zero failures, but zero
# failures nobody can explain.
$unexplained = @($failed | ForEach-Object { $_.Check })

$snapshot = [ordered]@{
    schema_version = "1.0.0"
    artifact_id    = "AG_READINESS_VALIDATION_V2"
    timestamp_utc  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.ffffffK")
    commit         = $commit
    branch         = $branch
    mode           = $Mode
    overall        = $overall
    frontend       = [ordered]@{}
    backend        = [ordered]@{}
    r4             = [ordered]@{}
    checks         = @($script:results)
    unexplained_failures = $unexplained
    safety = [ordered]@{
        orders_submitted            = 0
        broker_mutation_attempted   = $false
        strategy_parameters_changed = $false
        authority_changed           = $false
    }
}
foreach ($r in $script:results) {
    if ($r.Group -eq "frontend") { $snapshot.frontend[$r.Check] = $r.Status }
    if ($r.Group -eq "backend")  { $snapshot.backend[$r.Check]  = $r.Status }
}
if ($script:backendStats.Count -gt 0) { $snapshot.backend["full_suite_stats"] = $script:backendStats }
$snapshot.r4["validated_mode"] = $Mode
$snapshot.r4["execution_containment"] = (
    ($script:results | Where-Object { $_.Check -like "*safety tests*" }).Status
)

if (-not (Test-Path $ReadinessDir)) { New-Item -ItemType Directory -Path $ReadinessDir -Force | Out-Null }
$latest = Join-Path $ReadinessDir "latest.json"
$snapshot | ConvertTo-Json -Depth 8 | Set-Content -Path $latest -Encoding utf8
Write-Host "Snapshot written: $latest" -ForegroundColor DarkGray

if ($overall -eq "PASS") {
    Write-Host "OVERALL: PASS -- all checks green ($Mode mode)." -ForegroundColor Green
} else {
    Write-Host "OVERALL: FAIL -- $($failed.Count) check(s) failed. See table above." -ForegroundColor Red
}

Pop-Location
Pop-Location

# Only the final overall verdict sets the exit code. Individual checks never exit.
if ($overall -eq "PASS") { exit 0 } else { exit 1 }
