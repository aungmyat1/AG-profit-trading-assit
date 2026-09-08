# One-time local development setup (AG_FRONTEND_RUNTIME_VERIFICATION_AND_LOCAL_TEST_V1).
# Verifies Python/Node/package-manager, then installs frontend dependencies. Run this
# once (or whenever web/package.json changes); scripts/run_dev.ps1 is the lightweight
# script for normal daily use and does NOT install dependencies itself.
#
# Package manager: web/bun.lock is present (the frontend scaffold's original tool), but
# Bun is not installed in every developer environment. This script prefers Bun when
# available and falls back to npm (working from web/package.json alone) otherwise --
# it never deletes bun.lock and never generates npm lockfile churn beyond what npm
# itself creates on install.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $RepoRoot "web"

Write-Host ""
Write-Host "AG DEV SETUP" -ForegroundColor Cyan
Write-Host ""

$allPass = $true

# 1. Python
try {
    $pythonVersion = (python --version) 2>&1
    Write-Host "[PASS] Python ($pythonVersion)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Python not found on PATH" -ForegroundColor Red
    $allPass = $false
}

# 2. Node
try {
    $nodeVersion = (node --version) 2>&1
    Write-Host "[PASS] Node ($nodeVersion)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Node not found on PATH" -ForegroundColor Red
    $allPass = $false
}

if (-not $allPass) {
    Write-Host ""
    Write-Host "RESULT = DEV_SETUP_BLOCKED" -ForegroundColor Red
    exit 1
}

# 3. Package manager: prefer Bun (web/bun.lock is the canonical lockfile) if installed;
# otherwise fall back to npm without touching bun.lock.
$bunAvailable = $false
try {
    $bunVersion = (bun --version) 2>&1
    if ($LASTEXITCODE -eq 0) {
        $bunAvailable = $true
        Write-Host "[PASS] Package manager: Bun $bunVersion (matches web/bun.lock)" -ForegroundColor Green
    }
} catch {
    # bun not on PATH -- fall through to npm
}

if (-not $bunAvailable) {
    try {
        $npmVersion = (npm --version) 2>&1
        Write-Host "[PASS] Package manager: npm $npmVersion (fallback -- web/bun.lock is present but Bun is not installed here; npm installs from web/package.json directly)" -ForegroundColor Yellow
    } catch {
        Write-Host "[FAIL] Neither Bun nor npm is available" -ForegroundColor Red
        Write-Host ""
        Write-Host "RESULT = DEV_SETUP_BLOCKED" -ForegroundColor Red
        exit 1
    }
}

# 4. Install frontend dependencies
Write-Host "[RUN ] Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location $WebDir
try {
    if ($bunAvailable) {
        bun install
    } else {
        npm install --no-audit --no-fund
    }
    if ($LASTEXITCODE -ne 0) { throw "install exited with code $LASTEXITCODE" }
    Write-Host "[PASS] Frontend dependencies installed" -ForegroundColor Green
    Write-Host ""
    Write-Host "RESULT = DEV_SETUP_READY" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Frontend dependency install failed: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "RESULT = DEV_SETUP_BLOCKED" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location
