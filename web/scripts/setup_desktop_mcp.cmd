@echo off
REM Double-click to set up the Claude desktop MCP servers (Bybit + read-only MT5).
cd /d "%~dp0..\.."
node web\scripts\setup_desktop_mcp.mjs
echo.
pause
