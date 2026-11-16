@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\install_presentmon.ps1"
set "BARQ_EXIT=%ERRORLEVEL%"
pause
exit /b %BARQ_EXIT%
