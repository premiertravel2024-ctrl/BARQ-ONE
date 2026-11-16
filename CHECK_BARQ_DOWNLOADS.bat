@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo BARQ Download Doctor - no installs, no network requests
py -3.11 "%~dp0scripts\build_dependency_manager.py" --check
if errorlevel 1 (
  echo [BARQ] A prerequisite is missing. Fix it before BUILD_BARQ.bat.
  pause
  exit /b 1
)
echo [BARQ] Basic dependency prerequisites PASS.
pause
exit /b 0
