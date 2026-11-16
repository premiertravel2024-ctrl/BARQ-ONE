@echo off
setlocal
cd /d "%~dp0"
echo [BARQ] Re-testing the already compiled Setup.exe; no source rebuild.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_existing_installer_smoke.ps1" %*
if errorlevel 1 (
  echo.
  echo [ERROR] BARQ Setup smoke failed. Open release\installer-smoke-diagnostics.txt
  echo [ERROR] Full installer log: release\installer-smoke.log
  pause
  exit /b 1
)
echo [PASS] Installed BARQ.exe and BARQ_Wake.exe both passed the real smoke tests.
pause
exit /b 0
