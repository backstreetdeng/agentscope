@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\configure_market_mcp.ps1"
endlocal
