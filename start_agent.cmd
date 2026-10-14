@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_agent.ps1" %*
if errorlevel 1 (
  echo.
  echo 服务启动失败，请在 PowerShell 中执行 scripts\start_agent.ps1 查看错误。
  pause
  exit /b 1
)
echo.
echo 服务已启动；本机地址：http://127.0.0.1:7860/；局域网地址：http://10.11.2.43:7860/
echo 按任意键关闭本窗口；关闭后服务会继续在后台运行。
pause >nul
endlocal
