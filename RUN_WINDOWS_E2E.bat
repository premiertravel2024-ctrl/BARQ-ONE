@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python launcher not installed.
  exit /b 1
)
echo Checking actual Windows controls WITHOUT accessing network. Use --network to opt in to downloads.
py -3.11 scripts\windows_e2e.py %*
set "RESULT=%ERRORLEVEL%"
echo.
echo See release\BARQ_windows_e2e.md and release\BARQ_windows_e2e.json
exit /b %RESULT%
