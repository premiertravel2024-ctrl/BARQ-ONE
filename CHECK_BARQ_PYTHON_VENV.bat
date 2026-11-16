@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ROOT=%~dp0"
if not exist "%ROOT%scripts\create_build_venv.py" (
  echo [ERROR] Cannot find BARQ source files beside this BAT.
  exit /b 2
)
py -3.11 "%ROOT%scripts\create_build_venv.py" --probe
if errorlevel 1 (
  echo.
  echo [FAILED] Windows Python 3.11 venv bootstrap. No BARQ build was started.
  echo [LOG] "%ROOT%release\python-venv-probe.log"
  pause
  exit /b 1
)
echo [PASS] Python 3.11 build venv and pip are available.
echo [LOG] "%ROOT%release\python-venv-probe.log"
pause
exit /b 0
