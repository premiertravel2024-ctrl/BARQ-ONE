@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_prerequisites.ps1" %*
set "BARQ_PREPARE_RESULT=%ERRORLEVEL%"
pause
exit /b %BARQ_PREPARE_RESULT%
