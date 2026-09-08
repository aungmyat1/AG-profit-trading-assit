# AG Profit Trading -- lightweight daily development runtime
# (AG_FRONTEND_RUNTIME_VERIFICATION_AND_LOCAL_TEST_V1). Starts FastAPI (127.0.0.1:8000)
# and the Vite frontend (localhost:3000) as separate PowerShell jobs, prints the URLs,
# and does NOT touch MT5 -- MT5 stays an external application the operator
# starts/logs into themselves. No broker order is submitted by this script.
#
# This script does NOT install dependencies. Run scripts/setup_dev.ps1 once first
# (or whenever web/package.json changes).

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $RepoRoot "web"

Write-Host ""
Write-Host "AG Profit Trading -- Development Runtime" -ForegroundColor Cyan
Write-Host "=========================================="
Write-Host ""

# 1. Verify Python
try {
    $pythonVersion = (python --version) 2>&1
    Write-Host "Python: $pythonVersion"
} catch {
    Write-Host "ERROR: python not found on PATH." -ForegroundColor Red
    exit 1
}

# 2. Verify Node
try {
    $nodeVersion = (node --version) 2>&1
    Write-Host "Node: $nodeVersion"
} catch {
    Write-Host "ERROR: node not found on PATH." -ForegroundColor Red
    exit 1
}

# 3. Verify frontend dependencies exist -- do NOT install here
if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
    Write-Host ""
    Write-Host "Frontend dependencies missing." -ForegroundColor Red
    Write-Host "Run:" -ForegroundColor Yellow
    Write-Host "  .\scripts\setup_dev.ps1"
    Write-Host ""
    exit 1
}

# 4. Pick the same package manager setup_dev.ps1 would have used, for `npm run dev` /
# `bun run dev` consistency (Bun preferred if available, since web/bun.lock is present).
$bunAvailable = $false
try {
    $null = (bun --version) 2>&1
    if ($LASTEXITCODE -eq 0) { $bunAvailable = $true }
} catch {}

# 5. Start FastAPI (background job)
Write-Host ""
Write-Host "Starting FastAPI on http://127.0.0.1:8000 ..." -ForegroundColor Green
$apiJob = Start-Job -Name "AG-API" -ScriptBlock {
    param($repoRoot)
    Set-Location $repoRoot
    python scripts/run_api.py --host 127.0.0.1 --port 8000
} -ArgumentList $RepoRoot

# 6. Start Vite (background job)
Write-Host "Starting Vite frontend on http://localhost:3000 ..." -ForegroundColor Green
$viteJob = Start-Job -Name "AG-Vite" -ScriptBlock {
    param($webDir, $useBun)
    Set-Location $webDir
    if ($useBun) { bun run dev } else { npm run dev }
} -ArgumentList $WebDir, $bunAvailable

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Backend:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8000"
Write-Host ""
Write-Host "API docs:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8000/docs"
Write-Host ""
Write-Host "Frontend:" -ForegroundColor Cyan
Write-Host "  http://localhost:3000"
Write-Host ""
Write-Host "Environment: DEVELOPMENT" -ForegroundColor Yellow
Write-Host "Broker execution: NO AUTOMATIC ORDER EXECUTION" -ForegroundColor Yellow
Write-Host ""
Write-Host "Verify with: python scripts/test_dev_connection.py"
Write-Host "Press Ctrl+C to stop, or close this window (background jobs AG-API / AG-Vite)."
Write-Host ""

# Stream both jobs' output until the operator interrupts.
try {
    while ($true) {
        Receive-Job -Job $apiJob, $viteJob
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host ""
    Write-Host "Stopping AG-API / AG-Vite jobs..." -ForegroundColor Yellow
    Stop-Job -Job $apiJob, $viteJob -ErrorAction SilentlyContinue
    Remove-Job -Job $apiJob, $viteJob -ErrorAction SilentlyContinue
}
