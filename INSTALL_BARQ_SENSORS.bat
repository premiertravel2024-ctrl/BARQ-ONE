@echo off
setlocal
set "BARQ_HOME=%~dp0"
if not exist "%BARQ_HOME%scripts\install_hardware_monitor.ps1" (
  echo [BARQ] Sensor installer is missing from this installation.
  pause
  exit /b 2
)
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%BARQ_HOME%scripts\install_hardware_monitor.ps1"
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo [BARQ] Temperature provider could not be started; check the message above.
pause
exit /b %CODE%
