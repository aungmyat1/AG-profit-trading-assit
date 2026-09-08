# Bounded regression sweep for the AG_DEMO_EXECUTION_GATEWAY / AI-Studio-VS-Code
# integration surface (AG_VSCODE_ONE_CLICK_TEST_RUN_V1). Deliberately does NOT run
# expensive historical replay/backtest suites -- see AGENTS.md's minimum-context
# principle: run the narrowest relevant tests, not the full repository, for a
# transport/DX task like this one.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "AG integration test sweep (API, authorization, runtime_state, MT5 execution handler, Telegram)" -ForegroundColor Cyan

python -m pytest `
    tests/test_api.py `
    tests/test_authorization_core.py `
    tests/test_telegram_client.py `
    tests/test_telegram_gateway.py `
    tests/test_mt5_execution_handler.py `
    tests/test_runtime_state_store.py `
    -q

exit $LASTEXITCODE
