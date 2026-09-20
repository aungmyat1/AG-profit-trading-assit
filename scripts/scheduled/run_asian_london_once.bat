@echo off
REM AG FX ASIAN_LONDON scheduled slot (AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1, P1).
REM
REM Delegates to the fail-closed --once runner, which refuses (exit 2, nothing run) when:
REM   * today is not a Mon-Fri UTC trading day
REM   * now is outside the ASIAN_LONDON execution window (07:00-11:00 UTC)
REM   * the frozen WP3A.1 friction campaign is still collecting and this slot collides
REM     with one of its four frozen UTC windows
REM   * this (cycle, date, slot) already executed
REM
REM Uses the repository virtualenv explicitly -- NOT a bare `python`, which on this
REM machine resolves to a system interpreter without the project's dependencies.

setlocal
cd /d "%~dp0..\.."
set "PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo AG_FX_SLOT_ERROR: virtualenv python not found at "%PYTHON%" 1>&2
  exit /b 1
)
"%PYTHON%" scripts\run_fx_cycle_once.py --cycle ASIAN_LONDON --json >> "%TEMP%\ag_shadow_asian_london.log" 2>&1
exit /b %ERRORLEVEL%
